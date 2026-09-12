#!/bin/bash
set -euo pipefail
maths_dir="$(cd "$(dirname "$0")" && pwd)"
maths_python="${MATHS_PYTHON:-}"
if [ -z "$maths_python" ]; then
  maths_bundled="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
  if [ -x "$maths_bundled" ]; then
    maths_python="$maths_bundled"
  elif command -v python3 >/dev/null 2>&1; then
    maths_python="$(command -v python3)"
  else
    echo "未找到 Python。请安装 Python 3.10+ 后重试，或在 Codex 中让助手安装本目录的 maths 技能。"
    exit 1
  fi
fi
"$maths_python" "$maths_dir/install.py" "$@"
