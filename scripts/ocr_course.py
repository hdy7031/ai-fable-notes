"""OCR syllabus and reviewed chapters; share the site's Markdown and progress contracts."""
import html

import yaml

from content import ROOT, SLUG, split_markdown, validate, load_lessons


def load_course(root=ROOT):
    course = yaml.safe_load((root / 'data/ocr-course.yml').read_text(encoding='utf-8'))
    parts = [part['id'] for part in course['parts']]
    if len(parts) != len(set(parts)):
        raise ValueError('OCR 篇章 ID 重复')
    seen_modules, last_part = set(), -1
    for module in course['modules']:
        if (not SLUG.fullmatch(module['id']) or not module['id'].startswith('ocr-module-')
                or module['id'] in seen_modules or module['part'] not in parts
                or not set(module['prerequisites']) <= seen_modules
                or not 2 <= len(module['lessons']) <= 4):
            raise ValueError('OCR 模块、前置依赖或课时规划无效；前置模块须排在前面')
        part_index = parts.index(module['part'])
        if part_index < last_part:
            raise ValueError('OCR 模块必须按篇章顺序排列')
        last_part = part_index
        seen_modules.add(module['id'])
    ids, orders = set(), set()
    for chapter in course['chapters']:
        if (not SLUG.fullmatch(chapter['id']) or not chapter['id'].startswith('ocr-')
                or chapter['id'] in ids or chapter['order'] in orders
                or type(chapter['order']) is not int or chapter['order'] <= 0
                or chapter['module'] not in seen_modules
                or chapter['status'] not in ('pending', 'planned')):
            raise ValueError('OCR 课程 ID、模块、顺序或待补录/待学习状态无效')
        ids.add(chapter['id'])
        orders.add(chapter['order'])
    if course['next_chapter'] not in ids:
        raise ValueError('OCR 下一课必须引用已建立的课程位置')
    course['chapters'].sort(key=lambda item: item['order'])
    module_order = {module['id']: i for i, module in enumerate(course['modules'])}
    if [module_order[c['module']] for c in course['chapters']] != sorted(module_order[c['module']] for c in course['chapters']):
        raise ValueError('OCR 章节顺序必须与模块路线一致')
    return course


def load_chapters(root=ROOT):
    planned = {c['id']: c for c in load_course(root)['chapters']}
    fable_ids = {x['id'] for x in load_lessons(root)}
    chapters, seen = [], set()
    for path in sorted((root / 'docs/ocr/chapters').glob('*.md')):
        meta, body = split_markdown(path.read_text(encoding='utf-8'))
        meta = validate(meta, body, path.name, root)
        chapter = planned.get(meta['id'])
        if (not chapter or meta.get('course') != 'ocr' or meta['category'] != 'ocr'
                or meta['order'] != chapter['order'] or meta['title'] != chapter['title']
                or meta['id'] in seen or meta['id'] in fable_ids):
            raise ValueError('OCR 正文必须对应课程计划，且不能与寓言进度 ID 冲突')
        if any(ref not in planned for ref in meta['prerequisites'] + meta['next_concepts']):
            raise ValueError('OCR 正文引用未知课程章节')
        seen.add(meta['id'])
        chapters.append(dict(meta, file='ocr/chapters/' + path.name,
                             url='ocr/chapters/' + path.stem + '/'))
    return sorted(chapters, key=lambda item: item['order'])


def course_track(root=ROOT):
    chapters = {x['id']: x for x in load_chapters(root)}
    track = []
    previous = None
    for chapter in load_course(root)['chapters']:
        actual = chapters.get(chapter['id'])
        track.append(dict(chapter, category='ocr', published=actual is not None,
                          prerequisites=[previous] if previous else [],
                          story='已发布完整教学正文。' if actual else '等待经审查的完整教学原文。',
                          url=actual['url'] if actual else 'ocr/#' + chapter['id']))
        previous = chapter['id']
    return track


def _course_page(title, body):
    return (f'---\ntitle: {title}\nocr_layout: true\nhide:\n  - navigation\n  - toc\n---\n'
            '<div class="ocr-course" markdown="1">\n\n' + body + '\n\n</div>\n')


