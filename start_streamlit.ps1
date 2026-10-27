param([int]$Port = 8501)

$root = $PSScriptRoot
$health = "http://localhost:$Port/_stcore/health"

function Test-Health {
    try {
        $r = Invoke-WebRequest -Uri $health -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        return ($r.StatusCode -eq 200)
    } catch {
        return $false
    }
}

if (Test-Health) {
    "Streamlit already healthy on http://localhost:$Port"
    exit 0
}

$python = Join-Path $root ".venv\Scripts\python.exe"
$logDir = Join-Path $env:TEMP "jobscout"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stdout = Join-Path $logDir "streamlit-$Port.out.log"
$stderr = Join-Path $logDir "streamlit-$Port.err.log"

$proc = Start-Process -FilePath $python -ArgumentList @("-m", "streamlit", "run", "app.py", "--server.headless", "true", "--server.port", "$Port") -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
"Launched PID $($proc.Id); waiting for health..."

for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 500
    if (Test-Health) {
        "Streamlit healthy on http://localhost:$Port (PID $($proc.Id))"
        "stdout: $stdout"
        "stderr: $stderr"
        exit 0
    }
    $proc.Refresh()
    if ($proc.HasExited) {
        break
    }
}

"Streamlit did not become healthy within 20s."
if (Test-Path $stderr) {
    Get-Content $stderr -Tail 20
}
exit 1
