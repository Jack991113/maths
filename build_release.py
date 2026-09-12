"""Create the explicit, data-free distributable and its checksum."""
import hashlib
import shutil
import zipfile
from pathlib import Path

VERSION = "1.0.0"
BASE = Path(__file__).resolve().parent
release = BASE / "release"
name = f"maths-macos-{VERSION}"
staged = release / name
archive = release / (name + ".zip")
release.mkdir(exist_ok=True)
if staged.exists():
    shutil.rmtree(staged)
staged.mkdir()
shutil.copytree(BASE / "maths", staged / "maths", ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
shutil.copytree(BASE / "tests", staged / "tests", ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
for filename in ("install.py", "install.command", "install.ps1", "安装说明.md", "验证记录.md"):
    shutil.copy2(BASE / filename, staged / filename)
with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
    for path in sorted(staged.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"安装包不得包含符号链接: {path}")
        if path.is_file():
            if path.suffix in {".sqlite3", ".db"} or path.name in {".siliconflow-key", "api.json", "profile.json"}:
                raise ValueError(f"安装包混入个人数据: {path}")
            bundle.write(path, path.relative_to(release).as_posix())
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
checksum = archive.with_suffix(".zip.sha256")
checksum.write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
print(archive)
print(checksum)
