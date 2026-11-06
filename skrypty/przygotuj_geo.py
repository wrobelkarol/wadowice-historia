#!/usr/bin/env python3
"""Z surowych danych OSM (.cache_osm/) robi małe pliki dane/geo/*.geojson i sprawdza obrys powiatu."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import geo  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache_osm"
WY = ROOT / "dane" / "geo"
GMINY_POWIATU = {"Andrychów", "Brzeźnica", "Kalwaria Zebrzydowska", "Lanckorona", "Mucharz",
                 "Spytkowice", "Stryszów", "Tomice", "Wadowice", "Wieprz"}
TOL_GRANICA = 0.012  # km
TOL_DROGA = 0.015
KLASY = {"motorway": 0, "trunk": 1, "primary": 2, "secondary": 3, "tertiary": 4}
ATRYBUCJA = "© OpenStreetMap contributors, ODbL 1.0, https://www.openstreetmap.org/copyright"


def wczytaj(nazwa):
    return json.loads((CACHE / f"{nazwa}.json").read_text(encoding="utf-8"))["elements"]


def zapisz(nazwa, cechy):
    WY.mkdir(parents=True, exist_ok=True)
    obj = {"type": "FeatureCollection", "attribution": ATRYBUCJA, "features": cechy}
    (WY / f"{nazwa}.geojson").write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"  {nazwa}.geojson: {len(cechy)} cech, {(WY / f'{nazwa}.geojson').stat().st_size // 1024} KB")


def wspolrzedne(czlon):
    return [[w["lon"], w["lat"]] for w in czlon["geometry"]]


def geometria_relacji(rel, drogi_uproszczone=None, tol=TOL_GRANICA):
    zewn, wewn = [], []
    for m in rel["members"]:
        if m["type"] != "way" or "geometry" not in m:
            continue
        if drogi_uproszczone is not None:
            if m["ref"] not in drogi_uproszczone:
                drogi_uproszczone[m["ref"]] = [geo.zaokragl(p) for p in geo.uprosc(wspolrzedne(m), tol)]
            linia = drogi_uproszczone[m["ref"]]
        else:
            linia = [geo.zaokragl(p) for p in geo.uprosc(wspolrzedne(m), tol)]
        (wewn if m.get("role") == "inner" else zewn).append(linia)
    pol = []
    for r, zamk in geo.zszyj(zewn):
        if not zamk:
            print(f"  UWAGA: niedomknięty pierścień w {rel['tags'].get('name')}")
            continue
        pol.append([r])
    for r, zamk in geo.zszyj(wewn):
        if zamk and pol:
            pol[0].append(r)
    if len(pol) == 1:
        return {"type": "Polygon", "coordinates": pol[0]}
    return {"type": "MultiPolygon", "coordinates": pol}


def main():
    granice = wczytaj("granice")
    cache_drog = {}
    powiat = next(e for e in granice if e["tags"].get("admin_level") == "6")
    gminy = [e for e in granice if e["tags"].get("admin_level") == "7"]

    wew = [g for g in gminy if g["tags"]["name"].replace("gmina ", "") in GMINY_POWIATU]
    naz_wew = {g["tags"]["name"].replace("gmina ", "") for g in wew}
    print("Gminy powiatu:", len(wew), "brakuje:", GMINY_POWIATU - naz_wew)
    if naz_wew != GMINY_POWIATU:
        raise SystemExit("Lista gmin powiatu nie zgadza się z danymi OSM.")

    # Kontrola: obrys powiatu to dokładnie te drogi OSM, które należą do jednej z 10 gmin.
    drogi_gmin = {}
    for g in wew:
        for m in g["members"]:
            if m["type"] == "way":
                drogi_gmin[m["ref"]] = drogi_gmin.get(m["ref"], 0) + 1
    zewn = {r for r, n in drogi_gmin.items() if n == 1}
    drogi_powiatu = {m["ref"] for m in powiat["members"] if m["type"] == "way"}
    print(f"Kontrola obrysu: drogi powiatu {len(drogi_powiatu)}, zewnętrzne drogi 10 gmin {len(zewn)}, "
          f"różnica {len(drogi_powiatu ^ zewn)}")
    if drogi_powiatu != zewn:
        print("  UWAGA: obrys powiatu i suma gmin różnią się:", sorted(drogi_powiatu ^ zewn)[:20])

    g_powiat = geometria_relacji(powiat, cache_drog)
    cechy_gmin = []
    for g in sorted(gminy, key=lambda x: x["tags"]["name"]):
        nazwa = g["tags"]["name"].replace("gmina ", "")
        geom = geometria_relacji(g, cache_drog)
        cechy_gmin.append({"type": "Feature", "geometry": geom, "properties": {
            "nazwa": nazwa, "w_powiecie": nazwa in GMINY_POWIATU, "terc": g["tags"].get("teryt:terc"),
            "osm_relacja": g["id"], "etykieta": geo.punkt_etykiety(geom)}})
    print("Gminy przyległe:", ", ".join(c["properties"]["nazwa"] for c in cechy_gmin if not c["properties"]["w_powiecie"]))

    # Zasięg mapy: powiat i gminy przyległe bez granic wewnętrznych.
    wszystkie = [r for c in cechy_gmin for r in geo.pierscienie_geom(c["geometry"])]
    obrys = geo.rozpusc(wszystkie)
    obrys = [r for r in obrys if len(r) >= 4]
    g_zasieg = {"type": "Polygon", "coordinates": obrys}
    ob_zasieg = geo.Obszar(obrys)
    ob_powiat = geo.Obszar(geo.pierscienie_geom(g_powiat))
    print(f"Zasięg: {len(obrys)} pierścieni, {sum(len(r) for r in obrys)} punktów")

    zapisz("powiat", [{"type": "Feature", "geometry": g_powiat, "properties": {
        "nazwa": "powiat wadowicki", "terc": powiat["tags"].get("teryt:terc"), "osm_relacja": powiat["id"]}}])
    zapisz("gminy", cechy_gmin)
    zapisz("zasieg", [{"type": "Feature", "geometry": g_zasieg, "properties": {"nazwa": "powiat i gminy przyległe"}}])

    # Drogi: tylko odcinki w zasięgu, jedna cecha na klasę.
    def zbierz_drogi(elementy, klasa_fn, tol):
        wg_klasy = {}
        for w in elementy:
            if "geometry" not in w:
                continue
            kl = klasa_fn(w)
            pts = geo.uprosc([[g["lon"], g["lat"]] for g in w["geometry"]], tol)
            biez = []
            for a, b in zip(pts, pts[1:]):
                if ob_zasieg.zawiera(a) or ob_zasieg.zawiera(b):
                    if not biez:
                        biez = [geo.zaokragl(a)]
                    biez.append(geo.zaokragl(b))
                elif biez:
                    wg_klasy.setdefault(kl, []).append(biez)
                    biez = []
            if biez:
                wg_klasy.setdefault(kl, []).append(biez)
        return wg_klasy

    drogi = zbierz_drogi(wczytaj("drogi"), lambda w: KLASY[w["tags"]["highway"]], TOL_DROGA)
    zapisz("drogi", [{"type": "Feature", "geometry": {"type": "MultiLineString", "coordinates": drogi[k]},
                      "properties": {"klasa": k}} for k in sorted(drogi, reverse=True)])
    drobne = zbierz_drogi(wczytaj("drogi_drobne"), lambda w: 5, 0.02)
    zapisz("drogi_drobne", [{"type": "Feature", "geometry": {"type": "MultiLineString", "coordinates": drobne[k]},
                             "properties": {"klasa": k}} for k in drobne])

    # Skawa: rysowana tylko razem z wydarzeniem, które jej dotyczy; nie jest warstwą podkładu.
    skawa = zbierz_drogi(wczytaj("skawa"), lambda w: 0, TOL_DROGA)
    zapisz("skawa", [{"type": "Feature", "geometry": {"type": "MultiLineString", "coordinates": skawa[0]},
                      "properties": {"nazwa": "Skawa"}}])
    # Miasta poza zasięgiem mapy, między którymi źródła prowadzą trasy.
    zapisz("punkty_tras", [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(n["lon"], 5), round(n["lat"], 5)]},
                            "properties": {"nazwa": n["tags"]["name"], "typ": n["tags"]["place"], "gmina": None, "w_powiecie": False, "osm_wezel": n["id"]}}
                           for n in wczytaj("punkty_tras") if n["tags"].get("place") in ("city", "town")])

    # Miejscowości.
    ob_gmin = [(c["properties"]["nazwa"], geo.Obszar(geo.pierscienie_geom(c["geometry"]))) for c in cechy_gmin]
    miejsca = []
    for n in wczytaj("miejscowosci"):
        p = [n["lon"], n["lat"]]
        if "name" not in n.get("tags", {}) or not ob_zasieg.zawiera(p):
            continue
        t = n["tags"]
        gmina = next((nz for nz, ob in ob_gmin if ob.zawiera(p)), None)
        prop = {"nazwa": t["name"], "typ": t["place"], "gmina": gmina, "w_powiecie": ob_powiat.zawiera(p), "osm_wezel": n["id"]}
        if str(t.get("population", "")).isdigit():
            prop["ludnosc"] = int(t["population"])
        if t.get("wikidata"):
            prop["wikidata"] = t["wikidata"]
        miejsca.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(p[0], 5), round(p[1], 5)]}, "properties": prop})
    miejsca.sort(key=lambda f: (not f["properties"]["w_powiecie"], f["properties"]["nazwa"]))
    # Przysiółków jest ponad 2000, a potrzebne są dopiero przy dużym zbliżeniu: osobny plik doczytywany na żądanie.
    zapisz("miejscowosci", [f for f in miejsca if f["properties"]["typ"] != "hamlet"])
    zapisz("przysiolki", [f for f in miejsca if f["properties"]["typ"] == "hamlet"])

    # Granice miejscowości tam, gdzie są w OSM.
    wynik, widziane = [], set()
    for e in wczytaj("granice_miejscowosci"):
        t = e.get("tags", {})
        nazwa = t.get("name")
        if not nazwa:
            continue
        try:
            if e["type"] == "relation":
                geom = geometria_relacji(e, None)
            else:
                pts = [geo.zaokragl(p) for p in geo.uprosc([[g["lon"], g["lat"]] for g in e["geometry"]], TOL_GRANICA)]
                if pts[0] != pts[-1]:
                    continue
                geom = {"type": "Polygon", "coordinates": [pts]}
            rs = geo.pierscienie_geom(geom)
        except (KeyError, ValueError, IndexError):
            continue
        if not rs or not rs[0]:
            continue
        srodek = geo.punkt_etykiety(geom)
        if not ob_zasieg.zawiera(srodek):
            continue
        kl = (nazwa, e["type"], e["id"])
        if kl in widziane:
            continue
        widziane.add(kl)
        gmina = next((nz for nz, ob in ob_gmin if ob.zawiera(srodek)), None)
        wynik.append({"type": "Feature", "geometry": geom, "properties": {
            "nazwa": nazwa, "gmina": gmina, "admin_level": t.get("admin_level"), "place": t.get("place"),
            "osm": f"{e['type']}/{e['id']}"}})
    wynik.sort(key=lambda f: (f["properties"]["nazwa"], f["properties"]["osm"]))
    zapisz("miejscowosci_granice", wynik)


if __name__ == "__main__":
    main()