def course_index(root=ROOT):
    course, track = load_course(root), course_track(root)
    published = [c for c in track if c['published']]
    first = published[0] if published else None
    target = first['url'].removeprefix('ocr/') if first else f"parts/{course['parts'][0]['id']}/"
    title = html.escape(first['title']) if first else '先了解课程路线'
    action = '开始阅读 →' if first else '查看第一篇目录 →'
    lines = ['<header class="ocr-hero">', f'<p class="eyebrow">专题课程 · {len(course["parts"])} 篇 / {len(course["modules"])} 个模块</p>',
             '<h1>OCR 与文档智能</h1>',
             '<p class="ocr-intro">从图像与文字识别出发，逐步理解文档结构、模型选型与工程交付。</p>', '</header>',
             '<section id="ocr-dashboard" class="ocr-entry" aria-label="当前学习入口">',
             f'<div><p id="ocr-progress" class="ocr-status">已发布 {len(published)} 章</p>'
             f'<h2 id="ocr-current-title">{title}</h2></div>',
             f'<a id="ocr-continue" class="fable-primary" href="{target}">{action}</a>', '</section>',
             '<section aria-labelledby="ocr-route-title"><div class="section-heading">'
             '<h2 id="ocr-route-title">学习目录</h2><a href="about/">课程说明 →</a></div>',
             '<div class="ocr-parts">']
    for part in course['parts']:
        modules = [m for m in course['modules'] if m['part'] == part['id']]
        numbers = [course['modules'].index(m) + 1 for m in modules]
        label, title = part['title'].split('：', 1)
        scope = f'模块 {numbers[0]:02d}' + (f'–{numbers[-1]:02d}' if len(numbers) > 1 else '')
        lines += [f'<a class="ocr-part-card" href="parts/{part["id"]}/">'
                  f'<span class="ocr-part-label">{label}<span aria-hidden="true">↗</span></span>'
                  f'<h3>{html.escape(title)}</h3><span class="ocr-status">{scope} · {len(modules)} 个模块</span></a>']
    lines += ['</div></section>', '<section class="ocr-related" aria-labelledby="ocr-related-title">'
              '<h2 id="ocr-related-title">先读一点 AI 基础</h2>'
              '<p class="ocr-status">以下为本站通用 AI 课程，可用于补充 OCR 前置知识。</p>', '<ul>']
    lessons = {lesson['id']: lesson for lesson in load_lessons(root)}
    for lesson_id in ('convolution', 'receptive-field', 'ocr-pipeline'):
        if lesson_id in lessons:
            lesson = lessons[lesson_id]
            lines.append(f'<li><a href="../{lesson["url"]}">{html.escape(lesson["title"])}</a></li>')
    lines += ['</ul></section>', '<p class="ocr-footnote">完整正文经审查后发布，阅读进度保存在当前浏览器。<a href="../guide/ocr-import/">查看导入说明</a></p>']
    # Keep existing bookmarks and external links useful after moving the module lists.
    for part in course['parts']:
        lines.append(f'<p data-search-exclude class="ocr-anchor" id="{part["id"]}"><a data-ocr-redirect href="parts/{part["id"]}/">前往{html.escape(part["title"])}</a></p>')
    modules = {m['id']: m for m in course['modules']}
    for item in course['modules'] + track:
        module = item if item['id'] in modules else modules[item['module']]
        lines.append(f'<p data-search-exclude class="ocr-anchor" id="{item["id"]}"><a data-ocr-redirect '
                     f'href="parts/{module["part"]}/#{item["id"]}">查看{html.escape(item["title"])}</a></p>')
    return '\n'.join(lines)


