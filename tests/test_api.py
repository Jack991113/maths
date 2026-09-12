import io
import json
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "maths" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import api_client


class FakeOpener:
    def __init__(self, result):
        self.result = result
        self.request = None

    def open(self, request, timeout):
        self.request = request
        return io.BytesIO(json.dumps(self.result).encode())


class ApiTests(unittest.TestCase):
    def test_request_and_response(self):
        opener = FakeOpener({"model": "test-model", "choices": [{"finish_reason": "stop", "message": {"content": '{"answer":4}'}}], "usage": {"total_tokens": 20}})
        payload = api_client.make_payload("返回JSON：2+2", "test-model", json_mode=True)
        with patch("urllib.request.build_opener", return_value=opener):
            answer, meta = api_client.call_api(api_client.endpoint("https://api.siliconflow.cn/v1"), "test-token", payload)
        self.assertEqual(json.loads(answer), {"answer": 4})
        self.assertEqual(opener.request.get_header("Authorization"), "Bearer test-token")
        self.assertEqual(json.loads(opener.request.data)["messages"][-1]["content"], "返回JSON：2+2")
        self.assertEqual(meta["verification"], "unverified_model_output")
        self.assertNotIn("test-token", json.dumps(meta))

    def test_reject_truncation_and_empty_answer(self):
        for reason, content in [("length", "partial"), ("stop", "")]:
            opener = FakeOpener({"choices": [{"finish_reason": reason, "message": {"content": content}}]})
            with patch("urllib.request.build_opener", return_value=opener), self.assertRaises(ValueError):
                api_client.call_api("https://api.siliconflow.cn/v1/chat/completions", "test", api_client.make_payload("test", "test-model"))

    def test_error_does_not_echo_server_or_key(self):
        error = urllib.error.HTTPError("https://api.siliconflow.cn", 401, "test-token", {}, io.BytesIO(b"test-token"))
        with patch("urllib.request.OpenerDirector.open", side_effect=error):
            with self.assertRaises(ValueError) as raised:
                api_client.call_api("https://api.siliconflow.cn/v1/chat/completions", "test-token", api_client.make_payload("test", "test-model"))
        self.assertIn("401", str(raised.exception))
        self.assertNotIn("test-token", str(raised.exception))

    def test_dry_run_without_credentials_or_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = root / "request.txt"
            prompt.write_text("求解 x²−5x+6=0", encoding="utf-8")
            result = subprocess.run([sys.executable, str(SCRIPTS / "run.py"), "api_client", "--root", str(root), "call", "--prompt-file", str(prompt), "--dry-run"], capture_output=True, text=True, check=True)
            self.assertFalse(json.loads(result.stdout)["network_call"])
            self.assertEqual(list(root.iterdir()), [prompt])

    def test_reject_unsafe_or_malformed_endpoint(self):
        for url in ["http://api.siliconflow.cn/v1", "https://user:secret@example.com", "https://example.com?key=value"]:
            with self.assertRaises(ValueError):
                api_client.endpoint(url)


if __name__ == "__main__":
    unittest.main()
