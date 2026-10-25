# Jarvis app (Android)

The finished app is in every release as `Jarvis-App.apk`, plus `Jarvis-App.json` with version number and SHA-256.
The setup shows a QR code pointing to the latest version. This folder holds the source code.

## How it works

- A WebView with the interface `android/assets/app.html` and a small Java layer
  (`android/java/…/MainActivity.java`): the phone's speech recognition, voice output via the bridge, real-time mode via
  Gemini Live, update button.
- **No fixed addresses.** The home-network address and remote access come from pairing: via the pairing link
  `jarvis://koppeln?adresse=…&code=…` from your bridge's pairing page, or by typing them in. The app accepts http only
  for addresses in the local network (private IPv4, Tailscale, `*.local`), otherwise only https.
- Before the app sends its token on the home network, the bridge proves that it knows the token (HMAC over a
  random number).
- **Appearance from the bridge:** color, buttons, greeting and start lines come with the state
  (`oberflaeche`). An app update doesn't overwrite them.
- **Updates** from the latest GitHub release, checked via SHA-256. Android only installs what is signed with the
  same key.
- `android/assets/vorgaben.json` (defaults) controls this build: leave it empty for pairing via link; `update_github`
  points to this project. If your version lives on Forgejo or Gitea, also set `update_api` to their API, such as
  `https://forgejo.example.org/api/v1` (https only; the default is GitHub).

## Verifying it's genuine

The app in the releases is signed with this project's key (`CN=Jarvis Hausassistent, O=Hellraiser28`).
Certificate fingerprint (SHA-256):

```
98:2C:5F:E6:33:CF:91:4D:86:C6:F2:DA:77:EA:A5:A3:0E:67:48:56:27:07:B5:51:02:EA:82:3A:D1:E4:36:D1
```

Check it with `apksigner verify --print-certs Jarvis-App.apk` (Android SDK) or `keytool -printcert -jarfile
Jarvis-App.apk` (Java). If you see a different fingerprint, the file does not come from this project.

## Building it yourself

Only needed if you change the app. With your own key, updates from this project can no longer be installed
afterwards.

```sh
ANDROID_SDK=/pfad/zum/sdk SCHLUESSEL=/pfad/zu/schluessel.jks SCHLUESSEL_ALIAS=jarvis \
SCHLUESSEL_PASS_DATEI=/pfad/zur/passwortdatei app/bauen.sh
```

(`SCHLUESSEL` = keystore, `SCHLUESSEL_PASS_DATEI` = file containing the keystore password; replace the `/pfad/...`
placeholders with your own paths.)

The SDK needs `build-tools/34.0.0` and `platforms/android-34`. The build runs without Gradle in a JDK container.
That is why the Java code must not contain any lambdas.