def course_part(part_id, root=ROOT):
    course, track = load_course(root), course_track(root)
    part = next(p for p in course['parts'] if p['id'] == part_id)
    modules = {m['id']: m for m in course['modules']}
    label, title = part['title'].split('：', 1)
    lines = ['<nav class="ocr-breadcrumb" aria-label="课程位置"><a href="../../">← OCR 与文档智能</a></nav>',
             f'<header class="ocr-hero" id="{part_id}"><p class="eyebrow">{label}</p>'
             f'<h1>{html.escape(title)}</h1><p class="ocr-intro">按模块顺序浏览，展开查看课时、前置知识与实践目标。</p></header>',
             '<nav class="ocr-part-nav" aria-label="切换篇章">']
    for other in course['parts']:
        current = ' aria-current="page"' if other['id'] == part_id else ''
        lines.append(f'<a href="../{other["id"]}/"{current}>{other["title"].split("：", 1)[0]}</a>')
    lines += ['</nav>', '<h2 class="ocr-list-title">模块目录</h2>', '<div class="ocr-modules" markdown="1">']
    for number, module in enumerate(course['modules'], 1):
        if module['part'] != part_id:
            continue
        chapters = [c for c in track if c['module'] == module['id']]
        count = sum(c['published'] for c in chapters)
        status = f'已发布 {count} 章' if count else '待补录' if any(c['status'] == 'pending' for c in chapters) else '规划中'
        lines += [f'<details class="ocr-module" id="{module["id"]}" markdown="1">',
                  f'<summary markdown="1"><h3 class="ocr-module-heading" id="{module["id"]}-heading"><span class="ocr-module-number">{number:02d}</span>'
                  f'<span class="ocr-module-title">{html.escape(module["title"])}</span>'
                  f'<span class="ocr-status">{status}</span></h3></summary>', '',
                  '<div class="ocr-module-body" markdown="1">', '', '**课时规划**', '']
        lines.extend(f'- {lesson}' for lesson in module['lessons'])
        prerequisites = '、'.join(f'[{modules[ref]["title"]}]({modules[ref]["part"]}.md#{ref})' for ref in module['prerequisites']) or '无需前置模块'
        lines += ['', f'**前置知识** {prerequisites}', '', f'**实践目标** {module["practice"]}', '']
        if chapters:
            lines += ['**章节**', '', '<ul class="ocr-chapters">']
        for chapter in chapters:
            title = html.escape(chapter['title'])
            if chapter['published']:
                content = f'<a href="../../../{chapter["url"]}">{title}</a><span data-course-status>已发布</span>'
                state = f' data-course-id="{chapter["id"]}"'
            else:
                content = f'<span>{title}</span><span class="ocr-status">{"待补录" if chapter["status"] == "pending" else "规划中"}</span>'
                state = ''
            lines.append(f'<li id="{chapter["id"]}"{state}>{content}</li>')
        if chapters:
            lines += ['</ul>', '']
        lines += ['</div>', '</details>', '']
    lines += ['</div>', '<nav class="ocr-part-footer" aria-label="篇章顺序">']
    index = course['parts'].index(part)
    if index:
        previous = course['parts'][index - 1]
        lines.append(f'<a href="../{previous["id"]}/">← {html.escape(previous["title"])}</a>')
    if index + 1 < len(course['parts']):
        following = course['parts'][index + 1]
        lines.append(f'<a href="../{following["id"]}/">{html.escape(following["title"])} →</a>')
    lines += ['</nav>', '<p class="ocr-footnote"><a href="../../about/">课程说明与学习验收</a></p>']
    return _course_page(part['title'], '\n'.join(lines))


def course_about(root=ROOT):
    course = load_course(root)
    next_chapter = next(c for c in course_track(root) if c['id'] == course['next_chapter'])
    module = next(m for m in course['modules'] if m['id'] == next_chapter['module'])
    body = ('[← OCR 与文档智能](index.md)\n\n# 课程说明\n\n' + course['title'] + '。\n\n'
            '下一节正式课程为《[' + next_chapter['title'] + '](parts/' + module['part'] + '.md#' + next_chapter['id'] + ')》。\n\n'
            '四篇依次学习，共 12 个模块。模块 11 的数据、Loss 和评估知识从前期穿插，最后集中总结。'
            '课时可按真实教学拆分。已发布表示可以阅读完整正文，待补录表示历史教学原文等待导入，规划中表示未来教学。\n\n'
            + COURSE_NOTES)
    return _course_page('课程说明', body)


