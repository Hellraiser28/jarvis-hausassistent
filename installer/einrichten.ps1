# J.A.R.V.I.S. – Einrichtung, gestartet von der Jarvis-Setup.exe (Windows PowerShell 5.1, ohne Adminrechte).
# Liest die Antworten aus der INI des Setups (UTF-16) und löscht sie danach (sie kann einen Kopplungscode enthalten).
#   art=verbinden  PC-Client an einen bestehenden Jarvis koppeln: Python-Umgebung, Weckwort, Fenster, optional
#                  PC-Steuerung (Windows-MCP), Autostart und Desktop-Symbol.
#   art=neu        Claude Code installieren, Projektordner %USERPROFILE%\Jarvis mit EINRICHTUNG.md und antworten.json
#                  anlegen und Claude dort die Einrichtung im Gespräch beginnen lassen.
# Erneut ausführen = aktualisieren; Erledigtes wird übersprungen. Rückgabe: 0 = gut, 1 = Fehler.
param([Parameter(Mandatory = $true)][string]$Ini)

$ErrorActionPreference = 'Stop'
# Ordner aus dem eigenen Ort: das Setup legt dieses Skript nach <Ordner>\einrichtung (Ordner seit 25.10.2026 waehlbar)
$Ziel = Split-Path -Parent $PSScriptRoot
$Mitgeliefert = Join-Path $Ziel 'einrichtung'
$Py = Join-Path $Ziel 'venv\Scripts\python.exe'
$PyW = Join-Path $Ziel 'venv\Scripts\pythonw.exe'
$EinstPfad = Join-Path $Ziel 'einstellungen.json'
$Utf8 = New-Object System.Text.UTF8Encoding $false
# Volle Pfade statt PATH-Suche: eine fremde powershell.exe weiter vorn im PATH bekäme sonst Adminrechte
$PS = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
# Lieferkette (Prüfung 24.10.2026): feste Versionen mit Prüfsummen. Stichtag wie in release/pakete_aufloesen.sh,
# nichts, was danach erschienen ist (Zwei-Wochen-Regel), auch nicht bei den Abhängigkeiten von Windows-MCP.
$Stichtag = '2026-10-11T00:00:00Z'
$UvVersion = '0.12.24'
$UvInstallerSha = '05cfb8cca7fb43455b3efe78c9fab72189a97491e9fada5a3fa621f1afb9b3f4'   # laut GitHub-Release
$ModellBasis = 'https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/'
$Modelle = [ordered]@{
  'hey_jarvis_v0.1.onnx' = '94a13cfe60075b132f6a472e7e462e8123ee70861bc3fb58434a73712ee0d2cb'
  'melspectrogram.onnx'  = 'ba2b0e0f8b7b875369a2c89cb13360ff53bac436f2895cced9f479fa65eb176f'
  'embedding_model.onnx' = '70d164290c1d095d1d4ee149bc5e00543250a7316b59f31d056cff7bd3075c1f'
}
# PowerShell 5.1: TLS 1.2 nicht überall Standard (GitHub verlangt es); der Fortschrittsbalken bremst Downloads stark
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
$ProgressPreference = 'SilentlyContinue'

