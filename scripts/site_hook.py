"""Build the learning surfaces from the Markdown contract; never edit lesson bodies."""
from collections import defaultdict
import html
from itertools import groupby
import json
import re
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from content import ROOT, load_lessons, load_plan
from curriculum import MAIN_STAGES, MAIN_DESCRIPTION, ordered_stages, navigation_lessons, course_tracks, course_neighbors
from pasted_render import render_pasted

LESSONS = []
PLAN = {}
NAVIGATION = {}


def _label(text):
    return str(text).replace("[", "\\[").replace("]", "\\]")


def _write_if_changed(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _known():
    concepts = {c["id"]: dict(c, stage=s["id"]) for s in PLAN["stages"] for c in s["concepts"]}
    for lesson in LESSONS:
        concepts.setdefault(lesson["id"], dict(lesson, stage=lesson["category"]))
    return concepts


def _gaps():
    """Distinguish prerequisite gaps (including ancestors) from future directions."""
    known, by_id = _known(), {x["id"]: x for x in LESSONS}
    missing, seen = set(), set()
    def visit(concept_id):
        if concept_id in seen:
            return
        seen.add(concept_id)
        item = by_id.get(concept_id, known.get(concept_id, {}))
        if concept_id not in by_id:
            missing.add(concept_id)
        for prerequisite in item.get("prerequisites", []):
            visit(prerequisite)
    for lesson in LESSONS:
        for prerequisite in lesson["prerequisites"]:
            visit(prerequisite)
    return missing


def _concept_title(lesson):
    return _known().get(lesson["id"], lesson)["title"]


def _concept_link(concept_id, depth):
    known = _known()
    item = next((x for x in LESSONS if x["id"] == concept_id), None)
    if item:
        return f'<a href="{"../" * depth}{item["url"]}">{html.escape(_concept_title(item))}</a>'
    concept = known[concept_id]
    return f'<a class="missing-link" href="{"../" * depth}generated/stages/{concept["stage"]}/#concept-{concept_id}">{html.escape(concept["title"])}（待补录）</a>'


def _stage_cards(prefix=""):
    cards = []
    for index, stage in enumerate(PLAN["stages"], 1):
        actual = [x for x in LESSONS if x["category"] == stage["id"]]
        total = len({c["id"] for c in stage["concepts"]} | {x["id"] for x in actual})
        future = total - len(actual)
        status = f'已发布 {len(actual)} 篇 · 未学习' if actual else f'未来计划 · {total} 个概念'
        cards.append(f'''<a class="stage-card{' stage-card--planned' if not actual else ''}" data-stage-id="{stage['id']}" href="{prefix}generated/stages/{stage['id']}/">
<span class="stage-number">{'阶段' if stage['id'] in MAIN_STAGES else '支线'} {index if stage['id'] in MAIN_STAGES else index - len(MAIN_STAGES):02d}<span aria-hidden="true">↗</span></span>
<h3>{html.escape(stage['title'])}</h3><p>{html.escape(stage['description'])}</p>
<span class="stage-status" data-stage-status>{status}</span>
{f'<span class="stage-detail">{str(future) + " 个概念待发布" if future else "本阶段正文已齐全"}</span>' if actual else ''}
{f'<progress data-stage-progress value="0" max="{len(actual)}" aria-label="{html.escape(stage["title"])}完成进度"></progress>' if actual else ''}
</a>''')
    return '<div class="stage-grid" id="stage-cards">' + "".join(cards) + '</div>'


def _recent():
    # Only confirmed publication dates can establish recency; undated imports stay in the library.
    recent = sorted((x for x in LESSONS if x["date"]), key=lambda x: (x["date"], x["order"]), reverse=True)[:4]
    rows = []
    for lesson in recent:
        rows.append(f'<a class="recent-row" href="{lesson["url"]}"><time datetime="{lesson["date"]}">{lesson["date"]}</time><span><strong>{html.escape(_concept_title(lesson))}</strong><span>{html.escape(lesson["title"])}</span></span><span aria-hidden="true">↗</span></a>')
    return "".join(rows) or '<p class="subtle">暂没有可确认发布日期的文章。已收录的历史正文可在文章库阅读。</p>'


def _home_dashboard():
    first = next(iter(NAVIGATION['main']), None)
    stage = next((s for s in PLAN["stages"] if first and s["id"] == first["category"]), None)
    return f'''<div id="learning-dashboard">
<section class="continue-section" aria-labelledby="continue-heading">
<div class="section-heading"><h2 id="continue-heading">继续学习</h2><span id="continue-reason">从主线起点开始</span></div>
<div class="continue-card"><div class="continue-copy">
<a id="continue-stage" class="eyebrow" href="generated/stages/{stage['id'] if stage else PLAN['stages'][0]['id']}/">{html.escape(stage['title']) if stage else '学习路线'}</a>
<h3 id="continue-title">{html.escape(first['title']) + ('（待发布）' if not first['published'] else '') if first else '教材正在生长'}</h3>
<p id="continue-story">{html.escape(first['story']) if first else '先看看学习计划，已发布正文会自动出现在这里。'}</p>
<p id="continue-prerequisites" class="prerequisite-note">前置知识：无需前置，从这里开始。</p></div>
<a class="fable-primary" id="continue-reading" href="{first['url'] if first else 'generated/path/'}">{'开始阅读' if first and first['published'] else '查看待发布课程'} <span aria-hidden="true">→</span></a></div>
</section>
<section class="progress-summary" aria-label="阅读进度">
<div class="dashboard-stats"><div><strong id="total-count">{len(LESSONS)}</strong><span>已收录</span></div><div><strong id="completed-count">0</strong><span>已完成</span></div><div><strong id="progress-percent">0%</strong><span>阅读进度</span></div></div>
<div class="progress-summary__track"><progress id="overall-progress" value="0" max="100" aria-label="整体阅读进度"></progress><p id="reading-status">每完成一篇，知识就连起一小段。</p></div>
</section>
<section aria-labelledby="stages-title"><div class="section-heading"><h2 id="stages-title">知识阶段</h2><a href="generated/path/">完整学习路线 <span aria-hidden="true">→</span></a></div><p class="section-description">主线：{MAIN_DESCRIPTION}。概率与统计为独立支线。</p>{_stage_cards()}</section>
<section class="recent-section" aria-labelledby="recent-title"><div class="section-heading"><h2 id="recent-title">最近更新</h2><a href="generated/archive/">日期归档 <span aria-hidden="true">→</span></a></div><p class="section-description">按已确认的发布日期排列；历史正文的未知日期不作推测。</p><div class="recent-list">{_recent()}</div></section>
</div>'''


def _page(title, description, body):
    return f'---\ntitle: {title}\nhide:\n  - navigation\n  - toc\n---\n<div class="collection-page">\n<p class="eyebrow">AI FABLE NOTES / {title}</p><h1>{title}</h1><p class="collection-intro">{description}</p>\n{body}\n</div>\n'


def _library_nav(active):
    links = [('library', '精选分类'), ('domains', '知识领域'), ('chapters', '全部章节'), ('archive', '日期归档')]
    return '<nav class="collection-tabs" aria-label="文章浏览方式">' + ''.join(f'<a {"aria-current=page" if key == active else ""} href="../{key}/">{label}</a>' for key, label in links) + '</nav>'


def _article_rows(lessons, depth=2, wrap=True):
    rows = ''.join(f'<a class="article-row" data-library-id="{x["id"]}" href="{"../" * depth}{x["url"]}"><span><strong>{html.escape(_concept_title(x))}</strong><span>{html.escape(x["title"])}</span></span><span class="article-date">{x["date"] or "日期不详"}<span data-library-status>未学习</span></span><span aria-hidden="true">↗</span></a>' for x in lessons)
    return '<div class="article-list">' + rows + '</div>' if wrap else rows


def _chapters():
    sections = []
    titles = {stage['id']: stage['title'] for stage in PLAN['stages']}
    for track, label in (('main', '主线课程'), ('probability-statistics', '概率与统计 · 独立支线')):
        sections.append(f'<h2>{label}</h2>')
        for index, (category, group) in enumerate(groupby(NAVIGATION[track], key=lambda course: course['category']), 1):
            courses = list(group)
            rows = []
            for course in courses:
                lesson = next((item for item in LESSONS if item['id'] == course['id']), None)
                if lesson:
                    rows.append(_article_rows([lesson], wrap=False))
                else:
                    rows.append(f'<a class="article-row missing-link" href="../../{course["url"]}"><span><strong>{html.escape(course["title"])}</strong><span>正文尚未发布 · 查看阶段计划</span></span><span class="article-date">待发布</span><span aria-hidden="true">↗</span></a>')
            sections.append(f'<section class="library-section chapter-section"><div class="section-heading"><h3><span class="domain-number">{index:02d}</span>{html.escape(titles[category])}</h3><span>{sum(course["published"] for course in courses)} 篇已发布</span></div><div class="article-list">{"".join(rows)}</div></section>')
    return ''.join(sections)


def _course_rows(stage):
    known, gaps = _known(), _gaps()
    actual = [x for x in LESSONS if x["category"] == stage["id"]]
    concepts = [course for track in NAVIGATION.values() for course in track if course['category'] == stage['id']]
    rows = []
    for index, concept in enumerate(concepts, 1):
        lesson = next((x for x in actual if x['id'] == concept['id']), None)
        title = html.escape(known[concept['id']]['title'])
        heading = f'<a href="../../../{lesson["url"]}">{title}</a>' if lesson else title
        status = '已发布 · 未学习' if lesson else '必要前置 · 待发布' if concept['id'] in gaps else '待发布 · 未来计划'
        prerequisite_links = '、'.join(_concept_link(i, 3) for i in concept.get('prerequisites', [])) or '无需前置知识'
        rows.append(f'''<li id="concept-{concept['id']}" class="course-row{' course-row--planned' if not lesson else ''}" {f'data-course-id="{lesson["id"]}"' if lesson else ''}>
<span class="course-order">{index:02d}</span><div><h3>{heading}</h3>{f'<p class="course-story">{html.escape(lesson["title"])}</p>' if lesson else ''}<p class="course-prerequisites">前置：{prerequisite_links}</p></div><span class="status-tag" {'data-course-status' if lesson else ''}>{status}</span></li>''')
    return '<ol class="course-list">' + ''.join(rows) + '</ol>'


def on_config(config):
    global LESSONS, PLAN, NAVIGATION
    plan = load_plan()
    PLAN = dict(plan, stages=ordered_stages(plan))
    LESSONS = navigation_lessons(plan, load_lessons())
    NAVIGATION = course_tracks(plan, LESSONS)
    known, gaps = _known(), _gaps()
    generated = ROOT / 'docs/generated'
    gap_links = '、'.join(_concept_link(i, 2) for i in sorted(gaps, key=lambda i: known[i]['order'])) or '目前已发布课程的前置正文已齐全。'
    route = f'<div class="route-summary"><strong>{len(LESSONS)} 篇已发布</strong><span>{len(known)} 个计划概念</span><span>完成状态随阅读同步</span></div>{_stage_cards("../../")}<section id="prerequisite-gaps" class="gap-note"><h2>当前前置缺口</h2><p>{gap_links}</p><p class="subtle">这些概念是已发布课程所需的前置知识，等待正文补录。其他未发布概念列为未来计划，不会生成虚构文章链接。</p><a href="../missing/">查看全部待补录概念 →</a></section>'
    pages = {'path': _page('学习路线', f'主线：{MAIN_DESCRIPTION}。概率与统计作为独立支线，按需学习。', route)}
    pages['library'] = _page('文章库', f'{len(LESSONS)} 篇寓言，连接故事与 AI 概念。按主题探索，或回看某一天的发布。', _library_nav('library') + ''.join(f'<section class="library-section"><div class="section-heading"><h2>{html.escape(s["title"])}</h2><a href="../stages/{s["id"]}/">阶段路线 →</a></div>{_article_rows([x for x in LESSONS if x["category"] == s["id"]])}</section>' for s in PLAN['stages'] if any(x['category'] == s['id'] for x in LESSONS)))
    domain_sections = []
    for stage in PLAN['stages']:
        actual = [x for x in LESSONS if x['category'] == stage['id']]
        contents = _article_rows(actual) if actual else f'<p class="subtle">正文尚未发布。<a href="../stages/{stage["id"]}/">查看阶段计划 →</a></p>'
        domain_sections.append(f'<section id="domain-{stage["id"]}" class="library-section"><h2>{html.escape(stage["title"])}</h2>{contents}</section>')
    domain_links = '<nav class="anchor-links" aria-label="知识领域跳转">' + ''.join(f'<a href="#domain-{s["id"]}">{html.escape(s["title"])}</a>' for s in PLAN['stages']) + '</nav>'
    pages['domains'] = _page('知识领域', '按概念所属的知识领域查找正文。', _library_nav('domains') + domain_links + ''.join(domain_sections))
    pages['chapters'] = _page('全部章节', f'主线：{MAIN_DESCRIPTION}。概率与统计单列为独立支线；待发布课程仅链接阶段计划。', _library_nav('chapters') + _chapters())
    dates = defaultdict(list)
    for lesson in LESSONS:
        dates[lesson['date'] or '日期不详'].append(lesson)
    date_keys = sorted((d for d in dates if d != '日期不详'), reverse=True) + (['日期不详'] if '日期不详' in dates else [])
    pages['archive'] = _page('日期归档', '保留真实发布日期；日期不详的历史正文单独归档。原始月日标签可在文章页查看。', _library_nav('archive') + '<nav class="anchor-links" aria-label="日期跳转">' + ''.join(f'<a href="#date-{d}">{d}</a>' for d in date_keys) + '</nav>' + ''.join(f'<section id="date-{d}" class="library-section"><h2>{d}</h2>{_article_rows(dates[d])}</section>' for d in date_keys))
    pages['missing'] = _page('待补录清单', '前置缺口优先补录，其他概念保留在未来计划中。缺少正文时，只展示课程信息。', '<a class="back-link" href="../path/">← 返回学习路线</a>' + ''.join(f'<section class="library-section"><h2>{html.escape(s["title"])}</h2><ul>' + ''.join(f'<li>{_concept_link(c["id"], 2)} · {"必要前置缺口" if c["id"] in gaps else "未来计划"}</li>' for c in s['concepts'] if not any(x['id'] == c['id'] for x in LESSONS)) + '</ul></section>' for s in PLAN['stages'] if any(not any(x['id'] == c['id'] for x in LESSONS) for c in s['concepts'])))
    for name, text in pages.items():
        _write_if_changed(generated / f'{name}.md', text)
    for index, stage in enumerate(PLAN['stages'], 1):
        text = _page(stage['title'], html.escape(stage['description']), f'<a class="back-link" href="../../path/">← 全部学习路线</a><p class="subtle">阶段 {index:02d} · 已发布正文可直接阅读；前置待补录与未来计划不会链接到不存在的文章。</p>' + _course_rows(stage))
        _write_if_changed(generated / 'stages' / f'{stage["id"]}.md', text)
    _write_if_changed(ROOT / 'docs/assets/catalog.json', json.dumps({'version': 1, 'lessons': LESSONS, 'stages': PLAN['stages'], 'navigation': NAVIGATION}, ensure_ascii=False, indent=2))
    config['nav'] = [
        {'首页': 'index.md'},
        {'学习路线': ['generated/path.md'] + [{s['title']: f'generated/stages/{s["id"]}.md'} for s in PLAN['stages']] + [{'待补录清单': 'generated/missing.md'}]},
        {'文章库': ['generated/library.md', {'知识领域': 'generated/domains.md'}, {'全部章节': 'generated/chapters.md'}, {'日期归档': 'generated/archive.md'}] + [{s['title']: [{_concept_title(x): x['file']} for x in LESSONS if x['category'] == s['id']]} for s in PLAN['stages'] if any(x['category'] == s['id'] for x in LESSONS)]},
    ]
    return config


def on_pre_build(config):
    # Refresh when new Markdown is published, including during mkdocs serve.
    on_config(config)


def on_page_markdown(markdown, page, config, files):
    if page.file.src_uri == 'index.md':
        return markdown.replace('<!-- HOME_DASHBOARD -->', _home_dashboard())
    lesson = next((x for x in LESSONS if x['file'] == page.file.src_uri), None)
    if not lesson:
        return markdown
    page.meta['hide'] = ['navigation']
    page.meta['fable_layout'] = 'reading'
    markdown = render_pasted(markdown) if lesson.get('body_format') == 'plain-text' else _render_original(markdown)
    if not markdown.lstrip().startswith('# '):
        markdown = f"# {lesson['title']}\n\n" + markdown
    stage = next(s for s in PLAN['stages'] if s['id'] == lesson['category'])
    breadcrumb = f'<nav class="reading-breadcrumb" aria-label="课程位置"><a href="../../generated/path/">学习路线</a><span aria-hidden="true">/</span><a href="../../generated/stages/{stage["id"]}/">{html.escape(stage["title"])}</a><span aria-hidden="true">/</span><span>{html.escape(_concept_title(lesson))}</span></nav>\n\n'
    controls = f'<div class="lesson-controls" data-lesson-id="{lesson["id"]}"><span>{lesson["date"] or "日期不详"} · <span id="reading-label">未完成</span></span><button type="button" id="toggle-completed" aria-pressed="false">标记已完成</button><p id="save-status" role="status"></p></div>\n\n'
    if lesson.get('source_date_label'):
        controls += f'<p class="subtle">原始日期标签：{html.escape(lesson["source_date_label"])}（年份未注明）</p>\n\n'
    prerequisite = '、'.join(_concept_link(i, 2) for i in lesson['prerequisites']) or '无需前置知识'
    following = '、'.join(_concept_link(i, 2) for i in lesson['next_concepts']) or '可回到阶段路线继续探索'
    relation = f'<aside class="concept-relations" aria-label="知识联系"><h2>把知识连起来</h2><p><strong>前置概念</strong> {prerequisite}</p><p><strong>后续概念</strong> {following}</p></aside>'
    neighbors = []
    for other, label in zip(course_neighbors(NAVIGATION, lesson['id']), ('上一篇', '下一篇')):
        if other:
            status = '' if other['published'] else ' · 待发布'
            neighbors.append(f'<a href="../../{other["url"]}"><span>{label}{status}</span><strong>{html.escape(other["title"])}</strong></a>')
    return breadcrumb + controls + markdown + '\n\n' + relation + '<nav class="reading-neighbors" aria-label="前后篇">' + ''.join(neighbors) + '</nav>'
