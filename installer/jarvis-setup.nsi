; J.A.R.V.I.S. – Setup (NSIS 3, Unicode). Bauen: ./bauen.sh (makensis in einem Container, kein Windows nötig).
;
; Zwei Wege:
;   neu        Fragebogen -> antworten.json, Claude Code installieren, Einrichtung im Gespräch (EINRICHTUNG.md)
;   verbinden  PC-Client an einen bestehenden Jarvis koppeln (Kopplungscode)
; Dieses Skript sammelt nur die Antworten. Die eigentliche Arbeit macht einrichten.ps1, damit sie lesbar bleibt und
; sich ohne Setup testen lässt. Antworten gehen über eine UTF-16-INI an das Skript, nie über die Befehlszeile
; (Freitext darin wäre sonst ausführbar).

Unicode true
ManifestDPIAware true
SetCompressor /SOLID lzma
RequestExecutionLevel user

!ifndef VERSION
  !define VERSION "0.1.0"
!endif
!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\Jarvis"
!define POWERSHELL "$SYSDIR\WindowsPowerShell\v1.0\powershell.exe"

!include "MUI2.nsh"
!include "nsDialogs.nsh"
!include "LogicLib.nsh"
!include "WordFunc.nsh"
!include "x64.nsh"

Name "J.A.R.V.I.S."
OutFile "dist\Jarvis-Setup.exe"
InstallDir "$LOCALAPPDATA\Jarvis"
; Erneut ausfuehren: der Ordner der vorhandenen Installation ist die Vorgabe (seit 25.10.2026 waehlbar)
InstallDirRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\Jarvis" "InstallLocation"
BrandingText "$(T_BRANDING)"

; ------------------------------------------------------------------ Antworten
Var Dlg
Var Art                     ; neu | verbinden
Var hNeu
Var hVerb
Var Ergebnis
Var FertigText
Var FertigTitel
; verbinden
Var Bruecke
Var Code
Var hBruecke
Var hCode
Var PcSteuerung
Var hPcSteuerung
; neu: über dich
Var NameW
Var Rufname
Var Aussprache          ; seit 0.3.0: nur fuer die Stimme (antworten.json -> aussprache)
Var FaehText            ; seit 0.3.0: Beschriftungen fuer die Zusammenfassung (die INI bekommt die Kennungen)
Var BereichText
Var FaehAnzeige
Var BereichAnzeige
Var Sprache
Var Anrede
Var Technik
Var Persoenlichkeit
Var hName
Var hRuf
Var hAussprache
Var hSprache
Var hAnrede
Var hTechnik
Var hPers
; neu: Fähigkeiten (1/0)
Var F1
Var F2
Var F3
Var F4
Var F5
Var F6
Var F7
Var F8
Var F9
Var F10
Var F11
Var F12
Var hF1
Var hF2
Var hF3
Var hF4
Var hF5
Var hF6
Var hF7
Var hF8
Var hF9
Var hF10
Var hF11
Var hF12
Var Faehigkeiten
; neu: Vorhaben
Var Vorhaben
Var hVorhaben
; neu: Geräte und Start (Autostart/Desktop gelten für beide Wege)
Var Wohnort
Var Gehirn
Var Handy
Var Unterwegs
Var hWohnort
Var hGehirn
Var hHandy
Var hUnterwegs
Var PcSprache
Var Autostart
Var DesktopSym
Var hPcSprache
Var hAutostart
Var hDesktop
; Seite "Deine Oberflaeche" (seit 24.10.2026): Design, Bereiche der Hauptseite, Untertitel, eigene Wuensche
Var Design
Var hDesign
Var Untertitel
Var hUntertitel
Var O1
Var O2
Var O3
Var O4
Var O5
Var O6
Var O7
Var O8
Var O9
Var O10
Var hO1
Var hO2
Var hO3
Var hO4
Var hO5
Var hO6
Var hO7
Var hO8
Var hO9
Var hO10
Var Bereiche
Var Wuensche
Var hWuensche
Var OGezeigt
; Seite "Jarvis aufs Handy" (seit 25.10.2026): QR-Code auf die App im neuesten GitHub-Release
Var hQr
Var hQrBild

; ------------------------------------------------------------------ Seiten
!define MUI_ICON "dateien\jarvis.ico"
!define MUI_UNICON "dateien\jarvis.ico"
!define MUI_WELCOMEFINISHPAGE_BITMAP "dateien\seitenbild.bmp"
!define MUI_ABORTWARNING
!define MUI_LANGDLL_REGISTRY_ROOT "HKCU"
!define MUI_LANGDLL_REGISTRY_KEY "${UNINST_KEY}"
!define MUI_LANGDLL_REGISTRY_VALUENAME "Sprache"
!define MUI_LANGDLL_WINDOWTITLE "J.A.R.V.I.S."
!define MUI_LANGDLL_INFO "Sprache wählen / Choose a language"
!define MUI_ABORTWARNING_TEXT "$(T_ABBRUCH)"
!define MUI_WELCOMEPAGE_TITLE "$(T_WILLKOMMEN)"
!define MUI_WELCOMEPAGE_TEXT "$(T_WILLKOMMEN_TEXT)"
!insertmacro MUI_PAGE_WELCOME
; Lizenz (seit 25.10.2026): PolyForm Noncommercial verlangt Zustimmung ("Acceptance"), deshalb vor allem anderen
!define MUI_LICENSEPAGE_TEXT_TOP "$(T_LIZENZ_OBEN)"
!define MUI_LICENSEPAGE_TEXT_BOTTOM "$(T_LIZENZ_UNTEN)"
!define MUI_LICENSEPAGE_BUTTON "$(T_LIZENZ_KNOPF)"
!insertmacro MUI_PAGE_LICENSE "dateien\LICENSE.txt"
Page custom SeiteArt SeiteArtEnde
Page custom SeiteVerbinden SeiteVerbindenEnde
Page custom SeiteUeberDich SeiteUeberDichEnde
Page custom SeiteFaehigkeiten SeiteFaehigkeitenEnde
Page custom SeiteVorhaben SeiteVorhabenEnde
Page custom SeiteGeraete SeiteGeraeteEnde
Page custom SeiteApp SeiteAppEnde
Page custom SeiteOberflaeche SeiteOberflaecheEnde
; Ordner fuer den PC-Client (nur Weg "verbinden"; beim neuen Jarvis liegt das Projekt ohnehin unter %USERPROFILE%\Jarvis)
!define MUI_PAGE_HEADER_TEXT "$(T_ORDNER_KOPF)"
!define MUI_PAGE_HEADER_SUBTEXT "$(T_ORDNER_UNTER)"
!define MUI_DIRECTORYPAGE_TEXT_TOP "$(T_ORDNER_TEXT)"
!define MUI_PAGE_CUSTOMFUNCTION_PRE OrdnerVorher
!define MUI_PAGE_CUSTOMFUNCTION_LEAVE OrdnerVerlassen
!insertmacro MUI_PAGE_DIRECTORY
Page custom SeiteZusammenfassung
!define MUI_PAGE_HEADER_TEXT "$(T_LAEUFT_KOPF)"
!define MUI_PAGE_HEADER_SUBTEXT "$(T_LAEUFT_UNTER)"
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_TITLE "$FertigTitel"
!define MUI_FINISHPAGE_TEXT "$FertigText"
!define MUI_FINISHPAGE_NOREBOOTSUPPORT
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; Sprachen (seit 0.3.0): Deutsch zuerst (Vorgabe), Englisch. Beim Start fragt das Setup, vorbelegt mit der Sprache von
; Windows; die Wahl merkt sich die Deinstallation im Uninstall-Schluessel. Alle Texte stehen in texte.nsh.
!insertmacro MUI_LANGUAGE "German"
!insertmacro MUI_LANGUAGE "English"
!include "texte.nsh"

