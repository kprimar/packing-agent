# Registers a Windows Task Scheduler task that emails a daily outfit recommendation at 8PM.
# Run once: powershell -ExecutionPolicy Bypass .\setup_scheduler.ps1

$taskName  = "PackingAgentDailyOutfit"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$python    = Join-Path $scriptDir ".venv\Scripts\pythonw.exe"
$script    = Join-Path $scriptDir "daily_outfit.py"

if (-not (Test-Path $python)) {
    Write-Error "Python venv not found at $python"
    exit 1
}

$action    = New-ScheduledTaskAction -Execute $python -Argument "`"$script`"" -WorkingDirectory $scriptDir
$trigger   = New-ScheduledTaskTrigger -Daily -At "8:00PM"
$settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Packing Agent: email daily outfit recommendation at 8PM." `
    -Force | Out-Null

Write-Host "Scheduled task '$taskName' registered -- runs daily at 8PM."
Write-Host ""
Write-Host "To test it immediately:"
Write-Host "  Start-ScheduledTask -TaskName '$taskName'"
Write-Host ""
Write-Host "To remove it:"
Write-Host "  Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false"
