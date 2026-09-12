"""Run a maths command with dependencies installed outside the skill directory."""
import runpy
import sys
from pathlib import Path
from paths import codex_home

if len(sys.argv) < 2:
    raise SystemExit("用法：python scripts/run.py archive|build_documents|api_client|paths [参数]")
script = sys.argv.pop(1)
if script not in {"archive", "build_documents", "draw_figures", "api_client", "paths"}:
    raise SystemExit("未知 maths 命令")
skill_path = Path(__file__).resolve().parent.parent
home = skill_path.parent.parent if skill_path.parent.name == "skills" else codex_home()
packages = home / "maths-runtime" / "packages"
if packages.is_dir():
    sys.path.insert(0, str(packages))
sys.argv[0] = str(skill_path / "scripts" / (script + ".py"))
runpy.run_path(sys.argv[0], run_name="__main__")
