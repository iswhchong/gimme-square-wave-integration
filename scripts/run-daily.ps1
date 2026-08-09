# Gimme daily automation (fully automated).
# 1) Post YESTERDAY's Square sales to Wave via the idempotent one-shot path.
# 2) Export the same day's transactions to Google Sheets.
# Scheduled via Windows Task Scheduler at 10:00 daily.
#
# Idempotent: if a run is retried, already-posted entries are skipped (no
# double-posting). The authoritative audit trail is logs\run_*.log and
# logs\posted_ledger.jsonl; this wrapper also keeps its own transcript.

$repo = "C:\dev\gimme-apps\gimme-square-wave-integration"
Set-Location $repo
$py   = Join-Path $repo ".venv\Scripts\python.exe"
$date = (Get-Date).AddDays(-1).ToString("yyyy-MM-dd")   # yesterday, local (Edmonton)

New-Item -ItemType Directory -Force -Path (Join-Path $repo "logs") | Out-Null
$stamp   = (Get-Date).ToString("yyyyMMdd_HHmmss")
$wrapLog = Join-Path $repo "logs\daily_$stamp.log"
Start-Transcript -Path $wrapLog -Append | Out-Null

Write-Host "=== Gimme daily run for $date ==="

Write-Host "--- 1/2 Posting to Wave (force one-shot) ---"
& $py main.py --date $date --force-oneshot
$postExit = $LASTEXITCODE
Write-Host "main.py exit code: $postExit"

Write-Host "--- 2/2 Exporting to Google Sheets ---"
& $py square_to_sheets.py --date $date --end-date $date
$sheetsExit = $LASTEXITCODE
Write-Host "square_to_sheets.py exit code: $sheetsExit"

Stop-Transcript | Out-Null

# Surface any failure to Task Scheduler (non-zero result code).
if ($postExit -ne 0 -or $sheetsExit -ne 0) { exit 1 } else { exit 0 }
