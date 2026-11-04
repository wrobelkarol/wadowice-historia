#!/usr/bin/env python3
"""Pobiera surowe dane OSM (Overpass API) do .cache_osm/. Tylko biblioteka standardowa.

Uruchamiaj rzadko: publiczne serwery Overpass są współdzielone, a dane zmieniają się wolno.
Następny krok: skrypty/przygotuj_geo.py (upraszcza i zapisuje dane/geo/*.geojson).
"""
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache_osm"
SERWERY = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
POWIAT = 2432814  # relacja OSM: powiat wadowicki
BBOX = "49.60,19.05,50.15,20.05"  # z zapasem: powiat i gminy przyległe

ZAPYTANIA = {
    "granice": f"""[out:json][timeout:120];
rel({POWIAT})->.p;
way(r.p)->.w;
rel(bw.w)["boundary"="administrative"]["admin_level"="7"]->.przylegle;
.p map_to_area->.a;
rel(area.a)["boundary"="administrative"]["admin_level"="7"]->.wewnatrz;
(.p;.przylegle;.wewnatrz;);
out geom;""",
    "miejscowosci": f"""[out:json][timeout:120];
node["place"~"^(city|town|village|hamlet)$"]({BBOX});
out body;""",
    "drogi": f"""[out:json][timeout:180];
way["highway"~"^(motorway|trunk|primary|secondary|tertiary)$"]({BBOX});
out tags geom;""",
    "drogi_drobne": f"""[out:json][timeout:180];
way["highway"="unclassified"]({BBOX});
out tags geom;""",
    "granice_miejscowosci": f"""[out:json][timeout:180];
(
  rel["boundary"="administrative"]["admin_level"~"^(8|9|10)$"]({BBOX});
  rel["place"~"^(city|town|village|hamlet|suburb|quarter)$"]({BBOX});
  way["place"~"^(city|town|village|hamlet|suburb|quarter)$"]({BBOX});
);
out geom;""",
}


def pobierz(zapytanie):
    # curl, bo systemowy Python na macOS bywa zbudowany ze starym LibreSSL i nie łączy się z serwerem
    czekaj = 20
    for proba in range(16):
        url = SERWERY[proba % len(SERWERY)]
        wynik = subprocess.run(
            ["curl", "-sS", "-m", "200", "-A", "wadowice-historia-build/0.1",
             "--data-urlencode", "data=" + zapytanie, url],
            capture_output=True,
        )
        try:
            obj = json.loads(wynik.stdout)
            if obj.get("elements"):
                return obj
            print(f"  puste wyniki ({url}): {obj.get('remark', '')}", flush=True)
        except ValueError:
            print(f"  próba {proba + 1} ({url}): {wynik.stdout[:60]!r} {wynik.stderr[:80]!r}", flush=True)
        time.sleep(czekaj)
        czekaj = min(czekaj * 1.6, 240)
    raise SystemExit("Nie udało się pobrać danych: serwery Overpass nie odpowiadają.")


def main():
    CACHE.mkdir(exist_ok=True)
    nazwy = sys.argv[1:] or list(ZAPYTANIA)
    for nazwa in nazwy:
        plik = CACHE / f"{nazwa}.json"
        if plik.exists():
            print(f"{nazwa}: już pobrane", flush=True)
            continue
        print(f"{nazwa}: pobieram", flush=True)
        obj = pobierz(ZAPYTANIA[nazwa])
        plik.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        print(f"{nazwa}: {len(obj['elements'])} elementów, {plik.stat().st_size // 1024} KB", flush=True)
        time.sleep(10)


if __name__ == "__main__":
    main()
