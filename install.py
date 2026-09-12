#!/usr/bin/env python3
"""Install the portable maths skill without overwriting student data."""
import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path


def install(source, codex, root, skip_deps=False):
    if sys.version_info < (3, 10):
        raise ValueError("需要 Python 3.10 或更高版本")
    if not (source / "SKILL.md").is_file():
        raise ValueError("安装包不完整：缺少 maths/SKILL.md")
    target = codex / "skills" / "maths"
    if source.resolve() == target.resolve():
        raise ValueError("请从解压的安装包运行安装器")
    if root == target or target in root.parents:
        raise ValueError("学生数据目录必须位于技能目录之外")
    runtime = codex / "maths-runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    if not skip_deps and not all(importlib.util.find_spec(x) for x in ("docx", "PIL", "lxml")):
        packages = runtime / "packages"
        subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "--target", str(packages), "-r", str(source / "requirements.txt")], check=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".maths-install-", dir=target.parent))
    try:
        staged_skill = staging / "maths"
        shutil.copytree(source, staged_skill, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
        if target.exists():
            backup = codex / "maths-skill-backups" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            backup.parent.mkdir(parents=True, exist_ok=True)
            target.rename(backup)
        staged_skill.rename(target)
    finally:
        shutil.rmtree(staging)
    root.mkdir(parents=True, exist_ok=True)
    profile = root / "profile.json"
    if not profile.exists():
        shutil.copy2(target / "assets" / "default-profile.json", profile)
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex)
    env["MATHS_DATA_DIR"] = str(root)
    subprocess.run([sys.executable, str(target / "scripts" / "run.py"), "archive", "--root", str(root), "init"], env=env, check=True)
    record = {"python": sys.executable, "skill_dir": str(target), "data_dir": str(root), "dependencies_skipped": skip_deps}
    (runtime / "installation.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    # This mapping lives outside the package and is local to the destination computer.
    (runtime / "data-location.json").write_text(json.dumps({"data_dir": str(root)}, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex"))
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--skip-deps", action="store_true", help="仅在已有 docx/Pillow 依赖时使用")
    args = parser.parse_args()
    codex = args.codex_home.expanduser().resolve()
    location = codex / "maths-runtime" / "data-location.json"
    previous = json.loads(location.read_text(encoding="utf-8"))["data_dir"] if location.exists() else codex / "maths-data"
    root = Path(args.data_dir or os.environ.get("MATHS_DATA_DIR") or previous).expanduser().resolve()
    try:
        record = install(Path(__file__).resolve().parent / "maths", codex, root, args.skip_deps)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"安装未完成：{exc}") from None
    print(json.dumps({"installed": True, **record}, ensure_ascii=False, indent=2))
    print("maths 已安装。可在 Codex 新任务中使用 $maths 或你的数学出卷指令。")


if __name__ == "__main__":
    main()
