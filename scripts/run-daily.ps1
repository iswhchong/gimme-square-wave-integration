# Gimme daily automation.
# 1) Post YESTERDAY's Square sales to Wave (idempotent one-shot).
# 2) Post YESTERDAY's Square payout(s) to Wave (idempotent one-shot).
# 3) Export the same day's transactions to Google Sheets.
# Scheduled via Windows Task Scheduler at 10:00 daily.
#
# Payout note: the "Transfer from Square - A/R" leg can't be created via Wave's
# API, so the transfer amount posts to a SUSPENSE account (config
# PAYOUT_ACCOUNTS['suspense'], default Tee Time). After the run, open the posted
# payout in Wave, re-point that one suspense line to "Transfer from Square -
# Account Receivable", and set the actual settlement date. Fees + GST are final.
# Idempotent: retries never double-post (per-payout SQ_PAYOUT_<id> key).

$repo = "C:\dev\gimme-apps\gimme-square-wave-integration"
Set-Location $repo
$py   = Join-Path $repo ".venv\Scripts\python.exe"
$date = (Get-Date).AddDays(-1).ToString("yyyy-MM-dd")   # yesterday, local (Edmonton)

New-Item -ItemType Directory -Force -Path (Join-Path $repo "logs") | Out-Null
$stamp   = (Get-Date).ToString("yyyyMMdd_HHmmss")
$wrapLog = Join-Path $repo "logs\daily_$stamp.log"
Start-Transcript -Path $wrapLog -Append | Out-Null

Write-Host "=== Gimme daily run for $date ==="

Write-Host "--- 1/3 Posting sales to Wave (force one-shot) ---"
& $py main.py --date $date --force-oneshot
$salesExit = $LASTEXITCODE
Write-Host "main.py exit code: $salesExit"

Write-Host "--- 2/3 Posting payout(s) to Wave (force one-shot) ---"
& $py payouts.py --date $date --force-oneshot
$payoutExit = $LASTEXITCODE
Write-Host "payouts.py exit code: $payoutExit"

Write-Host "--- 3/3 Exporting to Google Sheets ---"
& $py square_to_sheets.py --date $date --end-date $date
$sheetsExit = $LASTEXITCODE
Write-Host "square_to_sheets.py exit code: $sheetsExit"

Stop-Transcript | Out-Null

if ($salesExit -ne 0 -or $payoutExit -ne 0 -or $sheetsExit -ne 0) { exit 1 } else { exit 0 }
