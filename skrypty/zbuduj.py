#!/usr/bin/env python3
"""Buduje stronę z danych badawczych: dane/events.json, obszary, podstrony wydarzeń, listę, „O projekcie”.

Użycie:  python3 skrypty/zbuduj.py [--dane ŚCIEŻKA_DO_KATALOGU_DATA]
Domyślnie czyta ../data (katalog data projektu badawczego, obok katalogu strona).
Tylko biblioteka standardowa.
"""
import argparse
import datetime
import html
import json
import pathlib
import re
import shutil
import sys
import unicodedata

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import geo  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
DANE = ROOT / "dane"
GEO = DANE / "geo"

TYPY_OBSZAROWE = {"epidemia", "epizootia", "glod"}
NAZWY_TYPOW = {
    "bitwa": "bitwa", "potyczka": "potyczka", "oblezenie": "oblężenie", "najazd": "najazd", "przemarsz": "przemarsz wojsk",
    "kwaterunek_rekwizycje": "kwaterunek i rekwizycje", "partyzantka_konspiracja": "partyzantka i konspiracja",
    "represje_egzekucja": "represje, egzekucja", "zniszczenie_pozar": "zniszczenie, pożar", "epidemia": "epidemia",
    "epizootia": "epizootia (zaraza bydła)", "glod": "głód", "powstanie_bunt": "powstanie, bunt",
    "zmiana_wladzy_granic": "zmiana władzy lub granic", "mobilizacja_werbunek": "mobilizacja, werbunek", "migracja_ludow": "migracja ludów",
    "szlak_handlowy": "szlak handlowy", "wyprawa": "wyprawa", "osadnictwo": "osadnictwo", "inne": "inne",
}
PEWNOSC = {
    "A": "co najmniej dwa niezależne źródła, w tym naukowe, encyklopedyczne lub pierwotne",
    "B": "jedno wiarygodne źródło",
    "C": "tylko strona popularna lub lokalna albo źródło mówi „prawdopodobnie”",
    "D": "legenda lub tradycja",
}
TYPY_ZRODEL = {"naukowe": "naukowe", "encyklopedia": "encyklopedia", "instytucjonalne": "instytucjonalne",
               "lokalne_popularne": "lokalne lub popularne", "zrodlo_pierwotne": "źródło pierwotne", "inne": "inne"}
MIESIACE = ["", "styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec", "lipiec", "sierpień", "wrzesień", "październik", "listopad", "grudzień"]
RZYM = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
WIEKI = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX"]
R_BUFOR_KM = 1.2
ROLE_ODRZUCONE = ("niepotwierdzony", "sprzeczne")

e = html.escape


def czesci(iso):
    p = str(iso).split("-")
    return int(p[0]), (int(p[1]) if len(p) > 1 else None), (int(p[2]) if len(p) > 2 else None)


def fmt_jeden(iso, dlugi):
    r, m, d = czesci(iso)
    if d:
        return f"{d} {RZYM[m]} {r}"
    if m:
        return f"{MIESIACE[m]} {r}" if dlugi else f"{RZYM[m]} {r}"
    return str(r)


def fmt_data(rek, dlugi=True):
    od, do, prec = rek["data_od"], rek["data_do"], rek["precyzja_daty"]
    if od is None and do is None:
        return "data nieznana"
    if od is None:
        return "przed " + fmt_jeden(do, dlugi)
    r_od = czesci(od)[0]
    if prec == "dekada":
        return f"lata {r_od % 100 // 10 * 10}. {WIEKI[r_od // 100 + 1]} w."
    if prec == "stulecie":
        return f"{WIEKI[r_od // 100 + 1]} w."
    if do is None or do == od:
        return fmt_jeden(od, dlugi)
    r_do, m_do, _ = czesci(do)
    _, m_od, d_od = czesci(od)
    if r_od == r_do and m_od and m_do and not d_od:
        return f"{RZYM[m_od]}–{RZYM[m_do]} {r_od}"
    return f"{fmt_jeden(od, False)}–{fmt_jeden(do, False)}"


def slugify(t):
    t = t.replace("ł", "l").replace("Ł", "l")
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def krotka_etykieta(rek, nadpisania):
    if rek["id"] in nadpisania:
        return nadpisania[rek["id"]]
    t = rek["tytul"]
    if ":" in t and len(t.split(":")[0].split()) >= 2:
        t = t.split(":")[0]
    t = t.split(";")[0]
    t = re.sub(r"\s*\([^)]*\d[^)]*\)\s*$", "", t)
    t = re.sub(r"\s*\(lat[^)]*$", "", t)
    if not re.search(r"przed\s+\d{3,4}(\s*r\.)?$", t):
        t = re.sub(r"[\s,]*(ok\.\s*)?([IVX]+\s+)?\d{3,4}([–/-]\d{2,4})?(\s*r\.)?$", "", t)
    return t.strip(" ,")


def wczytaj_statusy(katalog):
    """Status epok z data/epoki.json (projekt badawczy); brak pliku lub wpisu = decyduje obecność pliku."""
    plik = katalog / "epoki.json"
    if not plik.exists():
        return {}
    wynik = {}
    for x in json.loads(plik.read_text(encoding="utf-8")).get("epoki", []):
        od, do = x["id"].split("-")
        wynik[f"{int(od)}-{int(do)}"] = x.get("status")
    return wynik


