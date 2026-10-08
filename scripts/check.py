"""Small content/import/idempotency checks; no model calls or browser dependencies."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

from content import ROOT, compose, load_lessons, load_plan, privacy_check, publish


class ContentChecks(unittest.TestCase):
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
