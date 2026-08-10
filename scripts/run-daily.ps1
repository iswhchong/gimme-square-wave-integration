# Gimme daily automation.
# 1) Post Square sales to Wave (idempotent one-shot).
# 2) Post Square payout(s) to Wave (idempotent one-shot).
# 3) Export the day's transactions to Google Sheets.
# Scheduled via Windows Task Scheduler at 10:00 daily (no args -> yesterday).
#
# Optional: pass -Date YYYY-MM-DD to run a specific day instead of yesterday, e.g.
#   .\scripts\run-daily.ps1 -Date 2026-08-07
#
# Payout note: the "Transfer from Square - A/R" leg posts to a SUSPENSE line
# (Uncategorized Income); re-point it in Wave and set the actual settlement date.
# Idempotent: retries never double-post.

param([string]$Date)

$repo = "C:\dev\gimme-apps\gimme-square-wave-integration"
Set-Location $repo
$py   = Join-Path $repo ".venv\Scripts\python.exe"

# Use -Date if given (YYYY-MM-DD), otherwise yesterday in local (Edmonton) time.
if ($Date) {
    if ($Date -notmatch '^\d{4}-\d{2}-\d{2}$') { Write-Error "Date must be YYYY-MM-DD"; exit 2 }
    $day = $Date
} else {
    $day = (Get-Date).AddDays(-1).ToString("yyyy-MM-dd")
}

New-Item -ItemType Directory -Force -Path (Join-Path $repo "logs") | Out-Null
$stamp   = (Get-Date).ToString("yyyyMMdd_HHmmss")
$wrapLog = Join-Path $repo "logs\daily_$stamp.log"
Start-Transcript -Path $wrapLog -Append | Out-Null

Write-Host "=== Gimme daily run for $day ==="

Write-Host "--- 1/3 Posting sales to Wave (force one-shot) ---"
& $py main.py --date $day --force-oneshot
$salesExit = $LASTEXITCODE
Write-Host "main.py exit code: $salesExit"

Write-Host "--- 2/3 Posting payout(s) to Wave (force one-shot) ---"
& $py payouts.py --date $day --force-oneshot
$payoutExit = $LASTEXITCODE
Write-Host "payouts.py exit code: $payoutExit"

Write-Host "--- 3/3 Exporting to Google Sheets ---"
& $py square_to_sheets.py --date $day --end-date $day
$sheetsExit = $LASTEXITCODE
Write-Host "square_to_sheets.py exit code: $sheetsExit"

Stop-Transcript | Out-Null

if ($salesExit -ne 0 -or $payoutExit -ne 0 -or $sheetsExit -ne 0) { exit 1 } else { exit 0 }
