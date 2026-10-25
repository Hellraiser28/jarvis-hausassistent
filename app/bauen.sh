#!/bin/sh
# Jarvis-App selbst bauen (nur fuer eigene Aenderungen; die fertige App liegt in jedem Release).
#   ANDROID_SDK=/pfad/zum/sdk SCHLUESSEL=/pfad/zu/schluessel.jks SCHLUESSEL_ALIAS=jarvis \
#   SCHLUESSEL_PASS_DATEI=/pfad/zur/passwortdatei app/bauen.sh
# Das SDK braucht build-tools/34.0.0 und platforms/android-34. Gebaut wird ohne Gradle in einem kurzlebigen
# JDK-Container (aapt2, javac, d8, apksigner). Ergebnis: app/dist/Jarvis-App.apk
# Ein eigener Schluessel heisst: Updates aus dem Projekt lassen sich nicht mehr einspielen (Android verlangt denselben
# Schluessel). Schluessel sichern und nie neu erzeugen.
set -eu
HIER=$(cd "$(dirname "$0")" && pwd)
DOCKER=${DOCKER:-docker}
: "${ANDROID_SDK:?ANDROID_SDK fehlt}" "${SCHLUESSEL:?SCHLUESSEL fehlt}" "${SCHLUESSEL_PASS_DATEI:?SCHLUESSEL_PASS_DATEI fehlt}"
SCHLUESSEL_ALIAS=${SCHLUESSEL_ALIAS:-jarvis}
$DOCKER run --rm --user "$(id -u):$(id -g)" -e HOME=/arbeit/build/home -e ALIAS="$SCHLUESSEL_ALIAS" \
  -v "$HIER":/arbeit -v "$ANDROID_SDK":/sdk:ro -v "$SCHLUESSEL":/signing/schluessel.jks:ro \
  -v "$SCHLUESSEL_PASS_DATEI":/signing/pass:ro -w /arbeit eclipse-temurin:17-jdk sh apk_inner.sh
ls -l "$HIER/dist/Jarvis-App.apk"
sha256sum "$HIER/dist/Jarvis-App.apk"
