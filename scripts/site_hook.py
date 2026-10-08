"""Build the learning surfaces from the Markdown contract; never edit lesson bodies."""
import html
import json
import re
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from content import ROOT, load_lessons, load_plan
from curriculum import MAIN_STAGES, MAIN_DESCRIPTION, ordered_stages, navigation_lessons, course_tracks, course_neighbors
from pasted_render import render_pasted
from library_dates import library_dates

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
<section class="recent-section" aria-labelledby="recent-title"><div class="section-heading"><h2 id="recent-title">最近更新</h2><a href="generated/library/?sort=recent">浏览文章库 <span aria-hidden="true">→</span></a></div><p class="section-description">按已确认的发布日期排列；历史正文的未知日期不作推测。</p><div class="recent-list">{_recent()}</div></section>
</div>'''


def _page(title, description, body):
    return f'---\ntitle: {title}\nhide:\n  - navigation\n  - toc\n---\n<div class="collection-page">\n<p class="eyebrow">AI FABLE NOTES / {title}</p><h1>{title}</h1><p class="collection-intro">{description}</p>\n{body}\n</div>\n'


def _library():
    dates = library_dates(LESSONS)
    titles = {stage['id']: stage['title'] for stage in PLAN['stages']}
    numbers = {course['id']: index for index, course in enumerate(
        [course for track in NAVIGATION.values() for course in track], 1)}
    options = ''.join(f'<option value="{s["id"]}">{html.escape(s["title"])}</option>' for s in PLAN['stages'])
    rows = []
    for index, lesson in enumerate(LESSONS):
        concept = _concept_title(lesson)
        domain = titles[lesson['category']]
        keywords = ' '.join(str(lesson.get(key, '')) for key in ('keywords', 'tags'))
        search = html.escape(' '.join((concept, lesson['title'], domain, lesson['category'], lesson['id'], keywords)), quote=True)
        date = dates.get(lesson['id'])
        timestamp = date['timestamp'] if date else ''
        date_html = f'<span class="library-date" hidden>{date["label"]} <time datetime="{timestamp}">{date["day"]}</time></span>' if date else ''
        rows.append(f'''<a class="library-row" data-library-id="{lesson['id']}" data-domain="{lesson['category']}" data-search="{search}" data-rank="{index}" data-added="{timestamp}" href="../../{lesson['url']}">
<span class="library-order" aria-label="第 {numbers[lesson['id']]} 课">#{numbers[lesson['id']]:02d}</span>
<span class="library-copy"><strong>{html.escape(concept)}</strong><span class="library-story">{html.escape(lesson['title'])}</span><span class="library-meta">{html.escape(domain)}{date_html}</span></span>
<span class="library-status" data-library-status hidden>未读</span><span class="library-arrow" aria-hidden="true">↗</span></a>''')
    return f'''<section id="article-library" aria-label="已发布文章索引">
<form class="library-filters" hidden role="search" aria-label="筛选文章">
<label class="library-search">查找文章<input id="library-query" type="search" placeholder="概念、寓言标题或关键词" autocomplete="off"></label>
<label>知识领域<select id="library-domain"><option value="">全部领域</option>{options}</select></label>
<label>阅读状态<select id="library-state"><option value="">全部文章</option><option value="unfinished">未读 / 阅读中</option><option value="unread">未读</option><option value="reading">阅读中</option><option value="completed">已完成</option></select></label>
<label>排序<select id="library-sort"><option value="course">课程顺序</option><option value="recent">最近入库</option></select></label>
</form>
<p class="library-summary" id="library-count" role="status" aria-live="polite">{len(LESSONS)} 篇已发布文章</p>
<p class="subtle" id="library-date-note" hidden>历史文章按首次入库时间排序；新文章使用真实发布日期。未知时间排在最后。</p>
<noscript><p class="subtle">下方为全部已发布文章；启用 JavaScript 后可筛选、排序并查看本地阅读状态。</p></noscript>
<div class="library-list">{''.join(rows)}</div>
<p class="subtle" id="library-empty" hidden>没有符合条件的文章，试试其他关键词或清除筛选。</p>
</section>'''


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
    pages['library'] = _page('文章库', '查找概念、重温故事、按需阅读。', _library())
    for name, title in (('domains', '知识领域'), ('chapters', '全部章节'), ('archive', '日期归档')):
        pages[name] = _page(title, '文章浏览已合并到统一文章库，可搜索、筛选阅读状态与领域，并切换排序。', '<a class="fable-primary" href="../library/">前往文章库 →</a>').replace('hide:\n', 'search:\n  exclude: true\nhide:\n', 1)
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
        {'文章库': ['generated/library.md'] + [{s['title']: [{_concept_title(x): x['file']} for x in LESSONS if x['category'] == s['id']]} for s in PLAN['stages'] if any(x['category'] == s['id'] for x in LESSONS)]},
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
