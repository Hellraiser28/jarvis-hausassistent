"""Ed25519 (RFC 8032) nur mit der Standardbibliothek, fuer die Update-Signatur des PC-Clients (seit 0.3.2).

Pruefbericht 0.3.1, Fund 2: Bis 0.3.1 signierte die Bruecke Updates mit einem HMAC aus dem Token-Hash. Wer das Token
mitlas, konnte damit auch Updates bauen. Jetzt signiert sie mit einem eigenen Schluessel, dessen oeffentlichen Teil
der Client bei der Kopplung festhaelt; wer nur mitliest, kann kein Update bauen. Umsetzung nach dem
Referenzalgorithmus aus RFC 8032, Abschnitt 6 (langsam, aber fuer ein paar Signaturen am Tag reicht es; nicht
seitenkanalfest, deshalb nur auf dem eigenen Rechner signieren). Gegen die Testvektoren aus Abschnitt 7.1 geprueft
(tests/test_ed25519.py). Der PC-Client traegt eine Kopie von pruefen() in sich, weil sein Update nur eine Datei ist."""
import hashlib

P = 2 ** 255 - 19
L = 2 ** 252 + 27742317777372353535851937790883648493
D = -121665 * pow(121666, P - 2, P) % P
WURZEL_MINUS_1 = pow(2, (P - 1) // 4, P)


def _wurzel_x(y, vorzeichen):
    if y >= P:
        return None
    x2 = (y * y - 1) * pow(D * y * y + 1, P - 2, P)
    if x2 == 0:
        return None if vorzeichen else 0
    x = pow(x2, (P + 3) // 8, P)
    if (x * x - x2) % P:
        x = x * WURZEL_MINUS_1 % P
    if (x * x - x2) % P:
        return None
    if (x & 1) != vorzeichen:
        x = P - x
    return x


_GY = 4 * pow(5, P - 2, P) % P
_GX = _wurzel_x(_GY, 0)
G = (_GX, _GY, 1, _GX * _GY % P)


def _plus(a, b):
    w = (a[1] - a[0]) * (b[1] - b[0]) % P
    v = (a[1] + a[0]) * (b[1] + b[0]) % P
    c = 2 * a[3] * b[3] * D % P
    d = 2 * a[2] * b[2] % P
    e, f, g, h = v - w, d - c, d + c, v + w
    return e * f % P, g * h % P, f * g % P, e * h % P


def _mal(s, punkt):
    q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            q = _plus(q, punkt)
        punkt = _plus(punkt, punkt)
        s >>= 1
    return q


def _gleich(a, b):
    return (a[0] * b[2] - b[0] * a[2]) % P == 0 and (a[1] * b[2] - b[1] * a[2]) % P == 0


def _packen(punkt):
    z = pow(punkt[2], P - 2, P)
    x, y = punkt[0] * z % P, punkt[1] * z % P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _entpacken(b):
    if len(b) != 32:
        return None
    y = int.from_bytes(b, "little")
    vorzeichen, y = y >> 255, y & ((1 << 255) - 1)
    x = _wurzel_x(y, vorzeichen)
    return None if x is None else (x, y, 1, x * y % P)


def _h(b):
    return int.from_bytes(hashlib.sha512(b).digest(), "little")


def _erweitern(geheim):
    h = hashlib.sha512(geheim).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def oeffentlich(geheim):
    """32 Byte geheimer Schluessel -> 32 Byte oeffentlicher Schluessel."""
    if len(geheim) != 32:
        raise ValueError("geheimer Schluessel braucht 32 Byte")
    return _packen(_mal(_erweitern(geheim)[0], G))


def signieren(geheim, nachricht):
    a, praefix = _erweitern(geheim)
    oeff = _packen(_mal(a, G))
    r = _h(praefix + nachricht) % L
    rp = _packen(_mal(r, G))
    s = (r + _h(rp + oeff + nachricht) % L * a) % L
    return rp + s.to_bytes(32, "little")


def pruefen(oeff, nachricht, signatur):
    """True, wenn signatur (64 Byte) zu nachricht und oeff (32 Byte) passt. Nie eine Ausnahme fuer falsche Eingaben."""
    try:
        if len(oeff) != 32 or len(signatur) != 64:
            return False
        a, r = _entpacken(oeff), _entpacken(signatur[:32])
        s = int.from_bytes(signatur[32:], "little")
        if a is None or r is None or s >= L:
            return False
        h = _h(signatur[:32] + oeff + nachricht) % L
        return _gleich(_mal(s, G), _plus(r, _mal(h, a)))
    except (TypeError, ValueError):
        return False


def code_nachricht(version, sha256_hex):
    """Was fuer ein Client-Update signiert wird: Version und Pruefsumme zusammen (Pruefbericht 0.3.1, 12a), damit ein
    altes, gueltig signiertes Paar nicht unter einer hoeheren Nummer wieder ausgeliefert werden kann."""
    return ("jarvis-code:%d:%s" % (int(version), str(sha256_hex).lower())).encode()