# Sprache (seit 0.3.0): setup_sprache aus der INI (de oder en), gesetzt gleich nach dem Lesen der Antworten
$script:EN = $false
function T([string]$de, [string]$en) { if ($script:EN) { $en } else { $de } }
function Schritt($t) { Write-Host ''; Write-Host ">> $t" -ForegroundColor Cyan }
function Hinweis($t) { Write-Host "   $t" -ForegroundColor Yellow }
function Pruefe($was) { if ($LASTEXITCODE -ne 0) { throw ((T '{0} fehlgeschlagen (Code {1})' '{0} failed (code {1})') -f $was, $LASTEXITCODE) } }
function JaNein($w) { return ($w -eq '1') }
function Zufall() {
  $b = New-Object byte[] 32
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
  return -join ($b | ForEach-Object { '{0:x2}' -f $_ })
}
function Schreibe($Pfad, $Text) { [System.IO.File]::WriteAllText($Pfad, $Text, $Utf8) }
function Hex($Bytes) { return [BitConverter]::ToString($Bytes).Replace('-', '').ToLower() }
# Wie der PC-Client (seit 0.3.0 auch hier): Ein gespeichertes Token geht erst raus, wenn die Gegenstelle mit dem
# Token-Hash beweist, dass sie es kennt. Sonst bekaeme ein fremdes Geraet mit derselben Adresse es geschenkt.
function Bruecke-Echt([string]$Bruecke, [string]$Token) {
  if ($Bruecke -like 'https://*') { return $true }
  $Sha = [System.Security.Cryptography.SHA256]::Create()
  $TH = Hex ($Sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($Token)))
  $Kennung = (Hex ($Sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes("jarvis-kennung:$TH")))).Substring(0, 16)
  $Nonce = Zufall
  try { $R = Invoke-RestMethod -Uri "$Bruecke/v1/gesund?kennung=$Kennung&nonce=$Nonce" -TimeoutSec 10 } catch { return $false }
  $Mac = [System.Security.Cryptography.HMACSHA256]::new([System.Text.Encoding]::UTF8.GetBytes($TH))
  $Soll = Hex ($Mac.ComputeHash([System.Text.Encoding]::UTF8.GetBytes("jarvis-lan:$Nonce")))
  return ([string]$R.beweis -ceq $Soll)
}
# Seit 0.3.2 (Pruefbericht 0.3.1, Fund 1): Bevor der Kopplungscode rausgeht, beweist die Gegenstelle, dass sie ihn
# kennt (HMAC mit PBKDF2 aus Code, Salz und Runden). Ein fremdes Geraet unter der Adresse bekaeme sonst den Code, gaebe
# selbst ein Token aus und bestuende damit jeden spaeteren Brueckenbeweis. Eine Bruecke ohne diesen Beweis (vor 0.3.2)
# wird abgelehnt, sonst muesste ein Faelscher nur so tun, als kenne er ihn nicht.
function Koppel-Beweis([string]$Bruecke, [string]$Code) {
  $Nonce = Zufall
  try { $R = Invoke-RestMethod -Uri "$Bruecke/v1/koppeln/beweis?nonce=$Nonce" -TimeoutSec 15 } catch { return $false }
  $Runden = 0
  if (-not [int]::TryParse([string]$R.runden, [ref]$Runden) -or $Runden -lt 100000 -or $Runden -gt 2000000) { return $false }
  if ([string]$R.salz -cnotmatch '^[0-9a-f]{16,128}$') { return $false }
  $Salz = [byte[]]::new(([string]$R.salz).Length / 2)
  for ($i = 0; $i -lt $Salz.Length; $i++) { $Salz[$i] = [Convert]::ToByte(([string]$R.salz).Substring($i * 2, 2), 16) }
  $Norm = $Code.ToUpper() -creplace '[^A-Z0-9]', ''
  $Kdf = New-Object System.Security.Cryptography.Rfc2898DeriveBytes($Norm, $Salz, $Runden, [System.Security.Cryptography.HashAlgorithmName]::SHA256)
  $Mac = [System.Security.Cryptography.HMACSHA256]::new($Kdf.GetBytes(32))
  $Soll = Hex ($Mac.ComputeHash([System.Text.Encoding]::UTF8.GetBytes("jarvis-koppeln:$Nonce")))
  return ([string]$R.beweis -ceq $Soll)
}
# Werte aus /v1/client nur in ihrer erwarteten Form (seit 0.3.0, Sicherheitspruefung): Ports als Zahl, Sprache de/en,
# Adressen per http(s) auf dem Rechner der Bruecke, sonst kurze Texte
function Client-Wert([string]$k, $v, $BrueckenHost, $BrueckenIp) {
  if ($null -eq $v -or $v -is [bool]) { return $false }
  if ($k -in 'ohr_port', 'stimme_port') { return ("$v" -match '^\d{1,5}$') -and [int]"$v" -gt 0 -and [int]"$v" -lt 65536 }
  if ($k -eq 'sprache') { return ($v -is [string]) -and ($v -cin 'de', 'en') }
  if ($k -in 'hud', 'dateien') {
    $u = $null
    if (-not ($v -is [string]) -or $v.Length -gt 300 -or -not [Uri]::TryCreate($v, [UriKind]::Absolute, [ref]$u)) { return $false }
    if ($u.Scheme -notin 'http', 'https') { return $false }
    if ($u.Host -eq $BrueckenHost -or $u.Host -eq $BrueckenIp) { return $true }
    try { return [bool]([System.Net.Dns]::GetHostAddresses($u.Host) | Where-Object { $_.IPAddressToString -eq $BrueckenIp }) } catch { return $false }
  }
  return ($v -is [string]) -and $v.Trim().Length -gt 0 -and $v.Length -le 40
}

function Lies-Antworten($Pfad) {
  # Get-Content erkennt die UTF-16-Kennung des Setups. Nur key=value, keine Abschnitte nötig.
  $w = @{}
  foreach ($z in Get-Content -LiteralPath $Pfad) {
    if ($z -match '^\s*([A-Za-z_]+)\s*=(.*)$') { $w[$Matches[1]] = $Matches[2].Trim() }
  }
  return $w
}

function Verknuepfung($Ordner, $Datei, $Ziel_, $Argumente, $Arbeitsordner, $Symbol, $Beschreibung) {
  $S = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path ([Environment]::GetFolderPath($Ordner)) $Datei))
  $S.TargetPath = $Ziel_
  $S.Arguments = $Argumente
  $S.WorkingDirectory = $Arbeitsordner
  if ($Symbol) { $S.IconLocation = $Symbol }
  $S.Description = $Beschreibung
  $S.Save()
}

function Pruefsumme($Pfad) { return (Get-FileHash -LiteralPath $Pfad -Algorithm SHA256).Hash.ToLower() }

function Uv-Bereit() {
  $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
  if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    # feste Version, Installer erst nach Prüfsummen-Vergleich ausführen (nicht "irm | iex" auf die jeweils neueste)
    $Datei = Join-Path $env:TEMP "uv-installer-$UvVersion.ps1"
    Invoke-WebRequest -UseBasicParsing -Uri "https://astral.sh/uv/$UvVersion/install.ps1" -OutFile $Datei
    if ((Pruefsumme $Datei) -ne $UvInstallerSha) { Remove-Item -LiteralPath $Datei -Force; throw (T 'Prüfsumme des uv-Installers stimmt nicht' 'Checksum of the uv installer doesn''t match') }
    & $PS -ExecutionPolicy Bypass -NoProfile -File $Datei
    Pruefe 'uv-Installation'
    Remove-Item -LiteralPath $Datei -Force -ErrorAction SilentlyContinue
  }
  uv --version; Pruefe 'uv'
}

