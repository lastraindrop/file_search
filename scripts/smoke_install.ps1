# FileCortex clean-install 冒烟测试（Windows PowerShell）
# 用法: powershell -ExecutionPolicy Bypass -File scripts\smoke_install.ps1 [dist\file_cortex-*.whl]
# 验证: 全新 venv 安装 → CLI open/stage/export → Web /api/whoami
param(
    [string]$Wheel = ""
)

$ErrorActionPreference = "Stop"

if (-not $Wheel) {
    $Wheel = (Get-ChildItem dist\file_cortex-*.whl -ErrorAction SilentlyContinue | Select-Object -First 1).FullName
}
if (-not $Wheel -or -not (Test-Path $Wheel)) {
    Write-Error "no wheel found; run 'python -m build' first"
    exit 1
}

$Work = Join-Path $env:TEMP ("fctx_smoke_" + [guid]::NewGuid().ToString("N"))
$Venv = Join-Path $Work "venv"
$Proj = Join-Path $Work "project"
New-Item -ItemType Directory -Path $Proj -Force | Out-Null

try {
    Write-Host "==> creating venv"
    python -m venv $Venv
    $Py = Join-Path $Venv "Scripts\python.exe"
    $Pip = Join-Path $Venv "Scripts\pip.exe"

    Write-Host "==> installing $Wheel"
    & $Pip -q install $Wheel

    $env:FCTX_CONFIG_DIR = Join-Path $Work "config"

    Write-Host "==> CLI smoke"
    "hello filecortex" | Set-Content (Join-Path $Proj "a.txt")
    & (Join-Path $Venv "Scripts\fctx.exe") open $Proj | Out-Null
    $stageOut = & (Join-Path $Venv "Scripts\fctx.exe") stage $Proj "a.txt"
    if ($stageOut -notmatch "Staged") { throw "stage failed: $stageOut" }
    Push-Location $Proj
    try {
        & (Join-Path $Venv "Scripts\fctx.exe") export $Proj --format xml --output out.xml | Out-Null
    } finally { Pop-Location }
    if (-not (Select-String -Path (Join-Path $Proj "out.xml") -Pattern "<filecortex>" -Quiet)) {
        throw "export missing root element"
    }
    Write-Host "CLI OK"

    Write-Host "==> Web smoke"
    $port = 8765
    $outLog = Join-Path $Work "web_out.log"
    $errLog = Join-Path $Work "web_err.log"
    $web = Start-Process -FilePath (Join-Path $Venv "Scripts\fctx-web.exe") `
        -ArgumentList "--host 127.0.0.1 --port $port" -PassThru `
        -RedirectStandardOutput $outLog -RedirectStandardError $errLog `
        -WindowStyle Hidden
    try {
        $ok = $false
        $lastErr = ""
        foreach ($i in 1..40) {
            Start-Sleep -Milliseconds 800
            if ($web.HasExited) { break }
            try {
                $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$port/healthz" -UseBasicParsing -TimeoutSec 3
                if ($resp.StatusCode -eq 200 -and $resp.Content -match '"status"\s*:\s*"ok"') { $ok = $true; break }
            } catch { $lastErr = $_.Exception.Message }
        }
        if (-not $ok) {
            $tail = ""
            if (Test-Path $errLog) { $tail = (Get-Content $errLog -Tail 20) -join "`n" }
            throw "web server did not become healthy (last error: $lastErr). server stderr:`n$tail"
        }
    } finally {
        if ($web -and -not $web.HasExited) { Stop-Process -Id $web.Id -Force }
    }
    Write-Host "Web OK"

    Write-Host "SMOKE-OK"
} finally {
    Remove-Item -Recurse -Force $Work -ErrorAction SilentlyContinue
}
