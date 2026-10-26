# Security

## Trust boundary

Jarvis is built for **one home**. The trust boundary is your own home network or a VPN (e.g. Tailscale
or WireGuard). The bridge, through which all devices talk to the brain, never listens openly on the internet:

- only on 127.0.0.1 and the addresses your own devices come from
- the main token is only valid from 127.0.0.1; every other device has its own, revocable device token
- from outside the home only via VPN or via a second, hardened entry point behind a reverse proxy (only the necessary
  endpoints, only device tokens, lockout after failed attempts)

## How Jarvis is built

The rules are set out in detail in `EINRICHTUNG.md` (Phase 2, "Sicherheit"; English translation:
[EINRICHTUNG.en.md](EINRICHTUNG.en.md#security-non-negotiable), Phase 2, "Security (non-negotiable)"). The most
important ones:

- **Two brains.** The everyday brain has no shell and no file access, only the approved tools. A
  brain with a shell exists only if the person wants it, and only after approval.
- **Permissions depend on the token, not on the request.** Which device is speaking is in the token. Tools that act on
  the PC exist only for sources on an allow list.
- **Deny list in the tool.** What Jarvis must never touch (e.g. cameras, door locks) is blocked by the tool itself,
  not just by the instruction. Devices only via individual device IDs, never via areas or floors.
- **Third-party text is never an instruction.** Content from emails, calendars, websites and messages is data. Memory
  goes into the prompt as notes, not as instructions.
- **Sending to others only after a clear yes**, with a note that Jarvis sent the message.
- **No access to your own network by the back door:** sources added by voice only via http(s) and only
  public addresses, also after DNS resolution.
- **The app and PC client check the bridge before they send their token** (HMAC over a random number, computed with
  the hash of the token). This way, on a foreign Wi-Fi network with the same address, neither the token nor an update
  request goes to a foreign device. The web app cannot do this, see "Known limits".
- **The first pairing is protected too** (since 0.3.2): setup, Linux installer and app only send the pairing code once
  the other side has proven with it that it knows it (HMAC with a PBKDF2 key from the code, 200000 rounds, so an
  intercepted answer doesn't make guessing easy).
- **Appearance only via checked settings:** Jarvis changes its appearance via a dedicated tool with fixed
  keys and checked values, never via the page's code. Third-party text and routines don't change it.
- **Real-time mode can be switched off per device**, with a switch at the computer, not by voice command.
- **Settings from the gear menu** go through the same check as the tools (known keys,
  fixed values, length limits). Every paired device may change them, but buttons only devices and sources with PC rights: a
  button runs with the rights of the device it is clicked on. Undo and reset to default are always available.
- **Web app on the home network only:** the page under `/app` contains nothing secret and has a strict
  Content-Security-Policy (only the page's two scripts, by hash; connections only to the bridge; not
  embeddable). Web app devices are valid only on the home network, never via remote access and never with PC tools. The
  device token lives in the browser's storage; pairing again deletes it, revoking it at the computer invalidates it.
- **Interface without secrets:** the HUD page contains nothing personal. The PC window fetches its data with a
  token via the bridge; the local pass-through sits under a random path per start. Everything the pages
  display is escaped.
- **Test mode:** tests with the source `test…` run tools with an effect only as a dry run.
- **Secrets** never in the chat, never in Git, never in command lines. They live in files that only your own
  user account can read. The setup restricts the PC client's folder to this account (plus SYSTEM and
  Administrators), even if it lies outside the user profile.
- **Supply chain:** the setup downloads uv, the client's Python packages (including dependencies) and the wake word models
  in pinned versions and checks their SHA-256. New versions only once they are at least two weeks old.
  Exceptions: Windows-MCP is pinned only via this cut-off date (without checksums), an already installed uv is used in
  its existing version, and Claude Code and Git come in their current version from their official sources.
- **Updates:**
    - The PC client gets new versions from your own bridge, only after its proof and only with a signature. Since
      0.3.2 that is Ed25519 over version and checksum with the bridge's own key, which the client keeps from pairing;
      whoever reads the token can no longer build an update with it. If GitHub is configured, only releases with tag
      `pc-<Nummer>`, a checksum and the project's Ed25519 signature (the public key is in the client). It
      checks every six hours; `"auto_update": false` in the settings leaves only the button.
    - The release app asks GitHub for a new version (`Jarvis-App.json` with SHA-256) and downloads it only on
      tap. Android only installs what is signed with the same key.
    - The web app comes fresh from the bridge every time it is opened.

## Known limits

- **Jarvis does not tell voices apart.** Whoever speaks in the room speaks with the device's permissions. Jobs with a
  shell from speakers can therefore be switched off. Since 0.3.2, speech and real-time mode at the PC get no PC tools
  by default, because sound from the PC's own speakers (a video, a web page) counts as a speaker too. Switching it on
  means accepting exactly that.
- **A brain with a shell** can also reach blocked files. Then only instruction and approval protect against that.
- **The web app** comes via HTTP; its device token lives in the browser storage for that address. If, on a
  foreign network, a different device answers under the same address, it can read the token; a proof from the bridge
  doesn't help here, because the foreign page brings its own code. That is why web app devices are valid only on the
  home network and without PC tools. Preferably open the web app only at home. If you want more: serve the bridge
  via HTTPS under its own name (e.g. `tailscale cert`).
- **The Setup.exe is not signed.** Check the SHA-256 from the release notes before you run it.
- **Claude Code and Git** are installed by the setup in their current version from the official sources, not
  pinned.
- **PC control (Windows-MCP)** listens on port 8000 on all network adapters. It is only reachable from the
  Jarvis host: a firewall rule only for this address and only in private networks, plus an allow list and a
  separate key in Windows-MCP itself.
- What Jarvis builds, **Claude builds following this guide**. The result depends on the environment and on the
  person's decisions. The acceptance test in Phase 3 checks the most important points, but does not replace your own
  review.

## Reporting a vulnerability

Please not as a public issue. On GitHub, use "Security" → "Report a vulnerability" (private report). Say
which file is affected and how to reproduce the issue. You will get an answer as soon as someone has seen it.
This is a private project; there is no fixed response time.
