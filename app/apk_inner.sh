#!/bin/sh
# Laeuft im JDK-Container (bauen.sh). Bau ohne Gradle, deshalb keine Lambdas im Java-Code.
set -e
BT=/sdk/build-tools/34.0.0
JAR=/sdk/platforms/android-34/android.jar
O=/arbeit/build/apk
mkdir -p "$HOME"
rm -rf "$O" && mkdir -p "$O/res" "$O/gen" "$O/obj" "$O/dex" dist
"$BT/aapt2" compile --dir android/res -o "$O/res/res.zip"
"$BT/aapt2" link -o "$O/base.apk" -I "$JAR" --manifest android/AndroidManifest.xml -A android/assets --java "$O/gen" "$O/res/res.zip"
javac -nowarn -source 8 -target 8 -bootclasspath "$JAR" -d "$O/obj" \
  $(find "$O/gen" android/java -name '*.java') > "$O/javac.log" 2>&1 || { cat "$O/javac.log"; exit 1; }
"$BT/d8" --min-api 26 --output "$O/dex" $(find "$O/obj" -name '*.class')
cp "$O/base.apk" "$O/unsigned.apk"
( cd "$O/dex" && "$BT/aapt" add ../unsigned.apk classes.dex > /dev/null )
"$BT/zipalign" -f 4 "$O/unsigned.apk" "$O/aligned.apk"
"$BT/apksigner" sign --ks /signing/schluessel.jks --ks-key-alias "$ALIAS" --ks-pass file:/signing/pass \
  --out dist/Jarvis-App.apk "$O/aligned.apk"
"$BT/apksigner" verify --print-certs dist/Jarvis-App.apk | grep -E 'Signer #1 certificate SHA-256' || true
