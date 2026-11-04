"""Proste operacje geometryczne (bez zależności). Współrzędne: [lon, lat]; rzut lokalny w km."""
import math

LON0, LAT0, RKM = 19.53, 49.89, 6371.0
RAD = math.pi / 180
COS0 = math.cos(LAT0 * RAD)


def rzut(p):
    return (RKM * (p[0] - LON0) * RAD * COS0, -RKM * (p[1] - LAT0) * RAD)


def odleglosc_km(a, b):
    ax, ay = rzut(a)
    bx, by = rzut(b)
    return math.hypot(ax - bx, ay - by)


def uprosc(punkty, tol_km):
    """Douglas-Peucker z zachowaniem końców. Linie upraszczamy po jednej drodze OSM,
    więc wspólne granice sąsiadów pozostają identyczne."""
    if len(punkty) < 3:
        return list(punkty)
    xy = [rzut(p) for p in punkty]
    zostaw = [False] * len(punkty)
    zostaw[0] = zostaw[-1] = True
    stos = [(0, len(punkty) - 1)]
    while stos:
        a, b = stos.pop()
        ax, ay = xy[a]
        bx, by = xy[b]
        dx, dy = bx - ax, by - ay
        dl2 = dx * dx + dy * dy
        naj, ind = 0.0, None
        for i in range(a + 1, b):
            px, py = xy[i]
            if dl2 == 0:
                d = math.hypot(px - ax, py - ay)
            else:
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / dl2))
                d = math.hypot(px - ax - t * dx, py - ay - t * dy)
            if d > naj:
                naj, ind = d, i
        if ind is not None and naj > tol_km:
            zostaw[ind] = True
            stos.append((a, ind))
            stos.append((ind, b))
    return [p for p, z in zip(punkty, zostaw) if z]


def zaokragl(p):
    return [round(p[0], 5), round(p[1], 5)]


def zszyj(odcinki):
    """Łączy odcinki (listy punktów) w zamknięte pierścienie po wspólnych końcach."""
    def kl(p):
        return (round(p[0], 6), round(p[1], 6))

    wolne = [list(o) for o in odcinki if len(o) >= 2]
    pierscienie = []
    while wolne:
        biezacy = wolne.pop()
        postep = True
        while postep and kl(biezacy[0]) != kl(biezacy[-1]):
            postep = False
            for i, o in enumerate(wolne):
                if kl(o[0]) == kl(biezacy[-1]):
                    biezacy.extend(o[1:])
                elif kl(o[-1]) == kl(biezacy[-1]):
                    biezacy.extend(list(reversed(o))[1:])
                elif kl(o[-1]) == kl(biezacy[0]):
                    biezacy = o[:-1] + biezacy
                elif kl(o[0]) == kl(biezacy[0]):
                    biezacy = list(reversed(o))[:-1] + biezacy
                else:
                    continue
                wolne.pop(i)
                postep = True
                break
        pierscienie.append((biezacy, kl(biezacy[0]) == kl(biezacy[-1])))
    return pierscienie


class Obszar:
    """Test punktu w wielokącie (reguła parzystości) z podziałem krawędzi na pasy szerokości."""

    def __init__(self, pierscienie, pas=0.01):
        self.pas = pas
        self.pasy = {}
        self.minx = self.miny = float("inf")
        self.maxx = self.maxy = float("-inf")
        for r in pierscienie:
            for a, b in zip(r, r[1:]):
                self.minx, self.maxx = min(self.minx, a[0]), max(self.maxx, a[0])
                self.miny, self.maxy = min(self.miny, a[1]), max(self.maxy, a[1])
                lo, hi = sorted((a[1], b[1]))
                for k in range(int(lo // pas), int(hi // pas) + 1):
                    self.pasy.setdefault(k, []).append((a, b))

    def zawiera(self, p):
        x, y = p[0], p[1]
        if x < self.minx or x > self.maxx or y < self.miny or y > self.maxy:
            return False
        wew = False
        for a, b in self.pasy.get(int(y // self.pas), ()):
            if (a[1] > y) != (b[1] > y) and x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]:
                wew = not wew
        return wew


def pierscienie_geom(geom):
    if geom["type"] == "Polygon":
        return list(geom["coordinates"])
    if geom["type"] == "MultiPolygon":
        return [r for pol in geom["coordinates"] for r in pol]
    raise ValueError(geom["type"])


def pole_i_srodek(r):
    a = cx = cy = 0.0
    for p, q in zip(r, r[1:]):
        c = p[0] * q[1] - q[0] * p[1]
        a += c
        cx += (p[0] + q[0]) * c
        cy += (p[1] + q[1]) * c
    if a == 0:
        return 0.0, list(r[0])
    return abs(a) / 2, [cx / (3 * a), cy / (3 * a)]


def punkt_etykiety(geom):
    """Środek największej części; gdy wypada poza wielokątem, środek najdłuższego przekroju poziomego."""
    pierscienie = pierscienie_geom(geom)
    naj = max(pierscienie, key=lambda r: pole_i_srodek(r)[0])
    srodek = pole_i_srodek(naj)[1]
    ob = Obszar(pierscienie)
    if ob.zawiera(srodek):
        return [round(srodek[0], 5), round(srodek[1], 5)]
    y = srodek[1]
    xs = []
    for a, b in zip(naj, naj[1:]):
        if (a[1] > y) != (b[1] > y):
            xs.append((b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0])
    xs.sort()
    pary = list(zip(xs[0::2], xs[1::2]))
    if pary:
        l, r = max(pary, key=lambda t: t[1] - t[0])
        return [round((l + r) / 2, 5), round(y, 5)]
    return [round(srodek[0], 5), round(srodek[1], 5)]


def rozpusc(pierscienie):
    """Usuwa krawędzie wspólne sąsiednich pierścieni, zwraca zewnętrzne obrysy."""
    def kl(p):
        return (round(p[0], 5), round(p[1], 5))

    licznik = {}
    for r in pierscienie:
        for a, b in zip(r, r[1:]):
            k = tuple(sorted((kl(a), kl(b))))
            licznik[k] = licznik.get(k, 0) + 1
    odcinki = []
    for r in pierscienie:
        for a, b in zip(r, r[1:]):
            if licznik[tuple(sorted((kl(a), kl(b))))] == 1:
                odcinki.append([a, b])
    # Sklejanie przez mapę sąsiedztwa bez kierunku: sąsiednie pierścienie mogą biec w przeciwne strony.
    sasiedzi = {}
    for i, (a, b) in enumerate(odcinki):
        sasiedzi.setdefault(kl(a), []).append((i, b))
        sasiedzi.setdefault(kl(b), []).append((i, a))
    wynik = []
    uzyte = set()
    for i, (a, b) in enumerate(odcinki):
        if i in uzyte:
            continue
        uzyte.add(i)
        droga = [a, b]
        while kl(droga[-1]) != kl(droga[0]):
            nast = next(((j, p) for j, p in sasiedzi[kl(droga[-1])] if j not in uzyte), None)
            if nast is None:
                break
            uzyte.add(nast[0])
            droga.append(nast[1])
        if kl(droga[-1]) == kl(droga[0]):
            wynik.append(droga)
    return wynik


def okrag(p, r_km, n=20):
    wynik = []
    for i in range(n + 1):
        a = 2 * math.pi * (i % n) / n
        wynik.append([
            round(p[0] + r_km * math.cos(a) / (RKM * RAD * COS0), 5),
            round(p[1] + r_km * math.sin(a) / (RKM * RAD), 5),
        ])
    return wynik
