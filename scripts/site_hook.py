"""MkDocs hook: validate lessons and derive all navigation at build time."""
from collections import defaultdict
import html
import json
import re
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from content import ROOT, load_lessons, load_plan
from pasted_render import render_pasted

LESSONS = []


def _label(text):
    return str(text).replace("[", "\\[").replace("]", "\\]")


def _link(lesson):
    concept = next((c["title"] for s in load_plan()["stages"] for c in s["concepts"] if c["id"] == lesson["id"]), "")
    title = f"{concept} · {lesson['title']}" if concept and concept not in lesson["title"] else lesson["title"]
    return f"[{_label(title)}](../{lesson['file']})"


def _write_if_changed(path, text):
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")


def _render_original(markdown):
    # Display-only cleanup: the Markdown source remains byte-for-byte intact.
    def entity_label(match):
        try:
            value = json.loads(match.group(1))
            return value[1] if isinstance(value, list) and len(value) > 1 and isinstance(value[1], str) else match.group(0)
        except json.JSONDecodeError:
            return match.group(0)
    markdown = re.sub(r"entity(\[[^\n]*?\])", entity_label, markdown)
    rendered, seen_title, shift, fence = [], False, 0, None
    for line in markdown.splitlines(keepends=True):
        fence_match = re.match(r"^\s*(`{3,}|~{3,})", line)
        if fence_match:
            marker = fence_match.group(1)[0]
            fence = None if fence == marker else marker if fence is None else fence
        match = re.match(r"^(#{1,6}) (.*)", line) if fence is None else None
        if match:
            level = len(match.group(1))
            if level == 1:
                shift = 1 if seen_title else 0
                seen_title = True
            line = "#" * min(level + shift, 6) + line[level:]
        rendered.append(line)
    return "".join(rendered)


def on_config(config):
    global LESSONS
    LESSONS = load_lessons()
    plan = load_plan()
    by_id = {x["id"]: x for x in LESSONS}
    generated = ROOT / "docs/generated"
    generated.mkdir(parents=True, exist_ok=True)
    pages = {
        "path": ["# 学习路径", "按学习顺序阅读。待补录概念只有标题，实际正文到位后才会成为可阅读章节。"],
        "domains": ["# 知识领域", "按主题查找已收录的文章。"],
        "archive": ["# 日期归档", "发布日期以文章记录为准。日期不详的历史文章单独归档。"],
        "missing": ["# 待补录清单", "这份清单来自已知知识链。没有实际记录时，不生成故事、公式或发布日期。"],
    }
    for stage in plan["stages"]:
        pages["path"].append("## " + stage["title"])
        pages["domains"].append("## " + stage["title"])
        pages["missing"].append("## " + stage["title"])
        actual = [x for x in LESSONS if x["category"] == stage["id"]]
        concepts = {c["id"]: c for c in stage["concepts"]}
        concepts.update({x["id"]: x for x in actual})
        for concept in sorted(concepts.values(), key=lambda c: c["order"]):
            lesson = by_id.get(concept["id"])
            pages["path"].append(f"- {_link(lesson) if lesson else _label(concept['title']) + ' · 待补录'}")
        pages["domains"].extend([f"- {_link(x)} · {x['date'] or '日期不详'}" for x in actual] or ["暂无已导入正文。"])
        missing = [c for c in stage["concepts"] if c["id"] not in by_id]
        pages["missing"].extend([f"- {_label(c['title'])}（`{c['id']}`）" for c in missing] or ["本阶段已全部补录。"])
    dates = defaultdict(list)
    for lesson in LESSONS:
        dates[lesson["date"] or "日期不详"].append(lesson)
    for date in sorted(dates, reverse=True):
        pages["archive"].append("## " + date)
        pages["archive"].extend("- " + _link(x) + (" · 原始日期标签：" + _label(x["source_date_label"]) + "（年份未注明）" if x.get("source_date_label") else "") for x in dates[date])
    if not dates:
        pages["archive"].append("暂无已发布文章。历史导出文件尚未提供，当前导入数量为 **0**。")
    for name, lines in pages.items():
        _write_if_changed(generated / f"{name}.md", "\n\n".join(lines) + "\n")
    assets = ROOT / "docs/assets"
    assets.mkdir(parents=True, exist_ok=True)
    _write_if_changed(assets / "catalog.json", json.dumps({"version": 1, "lessons": LESSONS, "stages": plan["stages"]}, ensure_ascii=False, indent=2))
    config["nav"] = [
        {"首页": "index.md"}, {"学习路径": "generated/path.md"},
        {"知识领域": "generated/domains.md"}, {"日期归档": "generated/archive.md"},
    ]
    if LESSONS:
        config["nav"].append({"全部章节": [{s["title"]: [{x["title"]: x["file"]} for x in LESSONS if x["category"] == s["id"]]} for s in plan["stages"] if any(x["category"] == s["id"] for x in LESSONS)]})
    config["nav"] += [{"待补录": "generated/missing.md"}, {"使用说明": [{"阅读与进度": "guide/index.md"}, {"发布与导入": "guide/publishing.md"}]}]
    return config


def on_pre_build(config):
    # mkdocs serve reuses config between builds; new files must refresh the catalog.
    on_config(config)


def on_page_markdown(markdown, page, config, files):
    lesson = next((x for x in LESSONS if x["file"] == page.file.src_uri), None)
    if not lesson:
        return markdown
    markdown = render_pasted(markdown) if lesson.get("body_format") == "plain-text" else _render_original(markdown)
    title = html.escape(lesson["title"])
    if not markdown.lstrip().startswith("# "):
        markdown = f"# {lesson['title']}\n\n" + markdown
    controls = f'<div class="lesson-controls" data-lesson-id="{lesson["id"]}"><span>{title} · {lesson["date"] or "日期不详"}</span><button type="button" id="toggle-completed" aria-pressed="false">标记已完成</button><p id="save-status" role="status"></p></div>\n\n'
    if lesson.get("source_date_label"):
        controls += f'<p class="subtle">原始日期标签：{html.escape(lesson["source_date_label"])}（年份未注明）</p>\n\n'
    by_id = {x["id"]: x for x in LESSONS}
    known = {c["id"]: c["title"] for s in load_plan()["stages"] for c in s["concepts"]}
    def relations(ids):
        return "、".join(f"[{_label(by_id[i]['title'])}]({Path(by_id[i]['file']).name})" if i in by_id else _label(known.get(i, i)) + "（待补录）" for i in ids) or "无"
    relation = f"\n\n---\n\n**前置概念：** {relations(lesson['prerequisites'])}\n\n**后续概念：** {relations(lesson['next_concepts'])}\n\n"
    index = LESSONS.index(lesson)
    neighbors = []
    for offset, label in ((-1, "上一篇"), (1, "下一篇")):
        if 0 <= index + offset < len(LESSONS):
            other = LESSONS[index + offset]
            neighbors.append(f"**{label}：** [{_label(other['title'])}]({Path(other['file']).name})")
    return controls + markdown + relation + "\n\n".join(neighbors)