def wybierz_pliki(katalog, statusy):
    """Dla epoki opracowanej najnowsza wersja (_v2 przed plikiem bez sufiksu).
    Dla epoki w toku najstarsza, czyli ostatnia zakończona weryfikacja: nowsza może być niedokończona.
    Z takiej epoki pokazujemy tylko hipotezy wskazane w dane/hipotezy.json."""
    wersje = {}
    for p in sorted(katalog.glob("*_zweryfikowane*.jsonl")):
        m = re.match(r"^(\d+-\d+)_zweryfikowane(?:_v(\d+))?\.jsonl$", p.name)
        if not m:
            print(f"  pomijam plik o nieznanej nazwie: {p.name}")
            continue
        # Nazwy plików mają lata z zerami (0000-0966), a odcinki suwaka bez nich (0-966).
        od, do = m.group(1).split("-")
        wersje.setdefault(f"{int(od)}-{int(do)}", []).append((int(m.group(2) or 1), p))
    wyb = {}
    for klucz, lista in wersje.items():
        lista.sort(key=lambda x: x[0])
        if statusy.get(klucz, "opracowana") == "opracowana":
            wyb[klucz] = lista[-1][1]
        else:
            wyb[klucz] = lista[0][1]
            print(f"  epoka {klucz} ma status „{statusy[klucz]}”: czytam {lista[0][1].name}, tylko hipotezy z dane/hipotezy.json; pomijam nowsze: {[x[1].name for x in lista[1:]]}")
    return wyb


def czy_pokazac(rek):
    st = rek.get("weryfikacja", {}).get("status", "")
    return bool(st) and not st.startswith("duplikat") and st not in ROLE_ODRZUCONE


def wczytaj_json(sciezka, domyslnie):
    return json.loads(sciezka.read_text(encoding="utf-8")) if sciezka.exists() else domyslnie


def geojson(nazwa):
    return json.loads((GEO / f"{nazwa}.geojson").read_text(encoding="utf-8"))["features"]


class Miejsca:
    def __init__(self):
        self.punkty = {}
        for f in geojson("miejscowosci") + geojson("przysiolki") + geojson("punkty_tras"):
            self.punkty.setdefault(f["properties"]["nazwa"], []).append(f)
        self.granice = {}
        plik = GEO / "miejscowosci_granice.geojson"
        if plik.exists():
            for f in geojson("miejscowosci_granice"):
                self.granice.setdefault(f["properties"]["nazwa"], []).append(f)

    def punkt(self, nazwa, gmina=None):
        kand = self.punkty.get(nazwa, [])
        if gmina:
            pasujace = [f for f in kand if f["properties"]["gmina"] == gmina]
            if pasujace:
                kand = pasujace
        if not kand:
            return None
        waga = {"city": 0, "town": 1, "village": 2, "hamlet": 3}
        return sorted(kand, key=lambda f: waga.get(f["properties"]["typ"], 9))[0]

    def granica(self, nazwa, punkt):
        """Najmniejsza granica o tej nazwie zawierająca środek miejscowości."""
        najl, pole = None, float("inf")
        for f in self.granice.get(nazwa, []):
            rs = geo.pierscienie_geom(f["geometry"])
            if geo.Obszar(rs).zawiera(punkt):
                a = max(geo.pole_i_srodek(r)[0] for r in rs)
                if a < pole:
                    najl, pole = f, a
        return najl


def probki_w_zasiegu(linie, zasieg):
    """Punkty co około 300 m wzdłuż linii, tylko w zasięgu mapy: z nich wybieramy miejsce podpisu."""
    wynik = []
    for l in linie:
        for a, b in zip(l, l[1:]):
            n = max(1, int(geo.odleglosc_km(a, b) / 0.3))
            for i in range(n):
                p = [round(a[0] + (b[0] - a[0]) * i / n, 5), round(a[1] + (b[1] - a[1]) * i / n, 5)]
                if zasieg.zawiera(p):
                    wynik.append(p)
    return wynik


