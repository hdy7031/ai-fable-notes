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
from curriculum import MAIN_STAGES, ordered_stages, navigation_lessons, course_tracks, course_neighbors


class NavigationChecks(unittest.TestCase):
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
            self.assertIn('下一篇 · 待发布', neighbors)
            self.assertIn('../../generated/stages/training/#concept-chain-rule', neighbors)
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
            candidate = root / 'candidate.md'
            candidate.write_text(compose(dict(id='chain-rule', title='新发布课程', date='2026-10-09',
                category='training', order=80, prerequisites=['partial-derivative-and-gradient'],
                next_concepts=[]), '完整测试正文。'), encoding='utf-8')
            publish(candidate, root)
            lessons = load_lessons(root)
            dates = library_dates(lessons, root)
            self.assertEqual(dates['chain-rule']['label'], '发布')
            self.assertEqual(dates['vectors-and-matrices']['label'], '入库')
            self.assertIsNone(next(x for x in lessons if x['id'] == 'vectors-and-matrices')['date'])
            unknown = dict(lessons[-1], id='unknown-date', date=None)
            self.assertNotIn('unknown-date', library_dates([unknown], root))
            self.assertEqual(len(load_entry_index(root)), len(load_lessons()))
            with patch.multiple(site_hook, ROOT=root, load_lessons=lambda: lessons,
                    load_plan=lambda: load_plan(root), library_dates=lambda items: library_dates(items, root)):
                config = site_hook.on_config({})
            library = (root / 'docs/generated/library.md').read_text(encoding='utf-8')
            self.assertIn('data-library-id="chain-rule"', library)
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
