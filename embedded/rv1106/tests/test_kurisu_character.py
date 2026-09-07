"""Offline checks against the actual embedded persona loader, without API calls."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from agent_core.headless import create_manager
from agent_core.session.path_resolver import PathResolver


class KurisuCharacterTest(unittest.TestCase):
    def test_seed_prompt_and_restart_preserve_runtime(self):
        seed = ROOT / "characters/kurisu_amadeus"
        def hashes():
            return {str(p.relative_to(seed)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in seed.rglob("*") if p.is_file()}
        original = hashes()
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ):
            settings = dict(role_dir=str(seed), data_dir=temporary,
                            model=dict(name="qwen-plus", provider="qwen",
                                       base_url="https://example.invalid/v1"))
            manager = create_manager(settings, chat_agent=object())
            profile = json.loads((seed / "persona/profile.json").read_text(encoding="utf-8"))
            prompt = manager.prompt_builder.build_system_prompt()
            self.assertIn(profile["background"], prompt)
            self.assertIn("没有与冈部共同度过本篇夏天的记忆", prompt)
            runtime = Path(temporary) / "default/persona/profile.json"
            saved = json.loads(runtime.read_text(encoding="utf-8"))
            saved["background"] += "\n重启测试：保留已保存的运行数据。"
            runtime.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
            restarted = create_manager(settings, chat_agent=object())
            self.assertIn("重启测试：保留已保存的运行数据。", restarted.prompt_builder.build_system_prompt())
            memories = json.loads((seed / "persona/memories.json").read_text(encoding="utf-8"))
            self.assertEqual([len(v) for v in memories.values()], [6, 3, 21, 0, 0])
            self.assertEqual(memories, json.loads(
                (runtime.parent / "memories.json").read_text(encoding="utf-8")))
            entries = [entry for group in memories.values() for entry in group]
            self.assertEqual(len({entry["id"] for entry in entries}), 30)
            for entry in entries:
                self.assertIn("local_user_memory=false", entry["context"])
                self.assertIsInstance(entry["context"], str)
            self.assertEqual(original, hashes())
        PathResolver.clear_app_storage_root()


if __name__ == "__main__":
    unittest.main()
