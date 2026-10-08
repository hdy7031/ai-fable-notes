"""Explicit selection only. Raw ChatGPT exports stay in ignored .private/."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import zipfile

from content import ROOT, compose, load_lessons, load_plan, validate


def read_export(path: Path) -> list[dict]:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            names = [n for n in archive.namelist() if Path(n).name == "conversations.json"]
            if len(names) != 1:
                raise ValueError("ZIP 必须包含唯一 conversations.json；不会解压其他文件")
            raw = archive.read(names[0]).decode("utf-8-sig")
    else:
        raw = path.read_text(encoding="utf-8-sig")
    data = json.loads(raw)
    if isinstance(data, dict):
        data = data.get("conversations")
    if not isinstance(data, list):
        raise ValueError("仅支持官方 conversations.json 数组或包含它的 ZIP")
    return data


def selected_branch(conversation: dict) -> list[dict]:
    mapping = conversation.get("mapping", {})
    current = conversation.get("current_node")
    if not current or current not in mapping:
        raise ValueError("对话缺少 current_node，无法确认有效分支；请手动导出正文")
    nodes, seen = [], set()
    while current:
        if current in seen or current not in mapping:
            raise ValueError("对话分支数据损坏")
        seen.add(current)
        node = mapping[current]
        nodes.append(node)
        current = node.get("parent")
    return list(reversed(nodes))


def candidates(path: Path) -> dict:
    output = {}
    for conversation in read_export(path):
        conv_id = conversation.get("id") or conversation.get("conversation_id")
        if not conv_id:
            raise ValueError("对话缺少唯一 ID")
        for position, node in enumerate(selected_branch(conversation)):
            message = node.get("message")
            if not message or message.get("author", {}).get("role") != "assistant":
                continue
            if message.get("metadata", {}).get("is_visually_hidden_from_conversation"):
                continue
            if message.get("channel") not in (None, "final"):
                continue
            content = message.get("content", {})
            parts = content.get("parts", [])
            # Never silently drop images, attachments, or structured content.
            if content.get("content_type") != "text" or not parts or any(not isinstance(x, str) for x in parts):
                continue
            body = "\n".join(parts)
            if not body.strip():
                continue
            message_id = message.get("id") or node.get("id")
            key = f"{conv_id}/{message_id}"
            timestamp = message.get("create_time")
            date = None
            if isinstance(timestamp, (int, float)):
                date = dt.datetime.fromtimestamp(timestamp, dt.timezone(dt.timedelta(hours=8))).date().isoformat()
            output[key] = {"conversation_id": conv_id, "message_id": message_id, "conversation_title": conversation.get("title", ""), "position": position, "date": date, "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(), "body": body}
    return output


def private_path(path: Path) -> Path:
    resolved = path.resolve()
    private_root = (ROOT / ".private").resolve()
    if not resolved.is_relative_to(private_root):
        raise ValueError("候选正文、扫描结果与筛选清单必须放在本项目 .private/ 下")
    return resolved


def scan(source: Path, output: Path) -> int:
    output = private_path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    body_dir = output.parent / "candidates"
    body_dir.mkdir(exist_ok=True)
    rows = []
    for key, item in candidates(source).items():
        filename = hashlib.sha256(key.encode()).hexdigest()[:24] + ".md"
        path = body_dir / filename
        path.write_text(item["body"], encoding="utf-8", newline="")
        rows.append({k: v for k, v in item.items() if k != "body"} | {"candidate_file": str(path.relative_to(ROOT))})
    output.write_text(json.dumps({"version": 1, "candidates": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(rows)


def import_selected(source: Path, selection: Path) -> int:
    selection = private_path(selection)
    entries = json.loads(selection.read_text(encoding="utf-8"))["articles"]
    available = candidates(source)
    existing = load_lessons()
    existing_ids = {x["id"] for x in existing}
    existing_orders = {x["order"] for x in existing}
    prepared = []
    chosen_positions = {}
    for entry in entries:
        if entry.get("privacy_reviewed") is not True:
            raise ValueError("每篇文章必须明确 privacy_reviewed: true，确认正文无隐私和无关内容")
        key = f"{entry['conversation_id']}/{entry['message_id']}"
        if key not in available:
            raise ValueError("选中消息不属于有效助手文本分支，或包含不支持的附件")
        item = available[key]
        if entry.get("sha256") != item["sha256"]:
            raise ValueError("正文摘要不一致，禁止导入改写或过期的选择")
        meta = {k: entry[k] for k in ("id", "title", "category", "order", "prerequisites", "next_concepts")}
        # Only the selected message timestamp determines historical dates.
        meta["date"] = item["date"]
        if "date" in entry and entry["date"] != item["date"]:
            raise ValueError("禁止推测或修改历史生成日期；缺失时间戳使用 null")
        meta["source"] = "chatgpt-export"
        filename = f"{item['date'] or 'undated'}-{meta['id']}.md"
        validate(meta, item["body"], filename)
        if meta["id"] in existing_ids or meta["order"] in existing_orders:
            raise ValueError("历史导入遇到已有 ID 或顺序，停止并保留原文")
        existing_ids.add(meta["id"])
        existing_orders.add(meta["order"])
        chosen_positions.setdefault(item["conversation_id"], []).append((item["position"], meta["order"]))
        prepared.append((meta, item["body"], filename))
    # Within one conversation, preserve chapter chronology even if manifest is reordered.
    for positions in chosen_positions.values():
        orders = [order for _, order in sorted(positions)]
        if orders != sorted(orders):
            raise ValueError("学习顺序与原对话章节顺序冲突，请修正筛选清单")
    known = existing_ids | {c["id"] for s in load_plan()["stages"] for c in s["concepts"]}
    for meta, _, _ in prepared:
        if any(ref not in known for ref in meta["prerequisites"] + meta["next_concepts"]):
            raise ValueError("筛选清单引用未知概念，请先更新学习计划")
    # Stage and validate the whole batch before creating public files.
    staging = private_path(ROOT / ".private/prepared")
    staging.mkdir(parents=True, exist_ok=True)
    created = []
    try:
        for meta, body, filename in sorted(prepared, key=lambda x: x[0]["order"]):
            candidate = staging / filename
            candidate.write_text(compose(meta, body), encoding="utf-8", newline="")
            target = ROOT / "docs/lessons" / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("x", encoding="utf-8", newline="") as output:
                output.write(candidate.read_bytes().decode("utf-8"))
            created.append(target)
        load_lessons()
    except Exception:
        for target in created:
            target.unlink()
        raise
    return len(created)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    scan_parser = commands.add_parser("scan")
    scan_parser.add_argument("export", type=Path)
    scan_parser.add_argument("--output", type=Path, default=ROOT / ".private/candidates.json")
    import_parser = commands.add_parser("import")
    import_parser.add_argument("export", type=Path)
    import_parser.add_argument("--selection", type=Path, required=True)
    args = parser.parse_args()
    try:
        count = scan(args.export, args.output) if args.command == "scan" else import_selected(args.export, args.selection)
        print(f"{'本地候选消息' if args.command == 'scan' else '已导入完整文章'}: {count}")
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as error:
        parser.exit(1, f"导入停止: {error}\n")
