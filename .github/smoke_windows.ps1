param(
    [Parameter(Mandatory = $true)]
    [string] $ExePath
)

$ErrorActionPreference = 'Stop'
$exe = (Resolve-Path $ExePath).Path
$work = Join-Path $env:RUNNER_TEMP ([System.IO.Path]::GetRandomFileName())
New-Item -ItemType Directory -Path $work | Out-Null
$stdout = Join-Path $work 'yams.stdout.log'
$stderr = Join-Path $work 'yams.stderr.log'
$ready = $false
$appProcess = Start-Process -FilePath $exe -WorkingDirectory $work -PassThru `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr

try {
    for ($i = 0; $i -lt 120; $i++) {
        Start-Sleep -Seconds 1
        $appProcess.Refresh()
        if ($appProcess.HasExited) {
            throw "YAMS exited before serving its UI (exit code $($appProcess.ExitCode))"
        }
        try {
            $response = Invoke-WebRequest -Uri 'http://127.0.0.1:7860/' -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                $ready = $true
                break
            }
        } catch {}
    }
    if (-not $ready) { throw 'Timed out waiting for YAMS to serve its UI' }
    Write-Host "YAMS served its UI from $exe"
} finally {
    $appProcess.Refresh()
    if (-not $appProcess.HasExited) { Stop-Process -Id $appProcess.Id -Force }
    if (-not $ready) {
        Get-Content $stdout -ErrorAction SilentlyContinue
        Get-Content $stderr -ErrorAction SilentlyContinue
    }
}
