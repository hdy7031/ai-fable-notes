"""Shared Markdown contract. Generated navigation never edits lesson bodies."""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
REQUIRED = {"id", "title", "date", "category", "order", "prerequisites", "next_concepts"}


def split_markdown(text: str) -> tuple[dict, str]:
    text = text.removeprefix("\ufeff")
    match = re.match(r"\A---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    if not match:
        raise ValueError("文章必须包含 YAML front matter")
    meta = yaml.safe_load(match.group(1))
    if not isinstance(meta, dict):
        raise ValueError("文章元数据必须是对象")
    return meta, text[match.end():]


def compose(meta: dict, body: str) -> str:
    return "---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False) + "---\n" + body


def load_plan(root: Path = ROOT) -> dict:
    return yaml.safe_load((root / "data/learning-plan.yml").read_text(encoding="utf-8"))


def privacy_check(text: str) -> None:
    # Fail closed on high-confidence private identifiers. Never print matches.
    patterns = {
        "邮箱地址": r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
        "手机号": r"(?<!\d)1[3-9]\d{9}(?!\d)",
        "密钥或令牌": r"(?i)(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{16,}|Bearer\s+[A-Za-z0-9._-]{16,})",
        "本机用户路径": r"(?i)[A-Z]:[\\/]Users[\\/][^\s\\/]+",
        "活动 HTML": r"(?i)<\s*(?:script|iframe|object|embed)\b|\bon\w+\s*=|javascript:",
    }
    for label, pattern in patterns.items():
        if re.search(pattern, text):
            raise ValueError(f"检测到{label}，请在本地人工审查；未输出匹配内容")


def validate(meta: dict, body: str, filename: str, root: Path = ROOT) -> dict:
    missing = REQUIRED - meta.keys()
    if missing:
        raise ValueError("缺少元数据字段: " + ", ".join(sorted(missing)))
    if not isinstance(meta["id"], str) or not SLUG.fullmatch(meta["id"]):
        raise ValueError("id 必须是小写英文与数字组成的稳定 slug")
    if not isinstance(meta["title"], str) or not meta["title"].strip():
        raise ValueError("title 必须是非空字符串")
    date = meta["date"]
    if isinstance(date, dt.date):
        date = date.isoformat()
    if date is not None:
        if not isinstance(date, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            raise ValueError("date 必须是 YYYY-MM-DD 或 null（日期不详）")
        dt.date.fromisoformat(date)
    meta = dict(meta, date=date)
    expected = f"{date or 'undated'}-{meta['id']}.md"
    if filename != expected:
        raise ValueError(f"文件名必须为 {expected}")
    stages = load_plan(root)["stages"]
    if meta["category"] not in {s["id"] for s in stages}:
        raise ValueError("category 必须属于 learning-plan.yml 中的知识领域")
    if type(meta["order"]) is not int or meta["order"] <= 0:
        raise ValueError("order 必须是正整数")
    for key in ("prerequisites", "next_concepts"):
        if not isinstance(meta[key], list) or any(not isinstance(x, str) or not SLUG.fullmatch(x) for x in meta[key]):
            raise ValueError(f"{key} 必须是概念 ID 数组")
        if meta["id"] in meta[key] or len(meta[key]) != len(set(meta[key])):
            raise ValueError(f"{key} 不能引用自身或重复")
    if not body.strip():
        raise ValueError("正文不能为空；缺失历史内容应保留在待补录清单")
    privacy_check(compose(meta, body))
    return meta


def load_lessons(root: Path = ROOT) -> list[dict]:
    lessons, ids, orders = [], set(), set()
    for path in sorted((root / "docs/lessons").glob("*.md")):
        meta, body = split_markdown(path.read_text(encoding="utf-8"))
        meta = validate(meta, body, path.name, root)
        if meta["id"] in ids or meta["order"] in orders:
            raise ValueError(f"重复 ID 或学习顺序: {path.name}")
        ids.add(meta["id"])
        orders.add(meta["order"])
        lessons.append(dict(meta, file="lessons/" + path.name, url="lessons/" + path.stem + "/"))
    plan = load_plan(root)
    known = ids | {c["id"] for s in plan["stages"] for c in s["concepts"]}
    for lesson in lessons:
        for ref in lesson["prerequisites"] + lesson["next_concepts"]:
            if ref not in known:
                raise ValueError(f"{lesson['id']} 引用了未知概念 {ref}；请先更新学习计划")
    return sorted(lessons, key=lambda x: (x["order"], x["id"]))


def publish(input_path: Path, root: Path = ROOT) -> tuple[Path, bool]:
    """Create only. Identical retries are no-ops; changed bodies never overwrite."""
    text = input_path.read_bytes().decode("utf-8")
    meta, body = split_markdown(text)
    date = meta.get("date")
    name = f"{date or 'undated'}-{meta.get('id', '')}.md"
    validate(meta, body, name, root)
    existing = load_lessons(root)
    target = root / "docs/lessons" / name
    if target.exists():
        if target.read_bytes().decode("utf-8") == text:
            return target, False
        raise ValueError("文章已存在且内容不同，禁止覆盖；请人工审核后单独编辑")
    if any(x["id"] == meta["id"] or x["order"] == meta["order"] for x in existing):
        raise ValueError("ID 或学习顺序已经存在，禁止重复发布")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8", newline="") as output:
        output.write(text)
    try:
        load_lessons(root)
    except Exception:
        target.unlink()
        raise
    return target, True
