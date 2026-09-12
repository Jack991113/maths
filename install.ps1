$ErrorActionPreference = "Stop"
$mathsScript = Join-Path $PSScriptRoot "install.py"
if ($env:MATHS_PYTHON) {
    & $env:MATHS_PYTHON $mathsScript @args
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 $mathsScript @args
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python $mathsScript @args
} else {
    throw "请安装 Python 3.10+，然后重新运行安装脚本。"
}
if ($LASTEXITCODE -ne 0) { throw "maths 安装失败，请检查上方输出。" }
