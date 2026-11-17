<#
.SYNOPSIS
    切换 Echo Desktop 连接的服务器（本地 / 生产）。

.DESCRIPTION
    配置文件位置：%APPDATA%\EchoDesktop\config.json
    切换时会自动把当前配置存成 config.local.json 或 config.production.json，
    然后写入目标配置并启动客户端。

.EXAMPLE
    .\switch-server.ps1 status       # 只看当前连的是哪台
    .\switch-server.ps1 prod         # 切到生产并打开客户端窗口
    .\switch-server.ps1 local -NoGui # 切回本地，后台运行（无窗口）
    .\switch-server.ps1 stop         # 停掉正在运行的桌面客户端
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet("status", "prod", "local", "stop")]
    [string]$Target = "status",

    [switch]$NoGui
)

$ErrorActionPreference = "Stop"

$desktopDir = $PSScriptRoot
$repoRoot = Split-Path -Parent $desktopDir
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$dataDir = Join-Path $env:APPDATA "EchoDesktop"
$current = Join-Path $dataDir "config.json"
$prodFile = Join-Path $dataDir "config.production.json"
$localFile = Join-Path $dataDir "config.local.json"
$legacyProd = Join-Path $dataDir "config.production.bak"

function Read-Config([string]$Path) {
    if (-not (Test-Path $Path)) { return $null }
    return Get-Content $Path -Raw | ConvertFrom-Json
}

function Get-ServerKind($Config) {
    if ($null -eq $Config) { return "none" }
    if ($Config.server_url -match "127\.0\.0\.1|localhost") { return "local" }
    return "prod"
}

function Show-Status {
    $config = Read-Config $current
    if ($null -eq $config) {
        Write-Host "当前：未配对（$current 不存在）" -ForegroundColor Yellow
        return
    }
    $kind = Get-ServerKind $config
    $color = if ($kind -eq "prod") { "Green" } else { "Cyan" }
    Write-Host "当前连接：$kind" -ForegroundColor $color
    Write-Host "  server_url : $($config.server_url)"
    Write-Host "  node_id    : $($config.node_id)"
    Write-Host "  node_name  : $($config.node_name)"
    Write-Host "  自动批准   : $($config.auto_approve)"
    Write-Host ""
    foreach ($pair in @(@("生产", $prodFile), @("本地", $localFile))) {
        $saved = Read-Config $pair[1]
        if ($null -ne $saved) {
            Write-Host ("  已保存{0}配置：{1}（节点 {2}）" -f $pair[0], $saved.server_url, $saved.node_id)
        } else {
            Write-Host ("  已保存{0}配置：无" -f $pair[0]) -ForegroundColor DarkGray
        }
    }
}

function Save-Current {
    if (-not (Test-Path $current)) { return }
    $config = Read-Config $current
    $kind = Get-ServerKind $config
    if ($kind -eq "prod") {
        Copy-Item $current $prodFile -Force
    } elseif ($kind -eq "local") {
        Copy-Item $current $localFile -Force
    }
}

function Stop-Desktop {
    Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
        Where-Object { $_.CommandLine -like "*echo_desktop*" } |
        ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
            Write-Host "已停止进程 $($_.ProcessId)"
        }
}

function Start-Client {
    if (-not (Test-Path $python)) {
        throw "找不到 Python：$python"
    }
    $env:PYTHONPATH = $desktopDir

    # client 模式依赖 PySide6；本机没装时自动降级成无界面 run
    $hasGui = $false
    try {
        & $python -c "import PySide6" 2>$null
        $hasGui = ($LASTEXITCODE -eq 0)
    } catch {
        $hasGui = $false
    }

    if ($NoGui -or -not $hasGui) {
        $mode = "run"
        $launchPython = $python
        if (-not $hasGui -and -not $NoGui) {
            Write-Host "未安装 PySide6，自动使用无界面模式（run）" -ForegroundColor Yellow
        }
    } else {
        $mode = "client"
        $windowless = Join-Path (Split-Path $python) "pythonw.exe"
        $launchPython = if (Test-Path $windowless) { $windowless } else { $python }
    }

    Start-Process -FilePath $launchPython `
        -ArgumentList @("-B", "-m", "echo_desktop", $mode) `
        -WorkingDirectory $desktopDir
    Write-Host ("客户端已启动（{0} 模式）" -f $mode) -ForegroundColor Green
}

function Switch-To([string]$File, [string]$Label) {
    if (-not (Test-Path $File)) {
        throw "没有 $Label 配置：$File`n请先配对：`n  cd $desktopDir`n  python -m echo_desktop pair --code <配对码> --server <服务器地址>"
    }
    Stop-Desktop
    Save-Current
    Copy-Item $File $current -Force
    Write-Host ("已切换到{0}" -f $Label) -ForegroundColor Green
    Show-Status
    Start-Client
}

# 首次运行：把历史备份（config.production.bak）迁移成正式的生产配置
if (-not (Test-Path $prodFile) -and (Test-Path $legacyProd)) {
    Copy-Item $legacyProd $prodFile -Force
}

switch ($Target) {
    "status" { Show-Status }
    "stop" { Stop-Desktop; Show-Status }
    "prod" { Switch-To $prodFile "生产（api.echoaiforever.cn）" }
    "local" { Switch-To $localFile "本地（127.0.0.1:8000）" }
}
