# J.A.R.V.I.S. – Aufräumen vor der Deinstallation (ruft Deinstallieren.exe auf, Windows PowerShell 5.1).
# Entfernt, was das Setup angelegt hat: laufenden Client, seine Verknüpfungen, Windows-MCP samt Schlüssel und
# Firewall-Regel. Seit 25.10.2026 nur noch Eigenes: Windows-MCP nur, wenn das Setup es eingerichtet hat (Vermerk in den
# Einstellungen oder die Firewall-Regel „Jarvis Windows-MCP“), Verknüpfungen nur mit den Namen, die das Setup vergibt.
# Den Jarvis-Ordner (Vorgabe %LOCALAPPDATA%\Jarvis, seit 25.10.2026 wählbar) löscht danach die Deinstallation selbst. Claude Code, Git und uv bleiben (die
# können auch anderes nutzen); den Projektordner %USERPROFILE%\Jarvis löscht sie nur nach Rückfrage.
param([string]$Sprache = '')
$ErrorActionPreference = 'Continue'
# Sprache (seit 0.3.0): -Sprache vom Uninstaller (de oder en), sonst die Sprache von Windows
if (-not $Sprache) { $Sprache = $(if ((Get-UICulture).TwoLetterISOLanguageName -eq 'de') { 'de' } else { 'en' }) }
function T([string]$de, [string]$en) { if ($Sprache -eq 'en') { $en } else { $de } }
$Ziel = Split-Path -Parent $PSScriptRoot       # dieses Skript liegt in <Ordner>\einrichtung
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
$PS = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'

Write-Host (T 'Jarvis wird entfernt ...' 'Removing Jarvis ...') -ForegroundColor Cyan
Get-Process pythonw, python -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$Ziel\*" } | Stop-Process -Force

foreach ($Ordner in 'Startup', 'Desktop') {
  foreach ($Name in 'Jarvis.lnk', 'Jarvis-Einrichtung fortsetzen.lnk', 'Continue Jarvis setup.lnk') {
    $Pfad = Join-Path ([Environment]::GetFolderPath($Ordner)) $Name
    if (Test-Path -LiteralPath $Pfad) { Remove-Item -LiteralPath $Pfad -Force; Write-Host ("   $Name ($Ordner) " + (T 'entfernt' 'removed')) }
  }
}

$VomSetup = $false
try { $VomSetup = [bool](Get-Content (Join-Path $Ziel 'einstellungen.json') -Raw | ConvertFrom-Json).windows_mcp_vom_setup } catch { }
if (Get-NetFirewallRule -DisplayName 'Jarvis Windows-MCP*' -ErrorAction SilentlyContinue) { $VomSetup = $true }   # nur das Setup legt sie an
$McpOrdner = Join-Path $env:USERPROFILE '.windows-mcp'
if (-not $VomSetup -and ((Test-Path $McpOrdner) -or (Get-Command windows-mcp -ErrorAction SilentlyContinue))) {
  Write-Host ('   ' + (T 'Windows-MCP bleibt (nicht von diesem Setup eingerichtet).' 'Windows-MCP stays (not set up by this setup).'))
}
if ($VomSetup -and ((Test-Path $McpOrdner) -or (Get-Command windows-mcp -ErrorAction SilentlyContinue))) {
  # Der Starter windows-mcp.exe startet ein python.exe: beide über die Befehlszeile finden, nicht über den Namen
  Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match 'windows-mcp' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object { $_.TaskName -match 'windows-mcp' } |
    ForEach-Object { Unregister-ScheduledTask -TaskName $_.TaskName -TaskPath $_.TaskPath -Confirm:$false -ErrorAction SilentlyContinue }
  if (Get-Command uv -ErrorAction SilentlyContinue) { uv tool uninstall windows-mcp 2>$null | Out-Null }
  Remove-Item $McpOrdner -Recurse -Force -ErrorAction SilentlyContinue
  Write-Host ('   ' + (T 'Windows-MCP und sein Schlüssel entfernt' 'Windows-MCP and its key removed'))
}
# Die Firewall-Regel unabhängig davon prüfen: Sie kann den Ordner überleben (z. B. nach einem abgebrochenen Setup)
if (Get-NetFirewallRule -DisplayName 'Jarvis Windows-MCP*' -ErrorAction SilentlyContinue) {
  try {
    Write-Host ('   ' + (T 'Windows fragt einmal nach Administratorrechten (Firewall-Regel entfernen).' 'Windows asks once for administrator rights (removing the firewall rule).'))
    $Kodiert = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes(
      "Remove-NetFirewallRule -DisplayName 'Jarvis Windows-MCP*' -ErrorAction SilentlyContinue"))
    Start-Process $PS -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList "-NoProfile -EncodedCommand $Kodiert"
  } catch { }
  if (Get-NetFirewallRule -DisplayName 'Jarvis Windows-MCP*' -ErrorAction SilentlyContinue) {
    Write-Host ('   ' + (T 'Firewall-Regel blieb (Administratorrechte abgelehnt). Entfernen: Windows Defender Firewall, eingehende Regel „Jarvis Windows-MCP“.' 'Firewall rule kept (administrator rights declined). Remove it: Windows Defender Firewall, inbound rule “Jarvis Windows-MCP”.')) -ForegroundColor Yellow
  } else { Write-Host ('   ' + (T 'Firewall-Regel entfernt' 'Firewall rule removed')) }
}
Write-Host (T 'Fertig.' 'Done.') -ForegroundColor Green
Start-Sleep -Seconds 2
