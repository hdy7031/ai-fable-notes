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


def candidates(path: Path, include_user=False, title_keywords=(), conversation_ids=None) -> dict:
    output = {}
    for conversation in read_export(path):
        if title_keywords and not any(word.casefold() in conversation.get('title', '').casefold() for word in title_keywords):
            continue
        conv_id = conversation.get("id") or conversation.get("conversation_id")
        if conversation_ids is not None and conv_id not in conversation_ids:
            continue
        if not conv_id:
            raise ValueError("对话缺少唯一 ID")
        for position, node in enumerate(selected_branch(conversation)):
            message = node.get("message")
            if not message or message.get("author", {}).get("role") not in (("assistant", "user") if include_user else ("assistant",)):
                continue
            if message.get("metadata", {}).get("is_visually_hidden_from_conversation"):
                continue
            if message.get("channel") not in (None, "final"):
                continue
            if message.get('recipient') not in (None, 'all'):
                continue
            content = message.get("content", {})
            parts = content.get("parts", [])
            # Keep unsupported visible turns as blockers for multi-turn course imports.
            supported = (content.get("content_type") == "text" and bool(parts)
                         and all(isinstance(x, str) for x in parts)
                         and not message.get('metadata', {}).get('attachments'))
            body = "\n".join(parts) if supported else ""
            if not body.strip():
                if not include_user:
                    continue
                supported = False
            message_id = message.get("id") or node.get("id")
            key = f"{conv_id}/{message_id}"
            if not message_id or key in output:
                raise ValueError('消息 ID 缺失或重复，无法可靠追溯')
            timestamp = message.get("create_time")
            date = None
            if isinstance(timestamp, (int, float)):
                date = dt.datetime.fromtimestamp(timestamp, dt.timezone(dt.timedelta(hours=8))).date().isoformat()
            output[key] = {"conversation_id": conv_id, "message_id": message_id, "conversation_title": conversation.get("title", ""), "position": position, "role": message["author"]["role"], "supported": supported, "create_time": timestamp, "date": date, "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(), "body": body}
    return output


def private_path(path: Path) -> Path:
    resolved = path.resolve()
    private_root = (ROOT / ".private").resolve()
    if not resolved.is_relative_to(private_root):
        raise ValueError("候选正文、扫描结果与筛选清单必须放在本项目 .private/ 下")
    return resolved


def scan(source: Path, output: Path, include_user=False, title_keywords=()) -> int:
    output = private_path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    body_dir = output.parent / "candidates"
    body_dir.mkdir(exist_ok=True)
    rows = []
    for key, item in candidates(source, include_user=include_user, title_keywords=title_keywords).items():
        filename = hashlib.sha256(key.encode()).hexdigest()[:24] + ".md"
        path = body_dir / filename
        path.write_text(item["body"], encoding="utf-8", newline="")
        rows.append({k: v for k, v in item.items() if k != "body"} | {"candidate_file": str(path.relative_to(ROOT))})
    output.write_text(json.dumps({"version": 1, "export_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "candidates": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
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


def import_course(source: Path, selection: Path) -> int:
    """Explicit contiguous teaching turns; source IDs and receipts stay private."""
    from ocr_course import load_course, load_chapters
    selection = private_path(selection)
    manifest = json.loads(selection.read_text(encoding="utf-8"))
    export_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    if manifest.get("export_sha256") != export_sha:
        raise ValueError("原始导出 SHA-256 不一致，请重新扫描")
    entries = manifest["chapters"]
    if not entries:
        raise ValueError("没有明确选择的 OCR 章节")
    available = candidates(source, include_user=True,
                           conversation_ids={entry['conversation_id'] for entry in entries})
    plan = load_course()['chapters']
    known = {chapter['id']: chapter for chapter in plan}
    existing = {chapter['id'] for chapter in load_chapters()}
    prepared, claimed = [], set()
    positions = {}
    for entry in entries:
        if entry.get('privacy_reviewed') is not True:
            raise ValueError('每章必须逐条阅读并明确 privacy_reviewed: true')
        chapter = known.get(entry['id'])
        if not chapter or chapter['id'] in existing:
            raise ValueError('OCR 章节未知或已存在，禁止覆盖')
        existing.add(chapter['id'])
        messages = []
        for ref in entry['messages']:
            key = f"{entry['conversation_id']}/{ref['message_id']}"
            item = available.get(key)
            if not item or not item.get('supported') or item['sha256'] != ref.get('sha256'):
                raise ValueError('选中消息不在有效文本分支、含附件或 SHA-256 已改变')
            if key in claimed:
                raise ValueError('同一消息不能重复导入多个章节')
            claimed.add(key)
            messages.append(item)
        if not messages or not any(x['role'] == 'assistant' for x in messages):
            raise ValueError('章节必须包含完整助手教学消息')
        order = [x['position'] for x in messages]
        if order != sorted(order) or len(order) != len(set(order)):
            raise ValueError('章节消息必须按原文顺序且不能重复')
        span = [x for x in available.values() if x['conversation_id'] == entry['conversation_id']
                and order[0] <= x['position'] <= order[-1]]
        if len(span) != len(messages):
            raise ValueError('选中范围有遗漏问答或附件，不得跳过后声称章节完整')
        positions.setdefault(entry['conversation_id'], []).append((order[0], order[-1], chapter['order']))
        # Only add turn labels and whitespace. Never regenerate or trim source bodies.
        body = '\n\n'.join(f"## 第 {i} 轮 · {'追问' if item['role'] == 'user' else '讲解'}\n\n{item['body']}"
                             for i, item in enumerate(messages, 1))
        first_answer = next(x for x in messages if x['role'] == 'assistant')
        index = plan.index(chapter)
        meta = dict(id=chapter['id'], title=chapter['title'], date=first_answer['date'],
                    category='ocr', course='ocr', order=chapter['order'],
                    prerequisites=[plan[index - 1]['id']] if index else [],
                    next_concepts=[plan[index + 1]['id']] if index + 1 < len(plan) else [],
                    source='chatgpt-export')
        filename = f"{meta['date'] or 'undated'}-{meta['id']}.md"
        validate(meta, body, filename)
        target = ROOT / 'docs/ocr/chapters' / filename
        receipt = private_path(ROOT / '.private/ocr/receipts' / (meta['id'] + '.json'))
        if target.exists() or receipt.exists():
            raise ValueError('章节文件或私有来源记录已存在，保留原件并停止')
        provenance = dict(version=1, export_sha256=export_sha, source_path=str(source.resolve()),
                          chapter_id=meta['id'], target=str(target.relative_to(ROOT)),
                          body_sha256=hashlib.sha256(body.encode('utf-8')).hexdigest(),
                          messages=[{k: v for k, v in x.items() if k != 'body'} for x in messages],
                          privacy_reviewed=True)
        prepared.append((target, compose(meta, body), receipt, provenance))
    for ranges in positions.values():
        ordered = sorted(ranges)
        if ([x[2] for x in ordered] != sorted(x[2] for x in ordered)
                or any(a[1] >= b[0] for a, b in zip(ordered, ordered[1:]))):
            raise ValueError('章节范围重叠或课程顺序与原文冲突')
    created = []
    try:
        for target, text, receipt, provenance in prepared:
            target.parent.mkdir(parents=True, exist_ok=True)
            receipt.parent.mkdir(parents=True, exist_ok=True)
            for path, value in ((receipt, json.dumps(provenance, ensure_ascii=False, indent=2)),
                                (target, text)):
                with path.open('x', encoding='utf-8', newline='') as output:
                    created.append(path)
                    output.write(value)
        load_chapters()
    except Exception:
        for path in reversed(created):
            path.unlink()
        raise
    return len(prepared)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    scan_parser = commands.add_parser("scan")
    scan_parser.add_argument("export", type=Path)
    scan_parser.add_argument("--output", type=Path, default=ROOT / ".private/candidates.json")
    scan_parser.add_argument("--include-user", action="store_true", help="OCR 多轮教学：保留用户追问与不支持的附件标记")
    scan_parser.add_argument("--title-keywords", default="", help="逗号分隔，先按会话标题筛选")
    course_parser = commands.add_parser("import-course")
    course_parser.add_argument("export", type=Path)
    course_parser.add_argument("--selection", type=Path, required=True)
    import_parser = commands.add_parser("import")
    import_parser.add_argument("export", type=Path)
    import_parser.add_argument("--selection", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "scan":
            count = scan(args.export, args.output, args.include_user,
                         tuple(word.strip() for word in args.title_keywords.split(',') if word.strip()))
        elif args.command == "import-course":
            count = import_course(args.export, args.selection)
        else:
            count = import_selected(args.export, args.selection)
        print(f"{'本地候选消息' if args.command == 'scan' else '已导入完整文章'}: {count}")
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as error:
        parser.exit(1, f"导入停止: {error}\n")
