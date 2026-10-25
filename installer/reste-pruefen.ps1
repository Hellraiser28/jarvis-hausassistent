# Jarvis-Reste pruefen (nur lesen, aendert nichts). Nach dem Aufraeumen ausfuehren:
#   powershell -ExecutionPolicy Bypass -NoProfile -Command "irm <adresse>/reste-pruefen.ps1 | iex"
# Listet, was von einer Jarvis-Installation noch da ist: Ordner, Verknuepfungen, Aufgaben, Firewall-Regeln, Dienste,
# Prozesse, PATH-Eintraege, Programme. Bewusst nur ASCII (irm | iex kennt keine BOM).
# Getrennt davon "bewusst geblieben": Claude Code, uv, Git und Tailscale nimmt die Deinstallation absichtlich nicht mit
# (die koennen auch anderes nutzen). Sie zaehlen nicht als Rest, sonst kaeme nie "SAUBER" (Pruefung 24.10.2026).
# Sprache (seit 0.3.0): Deutsch auf deutschem Windows, sonst Englisch
$EN = (Get-UICulture).TwoLetterISOLanguageName -ne 'de'
function T([string]$de, [string]$en) { if ($EN) { $en } else { $de } }
$Funde = New-Object System.Collections.Generic.List[string]
$Geblieben = New-Object System.Collections.Generic.List[string]
function Fund($t) { $Funde.Add($t) }
function Geblieben($t) { $Geblieben.Add($t) }

$Ordner = @(
  (Join-Path $env:USERPROFILE 'Jarvis'),
  (Join-Path $env:LOCALAPPDATA 'Jarvis'),
  (Join-Path $env:USERPROFILE '.windows-mcp'),
  (Join-Path $env:USERPROFILE '.local\bin\windows-mcp.exe')
)
# Der Ordner ist seit 25.10.2026 im Setup waehlbar: steht die Installation noch in der Registry, auch dort nachsehen
$Reg = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Jarvis' -ErrorAction SilentlyContinue
if ($Reg -and $Reg.InstallLocation -and ($Ordner -notcontains $Reg.InstallLocation)) { $Ordner += $Reg.InstallLocation }
foreach ($o in $Ordner) { if (Test-Path -LiteralPath $o) { Fund ((T 'Datei/Ordner' 'File/folder') + ": $o") } }
# Ein selbst gebauter Jarvis (Weg "neu") legt oft weitere Ordner im Profil an, z. B. JarvisGehirn, Jarvis-Sicherung
# (Laptop-Test 25.10.2026): alles auf oberster Ebene, was Jarvis im Namen hat
Get-ChildItem $env:USERPROFILE -Filter '*Jarvis*' -Force -ErrorAction SilentlyContinue |
  Where-Object { $Ordner -notcontains $_.FullName } | ForEach-Object { Fund ((T 'Datei/Ordner' 'File/folder') + ": $($_.FullName)") }
$Werkzeuge = @(
  (Join-Path $env:USERPROFILE '.claude'),
  (Join-Path $env:USERPROFILE '.claude.json'),
  (Join-Path $env:USERPROFILE '.local\bin\claude.exe'),
  (Join-Path $env:USERPROFILE '.local\share\claude'),
  (Join-Path $env:USERPROFILE '.local\bin\uv.exe'),
  (Join-Path $env:APPDATA 'uv'),
  (Join-Path $env:LOCALAPPDATA 'uv'),
  (Join-Path $env:ProgramFiles 'Tailscale')
)
foreach ($o in $Werkzeuge) { if (Test-Path -LiteralPath $o) { Geblieben ((T 'Datei/Ordner' 'File/folder') + ": $o") } }

foreach ($Art in 'Startup', 'Desktop', 'Programs') {
  $Pfad = [Environment]::GetFolderPath($Art)
  if ($Pfad -and (Test-Path $Pfad)) {
    Get-ChildItem $Pfad -Filter '*Jarvis*' -Recurse -ErrorAction SilentlyContinue | ForEach-Object { Fund ((T 'Verknuepfung' 'Shortcut') + ": $($_.FullName)") }
  }
}

Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object { $_.TaskName -match 'jarvis|windows-mcp' -or $_.TaskPath -match 'jarvis' } |
  ForEach-Object { Fund ((T 'Aufgabe' 'Task') + ": $($_.TaskPath)$($_.TaskName)") }

