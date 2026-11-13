param(
    [ValidateRange(1,65535)][int]$Port = 9443,
    [string]$RemoteAddress = "LocalSubnet",
    [string]$RuleName = "CENTRAL CUBE Agent TCP"
)
$ErrorActionPreference = "Stop"
if (-not (Get-Command New-NetFirewallRule -ErrorAction SilentlyContinue)) {
    throw "Windows Defender Firewall cmdlets are unavailable. Run this script in elevated PowerShell."
}
New-NetFirewallRule -DisplayName $RuleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -RemoteAddress $RemoteAddress -Profile Domain,Private -EdgeTraversalPolicy Block -Enabled True | Out-Null
Write-Host "Created inbound TCP $Port rule for remote address '$RemoteAddress' on Domain/Private profiles only. Public profile remains blocked."