VIProductVersion "${VERSION}.0"
VIAddVersionKey /LANG=${LANG_GERMAN} "ProductName" "J.A.R.V.I.S."
VIAddVersionKey /LANG=${LANG_GERMAN} "FileDescription" "Jarvis-Einrichtung"
VIAddVersionKey /LANG=${LANG_GERMAN} "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=${LANG_GERMAN} "ProductVersion" "${VERSION}"
VIAddVersionKey /LANG=${LANG_GERMAN} "CompanyName" "Jarvis-Projekt"
VIAddVersionKey /LANG=${LANG_GERMAN} "LegalCopyright" "Copyright 2026 Hellraiser28 · PolyForm Noncommercial 1.0.0"
VIAddVersionKey /LANG=${LANG_ENGLISH} "ProductName" "J.A.R.V.I.S."
VIAddVersionKey /LANG=${LANG_ENGLISH} "FileDescription" "Jarvis setup"
VIAddVersionKey /LANG=${LANG_ENGLISH} "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=${LANG_ENGLISH} "ProductVersion" "${VERSION}"
VIAddVersionKey /LANG=${LANG_ENGLISH} "CompanyName" "Jarvis project"
VIAddVersionKey /LANG=${LANG_ENGLISH} "LegalCopyright" "Copyright 2026 Hellraiser28 · PolyForm Noncommercial 1.0.0"

; ------------------------------------------------------------------ Start
Function .onInit
  !insertmacro MUI_LANGDLL_DISPLAY
  StrCpy $Art "neu"
  StrCpy $PcSteuerung 0
  ; Jarvis spricht vorab die Sprache des Setups (auf der Seite "Über dich" umstellbar)
  ${If} $LANGUAGE == ${LANG_ENGLISH}
    StrCpy $Sprache "English"
  ${Else}
    StrCpy $Sprache "Deutsch"
  ${EndIf}
  StrCpy $Anrede "$(T_ANREDE_DU)"   ; angezeigt je Sprache, gespeichert wird Du/Sie (AntwortenSchreiben)
  StrCpy $Technik "$(T_TECHNIK2)"
  StrCpy $Persoenlichkeit "$(T_PERS1)"
  ; Kalender, Einkaufsliste, Nachrichten, Briefings vorgewählt
  StrCpy $F1 1
  StrCpy $F2 1
  StrCpy $F3 0
  StrCpy $F4 0
  StrCpy $F5 1
  StrCpy $F6 0
  StrCpy $F7 0
  StrCpy $F8 0
  StrCpy $F9 0
  StrCpy $F10 0
  StrCpy $F11 0
  StrCpy $F12 1
  StrCpy $Wohnort "$(T_WOHN3)"
  StrCpy $Gehirn "$(T_GEHIRN1)"
  StrCpy $Handy "$(T_KEINE)"
  StrCpy $Unterwegs "$(T_UNTERWEGS1)"
  StrCpy $PcSprache 1
  StrCpy $Autostart 1
  StrCpy $DesktopSym 1
  StrCpy $Design "$(T_DESIGN1)"
  StrCpy $Untertitel ""
  StrCpy $OGezeigt 0
FunctionEnd

!macro Ankreuzen HANDLE WERT
  ${If} ${WERT} == 1
    ${NSD_Check} ${HANDLE}
  ${EndIf}
!macroend

!macro Lesen HANDLE ZIEL
  ${NSD_GetState} ${HANDLE} ${ZIEL}
  ${If} ${ZIEL} == ${BST_CHECKED}
    StrCpy ${ZIEL} 1
  ${Else}
    StrCpy ${ZIEL} 0
  ${EndIf}
!macroend

; Mehrzeiliges Feld mit Zeilenumbruch (NSD_CreateMLText scrollt waagerecht statt umzubrechen)
!macro Textfeld X Y B H TEXT
  nsDialogs::CreateControl EDIT ${DEFAULT_STYLES}|${WS_TABSTOP}|${ES_AUTOVSCROLL}|${ES_MULTILINE}|${ES_WANTRETURN}|${WS_VSCROLL} ${WS_EX_WINDOWEDGE}|${WS_EX_CLIENTEDGE} ${X} ${Y} ${B} ${H} "${TEXT}"
!macroend

!macro Auswahl HANDLE WERT
  ${NSD_CB_SelectString} ${HANDLE} "${WERT}"
!macroend

; ------------------------------------------------------------------ Seite: Ordner (seit 25.10.2026)
Function OrdnerVorher
  ${If} $Art != "verbinden"
    Abort
  ${EndIf}
FunctionEnd

; Der Ordner endet immer auf \Jarvis: die Deinstallation loescht ihn ganz, ein gewaehltes "D:\Daten" darf sie nie treffen.
; Eine Aenderung an $INSTDIR in der Leave-Funktion der Verzeichnisseite uebernimmt NSIS nicht (Wine-Rundgang 25.10.):
; deshalb laeuft die Pruefung auch beim Aufbau der Zusammenfassung und am Anfang der Installation.
Function OrdnerNachher
  StrCpy $0 $INSTDIR 1 -1
  ${If} $0 == "\"
    StrCpy $INSTDIR $INSTDIR -1
  ${EndIf}
  StrCpy $0 $INSTDIR "" -7
  ${If} $0 != "\Jarvis"
    StrCpy $INSTDIR "$INSTDIR\Jarvis"
  ${EndIf}
