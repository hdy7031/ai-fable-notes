"""Small, separate OCR course; share the site's Markdown and progress contracts."""
import html

import yaml

from content import ROOT, SLUG, split_markdown, validate, load_lessons


def load_course(root=ROOT):
    course = yaml.safe_load((root / 'data/ocr-course.yml').read_text(encoding='utf-8'))
    ids, orders = set(), set()
    for chapter in course['chapters']:
        if (not SLUG.fullmatch(chapter['id']) or not chapter['id'].startswith('ocr-')
                or chapter['id'] in ids or chapter['order'] in orders
                or chapter['status'] not in ('pending', 'planned')):
            raise ValueError('OCR 课程 ID、顺序或待补录/规划状态无效')
        ids.add(chapter['id'])
        orders.add(chapter['order'])
    course['chapters'].sort(key=lambda item: item['order'])
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


def course_index(root=ROOT):
    track = course_track(root)
    published = sum(x['published'] for x in track)
    lines = ['# OCR 从零入门', '',
             '从图像像素出发，按顺序理解特征、训练与 CNN，再进入文字检测、识别和文档应用。'
             '网页保留完整教学与关键追问；Obsidian 用于概念沉淀和复习。', '',
             f'**已发布 {published} 章**。待补录表示已安排历史教学位置、尚缺可核验的完整原文；'
             '后续规划表示未来课程，均不代表已经学完或已有正文。', '',
             '<div id="ocr-dashboard"><p id="ocr-progress">阅读进度保存在当前浏览器。</p>'
             '<a id="ocr-continue" href="#ocr-pixels-rgb">从第一章开始 →</a></div>', '',
             '通过下表直接定位章节，也可使用全站搜索查找课程标题与已发布正文。', '',
             '| 顺序 | 章节 | 内容状态 |', '| --- | --- | --- |']
    for chapter in track:
        status = '已发布' if chapter['published'] else '待补录' if chapter['status'] == 'pending' else '后续规划'
        lines.append(f'| {chapter["order"]:02d} | [{chapter["title"]}](#{chapter["id"]}) | {status} |')
    for chapter in track:
        lines += ['', f'## {chapter["order"]:02d} · {chapter["title"]} {{#{chapter["id"]}}}', '']
        if chapter['published']:
            url = chapter['url'].removeprefix('ocr/')
            lines += [f'<p data-course-id="{chapter["id"]}"><a href="{url}">阅读完整章节 →</a> '
                      '<span data-course-status>已发布 · 未学习</span></p>']
        else:
            lines += ['**待补录**：尚未取得并审查本章完整教学消息。不会根据聊天摘要重建正文。'
                      if chapter['status'] == 'pending' else '**后续规划**：仅保留学习方向，尚未发布教学正文。']
        next_chapter = next((x for x in track if x['order'] > chapter['order']), None)
        if next_chapter:
            lines += ['', f'[下一章：{next_chapter["title"]}](#{next_chapter["id"]})']
    lines += ['', '## 学习与复习', '',
              '已发布章节支持数学公式、代码、站内搜索、前后章导航、完成标记与滚动位置恢复。'
              '进度沿用本站现有浏览器存储，OCR 使用独立稳定 ID；在[使用说明](../guide/index.md)中备份与恢复，'
              '没有跨设备自动同步。', '',
              'Obsidian 从“技术知识导航 → OCR 学习导航”进入课程与已有概念；复习笔记只提炼理解、例子和误区，'
              '链接本课程原章，不复制整篇教学。', '',
              '[补录完整教学的操作说明](../guide/ocr-import.md)', '']
    return '\n'.join(lines)


def render_chapter(markdown, lesson, root=ROOT):
    """Display-only wrappers, preserving the reviewed Markdown source."""
    from curriculum import course_neighbors
    title = html.escape(lesson['title'])
    body = markdown
    controls = (f'<nav class="reading-breadcrumb"><a href="../../">OCR 从零入门</a> / {title}</nav>\n\n'
                f'<div class="lesson-controls" data-lesson-id="{lesson["id"]}">'
                f'<span>{lesson["date"] or "日期不详"} · <span id="reading-label">未完成</span></span>'
                '<button type="button" id="toggle-completed" aria-pressed="false">标记已完成</button>'
                '<p id="save-status" role="status"></p></div>\n\n')
    neighbors = []
    for other, label in zip(course_neighbors({'ocr': course_track(root)}, lesson['id']), ('上一章', '下一章')):
        if other:
            status = '' if other['published'] else ' · 待补录' if other['status'] == 'pending' else ' · 后续规划'
            neighbors.append(f'<a href="../../../{other["url"]}"><span>{label}{status}</span>'
                             f'<strong>{html.escape(other["title"])}</strong></a>')
    return controls + body + '\n\n<nav class="reading-neighbors" aria-label="前后章">' + ''.join(neighbors) + '</nav>'
