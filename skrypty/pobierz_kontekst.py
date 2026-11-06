#!/usr/bin/env python3
"""Pobiera dane widoku „szerszy kontekst”: granice państw z Natural Earth (domena publiczna)
i położenia nazwanych miejsc z OSM (Nominatim). Następny krok: skrypty/przygotuj_geo.py."""
import json
import pathlib
import subprocess
import time
import urllib.parse

CACHE = pathlib.Path(__file__).resolve().parent.parent / ".cache_osm"
UA = "wadowice-historia-build/0.1"
NE = "https://cdn.jsdelivr.net/gh/nvkelso/natural-earth-vector@v5.1.2/geojson/ne_50m_admin_0_countries.geojson"
MIEJSCA = {"Ołomuniec": "Olomouc", "Brama Morawska": "Moravská brána", "Gliwice": "Gliwice", "Cieszyn": "Cieszyn",
           "Maków Podhalański": "Maków Podhalański", "Podgórze": "Podgórze, Kraków", "Oświęcim": "Oświęcim",
           "Kraków": "Kraków", "Praga": "Praha"}


def curl(*arg):
    return subprocess.run(["curl", "-sS", "-m", "200", "-L", "-A", UA, *arg], capture_output=True, check=True).stdout


def main():
    CACHE.mkdir(exist_ok=True)
    (CACHE / "ne_countries.geojson").write_bytes(curl(NE))
    wynik = {}
    for nazwa, q in MIEJSCA.items():
        r = json.loads(curl("https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&q=" + urllib.parse.quote(q)))
        if r:
            wynik[nazwa] = {"lon": round(float(r[0]["lon"]), 4), "lat": round(float(r[0]["lat"]), 4),
                            "osm": f'{r[0]["osm_type"]}/{r[0]["osm_id"]}', "opis": r[0]["display_name"][:60]}
        time.sleep(1.2)
    (CACHE / "kontekst_miejsca.json").write_text(json.dumps(wynik, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