FunctionEnd

;
; Seit 25.10.2026 (Pruefbericht): nie in den Projektordner eines neuen Jarvis (%USERPROFILE%\Jarvis, Gedaechtnis und
; geheim\) und nie in einen fremden, nicht leeren Ordner, denn die Deinstallation loescht den Ordner ganz.
Function OrdnerVerlassen
  Call OrdnerNachher
  ${If} $INSTDIR == "$PROFILE\Jarvis"
    MessageBox MB_ICONEXCLAMATION "$(T_ORDNER_RESERVIERT)"
    Abort
  ${EndIf}
  Call OrdnerFremd
  ${If} $1 == "1"
    MessageBox MB_ICONEXCLAMATION "$(T_ORDNER_FREMD)"
    Abort
  ${EndIf}
  ; Ohne Code geht es nur in einen Ordner, in dem dieser PC schon gekoppelt ist (erneutes Setup = aktualisieren)
  ${If} $Code == ""
  ${AndIfNot} ${FileExists} "$INSTDIR\einstellungen.json"
    MessageBox MB_ICONEXCLAMATION "$(T_ORDNER_UNGEKOPPELT)"
    Abort
  ${EndIf}
FunctionEnd

; $1 = "1", wenn $INSTDIR Dateien enthaelt, aber weder die Marke des Setups noch eine fruehere Installation
Function OrdnerFremd
  StrCpy $1 "0"
  ${If} ${FileExists} "$INSTDIR\.jarvis-client"
    Return
  ${EndIf}
  ${If} ${FileExists} "$INSTDIR\einstellungen.json"
  ${AndIf} ${FileExists} "$INSTDIR\jarvis_pc.py"
    Return
  ${EndIf}
  ClearErrors
  FindFirst $2 $3 "$INSTDIR\*.*"
  ${DoWhile} $3 != ""
    ${If} $3 != "."
    ${AndIf} $3 != ".."
      StrCpy $1 "1"
      ${ExitDo}
    ${EndIf}
    FindNext $2 $3
  ${Loop}
  FindClose $2
FunctionEnd

; ------------------------------------------------------------------ Seite: Art
Function SeiteArt
  !insertmacro MUI_HEADER_TEXT "$(T_ART_KOPF)" "$(T_ART_UNTER)"
  nsDialogs::Create 1018
  Pop $Dlg
  ${NSD_CreateFirstRadioButton} 0 0 100% 12u "$(T_ART_NEU)"
  Pop $hNeu
  ${NSD_CreateLabel} 12u 14u -12u 34u "$(T_ART_NEU_TEXT)"
  Pop $0
  ${NSD_CreateAdditionalRadioButton} 0 54u 100% 12u "$(T_ART_VERB)"
  Pop $hVerb
  ${NSD_CreateLabel} 12u 68u -12u 26u "$(T_ART_VERB_TEXT)"
  Pop $0
  ${NSD_CreateLabel} 0 104u 100% 30u "$(T_ART_ABO)"
  Pop $0
  ${If} $Art == "verbinden"
    ${NSD_Check} $hVerb
  ${Else}
    ${NSD_Check} $hNeu
  ${EndIf}
  nsDialogs::Show
FunctionEnd

Function SeiteArtEnde
  ${NSD_GetState} $hVerb $0
  ${If} $0 == ${BST_CHECKED}
    StrCpy $Art "verbinden"
  ${Else}
    StrCpy $Art "neu"
    ; Claude Code braucht Windows 10 1809 (Build 17763) oder neuer
    ReadRegStr $1 HKLM "SOFTWARE\Microsoft\Windows NT\CurrentVersion" "CurrentBuildNumber"
    ${If} $1 != ""
    ${AndIf} $1 < 17763
      MessageBox MB_ICONSTOP "$(T_ART_WINDOWS)"
      Abort
    ${EndIf}
  ${EndIf}
FunctionEnd

; ------------------------------------------------------------------ Seite: Verbinden
Function SeiteVerbinden
  ${If} $Art != "verbinden"
    Abort
  ${EndIf}
  !insertmacro MUI_HEADER_TEXT "$(T_VERB_KOPF)" "$(T_VERB_UNTER)"
  nsDialogs::Create 1018
  Pop $Dlg
  ${NSD_CreateLabel} 0 0 100% 10u "$(T_VERB_ADRESSE)"
  Pop $0
  ${NSD_CreateText} 0 11u 100% 12u "$Bruecke"
  Pop $hBruecke
  ${NSD_CreateLabel} 0 30u 140u 10u "$(T_VERB_CODE)"
  Pop $0
  ${NSD_CreateText} 0 41u 120u 12u "$Code"
  Pop $hCode
  ${NSD_SetTextLimit} $hCode 20
  ${NSD_CreateLabel} 150u 30u 150u 10u "$(T_VERB_NAME)"
  Pop $0
  ${NSD_CreateText} 150u 41u 150u 12u "$NameW"
  Pop $hName
  ${NSD_SetTextLimit} $hName 40
  ${NSD_CreateCheckBox} 0 62u 100% 11u "$(T_VERB_AUTOSTART)"
  Pop $hAutostart
  !insertmacro Ankreuzen $hAutostart $Autostart
  ${NSD_CreateCheckBox} 0 75u 100% 11u "$(T_DESKTOP)"
  Pop $hDesktop
  !insertmacro Ankreuzen $hDesktop $DesktopSym
  ${NSD_CreateCheckBox} 0 88u 100% 11u "$(T_VERB_PC)"
  Pop $hPcSteuerung
  !insertmacro Ankreuzen $hPcSteuerung $PcSteuerung
  ${NSD_CreateLabel} 12u 100u -12u 36u "$(T_VERB_PC_TEXT)"
  Pop $0
  ${NSD_SetFocus} $hBruecke
  nsDialogs::Show
FunctionEnd

Function SeiteVerbindenEnde
  ${NSD_GetText} $hBruecke $Bruecke
  ${NSD_GetText} $hCode $Code
  ${NSD_GetText} $hName $NameW
  !insertmacro Lesen $hAutostart $Autostart
  !insertmacro Lesen $hDesktop $DesktopSym
  !insertmacro Lesen $hPcSteuerung $PcSteuerung
  ${If} $Bruecke == ""
    MessageBox MB_ICONEXCLAMATION "$(T_VERB_ADRESSE_FEHLT)"
    ${NSD_SetFocus} $hBruecke
    Abort
  ${EndIf}
  ; Ohne Code geht es nur in einen schon gekoppelten Ordner; geprueft wird das nach der Ordnerwahl (OrdnerVerlassen)