# ------------------------------------------------------------------ Weg 1: mit bestehendem Jarvis verbinden
function Verbinden($A) {
  Schritt (T 'Ordner absichern' 'Securing the folder')
  # Seit 25.10.2026 (Pruefbericht): Der Ordner ist waehlbar. Ausserhalb des Benutzerprofils erbt er sonst z. B. von C:\
  # "Authentifizierte Benutzer: Aendern", dann koennten andere Konten das Token lesen oder jarvis_pc.py tauschen.
  # Deshalb Vererbung aus, Vollzugriff nur fuer dieses Konto, SYSTEM und Administratoren.
  try {
    $Ich = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    & (Join-Path $env:SystemRoot 'System32\icacls.exe') $Ziel /inheritance:r /grant:r "*${Ich}:(OI)(CI)F" `
      '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' /Q | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "icacls Code $LASTEXITCODE" }
    Write-Host ("   $Ziel " + (T 'nur für dein Konto (dazu SYSTEM und Administratoren).' 'only for your account (plus SYSTEM and administrators).'))
  } catch {
    Hinweis ((T 'Ordnerrechte ließen sich nicht setzen: ' 'Folder permissions couldn''t be set: ') + $_.Exception.Message)
    # Seit 0.3.2 (Pruefbericht 0.3.1, Fund 10): ausserhalb des eigenen Profils abbrechen, bevor das Token hineinkommt
    if (-not ($Ziel + '\').StartsWith($env:LOCALAPPDATA + '\', [System.StringComparison]::OrdinalIgnoreCase)) {
      throw (T 'Ohne eigene Ordnerrechte richte ich außerhalb des Benutzerprofils nichts ein, andere Konten könnten sonst das Token lesen. Bitte einen Ordner unter %LOCALAPPDATA% wählen.' 'Without dedicated folder permissions I won''t set up anything outside your user profile, other accounts could read the token. Please choose a folder under %LOCALAPPDATA%.')
    }
    Hinweis (T 'Am sichersten ist ein Ordner im eigenen Benutzerprofil (Vorgabe: %LOCALAPPDATA%\Jarvis).' 'Safest is a folder in your own user profile (default: %LOCALAPPDATA%\Jarvis).')
  }
  foreach ($Wolke in $env:OneDrive, $env:OneDriveConsumer, $env:OneDriveCommercial) {
    if ($Wolke -and $Ziel -like "$Wolke\*") {
      Hinweis (T 'Der Ordner liegt in OneDrive: Das Token würde mit hochgeladen. Besser einen Ordner außerhalb wählen.' 'The folder is in OneDrive: the token would be uploaded too. Better choose a folder outside it.')
      break
    }
  }

  Schritt (T 'Jarvis-Rechner finden' 'Finding the Jarvis host')
  $Adresse = $A['bruecke'].Trim()
  if ($Adresse -notmatch '^[a-z]+://') { $Adresse = "http://$Adresse" }
  $U = [Uri]$Adresse
  # ohne Port: 8770 (Standard der Brücke im Heimnetz); bei https gilt der Port der Adresse
  $Bruecke = '{0}://{1}:{2}' -f $U.Scheme, $U.Host, $(if ($U.Scheme -eq 'http' -and $A['bruecke'] -notmatch ':\d+') { 8770 } else { $U.Port })
  $JarvisIp = $U.Host
  $Dummy = $null
  if (-not [System.Net.IPAddress]::TryParse($JarvisIp, [ref]$Dummy)) {
    $JarvisIp = ([System.Net.Dns]::GetHostAddresses($U.Host) | Where-Object { $_.AddressFamily -eq 'InterNetwork' } |
                 Select-Object -First 1).IPAddressToString
  }
  # landet später in der Firewall-Regel (mit Adminrechten), also nur eine echte IPv4-Adresse
  if (-not $JarvisIp -or -not [System.Net.IPAddress]::TryParse($JarvisIp, [ref]$Dummy)) { throw ((T "Adresse '{0}' ließ sich nicht auflösen." "Address '{0}' couldn't be resolved.") -f $U.Host) }
  Write-Host ("   " + (T 'Brücke' 'Bridge') + ": $Bruecke (IP $JarvisIp)")
  $null = Invoke-RestMethod -Uri "$Bruecke/v1/gesund" -TimeoutSec 10
  Write-Host ('   ' + (T 'erreichbar.' 'reachable.')) -ForegroundColor Green

  Schritt (T 'Diesen PC koppeln' 'Pairing this PC')
  $Token = $null
  if (Test-Path $EinstPfad) {
    $Alt = Get-Content $EinstPfad -Raw | ConvertFrom-Json
    if ($Alt.bruecke -eq $Bruecke) { $Token = $Alt.token }
  }
  $UpdateSchluessel = $null
  if ($A['code']) {
    if (-not (Koppel-Beweis $Bruecke $A['code'])) {
      throw (T 'Unter dieser Adresse antwortet etwas, das deinen Kopplungscode nicht kennt. Der Code bleibt hier. Adresse prüfen, einen neuen Code erzeugen oder (bei einem Jarvis vor 0.3.2) zuerst den Jarvis aktualisieren.' 'Something answers at this address that doesn''t know your pairing code. The code stays here. Check the address, create a new code or (for a Jarvis before 0.3.2) update the Jarvis first.')
    }
    $Antwort = Invoke-RestMethod -Method Post -Uri "$Bruecke/v1/koppeln" -ContentType 'application/json; charset=utf-8' `
      -Body ([System.Text.Encoding]::UTF8.GetBytes((@{ code = $A['code'].Trim().ToUpper(); name = $env:COMPUTERNAME } | ConvertTo-Json))) -TimeoutSec 15
    $Token = $Antwort.token
    # seit 0.3.2: oeffentlicher Update-Schluessel der Bruecke; der Client prueft Updates dagegen (Ed25519)
    if ([string]$Antwort.update_schluessel -cmatch '^[0-9a-f]{64}$') { $UpdateSchluessel = [string]$Antwort.update_schluessel }
  }
  if (-not $Token) { throw (T 'Kein Kopplungscode und keine frühere Kopplung mit diesem Jarvis gefunden.' 'No pairing code and no earlier pairing with this Jarvis found.') }
  if (-not $A['code'] -and -not $Alt.ohne_brueckenbeweis -and -not (Bruecke-Echt $Bruecke $Token)) {
    throw (T 'Unter dieser Adresse antwortet etwas, das sich nicht als dein Jarvis ausweist. Das gespeicherte Token bleibt hier; Adresse und Netz prüfen oder mit einem Code neu koppeln.' 'Something answers at this address that cannot prove it is your Jarvis. The stored token stays here; check the address and network, or pair again with a code.')
  }
  $Kopf = @{ Authorization = "Bearer $Token" }
  $null = Invoke-RestMethod -Uri "$Bruecke/v1/zustand" -Headers $Kopf -TimeoutSec 10
  Write-Host ('   ' + (T 'Gekoppelt.' 'Paired.')) -ForegroundColor Green

  # Adressen für den Client: vom Jarvis selbst (falls er /v1/client kennt), sonst die Vorgaben des Clients
  $Client = $null
  try { $Client = Invoke-RestMethod -Uri "$Bruecke/v1/client" -Headers $Kopf -TimeoutSec 10 } catch { }

  Schritt (T 'Python-Umgebung für Jarvis (eigene Kopie, vorhandenes Python bleibt unberührt)' 'Python environment for Jarvis (its own copy, any existing Python stays untouched)')
  Uv-Bereit
  if (-not (Test-Path $Py)) { uv venv --python 3.12 (Join-Path $Ziel 'venv'); Pruefe 'venv' }
  # alle Pakete samt Abhängigkeiten mit fester Version und Prüfsumme (release/pakete_aufloesen.sh)
  uv pip install --python $Py --require-hashes -r (Join-Path $Mitgeliefert 'pakete.txt'); Pruefe (T 'Pakete' 'Packages')
  uv pip install --python $Py --no-deps --require-hashes -r (Join-Path $Mitgeliefert 'weckwort.txt'); Pruefe 'openWakeWord'

  Schritt (T 'Weckwort-Modell „Hey Jarvis“ laden (mit Prüfsumme)' 'Downloading the “Hey Jarvis” wake word model (with checksum)')
  $ModellOrdner = Join-Path $Ziel 'modelle'
  New-Item -ItemType Directory -Force -Path $ModellOrdner | Out-Null
  foreach ($Datei in $Modelle.Keys) {
    $Pfad = Join-Path $ModellOrdner $Datei
    if (-not ((Test-Path -LiteralPath $Pfad) -and (Pruefsumme $Pfad) -eq $Modelle[$Datei])) {
      Invoke-WebRequest -UseBasicParsing -Uri ($ModellBasis + $Datei) -OutFile $Pfad
    }
    if ((Pruefsumme $Pfad) -ne $Modelle[$Datei]) { Remove-Item -LiteralPath $Pfad -Force; throw ((T 'Prüfsumme von {0} stimmt nicht' 'Checksum of {0} doesn''t match') -f $Datei) }
  }
  Write-Host ('   ' + (T 'drei Modelle geprüft.' 'three models checked.'))

  Schritt (T 'Jarvis-Client einrichten' 'Setting up the Jarvis client')
  Copy-Item (Join-Path $Mitgeliefert 'jarvis_pc.py') (Join-Path $Ziel 'jarvis_pc.py') -Force
  Copy-Item (Join-Path $Mitgeliefert 'jarvis.ico') (Join-Path $Ziel 'jarvis.ico') -Force
  $Autostart = JaNein $A['autostart']
  $Desktop = JaNein $A['desktop_symbol']
  $Einst = [ordered]@{ nas = $JarvisIp; bruecke = $Bruecke; token = $Token; schwelle = 0.5; mikrofon = $null;
                       name = $A['name']; autostart = $Autostart; desktop_symbol = $Desktop;
                       desktop_symbol_angelegt = $Desktop }
  if ($Client) {
    foreach ($k in 'dateien', 'hud', 'ohr_port', 'stimme_port', 'sprache', 'stimme', 'aussprache') {
      if (Client-Wert $k $Client.$k $U.Host $JarvisIp) { $Einst[$k] = $Client.$k }
    }
  }
  # Erneuter Lauf mit derselben Bruecke: eigene Einstellungen behalten (seit 25.10.2026)
  if ($Alt -and $Alt.bruecke -eq $Bruecke) {
    foreach ($k in 'mikrofon', 'schwelle', 'update_github', 'auto_update', 'ohne_brueckenbeweis', 'windows_mcp_vom_setup') {
      if ($null -ne $Alt.$k) { $Einst[$k] = $Alt.$k }
    }
  }
  if ($UpdateSchluessel) { $Einst['update_schluessel'] = $UpdateSchluessel }
  elseif ($Alt -and $Alt.bruecke -eq $Bruecke -and ([string]$Alt.update_schluessel -cmatch '^[0-9a-f]{64}$')) { $Einst['update_schluessel'] = [string]$Alt.update_schluessel }
  # Version des mitgelieferten Clients: Nach einer Neuinstallation zeigt er keine "Neu in dieser Version"-Hinweise
  $CV = Select-String -Path (Join-Path $Mitgeliefert 'jarvis_pc.py') -Pattern '^VERSION = (\d+)' | Select-Object -First 1
  if ($CV) { $Einst['zuletzt_version'] = [int]$CV.Matches[0].Groups[1].Value }
  Schreibe $EinstPfad ($Einst | ConvertTo-Json)
  Write-Host ('   ' + (T 'Einstellungen gespeichert (Token nur in dieser Datei, für dein Benutzerkonto).' 'Settings saved (token only in this file, for your user account).'))

  if (JaNein $A['pc_steuerung']) {
    Schritt (T 'PC-Steuerung (Windows-MCP), nur vom Jarvis-Rechner erreichbar' 'PC control (Windows-MCP), reachable only from the Jarvis host')
    try {
      # eigene Adresse auf dem Weg zum Jarvis-Rechner (UDP verbindet nur logisch, es wird nichts gesendet)
      $Udp = New-Object System.Net.Sockets.UdpClient
      $Udp.Connect($JarvisIp, 9)
      $Ip = $Udp.Client.LocalEndPoint.Address.ToString()
      $Udp.Close()
      # Nur in privaten Netzen (und Domänen): in einem öffentlichen WLAN mit zufällig gleicher Adresse bleibt Port 8000 zu
      $Regel = "Remove-NetFirewallRule -DisplayName 'Jarvis Windows-MCP*' -ErrorAction SilentlyContinue; " +
               "New-NetFirewallRule -DisplayName 'Jarvis Windows-MCP (nur Jarvis-Rechner)' -Direction Inbound -Protocol TCP " +
               "-LocalPort 8000 -RemoteAddress $JarvisIp -Action Allow -Profile Private,Domain | Out-Null"
      Write-Host ('   ' + (T 'Windows fragt jetzt einmal nach Administratorrechten (Firewall-Regel für Port 8000).' 'Windows now asks once for administrator rights (firewall rule for port 8000).'))
      # kodiert übergeben: Anführungszeichen und Semikolons überstehen so jede Befehlszeile
      $Kodiert = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($Regel))
      Start-Process $PS -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList "-NoProfile -EncodedCommand $Kodiert"
      $Netz = $null
      try { $Netz = Get-NetConnectionProfile -InterfaceIndex (Get-NetIPAddress -IPAddress $Ip).InterfaceIndex } catch { }
      if ($Netz -and $Netz.NetworkCategory -eq 'Public') {
        Hinweis (T 'Windows führt dieses Netz als „Öffentlich“. Dann bleibt die PC-Steuerung zu. Zuhause umstellen:' 'Windows treats this network as “Public”, so PC control stays closed. Change it at home:')
        Hinweis (T 'Einstellungen > Netzwerk und Internet > (WLAN bzw. Ethernet) > Eigenschaften > Privates Netzwerk.' 'Settings > Network & internet > (Wi-Fi or Ethernet) > Properties > Private network.')
      }
      uv tool install --python 3.14 --force --exclude-newer $Stichtag windows-mcp==0.8.8; Pruefe 'Windows-MCP'
      $Schluessel = Zufall
      $McpOrdner = Join-Path $env:USERPROFILE '.windows-mcp'
      New-Item -ItemType Directory -Force -Path $McpOrdner | Out-Null
      $Toml = "[server]`ntransport = `"streamable-http`"`nhost = `"0.0.0.0`"`nport = 8000`nauth_key = `"$Schluessel`"`n" +
              "stateless_http = true`n`n[security]`nip_allowlist = [`"$JarvisIp/32`"]`n"
      Schreibe (Join-Path $McpOrdner 'config.toml') $Toml
      windows-mcp install --transport streamable-http --host 0.0.0.0 --port 8000 --force; Pruefe 'Windows-MCP-Autostart'
      $null = Invoke-RestMethod -Method Post -Uri "$Bruecke/v1/pc" -Headers $Kopf -ContentType 'application/json' `
        -Body (@{ ip = $Ip; port = 8000; key = $Schluessel; name = $env:COMPUTERNAME } | ConvertTo-Json)
      $Schluessel = $null
      Write-Host ("   " + ((T 'PC-Adresse {0} an Jarvis gemeldet.' 'PC address {0} reported to Jarvis.') -f $Ip)) -ForegroundColor Green
      # Merken, dass Windows-MCP von hier kommt: nur dann entfernt die Deinstallation es wieder
      $Einst['windows_mcp_vom_setup'] = $true
      Schreibe $EinstPfad ($Einst | ConvertTo-Json)
    } catch {
      Hinweis ((T 'PC-Steuerung nicht eingerichtet: ' 'PC control not set up: ') + $_.Exception.Message)
      Hinweis (T 'Jarvis läuft trotzdem. Setup später erneut starten, um es nachzuholen.' 'Jarvis runs anyway. Run the setup again later to catch up.')
    }
  }

  Schritt (T 'Autostart und Desktop-Symbol' 'Autostart and desktop icon')
  $Start = Join-Path ([Environment]::GetFolderPath('Startup')) 'Jarvis.lnk'
  $Skript = '"' + (Join-Path $Ziel 'jarvis_pc.py') + '"'
  $Symbol = Join-Path $Ziel 'jarvis.ico'
  if ($Autostart) { Verknuepfung 'Startup' 'Jarvis.lnk' $PyW $Skript $Ziel $Symbol 'J.A.R.V.I.S.' }
  elseif (Test-Path $Start) { Remove-Item $Start }
  if ($Desktop) { Verknuepfung 'Desktop' 'Jarvis.lnk' $PyW ($Skript + ' --fenster') $Ziel $Symbol 'J.A.R.V.I.S.' }
  Write-Host ('   Autostart: ' + $(if ($Autostart) { (T 'an' 'on') } else { (T 'aus' 'off') }) + (T ', Desktop-Symbol: ' ', desktop icon: ') +
              $(if ($Desktop) { (T 'ja' 'yes') } else { (T 'nein' 'no') }) + (T ' (umschaltbar im Jarvis-Fenster, Zahnrad)' ' (switchable in the Jarvis window, gear)'))

  Schritt (T 'Jarvis starten' 'Starting Jarvis')
  Get-Process pythonw -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$Ziel\*" } | Stop-Process -Force
  Start-Process $PyW -ArgumentList ($Skript + ' --begruessung') -WorkingDirectory $Ziel
  if (JaNein $A['pc_steuerung']) {
    Write-Host ('   ' + (T 'Warte, bis der Jarvis-Rechner diesen PC sieht (bis zu 40 s) ...' 'Waiting until the Jarvis host sees this PC (up to 40 s) ...'))
    $Online = $false
    for ($i = 0; $i -lt 8 -and -not $Online; $i++) {
      Start-Sleep -Seconds 5
      $Online = (Invoke-RestMethod -Uri "$Bruecke/v1/zustand" -Headers $Kopf).pc_online
    }
    if ($Online) { Write-Host ('   ' + (T 'Jarvis sieht diesen PC.' 'Jarvis sees this PC.')) -ForegroundColor Green }
    else { Hinweis (T 'Der Jarvis-Rechner erreicht die PC-Steuerung noch nicht (Protokoll: %USERPROFILE%\.windows-mcp\server.log).' 'The Jarvis host can''t reach PC control yet (log: %USERPROFILE%\.windows-mcp\server.log).') }
  }
  Write-Host ''
  Write-Host ('   ' + (T 'FERTIG. Sag „Hey Jarvis“ oder öffne das Jarvis-Fenster.' 'DONE. Say “Hey Jarvis” or open the Jarvis window.')) -ForegroundColor Green
}

# ------------------------------------------------------------------ Weg 2: neuen Jarvis mit Claude Code einrichten
function Neu($A) {
  $Projekt = Join-Path $env:USERPROFILE 'Jarvis'

  Schritt (T 'Projektordner anlegen' 'Creating the project folder')
  New-Item -ItemType Directory -Force -Path $Projekt, (Join-Path $Projekt 'einrichtung') | Out-Null
  # Bauanleitung in beiden Sprachen (seit 0.3.0); Claude bekommt die der Setup-Sprache genannt
  Copy-Item (Join-Path $Mitgeliefert 'EINRICHTUNG.md') (Join-Path $Projekt 'EINRICHTUNG.md') -Force
  Copy-Item (Join-Path $Mitgeliefert 'EINRICHTUNG.en.md') (Join-Path $Projekt 'EINRICHTUNG.en.md') -Force
  $Anleitung = T 'EINRICHTUNG.md' 'EINRICHTUNG.en.md'
  Copy-Item (Join-Path $Mitgeliefert 'jarvis_pc.py') (Join-Path $Projekt 'einrichtung\jarvis_pc.py') -Force
  Copy-Item (Join-Path $Mitgeliefert 'jarvis.ico') (Join-Path $Projekt 'einrichtung\jarvis.ico') -Force
  # Erneuter Lauf: Vorlagen, die Claude erweitert haben kann, nicht ueberschreiben; die neue Fassung liegt dann als
  # <name>.neu daneben (seit 25.10.2026)
  foreach ($f in 'hud.html', 'oberflaeche.py', 'verhalten.py', 'test_oberflaeche.py', 'test_verhalten.py', 'app.html',
                 'jarvis-web.js', 'webapp_bauen.py', 'jarvis.png',
                 'anhang.py', 'ed25519.py', 'ausgabe.py', 'pdf.py', 'bilddienst.py', 'konvertieren.py', 'zusatzdienste.py',
                 'test_anhang.py', 'test_ed25519.py', 'test_pdf.py', 'test_ausgabe.py', 'test_bilddienst.py', 'test_konvertieren.py') {
    $Dort = Join-Path $Projekt "einrichtung\$f"
    $Neu = Join-Path $Mitgeliefert $f
    if ((Test-Path -LiteralPath $Dort) -and (Pruefsumme $Dort) -ne (Pruefsumme $Neu)) {
      Copy-Item $Neu "$Dort.neu" -Force
      # Seit 0.3.4 (Pruefbericht 0.3.3, Fund 16): Sicherheitsmodule nicht nur nebenbei erwaehnen
      if (@('anhang.py', 'ed25519.py', 'ausgabe.py', 'pdf.py', 'bilddienst.py', 'konvertieren.py', 'zusatzdienste.py') -contains $f) {
        Write-Host ('   ' + (T 'WICHTIG: einrichtung\{0} ist ein Sicherheitsmodul und wurde nicht ersetzt. {0}.neu enthält Sicherheitskorrekturen: Claude im Jarvis-Ordner bitten, sie zu übernehmen, bevor Jarvis weiterläuft.' 'IMPORTANT: einrichtung\{0} is a security module and was not replaced. {0}.neu contains security fixes: ask Claude in the Jarvis folder to apply them before Jarvis keeps running.') -f $f) -ForegroundColor Red
      }
      Hinweis ((T 'einrichtung\{0} behalten (vielleicht angepasst), die neue Vorlage liegt als {0}.neu daneben.' 'kept einrichtung\{0} (maybe customized), the new template is next to it as {0}.neu.') -f $f)
    } else { Copy-Item $Neu $Dort -Force }
  }
  $F = @($A['faehigkeiten'] -split ',' | Where-Object { $_ })
  $Antworten = [ordered]@{
    quelle          = 'Jarvis-Setup ' + $A['setup_version']
    erstellt        = (Get-Date -Format 'yyyy-MM-dd HH:mm')
    name            = $A['name']
    rufname         = $A['rufname']
    aussprache      = $A['aussprache']
    sprache         = $A['sprache']
    anrede          = $A['anrede']
    technik         = $A['technik']
    persoenlichkeit = $A['persoenlichkeit']
    faehigkeiten    = [string[]]$F
    vorhaben        = ($A['vorhaben'] -replace '\\n', "`n")
    wohnort         = $A['wohnort']
    gehirn          = $A['gehirn']
    handy           = $A['handy']
    unterwegs       = $A['unterwegs']
    pc_sprache      = JaNein $A['pc_sprache']
    autostart       = JaNein $A['autostart']
    desktop_symbol  = JaNein $A['desktop_symbol']
    pc_steuerung    = JaNein $A['pc_steuerung']
    zusatzdienste   = [ordered]@{ bilder = $A['zusatz_bilder']; umwandeln = $A['zusatz_umwandeln'] }
    oberflaeche     = [ordered]@{
      design     = $A['oberflaeche_design']
      untertitel = $A['oberflaeche_untertitel']
      bereiche   = [string[]]@($A['oberflaeche_bereiche'] -split ',' | Where-Object { $_ })
      wuensche   = $A['oberflaeche_wuensche']
    }
  }
  Schreibe (Join-Path $Projekt 'antworten.json') ($Antworten | ConvertTo-Json -Depth 5)
  if (-not (Test-Path (Join-Path $Projekt 'CLAUDE.md'))) {
    if ($script:EN) {
      Schreibe (Join-Path $Projekt 'CLAUDE.md') (
      "# Jarvis project`n`n" +
      "This folder is this person's home assistant J.A.R.V.I.S., built by Claude Code.`n`n" +
      "- Build guide and rules: EINRICHTUNG.en.md (read before every change; German original: EINRICHTUNG.md).`n" +
      "- Answers from the setup: antworten.json. Confirmed profile after round 8: einrichtung/profil.json.`n" +
      "- Secrets live only under geheim\ (never print them, never in Git).`n" +
      "- Always run your own tests with a source test… (test mode).`n" +
      "- Interface: einrichtung/hud.html is the same for everyone. Personal things live only in the bridge settings`n" +
      "  (check module einrichtung/oberflaeche.py, round 6a; setze_sprache(`"en`")). Page updates never overwrite them.`n")
    } else {
    Schreibe (Join-Path $Projekt 'CLAUDE.md') (
      "# Jarvis-Projekt`n`n" +
      "Dieser Ordner ist der Hausassistent J.A.R.V.I.S. dieser Person, gebaut von Claude Code.`n`n" +
      "- Bauanleitung und Regeln: EINRICHTUNG.md (vor jeder Änderung lesen).`n" +
      "- Antworten aus dem Setup: antworten.json. Bestätigtes Profil nach Runde 8: einrichtung/profil.json.`n" +
      "- Geheimnisse liegen nur unter geheim\ (nie ausgeben, nie in Git).`n" +
      "- Eigene Proben immer mit einer Quelle test… (Testmodus).`n" +
      "- Oberfläche: einrichtung/hud.html ist für alle gleich. Persönliches steht nur in den Einstellungen der Brücke`n" +
      "  (Prüfmodul einrichtung/oberflaeche.py, Runde 6a). Updates der Seite überschreiben die Einstellungen nie.`n")
    }
  }
  Write-Host "   $Projekt"

  Schritt (T 'Git für Windows (optional, damit Claude Code die Bash nutzen kann)' 'Git for Windows (optional, so Claude Code can use bash)')
  if (Get-Command git -ErrorAction SilentlyContinue) { Write-Host ('   ' + (T 'schon da.' 'already there.')) }
  elseif (Get-Command winget -ErrorAction SilentlyContinue) {
    winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) { Hinweis (T 'Git ließ sich nicht installieren. Claude Code nimmt dann PowerShell, das reicht.' 'Git couldn''t be installed. Claude Code then uses PowerShell, that''s fine.') }
  } else { Hinweis (T 'winget fehlt, Git wird übersprungen. Claude Code nimmt dann PowerShell, das reicht.' 'winget is missing, Git is skipped. Claude Code then uses PowerShell, that''s fine.') }

  Schritt (T 'Claude Code installieren (offizieller Installer von claude.ai)' 'Installing Claude Code (official installer from claude.ai)')
  $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
  if (Get-Command claude -ErrorAction SilentlyContinue) { Write-Host ('   ' + (T 'schon da.' 'already there.')) }
  else {
    # eigener Prozess: ein exit im fremden Installer beendet sonst dieses Skript
    # Claude Code kommt bewusst aktuell vom offiziellen Installer (Anthropic), nicht festgenagelt
    & $PS -ExecutionPolicy Bypass -NoProfile -Command "irm https://claude.ai/install.ps1 | iex"
    Pruefe 'Claude-Code-Installation'
  }
  claude --version; Pruefe 'Claude Code'
  $ClaudeExe = (Get-Command claude).Source

  # Der Installer trägt seinen Ordner nicht immer dauerhaft in PATH ein: Nach dem Neustart fand ein neues Fenster
  # "claude" nicht mehr (Laptop-Test 23.10.2026). Deshalb für dieses Benutzerkonto ergänzen, und die Verknüpfung
  # ruft claude.exe ohnehin mit vollem Pfad auf.
  $ClaudeOrdner = Split-Path $ClaudeExe
  $Benutzerpfad = [Environment]::GetEnvironmentVariable('Path', 'User')
  if (-not (@($Benutzerpfad -split ';') -contains $ClaudeOrdner)) {
    [Environment]::SetEnvironmentVariable('Path', ((@($Benutzerpfad -split ';') + $ClaudeOrdner | Where-Object { $_ }) -join ';'), 'User')
    Write-Host ("   " + ((T '{0} dauerhaft in PATH eingetragen.' 'added {0} to PATH permanently.') -f $ClaudeOrdner))
  }

  $Fortsetzen = T 'Jarvis-Einrichtung fortsetzen' 'Continue Jarvis setup'
  Schritt ((T 'Desktop-Symbol „{0}“' 'Desktop icon “{0}”') -f $Fortsetzen)
  Verknuepfung 'Desktop' ($Fortsetzen + '.lnk') $ClaudeExe '--continue' `
    $Projekt (Join-Path $Mitgeliefert 'jarvis.ico') (T 'Setzt das Einrichtungsgespräch mit Claude fort' 'Continues the setup conversation with Claude')

  Schritt (T 'Claude Code starten' 'Starting Claude Code')
  # Fester Text, keine Antworten in der Befehlszeile: die liest Claude aus antworten.json
  Start-Process $ClaudeExe -WorkingDirectory $Projekt `
    -ArgumentList (T '"Lies EINRICHTUNG.md und antworten.json und fuehre mich durch die Einrichtung."' `
                     '"Read EINRICHTUNG.en.md and antworten.json and guide me through the setup."')
  Write-Host ''
  Write-Host ('   ' + (T 'FERTIG mit dem Setup-Teil. Claude Code läuft im neuen Fenster:' 'DONE with the setup part. Claude Code is running in the new window:')) -ForegroundColor Green
  Write-Host ('   ' + (T 'beim ersten Start im Browser anmelden und den Ordner „Jarvis“ als vertrauenswürdig bestätigen.' 'on first start, sign in in the browser and confirm the “Jarvis” folder as trusted.')) -ForegroundColor Green
}

# ------------------------------------------------------------------ Ablauf
$Code = 0
New-Item -ItemType Directory -Force -Path $Mitgeliefert | Out-Null
try { Start-Transcript -Path (Join-Path $Mitgeliefert 'einrichten.log') -Append | Out-Null } catch { }
try {
  Write-Host ''
  $A = Lies-Antworten $Ini
  $script:EN = ($A['setup_sprache'] -eq 'en')
  Write-Host ('   J . A . R . V . I . S .   ' + (T 'wird eingerichtet' 'is being set up')) -ForegroundColor Cyan
  Write-Host '   ------------------------------------------' -ForegroundColor DarkCyan
  Remove-Item -LiteralPath $Ini -Force -ErrorAction SilentlyContinue
  if ($A['art'] -eq 'verbinden') { Verbinden $A }
  elseif ($A['art'] -eq 'neu') { Neu $A }
  else { throw ((T "Unbekannte Art der Einrichtung: '{0}'" "Unknown kind of setup: '{0}'") -f $A['art']) }
  # Das Setup wertet Erfolg nur mit dieser Datei (ein Rückgabecode 0 allein kommt auch von Platzhaltern)
  Schreibe (Join-Path $Mitgeliefert 'fertig.ok') (Get-Date -Format s)
}
catch {
  $Code = 1
  Write-Host ''
  Write-Host ('   ' + (T 'FEHLER: ' 'ERROR: ') + $_.Exception.Message) -ForegroundColor Red
  Write-Host ('   ' + (T 'Protokoll: ' 'Log: ') + "$Mitgeliefert\einrichten.log") -ForegroundColor Red
}
try { Stop-Transcript | Out-Null } catch { }
Write-Host ''
Read-Host ('   ' + (T 'Enter schließt dieses Fenster' 'Enter closes this window')) | Out-Null
exit $Code