# Get-NetFirewallRule liefert ohne Adminrechte womoeglich nichts (Laptop-Test 25.10.2026), netsh geht immer.
# Gewertet wird nur die Zeile mit dem Regelnamen (deutsches oder englisches Windows).
$Regeln = @(Get-NetFirewallRule -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -match 'jarvis|windows-mcp' } |
  ForEach-Object { $_.DisplayName })
$Regeln += @(netsh advfirewall firewall show rule name=all 2>$null | Where-Object { $_ -match '^\s*(Rule Name|Regelname)\s*:\s*.*(jarvis|windows-mcp)' } |
  ForEach-Object { ($_ -split ':', 2)[1].Trim() })
$Regeln | Sort-Object -Unique | ForEach-Object { Fund ((T 'Firewall-Regel' 'Firewall rule') + ": $_") }
Get-NetFirewallRule -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -match 'tailscale' } |
  ForEach-Object { Geblieben ((T 'Firewall-Regel' 'Firewall rule') + ": $($_.DisplayName)") }

Get-Service -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'jarvis' -or $_.DisplayName -match 'jarvis' } |
  ForEach-Object { Fund ((T 'Dienst' 'Service') + ": $($_.DisplayName) ($($_.Status))") }
Get-Service -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'tailscale' -or $_.DisplayName -match 'tailscale' } |
  ForEach-Object { Geblieben ((T 'Dienst' 'Service') + ": $($_.DisplayName) ($($_.Status))") }

# Nach Programmen suchen, nicht nach dem Wort "jarvis": sonst meldet sich die Shell, die dieses Skript gestartet hat
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -match 'jarvis_pc\.py|windows-mcp' -and $_.ProcessId -ne $PID } |
  ForEach-Object { Fund ((T 'Prozess' 'Process') + ": $($_.Name) (PID $($_.ProcessId))") }
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -eq 'claude.exe' } |
  ForEach-Object { Geblieben ((T 'Prozess' 'Process') + ": claude.exe (PID $($_.ProcessId))") }

foreach ($Bereich in 'User', 'Machine') {
  ([Environment]::GetEnvironmentVariable('Path', $Bereich) -split ';') | Where-Object { $_ -match 'jarvis' } |
    ForEach-Object { Fund "PATH ($Bereich): $_" }
}

$Uninst = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall', 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall',
          'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'
foreach ($u in $Uninst) {
  Get-ChildItem $u -ErrorAction SilentlyContinue | ForEach-Object { Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue } |
    ForEach-Object {
      if ($_.DisplayName -match 'jarvis') { Fund ((T 'Programm' 'Program') + ": $($_.DisplayName)") }
      elseif ($_.DisplayName -match 'tailscale|^uv$|^Python 3\.1[24].*\(uv\)') { Geblieben ((T 'Programm' 'Program') + ": $($_.DisplayName)") }
    }
}

if ($env:OneDrive -and (Test-Path $env:OneDrive)) {
  Get-ChildItem $env:OneDrive -Filter '*Jarvis*' -Recurse -Depth 3 -ErrorAction SilentlyContinue |
    ForEach-Object { Fund "OneDrive: $($_.FullName)" }
}

Write-Host ''
if ($Geblieben.Count -gt 0) {
  Write-Host ('   ' + (T 'Bewusst geblieben (nicht von Jarvis allein genutzt, bei Bedarf selbst deinstallieren):' 'Kept on purpose (not used by Jarvis alone, uninstall yourself if needed):')) -ForegroundColor Cyan
  $Geblieben | ForEach-Object { Write-Host "   - $_" }
  Write-Host ''
}
if ($Funde.Count -eq 0) {
  Write-Host ('   ' + (T 'SAUBER: keine Jarvis-Reste gefunden.' 'CLEAN: no Jarvis leftovers found.')) -ForegroundColor Green
} else {
  Write-Host ("   $($Funde.Count) " + (T 'Reste gefunden:' 'leftovers found:')) -ForegroundColor Yellow
  $Funde | ForEach-Object { Write-Host "   - $_" }
}
Write-Host ''