FunctionEnd

; ------------------------------------------------------------------ Seite: Über dich
Function SeiteUeberDich
  ${If} $Art != "neu"
    Abort
  ${EndIf}
  !insertmacro MUI_HEADER_TEXT "$(T_DU_KOPF)" "$(T_DU_UNTER)"
  nsDialogs::Create 1018
  Pop $Dlg
  ${NSD_CreateLabel} 0 0 140u 10u "$(T_DU_NAME)"
  Pop $0
  ${NSD_CreateText} 0 11u 140u 12u "$NameW"
  Pop $hName
  ${NSD_SetTextLimit} $hName 40
  ${NSD_CreateLabel} 155u 0 145u 10u "$(T_DU_RUF)"
  Pop $0
  ${NSD_CreateText} 155u 11u 145u 12u "$Rufname"
  Pop $hRuf
  ${NSD_SetTextLimit} $hRuf 40
  ${NSD_CreateLabel} 0 27u 100% 10u "$(T_DU_AUSSPRACHE)"
  Pop $0
  ${NSD_CreateText} 0 38u 140u 12u "$Aussprache"
  Pop $hAussprache
  ${NSD_SetTextLimit} $hAussprache 40
  ${NSD_CreateLabel} 155u 40u 145u 10u "$(T_DU_AUSSPRACHE_BSP)"
  Pop $0
  ${NSD_CreateLabel} 0 56u 90u 10u "$(T_DU_SPRACHE)"
  Pop $0
  ${NSD_CreateDropList} 0 67u 90u 60u ""
  Pop $hSprache
  ${NSD_CB_AddString} $hSprache "Deutsch"
  ${NSD_CB_AddString} $hSprache "English"
  !insertmacro Auswahl $hSprache $Sprache
  ${NSD_CreateLabel} 100u 56u 80u 10u "$(T_DU_ANREDE)"
  Pop $0
  ${NSD_CreateDropList} 100u 67u 80u 60u ""
  Pop $hAnrede
  ${NSD_CB_AddString} $hAnrede "$(T_ANREDE_DU)"
  ${NSD_CB_AddString} $hAnrede "$(T_ANREDE_SIE)"
  !insertmacro Auswahl $hAnrede $Anrede
  ${NSD_CreateLabel} 190u 56u 110u 10u "$(T_DU_TECHNIK)"
  Pop $0
  ${NSD_CreateDropList} 190u 67u 110u 60u ""
  Pop $hTechnik
  ${NSD_CB_AddString} $hTechnik "$(T_TECHNIK1)"
  ${NSD_CB_AddString} $hTechnik "$(T_TECHNIK2)"
  ${NSD_CB_AddString} $hTechnik "$(T_TECHNIK3)"
  !insertmacro Auswahl $hTechnik $Technik
  ${NSD_CreateLabel} 0 85u 100% 10u "$(T_DU_PERS)"
  Pop $0
  ${NSD_CreateDropList} 0 96u 100% 70u ""
  Pop $hPers
  ${NSD_CB_AddString} $hPers "$(T_PERS1)"
  ${NSD_CB_AddString} $hPers "$(T_PERS2)"
  ${NSD_CB_AddString} $hPers "$(T_PERS3)"
  ${NSD_CB_AddString} $hPers "$(T_PERS4)"
  !insertmacro Auswahl $hPers $Persoenlichkeit
  ${NSD_CreateLabel} 0 115u 100% 25u "$(T_DU_HAUSHALT)"
  Pop $0
  ${NSD_SetFocus} $hName
  nsDialogs::Show
FunctionEnd

Function SeiteUeberDichEnde
  ${NSD_GetText} $hName $NameW
  ${NSD_GetText} $hRuf $Rufname
  ${NSD_GetText} $hAussprache $Aussprache
  ${NSD_GetText} $hSprache $Sprache
  ${NSD_GetText} $hAnrede $Anrede
  ${NSD_GetText} $hTechnik $Technik
  ${NSD_GetText} $hPers $Persoenlichkeit
  ${If} $Rufname == ""
    StrCpy $Rufname $NameW
  ${EndIf}
FunctionEnd

; ------------------------------------------------------------------ Seite: Fähigkeiten
Function SeiteFaehigkeiten
  ${If} $Art != "neu"
    Abort
  ${EndIf}
  !insertmacro MUI_HEADER_TEXT "$(T_FAEH_KOPF)" "$(T_FAEH_UNTER)"
  nsDialogs::Create 1018
  Pop $Dlg
  ${NSD_CreateLabel} 0 0 100% 20u "$(T_FAEH_TEXT)"
  Pop $0
  ${NSD_CreateCheckBox} 0 24u 145u 11u "$(T_F1)"
  Pop $hF1
  ${NSD_CreateCheckBox} 0 38u 145u 11u "$(T_F2)"
  Pop $hF2
  ${NSD_CreateCheckBox} 0 52u 145u 11u "$(T_F3)"
  Pop $hF3
  ${NSD_CreateCheckBox} 0 66u 145u 11u "$(T_F4)"
  Pop $hF4
  ${NSD_CreateCheckBox} 0 80u 145u 11u "$(T_F5)"
  Pop $hF5
  ${NSD_CreateCheckBox} 0 94u 145u 11u "$(T_F6)"
  Pop $hF6
  ${NSD_CreateCheckBox} 155u 24u 145u 11u "$(T_F7)"
  Pop $hF7
  ${NSD_CreateCheckBox} 155u 38u 145u 11u "$(T_F8)"
  Pop $hF8
  ${NSD_CreateCheckBox} 155u 52u 145u 11u "$(T_F9)"
  Pop $hF9
  ${NSD_CreateCheckBox} 155u 66u 145u 11u "$(T_F10)"
  Pop $hF10
  ${NSD_CreateCheckBox} 155u 80u 145u 11u "$(T_F11)"
  Pop $hF11
  ${NSD_CreateCheckBox} 155u 94u 145u 11u "$(T_F12)"
  Pop $hF12
  !insertmacro Ankreuzen $hF1 $F1
  !insertmacro Ankreuzen $hF2 $F2
  !insertmacro Ankreuzen $hF3 $F3
  !insertmacro Ankreuzen $hF4 $F4
  !insertmacro Ankreuzen $hF5 $F5
  !insertmacro Ankreuzen $hF6 $F6
  !insertmacro Ankreuzen $hF7 $F7
  !insertmacro Ankreuzen $hF8 $F8
  !insertmacro Ankreuzen $hF9 $F9
  !insertmacro Ankreuzen $hF10 $F10
  !insertmacro Ankreuzen $hF11 $F11
  !insertmacro Ankreuzen $hF12 $F12
  ${NSD_CreateLabel} 0 114u 100% 20u "$(T_FAEH_FEHLT)"
  Pop $0
  nsDialogs::Show
