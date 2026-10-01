# westock 安装脚本（Windows PowerShell，随技能包提供，可先审阅再执行）
#
# 用法:
#   .\setup.ps1                          # 装到 ~\.local\bin，版本取 latest.txt
#   .\setup.ps1 -Bindir "C:\tools" -Version v1.2.3
#   .\setup.ps1 -Help
#
# 参数（全部可选，均有默认值）:
#   -Bindir  安装目录        (默认 $env:USERPROFILE\.local\bin)
#   -Version 指定版本        (默认 latest.txt)
#   -Base    远程基址 URL    (默认脚本所在目录，本地安装)
#   -DryRun  只打印不执行
#   -Yes     跳过确认
#   -Help    显示帮助
[CmdletBinding()]
param(
  [string]$Bindir = "$env:USERPROFILE\.local\bin",
  [string]$Version = "",
  [string]$Base = "",
  [switch]$DryRun,
  [switch]$Yes,
  [switch]$Help
)

$ErrorActionPreference = "Stop"

$BinName = "westock.exe"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$CliBaseDefault = ""
if ([string]::IsNullOrEmpty($Base)) {
  $Base = if ($CliBaseDefault -match "^https?://") { $CliBaseDefault } else { $ScriptDir }
}
if (-not $PSBoundParameters.ContainsKey('Bindir') -and $env:WESTOCK_INSTALL_DIR) {
  $Bindir = $env:WESTOCK_INSTALL_DIR
}
if ([string]::IsNullOrWhiteSpace($Bindir)) { throw "安装目录不能为空" }

# 发布时注入的「SHA256.txt 清单文件」自身哈希（信任根，独立于 CDN）。
# 校验链：脚本内固定哈希 → 校验 SHA256.txt 未被篡改 → SHA256.txt 校验二进制。
$PinnedManifestSha256 = "f219523ed73ddd282a819423e1841ede1258d5c7ad8e773fb0ace8b7e22dabb5"

# 是否配置了 pinned 信任根（哨兵用拼接构造，避免发布期替换破坏比较基准）。
function Test-Pinned {
  $sentinel = "__PINNED_" + "MANIFEST_SHA256__"
  return (-not [string]::IsNullOrEmpty($PinnedManifestSha256)) -and ($PinnedManifestSha256 -ne $sentinel)
}

function Write-Info  { Write-Host $args }
function Write-Green { param([string]$Msg) Write-Host "✅ $Msg" -ForegroundColor Green }
function Write-Warn  { param([string]$Msg) Write-Host "⚠️  $Msg" -ForegroundColor Yellow }
function Write-Err   { param([string]$Msg) Write-Host "❌ $Msg" -ForegroundColor Red }

if ($Help) {
  Get-Help $MyInvocation.MyCommand.Path
  exit 0
}

# ---- 版本解析 ----
if ([string]::IsNullOrEmpty($Version)) {
  $latestFile = if ($Base -notmatch '^https?://') { Join-Path $Base "latest.txt" } else { $null }
  if ($Base -match '^https?://') {
    $Version = ([string](Invoke-WebRequest -Uri "$($Base.TrimEnd('/'))/latest.txt" -UseBasicParsing).Content).Trim()
  } elseif (Test-Path -LiteralPath $latestFile) {
    $Version = (Get-Content -LiteralPath $latestFile -Raw).Trim()
  } else {
    # 本地模式（bundled 渠道无网、无 latest.txt）：枚举 v* 目录取最新 tag
    $tag = Get-ChildItem -Directory -Path $Base -Filter "v*" |
      Where-Object { $_.Name -match '^v\d+\.\d+\.\d+' } |
      Sort-Object { [version]($_.Name -replace '^v', '') } -Descending |
      Select-Object -First 1
    if ($null -eq $tag) {
      Write-Err "未找到 latest.txt，且目录下无可用 v* 版本目录，请用 -Version 指定版本"
      exit 1
    }
    $Version = $tag.Name
  }
}
if (-not $Version.StartsWith("v")) { $Version = "v$Version" }
if ($Version -notmatch '^v\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$') {
  throw "版本格式无效，必须为 vX.Y.Z 或带合法版本后缀"
}
$NativeArch = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
if ($env:OS -ne 'Windows_NT' -or $NativeArch -ne 'AMD64') {
  throw "随包 Windows 二进制仅支持 amd64，请勿使用 ARM64 或非 Windows 环境"
}