COURSE_NOTES = """## OCR 与文档智能知识地图

| 数据流层次 | 输入与处理 | 这一层回答的问题 |
| --- | --- | --- |
| 01 · 图像与文档输入 | 图像、扫描件、原生 PDF、预处理 | 数据来自哪里，怎样表示？ |
| 02 · 文字感知 OCR / STR | 检测、裁剪矫正、字符与文本序列识别 | 文字在哪里，写了什么？ |
| 03 · 文档结构解析 | 版面、阅读顺序、表格、公式、印章 | 各区域怎样组织？ |
| 04 · 文档语义理解 | 分类、跨页切分、字段与上下文 | 这些内容表达什么业务含义？ |
| 05 · 多模态智能 | VLM、LLM、RAG、Agent 与工具 | 怎样结合视觉、语言与工具完成任务？ |
| 06 · 业务系统与工业交付 | API、数据库、人工审核、部署与质量控制 | 怎样可靠地核验、使用和维护结果？ |

**贯穿线 A · 技术演进**：传统方法 → 深度学习 → 多模态。**贯穿线 B · 实验与工程**：数据 → 训练 → 评估 → 选型 → 部署。六层按数据流组织；具体系统可以组合多个层次。

例如，识别出 `2026-11-07` 得到的是文字；版面分析定位落款区域；文档理解判断它是否为发文日期；业务系统再将字段与证据送入审核和存储。

## 贯穿案例与选型练习

| 案例 | 学习目标 |
| --- | --- |
| 主案例 · 法律卷宗智能识别 | 从 PDF 经 OCR、版面、文书切分与字段提取，进入证据关联、人工复核和归档 |
| 辅助案例 · 大学课表 OCR | 文字坐标、表格行列、合并单元格与课程语义绑定；保持独立实验 |
| 辅助案例 · 包装日期喷码检测 | 小字符、缺损、定位与规则校验；分别验证文字内容与印刷质量 |

案例是后续教学与实验计划。公开网页仅使用经过审查的脱敏或公开样本，不发布真实卷宗、客户资料或未核实实验数字。

每次选型先判断输入和目标，再选最简单可行的候选技术，用真实数据比较准确率、错误类型、耗时、资源与人工修正成本，最后安排部署、审核和反馈。原生 PDF 可先评估直接文本解析，复杂表格重点验证结构恢复；OCR 读对日期仍需单独检查缺墨等质量问题。具体模型版本在授课时核对官方资料。

## 教学与学习验收

**每项技术都连接五个问题**：原理是什么、过去如何解决、现在怎样改进、实际什么时候选它、如何验证效果。

每课从真实问题与小例子开始，逐步说明传统方法、现代机制和必要公式，再连接实际代码、失败场景与选型，最后用少量问题检查理解。完整原文保留数字、推导、代码、关键追问和明确订正。

| 深度 | 验收标准 |
| --- | --- |
| L1 · 理解 | 能解释输入、输出、核心原理与用途 |
| L2 · 应用 | 能运行、阅读关键代码并定位常见问题 |
| L3 · 选型与改进 | 能比较候选方案，根据实验结果作决定 |

核心模块目标为 L2；DBNet、CRNN/CTC、表格结构和系统选型争取 L3。经典过渡方法先达到 L1。完成标记只记录阅读，不等同于通过上述能力验收。

## 学习与复习

通过模块目录定位课时，也可全站搜索标题与已发布正文。已发布章节支持数学公式、代码、前后章导航、完成标记与滚动恢复。前后章沿已有章节位置跳转；完整学习依赖见模块目录。进度复用本站浏览器存储和 OCR 稳定 ID，与寓言路线分别展示；在[使用说明](../guide/index.md)中备份与恢复。

Obsidian 从“技术知识导航 → OCR 学习导航”进入课程与已有概念。复习通过原有 knowledge-ingest 合并概念、例子和误区，链接本课程原章。

[补录完整教学的操作说明](../guide/ocr-import.md)
"""


def render_chapter(markdown, lesson, root=ROOT):
    """Display-only wrappers, preserving the reviewed Markdown source."""
    from curriculum import course_neighbors
    title = html.escape(lesson['title'])
    body = markdown
    controls = (f'<nav class="reading-breadcrumb"><a href="../../">OCR 与文档智能</a> / {title}</nav>\n\n'
                f'<div class="lesson-controls" data-lesson-id="{lesson["id"]}">'
                f'<span>{lesson["date"] or "日期不详"} · <span id="reading-label">未完成</span></span>'
                '<button type="button" id="toggle-completed" aria-pressed="false">标记已完成</button>'
                '<p id="save-status" role="status"></p></div>\n\n')
    neighbors = []
    for other, label in zip(course_neighbors({'ocr': course_track(root)}, lesson['id']), ('上一章', '下一章')):
        if other:
            status = '' if other['published'] else ' · 待补录' if other['status'] == 'pending' else ' · 待学习'
            neighbors.append(f'<a href="../../../{other["url"]}"><span>{label}{status}</span>'
                             f'<strong>{html.escape(other["title"])}</strong></a>')
    return controls + body + '\n\n<nav class="reading-neighbors" aria-label="前后章">' + ''.join(neighbors) + '</nav>'
