"""Small content/import/idempotency checks; no model calls or browser dependencies."""
from pathlib import Path
import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from content import ROOT, compose, load_lessons, load_plan, privacy_check, publish
from curriculum import (MAIN_STAGES, BRANCH_STAGES, APPLIED_STAGES, TRACK_STAGES,
                        ordered_stages, navigation_lessons, course_tracks, course_neighbors)


class NavigationChecks(unittest.TestCase):
    def test_tracks_preserve_legacy_courses_and_order(self):
        plan, lessons = load_plan(), load_lessons()
        tracks = course_tracks(plan, lessons)
        self.assertEqual(list(tracks), ['main', 'applied', 'probability-statistics'])
        self.assertEqual(MAIN_STAGES, ('foundations', 'training', 'cnn', 'sequence-models', 'ocr'))
        self.assertEqual(BRANCH_STAGES, ('statistics', 'probability', 'probabilistic-learning'))
        legacy = json.loads((ROOT / 'scripts/fixtures/legacy-navigation.json').read_text(encoding='utf-8'))
        for track, expected in legacy.items():
            self.assertEqual([{key: course[key] for key in reference}
                              for course, reference in zip(tracks[track], expected)], expected)
            self.assertEqual(len(tracks[track]), len(expected))
        self.assertEqual(len(tracks['main']), 38)
        self.assertEqual(len(tracks['probability-statistics']), 15)
        ids = [course['id'] for courses in tracks.values() for course in courses]
        self.assertEqual(len(ids), len(set(ids)))
        for track, stages in TRACK_STAGES.items():
            self.assertEqual(list(dict.fromkeys(c['category'] for c in tracks[track])), list(stages))
            for stage in stages:
                orders = [c['order'] for c in tracks[track] if c['category'] == stage]
                self.assertEqual(orders, sorted(orders))
            self.assertIsNone(course_neighbors(tracks, tracks[track][0]['id'])[0])
            self.assertIsNone(course_neighbors(tracks, tracks[track][-1]['id'])[1])

    def test_applied_plan_references_and_planned_surfaces(self):
        import site_hook
        plan, lessons = load_plan(), load_lessons()
        # Keep the planned-state fixture valid as daily articles are published.
        lessons = [lesson for lesson in lessons if lesson['category'] not in APPLIED_STAGES]
        tracks = course_tracks(plan, lessons)
        expected = [
            (500, 'problem-framing-and-baseline'), (510, 'data-quality-and-leakage'),
            (520, 'transfer-learning-and-finetuning'), (530, 'metrics-and-error-analysis'),
            (540, 'ablation-and-reproducibility'), (600, 'object-detection-yolo'),
            (610, 'image-segmentation'), (620, 'image-embeddings-and-retrieval'),
            (630, 'clip-and-contrastive-learning'), (700, 'tokens-and-embeddings'),
            (710, 'pretraining-and-instruction-tuning'), (720, 'rag'),
            (730, 'vision-language-models'), (740, 'hallucinations-and-evaluation'),
            (800, 'tool-calling-and-workflows'), (810, 'agent-state-and-orchestration'),
            (820, 'model-export-and-serving'), (830, 'latency-throughput-and-quantization'),
        ]
        self.assertEqual([(c['order'], c['id']) for c in tracks['applied']], expected)
        concepts = {c['id']: c for stage in plan['stages'] for c in stage['concepts']}
        self.assertEqual(len(concepts), 71)
        self.assertEqual(len({c['order'] for c in concepts.values()}), len(concepts))
        for lesson in lessons:
            self.assertFalse(any(c['order'] == lesson['order'] and c['id'] != lesson['id'] for c in tracks['applied']))
        def visit(concept_id, ancestors=()):
            self.assertNotIn(concept_id, ancestors, '前置知识不能成环')
            for ref in concepts[concept_id]['prerequisites']:
                self.assertIn(ref, concepts)
                visit(ref, ancestors + (concept_id,))
        for concept_id in concepts:
            visit(concept_id)
        with patch.multiple(site_hook, LESSONS=lessons, PLAN=dict(plan, stages=ordered_stages(plan)), NAVIGATION=tracks):
            route = site_hook._route_sections()
            home = site_hook._home_overview()
            for course in tracks['applied']:
                self.assertIn('concept-' + course['id'], route)
                self.assertFalse(course['published'])
                self.assertNotIn('lessons/', course['url'])
                self.assertNotIn('data-course-id="' + course['id'] + '"', route)
                self.assertIn('#concept-' + course['id'], course['url'])
            self.assertIn('规划中 · 正文未发布', route)
            self.assertIn('data-overview-card="applied"', home)
            self.assertIn('18 个概念 · 规划中', home)
            self.assertIn('id="applied-suggestion"', route)
            self.assertNotIn('data-stage-progress', site_hook._stage_cards(track='applied'))

    def test_route_views_group_courses_and_offer_overview(self):
        import site_hook
        from html.parser import HTMLParser

        class RouteGroups(HTMLParser):
            def __init__(self):
                super().__init__()
                self.track = None
                self.groups = {}

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if 'data-route-track' in attrs:
                    self.track = attrs['data-route-track']
                    self.groups[self.track] = []
                if 'data-stage-id' in attrs:
                    self.groups[self.track].append(attrs['data-stage-id'])

        plan, lessons = load_plan(), load_lessons()
        with patch.multiple(site_hook, LESSONS=lessons, PLAN=dict(plan, stages=ordered_stages(plan)),
                            NAVIGATION=course_tracks(plan, lessons)):
            source = site_hook._route_sections()
            parser = RouteGroups()
            parser.feed(source)
            self.assertEqual(parser.groups, {track: list(stages) for track, stages in TRACK_STAGES.items()})
            self.assertIn('<option value="overview">总览</option>', source)
            self.assertIn('data-route-published', source)
            self.assertEqual(source.count('id="learning-dashboard"'), 1)

    def test_home_is_fixed_overview_and_learning_controls_live_on_route_page(self):
        import site_hook
        plan, lessons = load_plan(), load_lessons()
        tracks = course_tracks(plan, lessons)
        with patch.multiple(site_hook, LESSONS=lessons, PLAN=dict(plan, stages=ordered_stages(plan)), NAVIGATION=tracks):
            home, route = site_hook._home_overview(), site_hook._route_sections()
            self.assertEqual(home.count('data-overview-card='), 3)
            for track in ('main', 'applied', 'ocr'):
                self.assertIn(f'data-overview-card="{track}"', home)
            for marker in ('data-track-selector', 'data-route-track', 'data-stage-id',
                           'id="learning-dashboard"', 'data-overview-only', '<progress'):
                self.assertNotIn(marker, home)
            self.assertIn('generated/path/#main', home)
            self.assertIn('generated/path/#applied', home)
            self.assertIn('generated/path/#probability-statistics', home)
            self.assertIn('generated/library/?sort=recent', home)
            self.assertEqual(route.count('data-track-selector'), 1)
            self.assertIn('id="continue-reading" href="../../lessons/', route)
            self.assertIn('id="completed-count"', route)
            self.assertIn('id="progress-percent"', route)

    def test_date_independent_lesson_references_resolve_to_published_markdown(self):
        import site_hook
        plan, lessons = load_plan(), load_lessons()
        source = '[训练集](../undated-train-val-test.md) [泛化](../undated-overfitting.md) [未知](../undated-unknown.md)'
        page = SimpleNamespace(file=SimpleNamespace(src_uri=lessons[0]['file']), meta={})
        with patch.multiple(site_hook, LESSONS=lessons, PLAN=plan, NAVIGATION=course_tracks(plan, lessons)):
            rendered = site_hook.on_page_markdown(source, page, {}, [])
        for concept_id, label in (('train-val-test', '训练集'), ('overfitting', '泛化')):
            target = next(item for item in lessons if item['id'] == concept_id)
            self.assertIn(f'[{label}]({Path(target["file"]).name})', rendered)
        self.assertIn('[未知](../undated-unknown.md)', rendered)

    def test_applied_publication_updates_catalog_without_placeholder(self):
        import site_hook
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / 'data', root / 'data')
            (root / 'docs/lessons').mkdir(parents=True)
            for lesson in load_lessons():
                if lesson['category'] not in APPLIED_STAGES:
                    shutil.copyfile(ROOT / 'docs' / lesson['file'], root / 'docs' / lesson['file'])
            before = load_lessons(root)
            stage = next(s for s in load_plan(root)['stages'] if s['id'] == APPLIED_STAGES[0])
            concept = stage['concepts'][0]
            candidate = root / 'candidate.md'
            candidate.write_text(compose(dict(concept, category=stage['id'], date='2026-11-08', next_concepts=[]),
                                         '仅用于测试发布状态的合成正文。'), encoding='utf-8')
            publish(candidate, root)
            lessons = load_lessons(root)
            self.assertEqual(len(lessons), len(before) + 1)
            with patch.multiple(site_hook, ROOT=root, load_lessons=lambda: lessons, load_plan=lambda: load_plan(root)):
                site_hook.on_config({})
                rows = site_hook._course_rows(stage)
            catalog = json.loads((root / 'docs/assets/catalog.json').read_text(encoding='utf-8'))
            courses = catalog['navigation']['applied']
            self.assertTrue(courses[0]['published'])
            self.assertTrue(courses[0]['url'].startswith('lessons/'))
            self.assertFalse(courses[1]['published'])
            self.assertIn('data-course-id="problem-framing-and-baseline"', rows)
            self.assertNotIn('data-course-id="data-quality-and-leakage"', rows)
            self.assertIn('已发布 · 未学习', rows)
            self.assertIn('规划中 · 正文未发布', rows)
            library = (root / 'docs/generated/library.md').read_text(encoding='utf-8')
            self.assertIn('data-library-id="problem-framing-and-baseline"', library)
            self.assertNotIn('data-library-id="data-quality-and-leakage"', library)

    def test_navigation_order_preserves_metadata(self):
        lessons, plan = load_lessons(), load_plan()
        original = copy.deepcopy((lessons, plan))
        tracks = course_tracks(plan, lessons)
        categories = list(dict.fromkeys(course['category'] for course in tracks['main']))
        self.assertEqual(categories, list(MAIN_STAGES))
        displayed = navigation_lessons(plan, lessons)
        self.assertEqual([lesson['id'] for lesson in displayed],
                         [course['id'] for courses in tracks.values() for course in courses if course['published']])
        previous, following = course_neighbors(tracks, 'tensor-shape')
        self.assertEqual(following['id'], 'loss')
        self.assertEqual((lessons, plan), original)
        self.assertEqual({lesson['id']: lesson['order'] for lesson in displayed},
                         {lesson['id']: lesson['order'] for lesson in lessons})

    def test_library_shows_only_published_but_reader_preserves_gaps(self):
        import re
        import site_hook
        lessons, plan = load_lessons(), load_plan()
        tracks = course_tracks(plan, lessons)
        display_plan = dict(plan, stages=ordered_stages(plan))
        with patch.multiple(site_hook, LESSONS=navigation_lessons(plan, lessons), PLAN=display_plan, NAVIGATION=tracks):
            library = site_hook._library()
            urls = re.findall(r'href="../../([^"]+)"', library)
            self.assertEqual(urls, [lesson['url'] for lesson in navigation_lessons(plan, lessons)])
            self.assertNotIn('日期不详', library)
            self.assertNotIn('待发布', library)
            self.assertNotIn('collection-tabs', library)
            lesson = next(item for item in lessons if item['id'] == 'partial-derivative-and-gradient')
            page = SimpleNamespace(file=SimpleNamespace(src_uri=lesson['file']), meta={})
            rendered = site_hook.on_page_markdown('# 测试正文', page, {}, [])
            neighbors = rendered.split('aria-label="前后篇">')[1]
            self.assertIn('上一篇', neighbors)
            next_course = course_neighbors(tracks, lesson['id'])[1]
            self.assertIsNotNone(next_course)
            self.assertIn('下一篇', neighbors)
            self.assertIn(next_course['title'], neighbors)
            self.assertIn('../../' + next_course['url'], neighbors)
            if next_course['published']:
                self.assertNotIn('下一篇 · 待发布', neighbors)
            else:
                self.assertIn('下一篇 · 待发布', neighbors)
            self.assertNotIn('statistical-power', neighbors)
            self.assertNotIn('conditional-probability', neighbors)
            self.assertTrue(course_neighbors(tracks, 'relu')[1]['id'] == 'rnn')

    def test_library_updates_from_markdown_and_keeps_legacy_entries(self):
        import site_hook
        from library_dates import library_dates, load_entry_index
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / 'data', root / 'data')
            shutil.copytree(ROOT / 'docs/lessons', root / 'docs/lessons')
            existing_ids = {item['id'] for item in load_lessons(root)}
            future = next(((stage, concept)
                for stage in load_plan(root)['stages']
                for concept in stage['concepts']
                if concept['id'] not in existing_ids), None)
            if future is None:
                self.skipTest('所有计划课程已发布，没有新增文章的测试候选')
            stage, concept = future
            new_id = concept['id']
            candidate = root / 'candidate.md'
            candidate.write_text(compose(dict(id=new_id, title='新发布课程', date='2026-10-10',
                category=stage['id'], order=concept['order'],
                prerequisites=concept.get('prerequisites', []),
                next_concepts=[]), '完整测试正文。'), encoding='utf-8')
            publish(candidate, root)
            lessons = load_lessons(root)
            dates = library_dates(lessons, root)
            self.assertEqual(dates[new_id]['label'], '发布')
            self.assertEqual(dates['vectors-and-matrices']['label'], '入库')
            self.assertIsNone(next(x for x in lessons if x['id'] == 'vectors-and-matrices')['date'])
            unknown = dict(lessons[-1], id='unknown-date', date=None)
            self.assertNotIn('unknown-date', library_dates([unknown], root))
            self.assertTrue(set(load_entry_index(root)).issubset({item['id'] for item in lessons}))
            self.assertEqual(len(load_entry_index(root)), len(load_entry_index(ROOT)))
            with patch.multiple(site_hook, ROOT=root, load_lessons=lambda: lessons,
                    load_plan=lambda: load_plan(root), library_dates=lambda items: library_dates(items, root)):
                config = site_hook.on_config({})
            library = (root / 'docs/generated/library.md').read_text(encoding='utf-8')
            self.assertIn(f'data-library-id="{new_id}"', library)
            self.assertEqual(library.count('data-library-id='), len(lessons))
            for name in ('domains', 'chapters', 'archive'):
                legacy = (root / f'docs/generated/{name}.md').read_text(encoding='utf-8')
                self.assertIn('href="../library/"', legacy)
                self.assertNotIn('data-library-id=', legacy)
                self.assertNotIn(f'generated/{name}.md', str(config['nav']))

    def test_recommendations(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('推荐测试需要 Node.js；仅使用内置测试模块')
        with tempfile.TemporaryDirectory() as directory:
            navigation = Path(directory) / 'navigation.json'
            navigation.write_text(json.dumps(course_tracks(load_plan(), load_lessons()), ensure_ascii=False), encoding='utf-8')
            run = subprocess.run([node, str(ROOT / 'scripts/test_navigation.cjs'), str(navigation)], capture_output=True)
            self.assertEqual(run.returncode, 0, (run.stdout + run.stderr).decode('utf-8', errors='replace'))


class MathChecks(unittest.TestCase):
    def render(self, source, body_format=None):
        import markdown
        import site_hook
        from mkdocs.config import load_config
        lessons, plan = load_lessons(), load_plan()
        lesson = dict(lessons[0], body_format=body_format)
        page = SimpleNamespace(file=SimpleNamespace(src_uri=lesson['file']), meta={})
        with patch.multiple(site_hook, LESSONS=[lesson], PLAN=plan,
                NAVIGATION=course_tracks(plan, lessons)):
            rendered = site_hook.on_page_markdown(source, page, {}, [])
        config = load_config(str(ROOT / 'mkdocs.yml'))
        return markdown.markdown(rendered, extensions=config['markdown_extensions'],
                                 extension_configs=config['mdx_configs'])

    def test_matrix_without_blank_lines(self):
        from html import unescape
        expression = r'X=\begin{bmatrix}2&1&0\\2&9&1\\3&4&0\end{bmatrix}.'
        source = '矩阵：\n\\[\n' + expression + '\n\\]\n解释。'
        html = self.render(source)
        self.assertIn('<div class="arithmatex">\\[\n' + expression + '\n\\]</div>', unescape(html))
        self.assertIn('<p>解释。</p>', html)

    def test_normalized_dollars_and_idempotency(self):
        from site_hook import _normalize_display_math
        source = '公式：\n\n$$\nx^2\n$$\n\n解释。\n'
        self.assertEqual(_normalize_display_math(source), source)
        self.assertEqual(self.render(source).count('<div class="arithmatex">'), 1)
        adjacent = '前文\r\n\\[\r\nx\r\n\\]\r\n$$\r\ny\r\n$$\r\n后文'
        normalized = _normalize_display_math(adjacent)
        self.assertEqual(_normalize_display_math(normalized), normalized)
        self.assertEqual(normalized.replace('\r\n\r\n', '\r\n'), adjacent)
        spaced = '前文\n\\[  \n x\n\\]  \n后文'
        self.assertEqual(_normalize_display_math(spaced), '前文\n\n\\[  \n x\n\\]  \n\n后文')

    def test_adjacent_blocks(self):
        html = self.render('前文\n\\[\nx\n\\]\n$$\ny\n$$\n后文')
        self.assertEqual(html.count('<div class="arithmatex">'), 2)
        self.assertIn('<p>后文</p>', html)

    def test_inline_math_and_paragraphs_unchanged(self):
        from site_hook import _normalize_display_math
        source = '段落含 \\(x^2\\) 与 $y$。\n普通换行。\n\n另一段。'
        self.assertEqual(_normalize_display_math(source), source)
        self.assertEqual(self.render(source).count('<span class="arithmatex">'), 2)

    def test_code_examples_unchanged(self):
        from site_hook import _normalize_display_math
        for fence in ('```', '~~~~'):
            source = fence + 'text\n\\[\nx\n\\]\n$$\ny\n$$\n```\n' + fence + '\n'
            with self.subTest(fence=fence):
                self.assertEqual(_normalize_display_math(source), source)
                self.assertNotIn('class="arithmatex"', self.render(source))
        source = '示例：\n\n    \\[\n    x\n    \\]\n'
        self.assertEqual(_normalize_display_math(source), source)
        self.assertNotIn('class="arithmatex"', self.render(source))
        self.assertEqual(_normalize_display_math(source.replace('    ', '\t')), source.replace('    ', '\t'))
        listed = '- ```text\n    \\[\n    x\n    \\]\n    ```\n'
        self.assertEqual(_normalize_display_math(listed), listed)
        self.assertNotIn('class="arithmatex"', self.render(listed))

    def test_math_inside_list_keeps_list_structure(self):
        from site_hook import _normalize_display_math
        source = '- 列表项\n    \\[\n    x^2\n    \\]\n    项内说明。\n\n- 下一项\n'
        html = self.render(source)
        self.assertEqual(html.count('<li>'), 2)
        self.assertIn('<div class="arithmatex">', html.split('</li>')[0])
        self.assertIn('<p>项内说明。</p>', html.split('</li>')[0])
        normalized = _normalize_display_math(source)
        self.assertEqual(_normalize_display_math(normalized), normalized)
        code = '- 示例\n\n        \\[\n        x\n        \\]\n'
        self.assertEqual(_normalize_display_math(code), code)

    def test_plain_text_conversion_keeps_math_tables_and_diagrams(self):
        source = '今日寓言：测试\n故事第一句。\n故事第二句。\n一、公式\n\\[\nx^2\n\\]\n寓言\t概念\n哨兵\t感受野\n原图\n ↓\nConv 1\n'
        html = self.render(source, 'plain-text')
        self.assertEqual(html.count('<div class="arithmatex">'), 1)
        self.assertIn('<p>故事第一句。</p>\n<p>故事第二句。</p>', html)
        self.assertIn('<table>', html)
        self.assertIn('<td>感受野</td>', html)
        self.assertIn('<code', html)


class ContentChecks(unittest.TestCase):
    def test_pasted_display_preserves_math_and_restores_tables(self):
        from pasted_render import render_pasted
        source = "今日寓言：测试\n故事第一句。\n故事第二句。\n一、公式\n\\[\nx^2+1\n\\]\n寓言\t概念\n哨兵\t感受野\n原图\n ↓\nConv 1\n下一步知识网络\n结束。"
        rendered = render_pasted(source)
        self.assertIn("# 今日寓言：测试", rendered)
        self.assertIn("## 一、公式", rendered)
        self.assertIn("故事第一句。\n\n故事第二句。", rendered)
        self.assertIn("\\[\nx^2+1\n\\]", rendered)
        self.assertIn("| 哨兵 | 感受野 |", rendered)
        self.assertIn("```text\n原图\n ↓\nConv 1\n```", rendered)

    def test_repository_contract(self):
        lessons = load_lessons()
        plan = load_plan()
        concepts = [c for s in plan["stages"] for c in s["concepts"]]
        self.assertEqual(len(concepts), len({c["id"] for c in concepts}))
        self.assertGreaterEqual(len(concepts), 19)
        self.assertEqual(lessons, sorted(lessons, key=lambda x: (x["order"], x["id"])))

    def test_publish_retry_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "data", root / "data")
            meta = dict(id="receptive-field", title="测试概念", date="2026-01-01", category="cnn", order=10, prerequisites=[], next_concepts=["pooling"])
            candidate = root / "candidate.md"
            candidate.write_text(compose(meta, "完整测试正文。\n\n$$x^2$$\n"), encoding="utf-8")
            target, created = publish(candidate, root)
            self.assertTrue(created)
            self.assertFalse(publish(candidate, root)[1])
            original = target.read_bytes()
            candidate.write_text(compose(meta, "不同正文"), encoding="utf-8")
            with self.assertRaises(ValueError):
                publish(candidate, root)
            self.assertEqual(target.read_bytes(), original)

    def test_privacy_patterns(self):
        for value in ("learner@example.invalid", "sk-" + "a" * 30, '<script>alert(1)</script>'):
            with self.assertRaises(ValueError):
                privacy_check(value)

    def test_export_import_preserves_body_and_unknown_date(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "data", root / "data")
            (root / "scripts").mkdir()
            for filename in ("content.py", "import_chatgpt.py"):
                shutil.copy(ROOT / "scripts" / filename, root / "scripts" / filename)
            private = root / ".private"
            private.mkdir()
            body = "# 合成测试正文\r\n\r\n这里只验证导入，不是历史寓言。\r\n\r\n$$L=\\sum_i x_i^2$$\r\n\r\n全文结尾。"
            export = [{"id": "test-conversation", "title": "本地测试", "current_node": "assistant", "mapping": {"user": {"id": "user", "parent": None, "message": {"author": {"role": "user"}, "content": {"content_type": "text", "parts": ["无关用户消息"]}}}, "assistant": {"id": "assistant", "parent": "user", "message": {"id": "test-message", "author": {"role": "assistant"}, "create_time": None, "content": {"content_type": "text", "parts": [body]}}}}}]
            source = private / "conversations.json"
            source.write_text(json.dumps(export), encoding="utf-8")
            entry = dict(conversation_id="test-conversation", message_id="test-message", sha256=hashlib.sha256(body.encode()).hexdigest(), privacy_reviewed=True, id="receptive-field", title="合成测试", category="cnn", order=10, prerequisites=[], next_concepts=["pooling"])
            selection = private / "selection.json"
            selection.write_text(json.dumps({"articles": [entry]}), encoding="utf-8")
            run = subprocess.run([sys.executable, str(root / "scripts/import_chatgpt.py"), "import", str(source), "--selection", str(selection)], capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr.decode(errors="replace"))
            from content import split_markdown
            meta, actual = split_markdown((root / "docs/lessons/undated-receptive-field.md").read_bytes().decode("utf-8"))
            self.assertIsNone(meta["date"])
            self.assertEqual(actual, body)
            self.assertNotIn("无关用户消息", actual)


from check_ocr import OcrChecks


if __name__ == "__main__":
    unittest.main(verbosity=2)