$artifact = "westock-windows-amd64.exe"
$relative = "$Version/$artifact"
$dest = Join-Path $Bindir $BinName

Write-Info "将安装: $BinName $Version"
Write-Info "  源:   $Base/$relative"
Write-Info "  目标: $dest"
if ($DryRun) {
  Write-Info "(dry-run) 未做任何改动"
  exit 0
}

# ---- 确认 ----
if (-not $Yes) {
  $reply = Read-Host "确认安装? [Y/n]"
  if ($reply -match '^[Nn]$') {
    Write-Warn "已取消"
    exit 0
  }
}

# ---- 下载/拷贝 ----
$tmp = Join-Path $env:TEMP ("westock-install-" + [guid]::NewGuid().ToString())
try {
  if ($Base -match "^https?://") {
    $url = "$Base/$relative"
    Write-Info "⬇️  $url"
    Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing
  } else {
    $src = Join-Path $Base $relative
    if (-not (Test-Path $src)) { Write-Err "找不到二进制: $src"; exit 1 }
    Copy-Item -Force $src $tmp
  }

  # ---- 校验 ----
  $manifestText = $null
  if ($Base -match "^https?://") {
    try {
      $manifestText = (Invoke-WebRequest -Uri "$Base/$Version/SHA256.txt" -UseBasicParsing).Content
    } catch {
      if (Test-Pinned) { Write-Err "无法下载 SHA256.txt，且已配置固定校验值，拒绝安装"; exit 1 }
      Write-Warn "未找到 SHA256.txt，跳过校验"
    }
  } else {
    $checksumPath = Join-Path $Base "$Version/SHA256.txt"
    if (Test-Path $checksumPath) {
      $manifestText = Get-Content $checksumPath -Raw
    } else {
      if (Test-Pinned) { Write-Err "未找到 SHA256.txt，且已配置固定校验值，拒绝安装"; exit 1 }
      Write-Warn "未找到 SHA256.txt，跳过校验"
    }
  }

  # 信任根校验：先确认 SHA256.txt 清单本身未被篡改（独立于 CDN 的固定哈希）。
  if ((Test-Pinned) -and $null -ne $manifestText) {
    $manifestBytes = [System.Text.Encoding]::UTF8.GetBytes($manifestText)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
      $manifestActual = ([BitConverter]::ToString($sha.ComputeHash($manifestBytes))).Replace("-", "").ToLower()
    } finally {
      $sha.Dispose()
    }
    if ($manifestActual -ne $PinnedManifestSha256.ToLower()) {
      Write-Err "SHA256.txt 清单校验失败（疑似 CDN 被篡改），拒绝安装"
      Write-Err "  期望: $PinnedManifestSha256"
      Write-Err "  实际: $manifestActual"
      exit 1
    }
  }

  $lines = if ($null -ne $manifestText) { $manifestText -split "`n" } else { @() }
  $expected = $null
  foreach ($line in $lines) {
    if ($line -match "^([0-9a-fA-F]{64})\s+(.+)$" -and $Matches[2].Trim() -eq $artifact) {
      $expected = $Matches[1].ToLower()
      break
    }
  }
  if (-not $expected) { throw "SHA256.txt 中未找到 $artifact，拒绝安装" }
  $actual = (Get-FileHash -Path $tmp -Algorithm SHA256).Hash.ToLower()
  if ($actual -ne $expected) {
    throw "SHA256 校验失败: $artifact，拒绝安装"
  }

  New-Item -ItemType Directory -Force -Path $Bindir | Out-Null
  Move-Item -Force $tmp $dest
} finally {
  if (Test-Path $tmp) { Remove-Item -Force $tmp }
}

Write-Green "已安装 → $dest"

if (($env:Path -split ';') -contains $Bindir) {
  Write-Info "PATH 已包含 $Bindir"
} else {
  Write-Info "未修改用户 PATH；可直接使用 $dest，或确认后手动将安装目录加入 PATH。"
}
