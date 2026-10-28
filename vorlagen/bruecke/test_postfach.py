#!/usr/bin/env python3
"""Einheitentests fuer bruecke/postfach.py ohne Netz (seit 0.4): IMAP-UTF-7, Kennungen, Loesch-Ziele, Text aus
HTML-Mails, Anhaenge."""
import email
import email.policy
import os
import sys
from email.message import EmailMessage

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bruecke"))
import postfach as p  # noqa: E402

ok = fehler = 0


def pruef(name, bed, info=""):
    global ok, fehler
    if bed:
        ok += 1
    else:
        fehler += 1
        print("FEHLER:", name, info)


for roh, lesbar in (("Gel&APY-scht", "Gelöscht"), ("Entw&APw-rfe", "Entwürfe"), ("A&-B", "A&B"), ("INBOX", "INBOX"),
                    ("&ZeVnLIqe-", "日本語")):
    pruef("UTF-7 lesen " + roh, p.utf7_decode(roh) == lesbar, p.utf7_decode(roh))
    pruef("UTF-7 schreiben " + lesbar, p.utf7_encode(lesbar) == roh, p.utf7_encode(lesbar))
pruef("Kennung", p._id_teilen("Münchener Versicherung:42") == ("Münchener Versicherung", 42))
pruef("Kennung mit Doppelpunkt im Ordner", p._id_teilen("A:B:7") == ("A:B", 7))
for falsch in ("ohne", "Ordner:abc", "", None):
    try:
        p._id_teilen(falsch)
        pruef("Kennung abgelehnt: %r" % falsch, False)
    except p.Fehler:
        pruef("Kennung abgelehnt: %r" % falsch, True)
for z in ("Gelöscht", "Papierkorb", "Trash", "Deleted Items"):
    pruef("Loesch-Ziel verboten: " + z, p.VERBOTEN.search(z))
for z in ("Archiv", "Spamverdacht", "Posteingang", "Rechnungen"):
    pruef("Ziel erlaubt: " + z, not p.VERBOTEN.search(z))
m = EmailMessage()
m["From"] = "=?utf-8?q?M=C3=BCller?= <m@example.org>"
m["Subject"] = "Test"
m.set_content("<html><body><p>Hallo &amp; willkommen</p><script>alert(1)</script><br>Zeile 2</body></html>", subtype="html")
m.add_attachment(b"%PDF-1.4 test", maintype="application", subtype="pdf", filename="Rechnung.pdf")
msg = email.message_from_bytes(m.as_bytes(), policy=email.policy.default)
t = p._text(msg)
pruef("HTML zu Text", "Hallo & willkommen" in t and "Zeile 2" in t and "alert" not in t and "<" not in t, t)
a = p._anhaenge(msg)
pruef("Anhang erkannt", len(a) == 1 and a[0]["name"] == "Rechnung.pdf" and a[0]["roh"].startswith(b"%PDF"), a)
pruef("Kopfzeile dekodiert", p._dekodiere(m["From"]).startswith("Müller"))
print("Postfach: %d ok, %d Fehler" % (ok, fehler))
sys.exit(1 if fehler else 0)