def buduj_rekordy(pliki, ustawienia):
    miejsca = Miejsca()
    zasieg = geo.Obszar(geo.pierscienie_geom(geojson("zasieg")[0]["geometry"]))
    lok, nadpisania, slugi = ustawienia["lok"], ustawienia["etykiety"], ustawienia["slugi"]
    wyn, obszary, indeks_ob, uzyte_miejsca, ostrzezenia = [], [], {}, {}, []
    zuzyte_slugi = set(slugi.values())

    for epoka, plik in sorted(pliki.items(), key=lambda kv: int(kv[0].split("-")[0])):
        for linia in plik.read_text(encoding="utf-8").splitlines():
            if not linia.strip():
                continue
            r = json.loads(linia)
            if epoka in ustawienia["w_toku"] and r["id"] not in ustawienia["hipotezy"]:
                continue
            if not czy_pokazac(r) and r["id"] not in ustawienia["hipotezy"]:
                continue
            rok_od = czesci(r["data_od"])[0] if r["data_od"] else None
            rok_do = czesci(r["data_do"])[0] if r["data_do"] else rok_od
            et = krotka_etykieta(r, nadpisania)
            if r["id"] not in slugi:
                baza = slugify(et)
                if rok_od and str(rok_od) not in baza:
                    baza += f"-{rok_od}"
                s = baza
                if s in zuzyte_slugi:
                    s = f"{baza}-{slugify(r['id'].split('-', 2)[2])}"
                slugi[r["id"]] = s
                zuzyte_slugi.add(s)
            w = {
                "id": r["id"], "slug": slugi[r["id"]], "url": f"wydarzenie/{slugi[r['id']]}/", "epoka": epoka,
                "tytul": r["tytul"], "etykieta": et, "data": fmt_data(r, True), "data_krotka": fmt_data(r, False),
                "data_uwagi": r.get("data_uwagi") or "", "precyzja": r["precyzja_daty"], "rok_od": rok_od, "rok_do": rok_do,
                "miejscowosc": r["miejscowosc"], "gmina": r["gmina"], "zakres": r["zakres"], "typ": r["typ"],
                "typ_nazwa": NAZWY_TYPOW.get(r["typ"], r["typ"]), "opis": r["opis"], "strony": r.get("strony") or [],
                "legenda": bool(r.get("legenda")), "pewnosc": r["pewnosc"], "zrodla": r["zrodla"], "uwagi": r.get("uwagi") or "",
                "weryfikacja": {"status": r["weryfikacja"]["status"], "data": r["weryfikacja"].get("data_sprawdzenia")},
                "_data_od": r["data_od"], "szara": r["zakres"] == "bufor" or (r["zakres"] == "region" and bool(r["miejscowosc"])), "rodzaj": None, "punkt": None, "grupa": None, "obszar": None,
                "przyblizony": False, "notatka_lokalizacji": "", "na_mapie": False, "powod_listy": "",
            }
            if r["weryfikacja"]["status"] == "czesciowo":
                w["weryfikacja"]["uwagi"] = r["weryfikacja"].get("uwagi", "")

            if r.get("zasieg_opis"):
                w["zasieg_opis"] = r["zasieg_opis"]
            if r["id"] in ustawienia["hipotezy"] or r.get("hipoteza"):
                # Hipoteza nie jest zdarzeniem: bez geometrii, tylko własna podstrona i sekcja listy.
                notatka = ustawienia["hipotezy"].get(r["id"], "Źródło przedstawia to zjawisko jako hipotezę lub przedmiot sporu badaczy.")
                w.update(hipoteza=True, notatka_hipotezy=notatka, powod_listy="hipoteza")
                wyn.append(w)
                continue

            usta = lok.get(r["id"], {})
            if usta.get("data_tekst"):
                w["data"] = w["data_krotka"] = usta["data_tekst"]
            # Zjawisko obszarowe rysujemy tylko dla typów z kolorem (epidemia, epizootia, głód) i wskazanych miejscowości.
            # Pozostałe mają zasięg opisany słownie (np. cyrkuł, dolina), więc zostają na liście.
            obszarowe = r.get("charakter") == "obszar"
            w["notatka_lokalizacji"] = usta.get("notatka", "")

            if usta.get("lata"):
                w["lata"] = usta["lata"]
            if usta.get("linia") or usta.get("rzeka"):
                w["przyblizony"] = True
                if usta.get("rzeka"):
                    linie = geojson(usta["rzeka"])[0]["geometry"]["coordinates"]
                else:
                    pkt = [miejsca.punkt(nz) for nz in usta["linia"]]
                    if not all(pkt):
                        ostrzezenia.append(f"{r['id']}: brak punktu trasy w OSM: {usta['linia']}")
                    linie = [[f["geometry"]["coordinates"] for f in pkt if f]]
                wnetrze = probki_w_zasiegu(linie, zasieg)
                oid = f"L{len(obszary) + 1}"
                obszary.append({"type": "Feature", "geometry": {"type": "MultiLineString", "coordinates": linie}, "properties": {
                    "id": oid, "etykieta": wnetrze[len(wnetrze) // 2]}})
                w.update(rodzaj="linia", obszar=oid, linia_typ="rzeka" if usta.get("rzeka") else "trasa", etykieta_xy=obszary[-1]["properties"]["etykieta"])
            elif r["typ"] in TYPY_OBSZAROWE:
                nazwy = usta.get("miejscowosci") or ([r["miejscowosc"]] if r["miejscowosc"] else [])
                w["przyblizony"] = bool(usta.get("przyblizony"))
                pierscienie, opisane, brak = [], [], []
                for nz in nazwy:
                    pf = miejsca.punkt(nz, r["gmina"] if nz == r["miejscowosc"] else None)
                    if pf is None:
                        brak.append(nz)
                        continue
                    pt = pf["geometry"]["coordinates"]
                    gr = miejsca.granica(nz, pt)
                    if gr:
                        pierscienie.extend(geo.pierscienie_geom(gr["geometry"]))
                    else:
                        pierscienie.append(geo.okrag(pt, R_BUFOR_KM))
                        w["przyblizony"] = True
                        promien = str(R_BUFOR_KM).replace(".", ",")
                        w["notatka_lokalizacji"] = (w["notatka_lokalizacji"] + f" Dla miejscowości {nz} OSM nie podaje granicy: narysowano koło o promieniu {promien} km wokół jej środka.").strip()
                    opisane.append(nz)
                if brak:
                    ostrzezenia.append(f"{r['id']}: brak miejscowości w OSM dla obszaru: {brak}")
                if pierscienie:
                    klucz = "|".join(sorted(opisane))
                    if klucz not in indeks_ob:
                        rs = geo.rozpusc(pierscienie) if len(opisane) > 1 else pierscienie
                        rs = [x for x in rs if len(x) >= 4]
                        geom = {"type": "MultiPolygon", "coordinates": [[x] for x in rs]}
                        oid = f"O{len(obszary) + 1}"
                        indeks_ob[klucz] = oid
                        obszary.append({"type": "Feature", "geometry": geom, "properties": {
                            "id": oid, "miejsca": opisane, "etykieta": geo.punkt_etykiety(geom)}})
                    oid = indeks_ob[klucz]
                    cecha = next(o for o in obszary if o["properties"]["id"] == oid)
                    w.update(rodzaj="obszar", obszar=oid, etykieta_xy=cecha["properties"]["etykieta"], miejsce_obszaru=", ".join(opisane))
            elif r["miejscowosc"] and not obszarowe:
                pf = miejsca.punkt(r["miejscowosc"], r["gmina"])
                pt = None
                if pf is not None:
                    pt = pf["geometry"]["coordinates"]
                    if r["gmina"] and pf["properties"]["gmina"] != r["gmina"]:
                        ostrzezenia.append(f"{r['id']}: {r['miejscowosc']}: OSM wskazuje gminę {pf['properties']['gmina']}, a rekord {r['gmina']}")
                    uzyte_miejsca[r["miejscowosc"]] = pt
                    if r.get("lat") is not None:
                        d = geo.odleglosc_km(pt, [r["lon"], r["lat"]])
                        if d > 3:
                            ostrzezenia.append(f"{r['id']}: współrzędne rekordu {d:.1f} km od środka miejscowości w OSM")
                elif r.get("lat") is not None and zasieg.zawiera([r["lon"], r["lat"]]):
                    pt = [r["lon"], r["lat"]]
                    uzyte_miejsca[r["miejscowosc"]] = pt
                if pt is not None:
                    w.update(rodzaj="punkt", grupa=r["miejscowosc"], punkt=pt)

            if rok_od is None:
                w["powod_listy"] = "bez daty"
            elif w["rodzaj"]:
                w["na_mapie"] = True
            elif obszarowe:
                w["powod_listy"] = "zjawisko obszarowe"
            elif r["miejscowosc"]:
                w["powod_listy"] = "poza zasięgiem mapy" if r["zakres"] != "powiat" else "brak współrzędnych"
            else:
                w["powod_listy"] = "regionalne"

            wyn.append(w)

    def klucz_daty(w):
        if w["rok_od"] is None:
            return (1, 0, 0, 0, 0, w["id"])
        r, m, d = czesci(w["_data_od"])
        return (0, r, m or 0, d or 0, w["rok_do"] or 0, w["id"])

    wyn.sort(key=klucz_daty)
    for w in wyn:
        del w["_data_od"]
    # Poprzednie i następne prowadzą tylko po wydarzeniach, nie po hipotezach.
    lancuch = [w for w in wyn if not w.get("hipoteza")]
    for w in wyn:
        w["poprzednie"] = w["nastepne"] = None
    for i, w in enumerate(lancuch):
        w["poprzednie"] = lancuch[i - 1]["slug"] if i else None
        w["nastepne"] = lancuch[i + 1]["slug"] if i + 1 < len(lancuch) else None
    return wyn, obszary, uzyte_miejsca, ostrzezenia, slugi


# ---------- szablony ----------

def strona(tytul, tresc, glebokosc, wygenerowano, opis="", skrypty=""):
    w = "../" * glebokosc
    return f"""<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(tytul)}</title>
{f'<meta name="description" content="{e(opis)}">' if opis else ''}
<link rel="stylesheet" href="{w}assets/style.css">
</head>
<body>
<div class="podstrona">
<header class="podstrona-naglowek">
  <a class="marka" href="{w}" data-z-stanem>Wydarzenia w powiecie wadowickim</a>
  <nav aria-label="Główne">
    <a href="{w}" data-z-stanem>Mapa</a>
    <a href="{w}wydarzenia/" data-z-stanem>Wszystkie wydarzenia</a>
    <a href="{w}o-projekcie/" data-z-stanem>O projekcie</a>
  </nav>
</header>
<main>
{tresc}
</main>
<footer class="stopka">
  Mapa: © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a> (ODbL). Dane wygenerowano {e(wygenerowano)}.
</footer>
</div>
<script src="{w}assets/podstrona.js"></script>
{skrypty}
</body>
</html>
"""


def podstrona_wydarzenia(w, wg_sluga, wymiary, obszary_ind, wygenerowano):
    t = [f'<p class="data-wydarzenia">{e(w["data"])}</p>', f'<h1>{e(w["tytul"])}</h1>']
    if w.get("hipoteza"):
        t.append(f'<p class="plakietka plakietka-legenda"><span><b class="znak-hipotezy">Hipoteza.</b> {e(w["notatka_hipotezy"])}</span></p>')
    if w["data_uwagi"]:
        t.append(f'<p class="uwagi">{e(w["data_uwagi"])}</p>')
    miejsce = w["miejscowosc"] or ("zjawisko obszarowe, bez jednej miejscowości" if w["powod_listy"] == "zjawisko obszarowe" or w["rodzaj"] == "linia" else "region, bez jednej miejscowości")
    if w["szara"]:
        miejsce += " (poza powiatem)"
    meta = [("Miejsce", miejsce)]
    if w["gmina"]:
        meta.append(("Gmina", w["gmina"]))
    if w.get("zasieg_opis"):
        meta.append(("Zasięg", w["zasieg_opis"]))
    meta.append(("Typ", w["typ_nazwa"]))
    if w["strony"]:
        meta.append(("Strony", ", ".join(w["strony"])))
    t.append('<dl class="metryka">' + "".join(f"<dt>{e(a)}</dt><dd>{e(b)}</dd>" for a, b in meta) + "</dl>")
    t.append(f'<p class="plakietka"><b>{w["pewnosc"]}</b><span>Pewność {w["pewnosc"]}: {e(PEWNOSC[w["pewnosc"]])}.</span></p>')
    if w["legenda"]:
        t.append('<p class="plakietka plakietka-legenda"><span>Legenda: informacja pochodzi z tradycji lub legendy.</span></p>')
    t.append(f'<p class="opis">{e(w["opis"])}</p>')
    if w["rodzaj"] == "obszar" and w["przyblizony"]:
        t.append(f'<p class="ob-przyblizony"><b>Obszar przybliżony.</b> {e(w["notatka_lokalizacji"])}</p>')
    if w["rodzaj"] == "linia":
        t.append(f'<p class="ob-przyblizony"><b>Przebieg przybliżony.</b> {e(w["notatka_lokalizacji"])}</p>')
    t.append(mini_mapa(w, wymiary, obszary_ind))

    t.append("<h2>Źródła</h2><ul class=\"zrodla\">")
    for z in w["zrodla"]:
        tyt = e(z.get("tytul") or "")
        if z.get("url"):
            tyt = f'<a href="{e(z["url"])}" rel="noopener">{tyt}</a>'
        cz = [tyt]
        if z.get("autor"):
            cz.append(e(str(z["autor"])))
        if z.get("rok"):
            cz.append(e(str(z["rok"])))
        if z.get("strona"):
            cz.append("s. " + e(str(z["strona"])))
        if z.get("typ_zrodla"):
            cz.append(e(TYPY_ZRODEL.get(z["typ_zrodla"], z["typ_zrodla"])))
        blok = f"<li>{', '.join(cz)}"
        if z.get("cytat"):
            jez = f' lang="{e(z["jezyk"])}"' if z.get("jezyk") else ""
            blok += f"<blockquote{jez}>{e(z['cytat'])}</blockquote>"
        t.append(blok + "</li>")
    t.append("</ul>")
    if w["uwagi"]:
        t.append(f'<h2>Uwagi</h2><p class="uwagi">{e(w["uwagi"])}</p>')
    st = w["weryfikacja"]
    t.append(f'<h2>Weryfikacja</h2><p class="uwagi">Status: {e(st["status"])}' + (f', sprawdzono {e(st["data"])}' if st.get("data") else "") + ".</p>")
    if st.get("uwagi"):
        t.append(f'<details class="uwagi"><summary>Co potwierdzono tylko częściowo</summary><p>{e(st["uwagi"])}</p></details>')

    pop, nast = wg_sluga.get(w["poprzednie"]), wg_sluga.get(w["nastepne"])
    nav = ['<nav class="nawigacja" aria-label="Poprzednie i następne wydarzenie">']
    nav.append(f'<a data-z-stanem href="../{pop["slug"]}/"><small>← Poprzednie, {e(pop["data"])}</small>{e(pop["tytul"])}</a>' if pop else "<span></span>")
    nav.append(f'<a class="nast" data-z-stanem href="../{nast["slug"]}/"><small>Następne, {e(nast["data"])} →</small>{e(nast["tytul"])}</a>' if nast else "<span></span>")
    nav.append("</nav>")
    if pop or nast:
        t.append("".join(nav))
    t.append('<p><a data-z-stanem href="../../"><b>← Wróć do mapy</b></a></p>')
    return strona(w["tytul"], "\n".join(t), 2, wygenerowano, opis=w["opis"][:150])


def mini_mapa(w, wym, obszary_ind):
    x0, y0, sz, wy = wym
    warstwy, podpis = [], ""
    if w["rodzaj"] == "punkt":
        x, y = geo.rzut(w["punkt"])
        kol = "#8a8a8a" if w["szara"] else "#d10a11"
        pelna = w["pewnosc"] in ("A", "B")
        styl = f'fill="{kol}"' if pelna else f'fill="#fff" stroke="{kol}" stroke-width="0.32"'
        warstwy.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="0.7" {styl}/>')
        warstwy.append(f'<text x="{x:.2f}" y="{y - 1.2:.2f}" text-anchor="middle" class="mini-etykieta">{e(w["miejscowosc"])}</text>')
        podpis = "Punkt to środek miejscowości, nie dokładne miejsce zdarzenia."
    elif w["rodzaj"] == "obszar":
        f = obszary_ind[w["obszar"]]
        d = ""
        for pol in f["geometry"]["coordinates"]:
            for r in pol:
                d += "M" + "L".join(f"{geo.rzut(p)[0]:.2f} {geo.rzut(p)[1]:.2f}" for p in r) + "Z"
        kol = {"epidemia": ("#f5c800", "#a88900"), "epizootia": ("#e8791e", "#a8540f"), "glod": ("#8a5a2b", "#5f3c1b")}[w["typ"]]
        warstwy.append(f'<path d="{d}" fill="{kol[0]}" fill-opacity="0.5" fill-rule="evenodd" stroke="{kol[1]}" stroke-width="0.12"/>')
        x, y = geo.rzut(f["properties"]["etykieta"])
        warstwy.append(f'<text x="{x:.2f}" y="{y:.2f}" text-anchor="middle" class="mini-etykieta">{e(w["miejsce_obszaru"] if "," not in w["miejsce_obszaru"] else "")}</text>')
        podpis = "Obszar to dzisiejsze granice miejscowości z OSM." if not w["przyblizony"] else "Obszar przybliżony, zbudowany z dzisiejszych granic miejscowości z OSM."
    elif w["rodzaj"] == "linia":
        d = ""
        for l in obszary_ind[w["obszar"]]["geometry"]["coordinates"]:
            d += "M" + "L".join(f"{geo.rzut(p)[0]:.2f} {geo.rzut(p)[1]:.2f}" for p in l)
        if w["linia_typ"] == "rzeka":
            warstwy.append(f'<path d="{d}" fill="none" stroke="#2f6f9f" stroke-width="0.32" stroke-linejoin="round"/>')
            podpis = "Dzisiejszy bieg rzeki w zasięgu mapy, a nie zasięg zalania."
        else:
            warstwy.append(f'<path d="{d}" fill="none" stroke="#d10a11" stroke-width="0.26" stroke-dasharray="0.8 0.5"/>')
            podpis = "Linia jest schematem, nie dokładnym przebiegiem."
    elif w.get("hipoteza"):
        podpis = "Hipoteza nie wskazuje jednego miejsca, dlatego nie ma jej na mapie."
    elif w["powod_listy"] == "zjawisko obszarowe":
        podpis = "Źródła opisują zasięg tego zjawiska tylko słownie, dlatego nie ma go na mapie."
    elif w["powod_listy"] == "regionalne":
        podpis = "Wydarzenie regionalne: źródło nie wskazuje jednego miejsca, dlatego nie ma go na mapie."
    elif w["powod_listy"] == "poza zasięgiem mapy":
        podpis = f"{w['miejscowosc']} leży poza zasięgiem mapy, która obejmuje powiat i gminy przyległe."
    elif w["miejscowosc"]:
        podpis = f"Nie ustalono współrzędnych miejscowości {w['miejscowosc']}."
    if w["rok_od"] is None and w["rodzaj"]:
        podpis = "Źródło nie podaje roku, dlatego wydarzenia nie ma na głównej mapie ani na suwaku. " + podpis
    return (
        f'<figure style="margin:0"><svg class="mini" viewBox="{x0:.2f} {y0:.2f} {sz:.2f} {wy:.2f}" role="img" aria-label="Mała mapa z lokalizacją wydarzenia">'
        f'<style>.mini-etykieta{{font:700 1.5px Helvetica,Arial,sans-serif;fill:#000;paint-order:stroke;stroke:#fff;stroke-width:.5px}}</style>'
        f'<image href="../../dane/geo/mini.svg" x="{x0:.2f}" y="{y0:.2f}" width="{sz:.2f}" height="{wy:.2f}"/>'
        + "".join(warstwy) + f'</svg><figcaption class="mini-podpis">{e(podpis)}</figcaption></figure>'
    )


def mini_podklad():
    def d_linii(linie):
        return "".join("M" + "L".join(f"{geo.rzut(p)[0]:.2f} {geo.rzut(p)[1]:.2f}" for p in l) for l in linie)

    zas = geojson("zasieg")[0]["geometry"]["coordinates"]
    xy = [geo.rzut(p) for r in zas for p in r]
    m = 1.0
    x0, x1 = min(p[0] for p in xy) - m, max(p[0] for p in xy) + m
    y0, y1 = min(p[1] for p in xy) - m, max(p[1] for p in xy) + m
    cz = []
    for f in geojson("drogi"):
        if f["properties"]["klasa"] <= 3:
            cz.append(f'<path d="{d_linii(f["geometry"]["coordinates"])}" fill="none" stroke="#777" stroke-width="{0.09 if f["properties"]["klasa"] == 3 else 0.14}"/>')
    for f in geojson("gminy"):
        if not f["properties"]["w_powiecie"]:
            cz.append(f'<path d="{d_linii(geo.pierscienie_geom(f["geometry"]))}" fill="none" stroke="#444" stroke-width="0.08"/>')
    powiat = geojson("powiat")[0]["geometry"]
    cz.append(f'<path d="{d_linii(geo.pierscienie_geom(powiat))}" fill="none" stroke="#000" stroke-width="0.3" stroke-linejoin="round"/>')
    for f in geojson("miejscowosci"):
        if f["properties"]["typ"] in ("town", "city"):
            x, y = geo.rzut(f["geometry"]["coordinates"])
            cz.append(f'<text x="{x:.2f}" y="{y - 1.2:.2f}" text-anchor="middle" font-family="Helvetica,Arial,sans-serif" font-size="1.25" fill="#555">{e(f["properties"]["nazwa"])}</text>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0:.2f} {y0:.2f} {x1 - x0:.2f} {y1 - y0:.2f}">' + "".join(cz) + "</svg>")
    (GEO / "mini.svg").write_text(svg, encoding="utf-8")
    return x0, y0, x1 - x0, y1 - y0


def pozycja_listy(w, kierunek="../"):
    szukaj = " ".join([w["tytul"], w["opis"], w["miejscowosc"] or "", w["gmina"] or "", w["typ_nazwa"], " ".join(w["strony"]), w["data"]])
    miejsce = ", ".join(x for x in [w["miejscowosc"], ("gm. " + w["gmina"]) if w["gmina"] and w["gmina"] != w["miejscowosc"] else None] if x)
    dod = w["powod_listy"]
    if miejsce and dod:
        dod = " · " + dod
    if w["legenda"]:
        dod += " · legenda"
    return (f'<li data-szukaj="{e(szukaj)}"><a data-z-stanem href="{kierunek}{w["url"]}"><span class="pz pz-{w["pewnosc"]}" aria-label="pewność {w["pewnosc"]}">{w["pewnosc"]}</span>'
            f'<span class="lw-data">{e(w["data"])}</span><span class="lw-tytul">{e(w["tytul"])}<span class="lw-miejsce">{e(miejsce)}{e(dod)}</span></span></a></li>')


def strona_listy(wyd, wygenerowano):
    na = [w for w in wyd if w["na_mapie"]]
    poza = [w for w in wyd if not w["na_mapie"] and not w.get("hipoteza")]
    hip = [w for w in wyd if w.get("hipoteza")]
    t = ["<h1>Wszystkie wydarzenia</h1>",
         f'<p>Na tej liście są wszystkie rekordy, także słabiej udokumentowane (pewność C) i te, których nie ma na mapie. Razem: {len(na) + len(poza)}{" oraz hipotezy na końcu listy" if hip else ""}. Litera przy wydarzeniu to pewność, wyjaśniona na stronie <a data-z-stanem href="../o-projekcie/">O projekcie</a>.</p>',
         '<label for="filtr" style="font-weight:600">Szukaj w tytułach, opisach i nazwach miejsc</label>',
         '<input id="filtr" class="filtr" type="search" autocomplete="off" placeholder="np. Lanckorona, pożar, Suworow">',
         '<p id="licznik" class="licznik" role="status"></p>',
         f'<section class="sekcja-wykaz"><h2>Na mapie, chronologicznie</h2><ul class="lista-wszystkich">{"".join(pozycja_listy(w) for w in na)}</ul></section>',
         f'<section class="sekcja-wykaz" id="poza-mapa"><h2>Tylko na liście: regionalne, obszarowe, poza zasięgiem mapy, bez daty</h2><ul class="lista-wszystkich">{"".join(pozycja_listy(w) for w in poza)}</ul></section>']
    if hip:
        t.append(f'<section class="sekcja-wykaz" id="hipotezy"><h2>Hipotezy, nie potwierdzone wydarzenia</h2><ul class="lista-wszystkich">{"".join(pozycja_listy(w) for w in hip)}</ul></section>')
    return strona("Wszystkie wydarzenia: powiat wadowicki", "\n".join(t), 1, wygenerowano,
                  opis="Chronologiczna lista wydarzeń historycznych na terenie powiatu wadowickiego.",
                  skrypty='<script src="../assets/lista.js"></script>')


def strona_o_projekcie(wszystkie, epoki, wygenerowano, projekt):
    wyd = [w for w in wszystkie if not w.get("hipoteza")]
    hip = [w for w in wszystkie if w.get("hipoteza")]
    gminy = ["Andrychów", "Brzeźnica", "Kalwaria Zebrzydowska", "Lanckorona", "Mucharz", "Spytkowice", "Stryszów", "Tomice", "Wadowice", "Wieprz"]
    z_wyd = {w["gmina"] for w in wyd if w["gmina"]}
    puste = [g for g in gminy if g not in z_wyd]
    gotowe = [f'{x["od"]}–{x["do"]}' for x in epoki if x["gotowa"]]
    wkrotce = [f'{x["od"]}–{x["do"]}' for x in epoki if not x["gotowa"]]
    ile = {p: sum(1 for w in wyd if w["pewnosc"] == p) for p in "ABCD"}

    zrodla = {}
    for w in wszystkie:
        for z in w["zrodla"]:
            kl = z.get("url") or z.get("tytul")
            if kl and kl not in zrodla:
                zrodla[kl] = z
    def klucz(z):
        return (str(z.get("autor") or "~"), str(z.get("tytul") or ""))
    lista_zr = []
    for z in sorted(zrodla.values(), key=klucz):
        tyt = e(z.get("tytul") or "")
        if z.get("url"):
            tyt = f'<a href="{e(z["url"])}" rel="noopener">{tyt}</a>'
        cz = [x for x in [e(str(z["autor"])) if z.get("autor") else None, tyt, e(str(z["rok"])) if z.get("rok") else None] if x]
        lista_zr.append("<li>" + ", ".join(cz) + "</li>")
    repo = projekt.get("repozytorium")
    hipotezy_txt = ""
    if hip:
        hipotezy_txt = (f'<p>Osobno pokazujemy hipotezy ({len(hip)}): zjawiska, które źródła przedstawiają jako hipotezę lub przedmiot sporu badaczy. '
                        'Nie są to potwierdzone wydarzenia, nie ma ich na mapie i nie wchodzą do powyższych liczb. '
                        '<a data-z-stanem href="../wydarzenia/#hipotezy">Lista hipotez</a>.</p>\n')
    puste_epoki = "".join(
        f'<p>Epoka {x["od"]}–{x["do"]} jest opracowana, ale w sprawdzonych źródłach nie ma w niej zdarzeń, które można wskazać na mapie'
        + (": są tylko zjawiska obszarowe i hipotezy, opisane na liście" if x["ile"] or x["hipotezy"] else "")
        + ". To brak dowodu, a nie dowód, że nic się wtedy nie działo.</p>\n"
        for x in epoki if x["gotowa"] and not x["na_mapie"])

    t = f"""<h1>O projekcie</h1>
<p class="opis">Mapa pokazuje udokumentowane wydarzenia z lat 0–1945 na terenie dzisiejszego powiatu wadowickiego: bitwy, najazdy, przemarsze i kwaterunki wojsk, pożary, epidemie i inne. Dane powstają epokami.</p>
<p>Opracowane epoki: <b>{e(', '.join(gotowe))}</b>. W przygotowaniu: {e(', '.join(wkrotce))}.</p>
{puste_epoki}
<h2>Skąd są dane</h2>
<p>Agenci AI szukali wydarzeń w źródłach: Wikipedii, Słowniku geograficznym Królestwa Polskiego, artykułach naukowych i na stronach lokalnych. Osobny agent sprawdził każdy rekord w źródle: w epokach 0–966, 1648–1772 i 1772–1815 znaleziono w tekstach źródeł wszystkie cytaty (56, 131 i 57). Dane są wiarygodne, ale niekompletne. Opisy są własnymi parafrazami, a krótkie cytaty przy źródłach podano w języku oryginału.</p>
<p>Rekordy na stronie po scaleniu duplikatów: {len(wyd)} (pewność A: {ile['A']}, B: {ile['B']}, C: {ile['C']}, D: {ile['D']}). Rekordy niepotwierdzone i sprzeczne nie są pokazywane jako wydarzenia.</p>
{hipotezy_txt}
<h2>Jak liczona jest pewność</h2>
<dl class="metryka">
<dt><b>A</b></dt><dd>Co najmniej dwa niezależne źródła, w tym naukowe, encyklopedyczne lub pierwotne.</dd>
<dt><b>B</b></dt><dd>Jedno wiarygodne źródło.</dd>
<dt><b>C</b></dt><dd>Tylko strona popularna lub lokalna albo źródło mówi „prawdopodobnie”.</dd>
<dt><b>D</b></dt><dd>Legenda lub tradycja. Zawsze z wyraźnym oznaczeniem.</dd>
</dl>
<p>Mapa domyślnie pokazuje pewność A i B jako pełne kropki. Pewność C można włączyć w legendzie, wtedy kropka jest samym obrysem.</p>

<h2>Brak wydarzeń nie znaczy, że nic się nie działo</h2>
<p>{e(', '.join(puste))}: te gminy nie mają dziś żadnego wydarzenia. To brak dowodu w sprawdzonych źródłach, a nie dowód, że nic się tam nie działo. Tak samo należy czytać każde puste miejsce i każdy pusty okres na mapie.</p>

<h2>Ograniczenia</h2>
<ul>
<li>Mapa pokazuje dzisiejsze granice powiatu i gmin, choć wydarzenia działy się w innych ustrojach i podziałach administracyjnych.</li>
<li>Kropka stoi w środku miejscowości według OSM, a nie w dokładnym miejscu zdarzenia. Kropki jednej miejscowości są rozsunięte tylko po to, by dało się je kliknąć.</li>
<li>Obszar epidemii, zarazy bydła lub głodu to dzisiejsza granica wskazanej miejscowości. Gdy źródło jest mniej dokładne albo granicy brak, podstrona wydarzenia ma oznaczenie „obszar przybliżony”.</li>
<li>Zjawiska obszarowe, których zasięg źródła opisują tylko słownie (np. „cyrkuł myślenicki”), nie są rysowane: dawnych granic nie ma w danych, a rysowanie byłoby zgadywaniem.</li>
<li>Trasy na mapie to schematyczne linie między miejscami wskazanymi w źródłach, a nie dokładny przebieg dróg. Linia rzeki to jej dzisiejszy bieg, a nie zasięg zalania.</li>
<li>Wydarzenia regionalne, obszarowe i rekordy bez roku są tylko na <a data-z-stanem href="../wydarzenia/#poza-mapa">liście</a>. Gdy źródła podają różne daty, opis różnic jest na podstronie wydarzenia.</li>
<li>Część źródeł papierowych i rękopiśmiennych nie została sprawdzona bezpośrednio, tylko przez opracowania, które je cytują.</li>
</ul>

<h2>Dane i kod</h2>
<p><a href="../dane/events.json">Wszystkie wydarzenia w jednym pliku JSON</a>.{f' <a href="{e(repo)}">Repozytorium z kodem i granicami GeoJSON</a>.' if repo else ''}</p>

<h2>Atrybucje</h2>
<p>Granice, drogi i miejscowości: © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>, licencja Open Database License (ODbL). Biblioteka <a href="https://d3js.org">D3</a> (licencja ISC).</p>
<details><summary>Źródła użyte w danych ({len(lista_zr)})</summary><ul>{''.join(lista_zr)}</ul></details>
"""
    return strona("O projekcie: wydarzenia w powiecie wadowickim", t, 1, wygenerowano, opis="Skąd są dane, jak liczona jest pewność, ograniczenia i atrybucje.")


def zapisz(sciezka, tresc):
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    sciezka.write_text(tresc, encoding="utf-8")


def main():
    arg = argparse.ArgumentParser()
    arg.add_argument("--dane", default=str(ROOT.parent / "data"))
    a = arg.parse_args()
    katalog = pathlib.Path(a.dane)
    statusy = wczytaj_statusy(katalog)
    pliki = wybierz_pliki(katalog, statusy)
    if not pliki:
        raise SystemExit(f"Brak plików *_zweryfikowane*.jsonl w {katalog}")
    print("Pliki:", ", ".join(p.name for p in pliki.values()))

    ustawienia = {
        "lok": wczytaj_json(DANE / "lokalizacje_wydarzen.json", {}),
        "etykiety": wczytaj_json(DANE / "etykiety.json", {}),
        "hipotezy": wczytaj_json(DANE / "hipotezy.json", {}),
        "slugi": wczytaj_json(DANE / "slugi.json", {}),
        "w_toku": {k for k in pliki if statusy.get(k, "opracowana") != "opracowana"},
    }
    ustawienia["lok"].pop("_opis", None)
    ustawienia["etykiety"].pop("_opis", None)
    ustawienia["hipotezy"].pop("_opis", None)
    wyd, obszary, uzyte, ostrzezenia, slugi = buduj_rekordy(pliki, ustawienia)
    (DANE / "slugi.json").write_text(json.dumps(slugi, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")

    epoki = wczytaj_json(DANE / "epoki.json", [])
    klucze = {f'{x["od"]}-{x["do"]}' for x in epoki}
    for k in pliki:
        if k not in klucze:
            print(f"  UWAGA: epoka {k} nie ma odcinka w dane/epoki.json")
    for x in epoki:
        klucz = f'{x["od"]}-{x["do"]}'
        x["gotowa"] = klucz in pliki and klucz not in ustawienia["w_toku"]
        if statusy.get(klucz) == "opracowana" and klucz not in pliki:
            print(f"  UWAGA: epoka {klucz}: data/epoki.json podaje „opracowana”, a pliku zweryfikowanego nie ma")
        x["ile"] = sum(1 for w in wyd if w["epoka"] == klucz and not w.get("hipoteza"))
        x["hipotezy"] = sum(1 for w in wyd if w["epoka"] == klucz and w.get("hipoteza"))
        x["na_mapie"] = sum(1 for w in wyd if w["epoka"] == klucz and w["na_mapie"])

    wygenerowano = datetime.date.today().isoformat()
    obj = {"wygenerowano": wygenerowano, "atrybucja_mapy": "© OpenStreetMap contributors (ODbL)",
           "epoki": epoki, "miejsca": uzyte, "wydarzenia": wyd}
    zapisz(DANE / "events.json", json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
    zapisz(GEO / "obszary.geojson", json.dumps({"type": "FeatureCollection", "attribution": "© OpenStreetMap contributors, ODbL 1.0", "features": obszary}, ensure_ascii=False, separators=(",", ":")))

    wym = mini_podklad()
    ob_ind = {o["properties"]["id"]: o for o in obszary}
    wg_sluga = {w["slug"]: w for w in wyd}
    kat = ROOT / "wydarzenie"
    if kat.exists():
        shutil.rmtree(kat)
    for w in wyd:
        zapisz(kat / w["slug"] / "index.html", podstrona_wydarzenia(w, wg_sluga, wym, ob_ind, wygenerowano))
    zapisz(ROOT / "wydarzenia" / "index.html", strona_listy(wyd, wygenerowano))
    zapisz(ROOT / "o-projekcie" / "index.html", strona_o_projekcie(wyd, epoki, wygenerowano, wczytaj_json(DANE / "projekt.json", {})))

    na = [w for w in wyd if w["na_mapie"]]
    print(f"Hipotezy: {sum(1 for w in wyd if w.get('hipoteza'))}")
    print(f"Rekordy: {sum(1 for w in wyd if not w.get('hipoteza'))}; na mapie: {len(na)} (punkty {sum(w['rodzaj'] == 'punkt' for w in na)}, obszary {sum(w['rodzaj'] == 'obszar' for w in na)})")
    print("Domyślnie widoczne (A, B):", sum(w["pewnosc"] in "AB" for w in na), "; wszystkie A, B:", sum(w["pewnosc"] in "AB" for w in wyd))
    for w in wyd:
        if not w["na_mapie"]:
            print(f"  tylko lista: {w['id']} [{w['powod_listy']}] {w['tytul'][:60]}")
    for o in ostrzezenia:
        print("  UWAGA:", o)


if __name__ == "__main__":
    main()