FunctionEnd

!macro Faehigkeit WERT NAME TEXT
  ${If} ${WERT} == 1
    StrCpy $Faehigkeiten "$Faehigkeiten${NAME},"
    StrCpy $FaehText "$FaehText${TEXT}, "
  ${EndIf}
!macroend

Function SeiteFaehigkeitenEnde
  !insertmacro Lesen $hF1 $F1
  !insertmacro Lesen $hF2 $F2
  !insertmacro Lesen $hF3 $F3
  !insertmacro Lesen $hF4 $F4
  !insertmacro Lesen $hF5 $F5
  !insertmacro Lesen $hF6 $F6
  !insertmacro Lesen $hF7 $F7
  !insertmacro Lesen $hF8 $F8
  !insertmacro Lesen $hF9 $F9
  !insertmacro Lesen $hF10 $F10
  !insertmacro Lesen $hF11 $F11
  !insertmacro Lesen $hF12 $F12
  StrCpy $Faehigkeiten ""
  StrCpy $FaehText ""
  !insertmacro Faehigkeit $F1 "kalender" "$(T_F1)"
  !insertmacro Faehigkeit $F2 "einkauf_aufgaben" "$(T_F2)"
  !insertmacro Faehigkeit $F3 "smart_home" "$(T_F3)"
  !insertmacro Faehigkeit $F4 "musik" "$(T_F4)"
  !insertmacro Faehigkeit $F5 "nachrichten" "$(T_F5)"
  !insertmacro Faehigkeit $F6 "sport" "$(T_F6)"
  !insertmacro Faehigkeit $F7 "unterwegs" "$(T_F7)"
  !insertmacro Faehigkeit $F8 "medien" "$(T_F8)"
  !insertmacro Faehigkeit $F9 "pc_steuerung" "$(T_F9)"
  !insertmacro Faehigkeit $F10 "email_lesen" "$(T_F10)"
  !insertmacro Faehigkeit $F11 "energie" "$(T_F11)"
  !insertmacro Faehigkeit $F12 "briefings" "$(T_F12)"
  StrCpy $PcSteuerung $F9
FunctionEnd

; ------------------------------------------------------------------ Seite: Vorhaben
Function SeiteVorhaben
  ${If} $Art != "neu"
    Abort
  ${EndIf}
  !insertmacro MUI_HEADER_TEXT "$(T_VOR_KOPF)" "$(T_VOR_UNTER)"
  nsDialogs::Create 1018
  Pop $Dlg
  ${NSD_CreateLabel} 0 0 100% 30u "$(T_VOR_TEXT)"
  Pop $0
  !insertmacro Textfeld 0 32u 100% 88u "$Vorhaben"
  Pop $hVorhaben
  ${NSD_SetTextLimit} $hVorhaben 1000
  ${NSD_CreateLabel} 0 124u 100% 12u "$(T_VOR_GRENZE)"
  Pop $0
  ${NSD_SetFocus} $hVorhaben
  nsDialogs::Show
FunctionEnd

Function SeiteVorhabenEnde
  ${NSD_GetText} $hVorhaben $Vorhaben
FunctionEnd

; ------------------------------------------------------------------ Seite: Geräte und Start
Function SeiteGeraete
  ${If} $Art != "neu"
    Abort
  ${EndIf}
  !insertmacro MUI_HEADER_TEXT "$(T_GER_KOPF)" "$(T_GER_UNTER)"
  nsDialogs::Create 1018
  Pop $Dlg
  ${NSD_CreateLabel} 0 0 100% 10u "$(T_GER_WOHNORT)"
  Pop $0
  ${NSD_CreateDropList} 0 11u 100% 60u ""
  Pop $hWohnort
  ${NSD_CB_AddString} $hWohnort "$(T_WOHN1)"
  ${NSD_CB_AddString} $hWohnort "$(T_WOHN2)"
  ${NSD_CB_AddString} $hWohnort "$(T_WOHN3)"
  !insertmacro Auswahl $hWohnort $Wohnort
  ${NSD_CreateLabel} 0 28u 100% 10u "$(T_GER_GEHIRN)"
  Pop $0
  ${NSD_CreateDropList} 0 39u 100% 70u ""
  Pop $hGehirn
  ${NSD_CB_AddString} $hGehirn "$(T_GEHIRN1)"
  ${NSD_CB_AddString} $hGehirn "$(T_GEHIRN2)"
  ${NSD_CB_AddString} $hGehirn "$(T_GEHIRN3)"
  ${NSD_CB_AddString} $hGehirn "$(T_WEISS_NICHT)"
  !insertmacro Auswahl $hGehirn $Gehirn
  ${NSD_CreateLabel} 0 56u 145u 10u "$(T_GER_HANDY)"
  Pop $0
  ${NSD_CreateDropList} 0 67u 145u 60u ""
  Pop $hHandy
  ${NSD_CB_AddString} $hHandy "$(T_HANDY1)"
  ${NSD_CB_AddString} $hHandy "$(T_HANDY2)"
  ${NSD_CB_AddString} $hHandy "$(T_KEINE)"
  !insertmacro Auswahl $hHandy $Handy
  ${NSD_CreateLabel} 155u 56u 145u 10u "$(T_GER_UNTERWEGS)"
  Pop $0
  ${NSD_CreateDropList} 155u 67u 145u 70u ""
  Pop $hUnterwegs
  ${NSD_CB_AddString} $hUnterwegs "$(T_UNTERWEGS1)"
  ${NSD_CB_AddString} $hUnterwegs "$(T_UNTERWEGS2)"
  ${NSD_CB_AddString} $hUnterwegs "$(T_UNTERWEGS3)"
  ${NSD_CB_AddString} $hUnterwegs "$(T_WEISS_NICHT)"
  !insertmacro Auswahl $hUnterwegs $Unterwegs
  ${NSD_CreateCheckBox} 0 88u 100% 11u "$(T_GER_SPRACHE)"
  Pop $hPcSprache
  !insertmacro Ankreuzen $hPcSprache $PcSprache
  ${NSD_CreateCheckBox} 0 101u 100% 11u "$(T_GER_AUTOSTART)"
  Pop $hAutostart
  !insertmacro Ankreuzen $hAutostart $Autostart
  ${NSD_CreateCheckBox} 0 114u 100% 11u "$(T_DESKTOP)"
  Pop $hDesktop
  !insertmacro Ankreuzen $hDesktop $DesktopSym
  nsDialogs::Show
