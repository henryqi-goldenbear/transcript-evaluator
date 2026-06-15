param(
  [string]$OpenUrl = "",
  [string]$Python = "python",
  [int]$Port = 3000
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")

function Test-PipelineServer {
  param([int]$Port)
  try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/pipeline-log/health" -UseBasicParsing -TimeoutSec 1
    return ($response.StatusCode -eq 204 -and [string]$response.Headers["Server"] -like "TranscriptEvaluatorPipeline*")
  } catch {
    return $false
  }
}

if (-not (Test-PipelineServer -Port $Port)) {
  $listeners = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique
  foreach ($listenerPid in $listeners) {
    Stop-Process -Id $listenerPid -Force -ErrorAction SilentlyContinue
  }

  Start-Process $Python `
    -ArgumentList "-m", "src.agent1.txt_to_json", "--serve-internal", "$Port" `
    -WorkingDirectory $root `
    -WindowStyle Hidden

  $deadline = (Get-Date).AddSeconds(8)
  while ((Get-Date) -lt $deadline) {
    if (Test-PipelineServer -Port $Port) {
      break
    }
    Start-Sleep -Milliseconds 250
  }
}

if (-not (Test-PipelineServer -Port $Port)) {
  throw "Pipeline server did not start on port $Port."
}

if ($OpenUrl) {
  Start-Process $OpenUrl
}
