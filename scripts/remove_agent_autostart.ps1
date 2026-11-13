param([string]$TaskName = "CENTRAL CUBE Agent")
$ErrorActionPreference = "Stop"
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "Agent scheduled task removed."