FunctionEnd

Function SeiteGeraeteEnde
  ${NSD_GetText} $hWohnort $Wohnort
  ${NSD_GetText} $hGehirn $Gehirn
  ${NSD_GetText} $hHandy $Handy
  ${NSD_GetText} $hUnterwegs $Unterwegs
  !insertmacro Lesen $hPcSprache $PcSprache
  !insertmacro Lesen $hAutostart $Autostart
  !insertmacro Lesen $hDesktop $DesktopSym
FunctionEnd

; ------------------------------------------------------------------ Seite: Jarvis aufs Handy
; Nur wenn im Schritt davor die Android-App gewaehlt wurde. Der Code fuehrt auf die APK im neuesten GitHub-Release
; (APP_URL aus bauen.sh, dieselbe Adresse wie der Link). Gekoppelt wird spaeter: Sobald die Bruecke laeuft, zeigt Claude
; einen zweiten Code (Bauanleitung, Baustein "Android-App").
Function SeiteApp
  ${If} $Art != "neu"
    Abort
  ${EndIf}
  StrCpy $0 $Handy 7
  ${If} $0 != "Android"
    Abort
  ${EndIf}
  !insertmacro MUI_HEADER_TEXT "$(T_APP_KOPF)" "$(T_APP_UNTER)"
  nsDialogs::Create 1018
  Pop $Dlg
  InitPluginsDir
  File "/oname=$PLUGINSDIR\app-qr.bmp" "dateien\app-qr.bmp"
  ${NSD_CreateBitmap} 0 0 110u 110u ""
  Pop $hQr
  ${NSD_SetImage} $hQr "$PLUGINSDIR\app-qr.bmp" $hQrBild
  ${NSD_CreateLabel} 120u 0 180u 80u "$(T_APP_TEXT)"
  Pop $0
  ${NSD_CreateLink} 120u 86u 180u 12u "$(T_APP_LINK)"
  Pop $0
  ${NSD_OnClick} $0 AppLinkOeffnen
  nsDialogs::Show
  ${NSD_FreeImage} $hQrBild
FunctionEnd

Function AppLinkOeffnen
  ExecShell "open" "${APP_URL}"
FunctionEnd

Function SeiteAppEnde
FunctionEnd

; ------------------------------------------------------------------ Seite: Deine Oberflaeche
; Was im Jarvis-Fenster stehen soll. Claude baut daraus die Oberflaeche (Bauanleitung, Runde 6a): nur die gewaehlten
; Bereiche, persoenliche Begruessung, eigene Schnellaktionen. Vorauswahl passt zu den gewaehlten Faehigkeiten.
Function SeiteOberflaeche
  ${If} $Art != "neu"
    Abort
  ${EndIf}
  ${If} $OGezeigt == 0
    StrCpy $OGezeigt 1
    StrCpy $O1 1
    StrCpy $O2 0
    ${If} $F3 == 1
    ${OrIf} $F11 == 1
      StrCpy $O2 1
    ${EndIf}
    StrCpy $O3 $F1
    StrCpy $O4 $F5
    StrCpy $O5 $F5
    StrCpy $O6 1
    StrCpy $O7 1
    StrCpy $O8 1
    StrCpy $O9 1
    StrCpy $O10 1
    ${If} $Untertitel == ""
    ${AndIf} $Rufname != ""
      StrCpy $Untertitel "$(T_ZUHAUSE_RUF)"
    ${ElseIf} $Untertitel == ""
    ${AndIf} $NameW != ""
      StrCpy $Untertitel "$(T_ZUHAUSE_NAME)"
    ${EndIf}
  ${EndIf}
  !insertmacro MUI_HEADER_TEXT "$(T_OB_KOPF)" "$(T_OB_UNTER)"
  nsDialogs::Create 1018
  Pop $Dlg
  ${NSD_CreateLabel} 0 0 145u 10u "$(T_OB_DESIGN)"
  Pop $0
  ${NSD_CreateDropList} 0 11u 145u 70u ""
  Pop $hDesign
  ${NSD_CB_AddString} $hDesign "$(T_DESIGN1)"
  ${NSD_CB_AddString} $hDesign "$(T_DESIGN2)"
  ${NSD_CB_AddString} $hDesign "$(T_DESIGN3)"
  ${NSD_CB_AddString} $hDesign "$(T_DESIGN4)"
  ${NSD_CB_AddString} $hDesign "$(T_DESIGN5)"
  !insertmacro Auswahl $hDesign $Design
  ${NSD_CreateLabel} 155u 0 145u 10u "$(T_OB_UNTERTITEL)"
  Pop $0
  ${NSD_CreateText} 155u 11u 145u 12u "$Untertitel"
  Pop $hUntertitel
  ${NSD_SetTextLimit} $hUntertitel 60
  ${NSD_CreateLabel} 0 29u 100% 10u "$(T_OB_HAUPT)"
  Pop $0
  ${NSD_CreateCheckBox} 0 41u 145u 11u "$(T_O1)"
  Pop $hO1
  ${NSD_CreateCheckBox} 0 53u 145u 11u "$(T_O2)"
  Pop $hO2
  ${NSD_CreateCheckBox} 0 65u 145u 11u "$(T_F1)"
  Pop $hO3
  ${NSD_CreateCheckBox} 0 77u 145u 11u "$(T_O4)"
  Pop $hO4
  ${NSD_CreateCheckBox} 0 89u 145u 11u "$(T_O5)"
  Pop $hO5
  ${NSD_CreateCheckBox} 155u 41u 145u 11u "$(T_O6)"
  Pop $hO6
  ${NSD_CreateCheckBox} 155u 53u 145u 11u "$(T_O7)"
  Pop $hO7
  ${NSD_CreateCheckBox} 155u 65u 145u 11u "$(T_O8)"
  Pop $hO8
  ${NSD_CreateCheckBox} 155u 77u 145u 11u "$(T_O9)"
  Pop $hO9
  ${NSD_CreateCheckBox} 155u 89u 145u 11u "$(T_O10)"
  Pop $hO10
  !insertmacro Ankreuzen $hO1 $O1
  !insertmacro Ankreuzen $hO2 $O2
  !insertmacro Ankreuzen $hO3 $O3
  !insertmacro Ankreuzen $hO4 $O4
  !insertmacro Ankreuzen $hO5 $O5
  !insertmacro Ankreuzen $hO6 $O6
  !insertmacro Ankreuzen $hO7 $O7
  !insertmacro Ankreuzen $hO8 $O8
  !insertmacro Ankreuzen $hO9 $O9
  !insertmacro Ankreuzen $hO10 $O10
  ${NSD_CreateLabel} 0 105u 100% 10u "$(T_OB_WUENSCHE)"
  Pop $0
  ${NSD_CreateText} 0 116u 100% 12u "$Wuensche"
  Pop $hWuensche
  ${NSD_SetTextLimit} $hWuensche 300
  nsDialogs::Show
