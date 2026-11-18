# Echo 本地开发环境一键启动
# 双击 launch-echo.cmd 运行；VM 本身由 Hyper-V 自动启动，不在本脚本范围内

param()

$ErrorActionPreference = "Continue"
$Root = "F:\project_work\AI_Chat"
$Backend = Join-Path $Root "Echo-backend"
$Bootstrap = "F:\project_work\echo_computer\vm-bootstrap"
$DbUrlFile = "C:\Users\leafwind\AppData\Local\Temp\echo_local_db_url.txt"
$LogFile = Join-Path $Root "launch.log"

function Write-Step([string]$Message) {
    $line = "{0} {1}" -f (Get-Date -Format "HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

Write-Step "=== Echo 本地环境启动 ==="

# 0. VM 状态（Hyper-V 自动启动；这里只检查并提示，不需要管理员）
$vmProcess = Get-Process -Name "vmwp" -ErrorAction SilentlyContinue
if ($vmProcess) {
    Write-Step "EchoComputer VM 在运行"
} else {
    Write-Step "EchoComputer VM 未运行（Hyper-V 开机自动启动应已配置；未起时请用 Hyper-V 管理器或管理员执行 Start-VM -Name EchoComputer）"
}

# 1. Docker Desktop
$dockerExe = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
if (-not (Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue)) {
    if (Test-Path $dockerExe) {
        Start-Process -FilePath $dockerExe
        Write-Step "Docker Desktop 启动中..."
    } else {
        Write-Step "找不到 Docker Desktop，跳过"
    }
} else {
    Write-Step "Docker Desktop 已在运行"
}

$dockerReady = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 3
    $info = docker info --format "{{.ServerVersion}}" 2>$null
    if ($LASTEXITCODE -eq 0 -and $info) {
        Write-Step "Docker 就绪: $info"
        $dockerReady = $true
        break
    }
}
if (-not $dockerReady) {
    Write-Step "Docker 未就绪，后续步骤跳过"
}

# 2. 本地数据库
if ($dockerReady) {
    docker start echo-local-pg 2>&1 | Out-Null
    for ($i = 0; $i -lt 15; $i++) {
        Start-Sleep -Seconds 2
        $conn = Test-NetConnection -ComputerName 127.0.0.1 -Port 5433 -WarningAction SilentlyContinue
        if ($conn.TcpTestSucceeded) {
            Write-Step "PostgreSQL 5433 就绪"
            break
        }
    }
}

# 3. 本地后端
$backendListening = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($backendListening) {
    Write-Step "本地后端已在运行（8000）"
} else {
    $dbUrl = ""
    if (Test-Path $DbUrlFile) {
        $dbUrl = (Get-Content -Path $DbUrlFile -Raw).Trim()
    }
    if (-not $dbUrl) {
        Write-Step "缺少本地数据库连接串，跳过本地后端"
    } else {
        $env:DATABASE_URL = $dbUrl
        $env:PRESENCE_ENABLED = "false"
        $env:PROACTIVE_CHAT_ENABLED = "true"
        $env:DAILY_LETTER_ENABLED = "false"
        $env:PUSH_ENABLED = "true"
        Start-Process -FilePath "python" `
            -ArgumentList "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000" `
            -WorkingDirectory $Backend `
            -WindowStyle Hidden
        Write-Step "本地后端启动中..."
    }
}

# 4. 8899 下载服务（VM 更新 agent/bridge 时用）
$downloadListening = Get-NetTCPConnection -LocalPort 8899 -State Listen -ErrorAction SilentlyContinue
if ($downloadListening) {
    Write-Step "8899 文件服务已在运行"
} else {
    Start-Process -FilePath "python" `
        -ArgumentList "-m", "http.server", "8899", "--bind", "0.0.0.0", "--directory", $Bootstrap `
        -WindowStyle Hidden
    Write-Step "8899 文件服务启动"
}

# 5. 健康检查
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 2
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health/ready" -TimeoutSec 3
        Write-Step "本地后端就绪: $($health.status)/$($health.database)"
        break
    } catch {
        # 后端还没起来，继续等
    }
}

Write-Step "=== 完成（VM 由 Hyper-V 自动启动）==="
Write-Host ""
Write-Host "VM 说明："
Write-Host "  - EchoComputer 已配置开机自动启动（Hyper-V）"
Write-Host "  - VM 内 agent / 微信 / 微信桥 由计划任务在登录后自动启动"
Write-Host "  - 若 VM 没起来，请在 Hyper-V 管理器手动启动，或运行："
Write-Host "      Start-VM -Name EchoComputer"
Write-Host ""
