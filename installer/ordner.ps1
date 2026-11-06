# J.A.R.V.I.S. - Ordner pruefen und absichern (seit 0.7.0, Claude Security F4). Windows PowerShell 5.1, ohne Adminrechte.
# Aufruf: ordner.ps1 -Ordner <Pfad> [-NurPruefen]
#   Das Setup startet es aus seinem eigenen Temp-Ordner, BEVOR es etwas in den Ordner schreibt; einrichten.ps1 ruft
#   dieselbe Pruefung noch einmal auf. Nur ASCII, damit PowerShell 5.1 es ohne BOM richtig liest.
# Ausserhalb von %LOCALAPPDATA% wird ein vorhandener Ordner nur uebernommen, wenn er samt Inhalt diesem Konto (oder
# SYSTEM/Administratoren) gehoert, kein anderes Konto eigene (explizite) Rechte darauf hat und nichts darin eine
# Verknuepfung (Junction/Symlink) ist. Sonst koennte ein anderes Konto vorher einen Ordner mit "Jeder: Vollzugriff" oder
# eine eigene pythonw.exe angelegt haben und danach das Token lesen oder Code als dieses Konto starten.
# Absichern: alle expliziten Rechte darunter zuruecksetzen, dann am Ordner Vererbung aus und Vollzugriff nur fuer dieses
# Konto, SYSTEM und Administratoren (geschuetzte DACL, Unterordner erben sie). Danach wird noch einmal geprueft.
# Rueckgabe: 0 = in Ordnung (und abgesichert), 2 = fremder Ordner (abgelehnt), 3 = Rechte liessen sich nicht setzen.
param([Parameter(Mandatory = $true)][string]$Ordner, [switch]$NurPruefen)

$ErrorActionPreference = 'Stop'
$Ich = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$Erlaubt = @($Ich, 'S-1-5-18', 'S-1-5-32-544')
$Icacls = Join-Path $env:SystemRoot 'System32\icacls.exe'
$Ordner = [System.IO.Path]::GetFullPath($Ordner.TrimEnd('\'))
$ImProfil = ($Ordner + '\').StartsWith($env:LOCALAPPDATA.TrimEnd('\') + '\', [System.StringComparison]::OrdinalIgnoreCase)

function Fremd([string]$Pfad) {
  # Grund als Text, wenn $Pfad (oder etwas darin) nicht nur diesem Konto, SYSTEM oder den Administratoren gehoert
  $Liste = @(Get-Item -LiteralPath $Pfad -Force)
  if ($Liste[0].PSIsContainer) { $Liste += @(Get-ChildItem -LiteralPath $Pfad -Recurse -Force -ErrorAction Stop) }
  foreach ($E in $Liste) {
    if ($E.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { return "Verknuepfung: $($E.FullName)" }
    $Acl = Get-Acl -LiteralPath $E.FullName
    $Besitzer = $Acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value
    if ($Erlaubt -notcontains $Besitzer) { return "Besitzer $Besitzer`: $($E.FullName)" }
    foreach ($R in $Acl.GetAccessRules($true, $false, [System.Security.Principal.SecurityIdentifier])) {
      if ($Erlaubt -notcontains $R.IdentityReference.Value) { return "Recht fuer $($R.IdentityReference.Value): $($E.FullName)" }
    }
  }
  return $null
}

try {
  $Neu = -not (Test-Path -LiteralPath $Ordner)
  if (-not $Neu -and -not $ImProfil) {
    $Grund = Fremd $Ordner
    if ($Grund) { Write-Output "ABGELEHNT $Grund"; exit 2 }
  }
  if ($NurPruefen) { Write-Output 'OK geprueft'; exit 0 }
  if ($Neu) { New-Item -ItemType Directory -Force -Path $Ordner | Out-Null }
  # 1. Explizite Rechte darunter weg, alles erbt wieder (auch Unterordner mit eigener, geschuetzter DACL)
  if (@(Get-ChildItem -LiteralPath $Ordner -Force).Count -gt 0) {
    & $Icacls (Join-Path $Ordner '*') /reset /T /C /Q | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "icacls /reset Code $LASTEXITCODE" }
  }
  # 2. Am Ordner selbst: nichts erben, nur diese drei (ersetzt die ganze DACL, Unterordner erben sie)
  & $Icacls $Ordner /reset /Q | Out-Null
  & $Icacls $Ordner /inheritance:r /grant:r "*${Ich}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' /Q | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "icacls /grant Code $LASTEXITCODE" }
  # 3. Besitzer: der eigene Ordner gehoert danach diesem Konto (SYSTEM/Administratoren bleiben, die duerfen ohnehin alles)
  $Besitzer = (Get-Acl -LiteralPath $Ordner).GetOwner([System.Security.Principal.SecurityIdentifier]).Value
  if ($Erlaubt -notcontains $Besitzer) {
    & $Icacls $Ordner /setowner "*$Ich" /Q | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "icacls /setowner Code $LASTEXITCODE" }
  }
  # 4. Nachpruefen: die DACL ist geschuetzt und hat nur die drei Eintraege, und nichts Fremdes ist dazwischen entstanden
  $Acl = Get-Acl -LiteralPath $Ordner
  $Sids = @($Acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]) | ForEach-Object { $_.IdentityReference.Value })
  if (-not $Acl.AreAccessRulesProtected -or @($Sids | Where-Object { $Erlaubt -notcontains $_ }).Count -gt 0) {
    throw 'DACL nach dem Absichern nicht wie erwartet'
  }
  if (-not $ImProfil) {
    $Grund = Fremd $Ordner
    if ($Grund) { Write-Output "ABGELEHNT nach dem Absichern: $Grund"; exit 2 }
  }
  Write-Output 'OK abgesichert'
  exit 0
} catch {
  Write-Output ("FEHLER " + $_.Exception.Message)
  exit 3
}
