"""Small, non-streaming SiliconFlow client. Sends only the supplied prompt file."""
import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from paths import data_root

DEFAULTS = {"base_url": "https://api.siliconflow.cn/v1", "model": "deepseek-ai/DeepSeek-V4-Flash"}


def settings(root):
    path = root / "api.json"
    saved = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return {**DEFAULTS, **saved}


def endpoint(base_url):
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Base URL 必须是无凭据、无查询参数的 HTTPS 地址，例如 https://api.siliconflow.cn/v1")
    return base_url.rstrip("/") + "/chat/completions"


def make_payload(prompt, model, max_tokens=8192, json_mode=False):
    if not prompt.strip() or not model.strip():
        raise ValueError("提示文本与模型名称不能为空")
    if max_tokens < 1:
        raise ValueError("max_tokens 必须为正整数")
    system = "你是初中数学教师。依据用户提供的题目与作答证据工作。明确区分原创题与真题，不编造题源、学生错因或掌握率。给出可核查的解答与分步得分点。"
    if json_mode:
        system += "仅输出符合用户指定结构的 JSON 对象。"
    payload = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}], "stream": False, "max_tokens": max_tokens}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    return payload


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def call_api(url, key, payload, timeout=60):
    if not key:
        raise ValueError("未配置密钥。设置 SILICONFLOW_API_KEY，或先运行 api_client.py configure")
    request = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"}, method="POST")
    # No automatic retry: a timeout need not mean the provider did not process the request.
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=timeout) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        hints = {400: "检查模型名称及请求参数", 401: "检查 API 密钥", 403: "检查账户权限", 404: "检查模型是否仍可用以及 Base URL", 429: "检查额度或限流，稍后手动重试"}
        raise ValueError(f"硅基流动 HTTP {exc.code}：{hints.get(exc.code, '请求失败，请稍后检查服务状态')}。未自动重试。") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ValueError("API 网络连接失败或超时；是否已处理请求尚不确定，未自动重试。") from exc
    choices = result.get("choices", [])
    if not choices:
        raise ValueError("API 没有返回候选答案")
    choice = choices[0]
    if choice.get("finish_reason") != "stop":
        raise ValueError("API 输出未正常结束（可能被截断），未写入成品；请调整请求后重新生成")
    content = choice.get("message", {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("API 没有返回答案正文")
    if payload.get("response_format"):
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("API JSON 输出必须是对象")
    return content, {"model": result.get("model", payload["model"]), "usage": result.get("usage"), "verification": "unverified_model_output"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=data_root())
    commands = parser.add_subparsers(dest="command", required=True)
    config = commands.add_parser("configure", help="交互输入密钥；保存到独立数据目录")
    config.add_argument("--model", default=DEFAULTS["model"])
    config.add_argument("--base-url", default=DEFAULTS["base_url"])
    call = commands.add_parser("call")
    call.add_argument("--prompt-file", type=Path, required=True)
    call.add_argument("--out", type=Path)
    call.add_argument("--model")
    call.add_argument("--base-url")
    call.add_argument("--max-tokens", type=int, default=8192)
    call.add_argument("--timeout", type=float, default=60)
    call.add_argument("--json", action="store_true")
    call.add_argument("--dry-run", action="store_true", help="只校验请求，不联网，不需要密钥")
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    try:
        if args.command == "configure":
            endpoint(args.base_url)
            if not args.model.strip():
                raise ValueError("模型名称不能为空")
            key = getpass.getpass("硅基流动 API Key（输入不显示）：").strip()
            if not key:
                raise ValueError("密钥为空，配置未保存")
            root.mkdir(parents=True, exist_ok=True)
            key_path = root / ".siliconflow-key"
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(key)
            key_path.chmod(0o600)
            (root / "api.json").write_text(json.dumps({"base_url": args.base_url, "model": args.model}, ensure_ascii=False, indent=2), encoding="utf-8")
            print("API 配置已保存。")
            return
        cfg = settings(root)
        url = endpoint(args.base_url or cfg["base_url"])
        payload = make_payload(args.prompt_file.read_text(encoding="utf-8"), args.model or os.environ.get("SILICONFLOW_MODEL") or cfg["model"], args.max_tokens, args.json)
        if args.dry_run:
            print(json.dumps({"network_call": False, "endpoint": url, "model": payload["model"], "prompt_characters": len(payload["messages"][-1]["content"]), "json_mode": args.json}, ensure_ascii=False))
            return
        if not args.out:
            raise ValueError("实际调用需要 --out，指定模型答案的保存文件")
        if args.out.exists() or args.out.with_suffix(args.out.suffix + ".meta.json").exists():
            raise ValueError("输出已存在，请使用新文件名，避免覆盖原答案")
        if args.timeout <= 0:
            raise ValueError("timeout 必须为正数")
        secret = root / ".siliconflow-key"
        key = os.environ.get("SILICONFLOW_API_KEY") or (secret.read_text(encoding="utf-8").strip() if secret.exists() else "")
        content, meta = call_api(url, key, payload, args.timeout)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(content, encoding="utf-8")
        args.out.with_suffix(args.out.suffix + ".meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"output": str(args.out.resolve()), **meta}, ensure_ascii=False))
    except (ValueError, OSError, EOFError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