FunctionEnd

!macro Bereich WERT NAME TEXT
  ${If} ${WERT} == 1
    StrCpy $Bereiche "$Bereiche${NAME},"
    StrCpy $BereichText "$BereichText${TEXT}, "
  ${EndIf}
!macroend

Function SeiteOberflaecheEnde
  ${NSD_GetText} $hDesign $Design
  ${NSD_GetText} $hUntertitel $Untertitel
  ${NSD_GetText} $hWuensche $Wuensche
  !insertmacro Lesen $hO1 $O1
  !insertmacro Lesen $hO2 $O2
  !insertmacro Lesen $hO3 $O3
  !insertmacro Lesen $hO4 $O4
  !insertmacro Lesen $hO5 $O5
  !insertmacro Lesen $hO6 $O6
  !insertmacro Lesen $hO7 $O7
  !insertmacro Lesen $hO8 $O8
  !insertmacro Lesen $hO9 $O9
  !insertmacro Lesen $hO10 $O10
  StrCpy $Bereiche ""
  StrCpy $BereichText ""
  !insertmacro Bereich $O1 "systeme" "$(T_O1)"
  !insertmacro Bereich $O2 "haus" "$(T_O2)"
  !insertmacro Bereich $O3 "kalender" "$(T_F1)"
  !insertmacro Bereich $O4 "welt" "$(T_O4)"
  !insertmacro Bereich $O5 "laufband" "$(T_O5)"
  !insertmacro Bereich $O6 "wetter" "$(T_O6)"
  !insertmacro Bereich $O7 "verbindungen" "$(T_O7)"
  !insertmacro Bereich $O8 "gespraech" "$(T_O8)"
  !insertmacro Bereich $O9 "aktionen" "$(T_O9)"
  !insertmacro Bereich $O10 "begruessung" "$(T_O10)"
FunctionEnd

; ------------------------------------------------------------------ Seite: Zusammenfassung
!macro JaNein WERT ZIEL
  ${If} ${WERT} == 1
    StrCpy ${ZIEL} "$(T_JA)"
  ${Else}
    StrCpy ${ZIEL} "$(T_NEIN)"
  ${EndIf}
!macroend

Function SeiteZusammenfassung
  Call OrdnerNachher
  !insertmacro MUI_HEADER_TEXT "$(T_ZUS_KOPF)" "$(T_ZUS_UNTER)"
  nsDialogs::Create 1018
  Pop $Dlg
  !insertmacro JaNein $Autostart $3
  !insertmacro JaNein $DesktopSym $4
  !insertmacro JaNein $PcSteuerung $5
  ${If} $Art == "verbinden"
    StrCpy $0 "$(T_ZUS_VERB)"
  ${Else}
    !insertmacro JaNein $PcSprache $6
    StrCpy $1 $Vorhaben 200
    ${If} $1 != $Vorhaben
      StrCpy $1 "$1 …"
    ${EndIf}
    ${If} $1 == ""
      StrCpy $1 "$(T_ZUS_NICHTS)"
    ${EndIf}
    StrCpy $FaehAnzeige $FaehText -2          ; letztes ", " weg
    StrCpy $BereichAnzeige $BereichText -2
    StrCpy $7 ""
    ${If} $Aussprache != ""
      StrCpy $7 "$(T_ZUS_AUSSPRACHE)"
    ${EndIf}
    StrCpy $0 "$(T_ZUS_NEU)"
  ${EndIf}
  !insertmacro Textfeld 0 0 100% 100% "$0"
  Pop $1
  ${NSD_Edit_SetReadOnly} $1 1
  nsDialogs::Show
FunctionEnd

; ------------------------------------------------------------------ Installation
Function AntwortenSchreiben
  StrCpy $9 "$INSTDIR\einrichtung\antworten.ini"
  ; leere Datei mit UTF-16-Kennung, damit Windows die INI in Unicode schreibt (Umlaute, Sonderzeichen)
  FileOpen $0 $9 w
  FileWriteWord $0 0xFEFF
  FileClose $0
  ${WordReplace} "$Vorhaben" "$\r$\n" "\n" "+" $1
  WriteINIStr $9 "jarvis" "art" $Art
  WriteINIStr $9 "jarvis" "setup_version" "${VERSION}"
  ${If} $LANGUAGE == ${LANG_ENGLISH}
    WriteINIStr $9 "jarvis" "setup_sprache" "en"
  ${Else}
    WriteINIStr $9 "jarvis" "setup_sprache" "de"
  ${EndIf}
  WriteINIStr $9 "jarvis" "name" $NameW
  WriteINIStr $9 "jarvis" "autostart" $Autostart
  WriteINIStr $9 "jarvis" "desktop_symbol" $DesktopSym
  WriteINIStr $9 "jarvis" "pc_steuerung" $PcSteuerung
  ${If} $Art == "verbinden"
    WriteINIStr $9 "jarvis" "bruecke" $Bruecke
    WriteINIStr $9 "jarvis" "code" $Code
  ${Else}
    WriteINIStr $9 "jarvis" "rufname" $Rufname
    WriteINIStr $9 "jarvis" "aussprache" $Aussprache
    WriteINIStr $9 "jarvis" "sprache" $Sprache
    ${If} $Anrede == "$(T_ANREDE_SIE)"
      WriteINIStr $9 "jarvis" "anrede" "Sie"
    ${Else}
      WriteINIStr $9 "jarvis" "anrede" "Du"
    ${EndIf}
    WriteINIStr $9 "jarvis" "technik" $Technik
    WriteINIStr $9 "jarvis" "persoenlichkeit" $Persoenlichkeit
    WriteINIStr $9 "jarvis" "faehigkeiten" $Faehigkeiten
    WriteINIStr $9 "jarvis" "vorhaben" $1
    WriteINIStr $9 "jarvis" "wohnort" $Wohnort
    WriteINIStr $9 "jarvis" "gehirn" $Gehirn
    WriteINIStr $9 "jarvis" "handy" $Handy
    WriteINIStr $9 "jarvis" "unterwegs" $Unterwegs
    WriteINIStr $9 "jarvis" "pc_sprache" $PcSprache
    WriteINIStr $9 "jarvis" "oberflaeche_design" $Design
    WriteINIStr $9 "jarvis" "oberflaeche_untertitel" $Untertitel
    WriteINIStr $9 "jarvis" "oberflaeche_bereiche" $Bereiche
    WriteINIStr $9 "jarvis" "oberflaeche_wuensche" $Wuensche
  ${EndIf}
  FlushINI $9
