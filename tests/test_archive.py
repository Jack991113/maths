"""Behavior tests use disposable roots only; never populate the student's archive."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / "maths" / "scripts" / "archive.py"
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jR1cAAAAASUVORK5CYII=")


class ArchiveBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="maths-test-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "student-data"
        self.image = self.base / "学生手写原图.png"
        self.image.write_bytes(PNG)
        self.cli("init")

    def cli(self, *args, root=None, payload=None, success=True):
        command = [sys.executable, str(SCRIPT), "--root", str(root or self.root), *args]
        if payload is not None:
            source = self.base / "input.json"
            source.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            command += ["--file", str(source)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0 if success else 2, result.stdout + result.stderr)
        return json.loads(result.stdout if success else result.stderr)

    def question(self, item="第1题", image=None):
        return {"stem": "解方程 x² − 5x + 6 = 0。", "topics": ["一元二次方程"],
                "source_images": [str(image or self.image)], "source_item_key": item,
                "source": {"type": "user_upload", "citation": "测试原图，非学生真实数据"},
                "recognition": {"status": "confirmed", "notes": "测试输入"},
                "answer": {"text": "x=2 或 x=3", "verification_status": "verified", "verification_notes": "2²−5×2+6=0；3²−5×3+6=0"}}

    def attempt(self):
        return {"process_text": "测试作答：学生写 x=2，漏写另一根。", "result": "partial",
                "score": 2, "max_score": 4, "assistance": "none", "kind": "initial",
                "error_analysis": {"status": "confirmed", "causes": ["漏根"], "evidence": "作答只写出 x=2；另一根 x=3 未写。"}}

    def test_originals_dedup_multiple_items_and_no_fabricated_attempt(self):
        first = self.cli("add", payload=self.question())
        duplicate = self.cli("add", payload=self.question())
        self.assertEqual(duplicate["status"], "existing")
        self.assertEqual(duplicate["id"], first["id"])
        second = self.cli("add", payload=self.question("第2题"))
        self.assertNotEqual(first["id"], second["id"])
        self.image.unlink()
        shown = self.cli("show", "--question", first["id"])
        preserved = self.root / shown["question"]["source_images"][0]["path"]
        self.assertEqual(preserved.read_bytes(), PNG)
        self.assertEqual(shown["question"]["source_images"][0]["sha256"], hashlib.sha256(PNG).hexdigest())
        self.assertEqual(shown["attempts"], [])
        self.assertEqual(self.cli("summary")["attempt_count"], 0)
        self.assertEqual(len(self.cli("list", "--topic", "一元二次方程")), 2)
        self.assertEqual(self.cli("list", "--topic", "圆"), [])

    def test_versions_and_actual_attempts_remain_separate(self):
        first = self.cli("add", payload=self.question())
        attempt = self.cli("attempt", "--question", first["id"], payload=self.attempt())
        edited = self.question()
        edited["stem"] = "解方程 x² − 5x + 6 = 0，并验根。"
        revised = self.cli("revise", "--question", first["id"], payload=edited)
        self.assertEqual(revised["version"], 2)
        correction = self.attempt()
        correction.update(kind="correction", process_text="测试订正：看答案后补上 x=3。", result="correct", score=4, assistance="answer_seen", linked_attempt_id=attempt["id"], error_analysis={"status": "unknown"})
        self.cli("attempt", "--question", first["id"], payload=correction)
        self.cli("add", payload=self.question())
        shown = self.cli("show", "--question", first["id"])
        self.assertEqual(len(shown["revisions"]), 2)
        self.assertEqual(shown["revisions"][0]["question"]["stem"], self.question()["stem"])
        self.assertEqual(len(shown["attempts"]), 2)
        self.assertEqual([a["question_version"] for a in shown["attempts"]], [1, 2])
        self.assertEqual(shown["attempts"][1]["attempt"]["linked_attempt_id"], attempt["id"])
        summary = self.cli("summary")
        self.assertEqual(summary["assistance_counts"], {"none": 1, "answer_seen": 1})
        self.assertEqual(summary["confirmed_error_cause_events"], {"漏根": 1})
        self.assertFalse(any("rate" in key or "mastery" in key for key in summary))

    def test_invalid_input_never_changes_records_or_assets(self):
        first = self.cli("add", payload=self.question())
        baseline = self.cli("show", "--question", first["id"])
        files = set((self.root / "assets").iterdir())
        missing_item = self.question()
        missing_item.pop("source_item_key")
        self.cli("add", payload=missing_item, success=False)
        bad_images = self.question("第2题")
        bad_images["source_images"].append(str(self.base / "missing.png"))
        self.cli("add", payload=bad_images, success=False)
        wrong_score = self.attempt()
        wrong_score["score"] = 9
        self.cli("attempt", "--question", first["id"], payload=wrong_score, success=False)
        no_evidence = self.attempt()
        no_evidence["process_text"] = ""
        self.cli("attempt", "--question", first["id"], payload=no_evidence, success=False)
        wrong_link = self.attempt()
        wrong_link["linked_attempt_id"] = "a_missing"
        self.cli("attempt", "--question", first["id"], payload=wrong_link, success=False)
        self.assertEqual(self.cli("show", "--question", first["id"]), baseline)
        self.assertEqual(set((self.root / "assets").iterdir()), files)
        self.assertEqual(self.cli("summary")["question_count"], 1)

    def test_analysis_annotations_preserve_original_and_do_not_add_attempts(self):
        question = self.cli("add", payload=self.question())
        attempt = self.attempt()
        attempt["error_analysis"]["status"] = "hypothesis"
        initial = self.cli("attempt", "--question", question["id"], payload=attempt)
        self.assertEqual(self.cli("summary")["hypothesized_error_cause_events"], {"漏根": 1})
        annotation = {"reason": "测试：重新阅读原图确认遗漏另一根", "changes": {
            "error_analysis": {"status": "confirmed", "causes": ["漏根"], "evidence": "测试原图只写 x=2，x=3 没有写出"}}}
        revised = self.cli("annotate", "--attempt", initial["id"], payload=annotation)
        self.assertEqual(revised["attempt"]["error_analysis"]["status"], "hypothesis")
        self.assertEqual(revised["effective_attempt"]["error_analysis"]["status"], "confirmed")
        self.assertEqual(len(revised["annotations"]), 1)
        invalid = {"reason": "分数矛盾应拒绝", "changes": {"result": "correct"}}
        self.cli("annotate", "--attempt", initial["id"], payload=invalid, success=False)
        shown = self.cli("show", "--question", question["id"])
        self.assertEqual(len(shown["attempts"]), 1)
        self.assertEqual(len(shown["attempts"][0]["annotations"]), 1)
        summary = self.cli("summary")
        self.assertEqual(summary["attempt_count"], 1)
        self.assertEqual(summary["hypothesized_error_cause_events"], {})
        self.assertEqual(summary["confirmed_error_cause_events"], {"漏根": 1})
        corrected = {"reason": "测试：核对评分标准后纠正评分记录", "changes": {"result": "correct", "score": 4,
            "error_analysis": {"status": "unknown", "causes": [], "evidence": ""}}}
        self.cli("annotate", "--attempt", initial["id"], payload=corrected)
        summary = self.cli("summary")
        self.assertEqual(summary["attempt_count"], 1)
        self.assertEqual(summary["recorded_results"], {"correct": 1})
        self.assertEqual(summary["confirmed_error_cause_events"], {})
        self.cli("delete", "--question", question["id"])
        self.cli("annotate", "--attempt", initial["id"], payload=annotation, success=False)

    def test_delete_preserves_shared_images_and_clears_all_versions_and_attempts(self):
        first = self.cli("add", payload=self.question())
        second = self.cli("add", payload=self.question("第2题"))
        event = self.attempt()
        event["process_images"] = [str(self.image)]
        self.cli("attempt", "--question", second["id"], payload=event)
        shared = self.root / first["question"]["source_images"][0]["path"]
        self.cli("delete", "--question", first["id"])
        self.assertTrue(shared.exists())
        self.assertEqual(self.cli("summary")["question_count"], 1)
        replacement = self.base / "重拍.png"
        replacement.write_bytes(PNG + b"new-photo-test-bytes")
        self.cli("revise", "--question", second["id"], payload=self.question("第2题", replacement))
        self.assertTrue(shared.exists(), "版本更新不能清除旧原图")
        profile = self.root / "profile.json"
        profile.write_text('{"name":"保留档案"}', encoding="utf-8")
        deleted = self.cli("delete", "--all")
        self.assertEqual(len(deleted["removed_assets"]), 2)
        self.assertEqual(list((self.root / "assets").iterdir()), [])
        self.assertEqual(self.cli("summary")["attempt_count"], 0)
        self.assertTrue(profile.exists())
        self.cli("show", "--question", second["id"], success=False)

    def test_init_is_idempotent_and_preserves_profile(self):
        first = self.cli("add", payload=self.question())
        profile = self.root / "profile.json"
        profile.write_text('{"student":"test"}', encoding="utf-8")
        profile_before = profile.read_bytes()
        self.assertEqual(self.cli("init")["status"], "existing")
        self.assertEqual(profile.read_bytes(), profile_before)
        self.assertEqual(self.cli("show", "--question", first["id"])["id"], first["id"])

    def test_default_root_uses_paths_environment_without_touching_real_data(self):
        configured = self.base / "environment-data"
        environment = dict(os.environ, MATHS_DATA_DIR=str(configured))
        result = subprocess.run([sys.executable, str(SCRIPT), "init"], env=environment,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["root"], str(configured.resolve()))
        self.assertTrue((configured / "archive.sqlite3").is_file())

    def test_backup_restore_and_readable_export(self):
        first = self.cli("add", payload=self.question())
        event = self.cli("attempt", "--question", first["id"], payload=self.attempt())
        self.cli("annotate", "--attempt", event["id"], payload={"reason": "测试：补充提示状态", "changes": {"assistance": "hint"}})
        profile = self.root / "profile.json"
        profile.write_text('{"exam_year":2027}', encoding="utf-8")
        backup = self.base / "迁移档案.zip"
        self.cli("backup", "--out", str(backup))
        original_backup = backup.read_bytes()
        self.cli("backup", "--out", str(backup), success=False)
        self.assertEqual(backup.read_bytes(), original_backup)
        migrated = self.base / "another-computer" / "maths-data"
        self.cli("restore", "--from", str(backup), root=migrated)
        self.assertEqual(self.cli("show", "--question", first["id"], root=migrated), self.cli("show", "--question", first["id"]))
        self.assertEqual((migrated / "profile.json").read_bytes(), profile.read_bytes())
        image_path = first["question"]["source_images"][0]["path"]
        self.assertEqual((migrated / image_path).read_bytes(), PNG)
        readable = self.base / "可读档案.json"
        self.cli("export", "--out", str(readable), root=migrated)
        self.assertEqual(json.loads(readable.read_text(encoding="utf-8"))["questions"][0]["id"], first["id"])
        self.cli("restore", "--from", str(backup), root=migrated, success=False)
        self.assertEqual(self.cli("summary", root=migrated)["question_count"], 1)

    def test_corrupt_or_unsafe_migration_does_not_replace_target(self):
        self.cli("add", payload=self.question())
        backup = self.base / "good.zip"
        self.cli("backup", "--out", str(backup))
        corrupt = self.base / "corrupt.zip"
        with zipfile.ZipFile(backup) as good, zipfile.ZipFile(corrupt, "w") as bad:
            for info in good.infolist():
                bad.writestr(info.filename, b"damaged" if info.filename.startswith("assets/") else good.read(info))
        target = self.base / "restored"
        self.cli("restore", "--from", str(corrupt), root=target, success=False)
        self.assertFalse(target.exists())
        unsafe = self.base / "unsafe.zip"
        with zipfile.ZipFile(backup) as good, zipfile.ZipFile(unsafe, "w") as bad:
            for info in good.infolist():
                bad.writestr(info.filename, good.read(info))
            bad.writestr("../escape.txt", "bad")
        self.cli("restore", "--from", str(unsafe), root=target, success=False)
        self.assertFalse((self.base / "escape.txt").exists())
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
