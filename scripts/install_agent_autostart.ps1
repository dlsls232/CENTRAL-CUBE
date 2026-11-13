param(
    [Parameter(Mandatory=$true)][string]$AgentExe,
    [Parameter(Mandatory=$true)][string]$AgentArguments,
    [string]$TaskName = "CENTRAL CUBE Agent"
)
$ErrorActionPreference = "Stop"
$resolved = (Resolve-Path -LiteralPath $AgentExe).Path
if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) { throw "Agent EXE not found: $resolved" }
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $resolved -Argument $AgentArguments
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Days 0)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "CENTRAL CUBE mTLS remote management agent" -Force | Out-Null
Write-Host "Agent scheduled task installed for $user. Review the task arguments and protect certificate/key ACLs."
