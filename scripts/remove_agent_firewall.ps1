param([string]$RuleName = "CENTRAL CUBE Agent TCP")
$ErrorActionPreference = "Stop"
Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue | Remove-NetFirewallRule
Write-Host "CENTRAL CUBE Agent firewall rule removed."
