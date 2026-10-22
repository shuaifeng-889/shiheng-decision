# 史衡 · 五链决策模型 —— Windows 一键安装
#
# 用法（PowerShell）：
#   .\install.ps1                 装到 $env:USERPROFILE\.workbuddy\skills\shiheng-decision
#   .\install.ps1 -Target "D:\skills\shiheng-decision"
#   .\install.ps1 -Mode Copy      复制而非软链接（默认软链接，失败自动回退到复制）
#
# 只做三件事：检查环境、放到 skills 路径下、跑一次自检。不删除任何文件。
# 如果目标已存在，会先征求确认。

[CmdletBinding()]
param(
    [string]$Target = "",
    [ValidateSet("Link", "Copy")]
    [string]$Mode = "Link"
)

$ErrorActionPreference = "Stop"

$Name = "shiheng-decision"
$Src  = Split-Path -Parent $MyInvocation.MyCommand.Definition

# ---- 1. 找 Python ----------------------------------------------------------
$PyExe = $null
foreach ($cand in @("python", "python3", "py")) {
    $cmd = Get-Command $cand -ErrorAction SilentlyContinue
    if ($cmd) {
        try {
            $ver = & $cand -c "import sys; print(sys.version_info[0]*100+sys.version_info[1])" 2>$null
            if ([int]$ver -ge 308) { $PyExe = $cand; break }
        } catch { }
    }
}

if (-not $PyExe) {
    Write-Host "错误：找不到 Python 3.8 或更高版本。" -ForegroundColor Red
    Write-Host "      本项目全部功能依赖 Python，请先安装：https://www.python.org/downloads/" -ForegroundColor Red
    Write-Host "      安装时记得勾选 'Add Python to PATH'。" -ForegroundColor Red
    exit 1
}

$pyVer = & $PyExe --version 2>&1
Write-Host "Python  ：$pyVer"
Write-Host "源目录  ：$Src"

# ---- 2. 确定安装位置 --------------------------------------------------------
if ([string]::IsNullOrWhiteSpace($Target)) {
    $Target = Join-Path $env:USERPROFILE ".workbuddy\skills\$Name"
}
Write-Host "安装到  ：$Target"

$srcFull = [System.IO.Path]::GetFullPath($Src).TrimEnd('\')
$dstFull = [System.IO.Path]::GetFullPath($Target).TrimEnd('\')
if ($srcFull -eq $dstFull) {
    Write-Host "提示：源目录与目标目录相同，无需安装。"
    exit 0
}

if (Test-Path $Target) {
    Write-Host ""
    Write-Host "目标已存在：$Target" -ForegroundColor Yellow
    $ans = Read-Host "覆盖它吗？已有的改动会丢失（建议先备份）[y/N]"
    if ($ans -notmatch '^(y|yes|Y|YES)$') {
        Write-Host "已取消，未做任何改动。"
        exit 0
    }
    Remove-Item -LiteralPath $Target -Recurse -Force
}

$parent = Split-Path -Parent $Target
if (-not (Test-Path $parent)) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
}

# ---- 3. 软链接或复制 --------------------------------------------------------
if ($Mode -eq "Link") {
    try {
        New-Item -ItemType SymbolicLink -Path $Target -Value $Src -ErrorAction Stop | Out-Null
        Write-Host "已创建软链接。之后在源目录的改动会立即生效。"
    } catch {
        Write-Host "软链接失败（Windows 需开发者模式或管理员权限），改为复制。" -ForegroundColor Yellow
        $Mode = "Copy"
    }
}

if ($Mode -eq "Copy") {
    Copy-Item -LiteralPath $Src -Destination $Target -Recurse -Force
    Write-Host "已复制全部文件。"
}

# ---- 4. 自检 ---------------------------------------------------------------
Write-Host ""
Write-Host "运行自检……"
$check = & $PyExe "$Src\scripts\cli.py" validate 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "自检通过：数据完整，命令行可用。" -ForegroundColor Green
} else {
    Write-Host "自检失败。请手动运行排查：" -ForegroundColor Red
    Write-Host "  $PyExe `"$Src\scripts\cli.py`" validate"
    Write-Host $check
    exit 1
}

# ---- 5. 提示 ---------------------------------------------------------------
Write-Host ""
Write-Host "安装完成。" -ForegroundColor Green
Write-Host ""
Write-Host "在终端里用（不需要任何 Agent）："
Write-Host "  $PyExe `"$Target\scripts\cli.py`" decide --interactive"
Write-Host "  $PyExe `"$Target\scripts\cli.py`" cases --search 粮道"
Write-Host ""
Write-Host "想少敲路径，在 PowerShell 配置文件里加一个函数："
Write-Host "  function shiheng { & `"$PyExe`" `"$Target\scripts\cli.py`" @args }"
Write-Host ""
Write-Host "教程在 $Target\tutorial\ ，从 01-install.md 开始读。"
