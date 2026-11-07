"""Focused synthetic checks; never publish fixtures as real teaching."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from content import ROOT, split_markdown
from ocr_course import course_index, course_part, course_track, load_course


class OcrChecks(unittest.TestCase):
    def fixture(self, directory):
        root = Path(directory)
        shutil.copytree(ROOT / 'data', root / 'data')
        (root / 'scripts').mkdir()
        for name in ('content.py', 'ocr_course.py', 'import_chatgpt.py'):
            shutil.copy(ROOT / 'scripts' / name, root / 'scripts' / name)
        private = root / '.private'
        private.mkdir()
        bodies = ['合成提问：像素如何表示？',
                  '# 合成讲解\r\n\\[\nX=\\begin{bmatrix}1&2\\\\3&4\\end{bmatrix}\n\\]\n```python\nprint(1)\n```',
                  '合成追问：三个颜色通道呢？', '合成解释：保留追问和完整例子。']
        mapping, refs = {}, []
        for i, body in enumerate(bodies):
            mid = f'm{i}'
            mapping[mid] = dict(id=mid, parent=f'm{i-1}' if i else None,
                                message=dict(id=mid, author=dict(role='user' if i % 2 == 0 else 'assistant'),
                                             content=dict(content_type='text', parts=[body])))
            refs.append(dict(message_id=mid, sha256=hashlib.sha256(body.encode()).hexdigest()))
        source = private / 'conversations.json'
        export = [dict(id='synthetic-conversation', title='OCR 合成验收', current_node='m3', mapping=mapping)]
        source.write_text(json.dumps(export), encoding='utf-8')
        manifest = dict(export_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                        chapters=[dict(id='ocr-pixels-rgb', conversation_id='synthetic-conversation',
                                       privacy_reviewed=True, messages=refs)])
        return root, source, manifest, bodies, export

    def run_import(self, root, source, manifest):
        selection = root / '.private/selection.json'
        selection.write_text(json.dumps(manifest), encoding='utf-8')
        return subprocess.run([sys.executable, str(root / 'scripts/import_chatgpt.py'), 'import-course',
                               str(source), '--selection', str(selection)], capture_output=True)

    def test_full_turns_receipt_progress_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root, source, manifest, bodies, _ = self.fixture(directory)
            run = self.run_import(root, source, manifest)
            self.assertEqual(run.returncode, 0, run.stderr.decode(errors='replace'))
            target = root / 'docs/ocr/chapters/undated-ocr-pixels-rgb.md'
            original = target.read_bytes()
            meta, body = split_markdown(original.decode())
            self.assertIsNone(meta['date'])
            for source_body in bodies:
                self.assertIn(source_body, body)
            self.assertNotIn('synthetic-conversation', original.decode())
            receipt = json.loads((root / '.private/ocr/receipts/ocr-pixels-rgb.json').read_text(encoding='utf-8'))
            self.assertEqual(receipt['body_sha256'], hashlib.sha256(body.encode()).hexdigest())
            self.assertEqual(len(receipt['messages']), 4)
            track = course_track(root)
            self.assertTrue(track[0]['published'])
            self.assertFalse(track[1]['published'])
            self.assertEqual(track[1]['url'], 'ocr/#ocr-convolution-features')
            index = course_index(root)
            self.assertIn('data-course-id="ocr-pixels-rgb"', course_part("ocr-part-1", root))
            self.assertIn('chapters/undated-ocr-pixels-rgb/', index)
            self.assertIn('已发布 1 章', index)
            self.assertNotEqual(self.run_import(root, source, manifest).returncode, 0)
            self.assertEqual(target.read_bytes(), original)
            # Exercise the actual MkDocs hook with a published OCR body, not just empty-course builds.
            for folder in ('scripts', 'docs'):
                shutil.copytree(ROOT / folder, root / folder, dirs_exist_ok=True)
            shutil.copyfile(ROOT / 'mkdocs.yml', root / 'mkdocs.yml')
            build = subprocess.run([sys.executable, '-m', 'mkdocs', 'build', '--strict'],
                                   cwd=root, capture_output=True)
            self.assertEqual(build.returncode, 0, build.stderr.decode(errors='replace'))
            page = (root / 'site/ocr/chapters/undated-ocr-pixels-rgb/index.html').read_text(encoding='utf-8')
            self.assertIn('class="arithmatex"', page)
            self.assertIn('aria-label="前后章"', page)
            part_page = (root / 'site/ocr/parts/ocr-part-1/index.html').read_text(encoding='utf-8')
            self.assertIn('../../../ocr/chapters/undated-ocr-pixels-rgb/', part_page)
            self.assertIn('assets/ocr.css', part_page)
            self.assertIn('<strong>课时规划</strong>', part_page)
            self.assertNotIn('assets/ocr.css', page)
            self.assertIn('../../../ocr/#ocr-convolution-features', page)


    def test_reject_changed_hash_gaps_attachments_and_unreviewed(self):
        for case in ('source-hash', 'message-hash', 'gap', 'attachment', 'privacy', 'unreviewed'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root, source, manifest, _, export = self.fixture(directory)
                entry = manifest['chapters'][0]
                if case == 'source-hash':
                    manifest['export_sha256'] = '0' * 64
                elif case == 'message-hash':
                    entry['messages'][0]['sha256'] = '0' * 64
                elif case == 'gap':
                    del entry['messages'][2]
                elif case == 'unreviewed':
                    entry['privacy_reviewed'] = False
                else:
                    message = export[0]['mapping']['m2']['message']
                    if case == 'attachment':
                        message['metadata'] = {'attachments': [{'id': 'synthetic-image'}]}
                    else:
                        message['content']['parts'] = ['synthetic@example.invalid']
                        entry['messages'][2]['sha256'] = hashlib.sha256(message['content']['parts'][0].encode()).hexdigest()
                    source.write_text(json.dumps(export), encoding='utf-8')
                    manifest['export_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
                self.assertNotEqual(self.run_import(root, source, manifest).returncode, 0)
                self.assertEqual(list((root / 'docs/ocr/chapters').glob('*.md')), [])
                self.assertEqual(list((root / '.private/ocr/receipts').glob('*.json')), [])

    def test_module_dependencies_and_legacy_anchors(self):
        course = load_course()
        self.assertEqual(len(course['parts']), 4)
        self.assertEqual(len(course['modules']), 12)
        index = course_index()
        for chapter_id in ('ocr-pixels-rgb', 'ocr-convolution-features', 'ocr-training',
                           'ocr-cnn-structure', 'ocr-dbnet', 'ocr-crnn-ctc',
                           'ocr-paddleocr', 'ocr-document-intelligence'):
            self.assertIn('id="' + chapter_id + '"', index)
            self.assertIn('data-ocr-redirect', index)
        self.assertEqual(course['next_chapter'], 'ocr-dbnet')
        for part in course['parts']:
            page = course_part(part['id'])
            for module in (m for m in course['modules'] if m['part'] == part['id']):
                self.assertIn('id="' + module['id'] + '"', page)
                self.assertIn(module['practice'], page)
                for lesson in module['lessons']:
                    self.assertIn(lesson, page)
        self.assertNotIn('开始阅读', index)
        self.assertNotIn('实践目标', index)
        with tempfile.TemporaryDirectory() as directory:
            import yaml
            root = Path(directory)
            (root / 'data').mkdir()
            course['modules'][0]['prerequisites'] = ['ocr-module-12']
            (root / 'data/ocr-course.yml').write_text(yaml.safe_dump(course), encoding='utf-8')
            with self.assertRaises(ValueError):
                load_course(root)

    def test_title_filter_before_branch_and_scan_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root, source, _, _, export = self.fixture(directory)
            export.append(dict(id='unrelated', title='其他话题', mapping={}))
            source.write_text(json.dumps(export), encoding='utf-8')
            output = root / '.private/ocr/candidates.json'
            run = subprocess.run([sys.executable, str(root / 'scripts/import_chatgpt.py'), 'scan', str(source),
                                  '--include-user', '--title-keywords', 'OCR', '--output', str(output)], capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr.decode(errors='replace'))
            scanned = json.loads(output.read_text(encoding='utf-8'))
            self.assertEqual(len(scanned['candidates']), 4)
            self.assertEqual(scanned['export_sha256'], hashlib.sha256(source.read_bytes()).hexdigest())
