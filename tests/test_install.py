import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]


class InstallationTests(unittest.TestCase):
    def test_clean_install_upgrade_and_custom_data(self):
        with tempfile.TemporaryDirectory(prefix="maths-install-test-") as tmp:
            directory = Path(tmp)
            codex = directory / "Codex with spaces"
            data = directory / "学生档案"
            env = os.environ.copy()
            env.pop("CODEX_HOME", None)
            env.pop("MATHS_DATA_DIR", None)
            base = [sys.executable, str(WORKSPACE / "install.py"), "--codex-home", str(codex), "--skip-deps"]
            subprocess.run(base + ["--data-dir", str(data)], env=env, check=True, capture_output=True, text=True)
            skill = codex / "skills" / "maths"
            self.assertTrue((skill / "SKILL.md").is_file())
            profile = data / "profile.json"
            personal = json.loads(profile.read_text(encoding="utf-8"))
            personal["current_topic"] = "安装升级保留检查"
            profile.write_text(json.dumps(personal, ensure_ascii=False), encoding="utf-8")
            subprocess.run(base, env=env, check=True, capture_output=True, text=True)
            self.assertEqual(json.loads(profile.read_text(encoding="utf-8"))["current_topic"], "安装升级保留检查")
            self.assertEqual(len(list((codex / "maths-skill-backups").iterdir())), 1)
            resolved = subprocess.run([sys.executable, str(skill / "scripts" / "run.py"), "paths"], env=env, check=True, capture_output=True, text=True).stdout.strip()
            self.assertEqual(Path(resolved), data.resolve())
            self.assertFalse((skill / "profile.json").exists())
            self.assertFalse((skill / ".siliconflow-key").exists())


if __name__ == "__main__":
    unittest.main()