FunctionEnd

Section "Jarvis"
  Call OrdnerNachher
  SetOutPath "$INSTDIR\einrichtung"
  ; Marke: diesen Ordner hat das Setup angelegt, nur dann loescht die Deinstallation ihn ganz
  FileOpen $0 "$INSTDIR\.jarvis-client" w
  FileWrite $0 "Angelegt vom J.A.R.V.I.S.-Setup. Die Deinstallation entfernt diesen Ordner ganz.$\r$\n"
  FileClose $0
  File "dateien\einrichten.ps1"
  File "dateien\entfernen.ps1"
  File "dateien\EINRICHTUNG.md"
  File "dateien\EINRICHTUNG.en.md"
  File "dateien\jarvis_pc.py"
  File "dateien\jarvis.ico"
  File "dateien\hud.html"
  File "dateien\oberflaeche.py"
  File "dateien\verhalten.py"
  File "dateien\app.html"
  File "dateien\jarvis-web.js"
  File "dateien\webapp_bauen.py"
  File "dateien\jarvis.png"
  File "dateien\test_oberflaeche.py"
  File "dateien\test_verhalten.py"
  File "dateien\pakete.txt"
  File "dateien\weckwort.txt"
  Call AntwortenSchreiben

  WriteUninstaller "$INSTDIR\Deinstallieren.exe"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayName" "J.A.R.V.I.S."
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINST_KEY}" "Publisher" "Jarvis-Projekt"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\einrichtung\jarvis.ico"
  WriteRegStr HKCU "${UNINST_KEY}" "UninstallString" '"$INSTDIR\Deinstallieren.exe"'
  WriteRegStr HKCU "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair" 1

  DetailPrint "$(T_DETAIL_FENSTER)"
  ; 64-Bit-PowerShell, nicht die 32-Bit-Kopie aus SysWOW64 (das Setup selbst ist 32 Bit)
  ${If} ${RunningX64}
    ${DisableX64FSRedirection}
  ${EndIf}
  Delete "$INSTDIR\einrichtung\fertig.ok"
  ExecWait '"${POWERSHELL}" -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\einrichtung\einrichten.ps1" -Ini "$INSTDIR\einrichtung\antworten.ini"' $Ergebnis
  ${If} ${RunningX64}
    ${EnableX64FSRedirection}
  ${EndIf}
  DetailPrint "$(T_DETAIL_ENDE)"

  ${IfNot} ${FileExists} "$INSTDIR\einrichtung\fertig.ok"
  ${AndIf} $Ergebnis == 0
    StrCpy $Ergebnis "-1"
  ${EndIf}
  ${If} $Ergebnis != 0
    StrCpy $FertigTitel "$(T_FEHL_TITEL)"
    StrCpy $FertigText "$(T_FEHL_TEXT)"
  ${ElseIf} $Art == "verbinden"
    StrCpy $FertigTitel "$(T_VERB_TITEL)"
    StrCpy $FertigText "$(T_VERB_TEXT)"
  ${Else}
    StrCpy $FertigTitel "$(T_NEU_TITEL)"
    StrCpy $FertigText "$(T_NEU_TEXT)"
  ${EndIf}
SectionEnd

; ------------------------------------------------------------------ Deinstallation
Function un.onInit
  !insertmacro MUI_UNGETLANGUAGE
FunctionEnd

Section "Uninstall"
  StrCpy $2 "de"
  ${If} $LANGUAGE == ${LANG_ENGLISH}
    StrCpy $2 "en"
  ${EndIf}
  ${If} ${RunningX64}
    ${DisableX64FSRedirection}
  ${EndIf}
  ${If} ${FileExists} "$INSTDIR\einrichtung\entfernen.ps1"
    ExecWait '"${POWERSHELL}" -NoProfile -ExecutionPolicy Bypass -File "$INSTDIR\einrichtung\entfernen.ps1" -Sprache $2'
  ${EndIf}
  ${If} ${RunningX64}
    ${EnableX64FSRedirection}
  ${EndIf}
  DeleteRegKey HKCU "${UNINST_KEY}"
  Delete "$INSTDIR\Deinstallieren.exe"
  ; Ganz loeschen nur einen Ordner namens Jarvis mit der Marke des Setups (oder den Vorgabeordner), nie den
  ; Projektordner eines neuen Jarvis; sonst nur die eigenen Teile (Pruefbericht 25.10.2026)
  StrCpy $0 $INSTDIR "" -7
  StrCpy $1 "0"
  ${If} $0 == "\Jarvis"
  ${AndIf} $INSTDIR != "$PROFILE\Jarvis"
    ${If} ${FileExists} "$INSTDIR\.jarvis-client"
    ${OrIf} $INSTDIR == "$LOCALAPPDATA\Jarvis"
      StrCpy $1 "1"
    ${EndIf}
  ${EndIf}
  ${If} $1 == "1"
    RMDir /r "$INSTDIR"
  ${Else}
    Delete "$INSTDIR\.jarvis-client"
    RMDir /r "$INSTDIR\einrichtung"
    RMDir /r "$INSTDIR\venv"
    RMDir /r "$INSTDIR\modelle"
    Delete "$INSTDIR\jarvis_pc.py"
    Delete "$INSTDIR\einstellungen.json"
    Delete "$INSTDIR\jarvis*.log"
    Delete "$INSTDIR\jarvis*.ico"
    RMDir "$INSTDIR"
  ${EndIf}
  ${If} ${FileExists} "$PROFILE\Jarvis\*.*"
    MessageBox MB_YESNO|MB_ICONQUESTION|MB_DEFBUTTON2 "$(T_PROJEKT_LOESCHEN)" IDYES projekt_loeschen
    Goto ende
    projekt_loeschen:
      RMDir /r "$PROFILE\Jarvis"
    ende:
  ${EndIf}
SectionEnd
