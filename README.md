# Wydarzenia w powiecie wadowickim, 0–1945

Statyczna strona z mapą udokumentowanych wydarzeń historycznych na terenie dzisiejszego powiatu wadowickiego (woj. małopolskie). Wygląd jak czarno-biała mapa z atlasu: białe tło, gruba granica powiatu, drogi i nazwy z OpenStreetMap, czerwone kropki z napisami, kolorowe obszary epidemii. Każde wydarzenie ma własną podstronę ze źródłami.

Dane powstają epokami. Dziś opracowane są epoki 0–966, 1564–1648, 1648–1772 i 1772–1815 (status każdej epoki czyta skrypt z `data/epoki.json` projektu badawczego).

## Uruchomienie lokalne

Strona nie potrzebuje budowania, żeby ją obejrzeć. Wystarczy serwer statyczny, bo przeglądarka nie wczyta plików JSON z `file://`:

```bash
python3 -m http.server 8765
```

Potem otwórz http://localhost:8765/.

## Dodanie nowej epoki

1. Wrzuć plik `<od>-<do>_zweryfikowane.jsonl` (lub `_v2`, `_v3`) do katalogu `data` projektu badawczego. Skrypt bierze najnowszą wersję każdej epoki.
2. Uruchom skrypt. Domyślnie czyta `../data`, inną ścieżkę podaj przez `--dane`:

   ```bash
   python3 skrypty/zbuduj.py
   ```

3. Przeczytaj wypis: rekordy tylko na liście i ostrzeżenia, np. miejscowość bez współrzędnych.
4. Zatwierdź zmiany (`git commit`) i wypchnij.

Epoka zapala się na suwaku sama, jeśli jej lata są w `dane/epoki.json`. Nowy zakres lat dopisz tam.

Skrypt respektuje `data/epoki.json` z projektu badawczego. Epoka o statusie innym niż `opracowana` jest na suwaku „w przygotowaniu”, a jej rekordy nie trafiają na stronę (poza hipotezami z `dane/hipotezy.json`, czytanymi z ostatniej zakończonej weryfikacji, czyli najstarszego pliku). Po zmianie statusu na `opracowana` skrypt weźmie najnowszą wersję.

## Co jest na mapie

Każdy rekord, który przeszedł filtr (status, pewność), jest na mapie. Wydarzenia punktowe są domyślnie widoczne przy pewności A i B, zjawiska obszarowe (`charakter: obszar`) także przy C.

- `zasieg: szerszy`: nakładka w pasy na cały widok, z podpisami w panelu „Zjawiska obejmujące cały region”.
- `zasieg: powiat` albo `zakres: region` bez ustalonych granic: nakładka na powiat. Bez pola `zasieg` ma podpis „zasięg nieokreślony”.
- `zasieg: sasiedni` i miejsca poza zasięgiem: znacznik ze strzałką na krawędzi oraz kropka w widoku „Pokaż szerszy kontekst”. Skrypt ostrzega, jeśli rekord nie ma wpisu `kontekst`.
- `data_szacowana: true`: data z „ok.”, przerywany obrys i blok „Data szacowana” na podstronie.

## Pliki, które można poprawiać ręcznie

- `dane/lokalizacje_wydarzen.json`: miejsce wydarzenia, gdy nie wynika wprost z pól rekordu: `miejscowosci` (obszar), `linia` (schematyczna trasa), `rzeka`, `kontekst` (miejsce poza mapą), `punkt_miedzy`, `lata`, `data_tekst`, `notatka`, `przyblizony`.
- `dane/kontekst_miejsca.json`: położenia miejsc poza zasięgiem mapy, z OSM (`skrypty/pobierz_kontekst.py`).
- `dane/etykiety.json`: krótszy napis na mapie.
- `dane/hipotezy.json`: rekordy niepotwierdzone jako zdarzenia, pokazywane jako hipotezy tła (id → notatka). Rekordy z `hipoteza: true` trafiają tam same. Hipoteza ma plakietkę, przerywaną linię i własną sekcję na liście, a nie wchodzi do liczby wydarzeń. Status w danych badawczych się nie zmienia.
- `dane/slugi.json`: adresy podstron. Skrypt tylko dopisuje nowe, dzięki czemu adresy są stałe nawet po zmianie tytułu.
- `dane/projekt.json`: adres repozytorium widoczny w „O projekcie”.
- `assets/konfiguracja.js`: progi skali, granice 10 gmin powiatu (`gminyWewnetrzne`, domyślnie wyłączone), domyślny zakres lat.

Skrypt nie zmienia treści historycznej. Wszystko na stronie pochodzi z JSONL i z OSM.

## Odświeżenie danych OSM

Rzadko potrzebne. Pierwszy skrypt pobiera dane z Overpass API do `.cache_osm/`, drugi upraszcza je i zapisuje w `dane/geo/`:

```bash
python3 skrypty/pobierz_osm.py
python3 skrypty/pobierz_kontekst.py
python3 skrypty/przygotuj_geo.py
python3 skrypty/zbuduj.py
```

`przygotuj_geo.py` sprawdza też, czy obrys powiatu to dokładnie zewnętrzne granice 10 gmin.

## Dlaczego SVG, a nie MapLibre

Mapa jest rysowana w SVG, a D3 odpowiada tylko za przybliżanie i przesuwanie.

- Wektory są ostre na każdym ekranie i na wydruku.
- Kropki i napisy są zwykłymi linkami, więc działają klawiatura, czytniki ekranu, otwieranie w nowej karcie.
- Nie trzeba hostować plików glifów, których MapLibre wymaga do własnych etykiet.
- Układ etykiet (najpierw wyższa pewność, potem nowsze, bez nakładania) i rozsuwanie kropek i tak wymagają własnego kodu.

Koszt: SVG słabiej znosi bardzo dużo elementów. Przy tej skali danych (jeden powiat) to nie przeszkadza.

## Licencje i atrybucje

- Dane mapy (granice, drogi, miejscowości w `dane/geo/`): © OpenStreetMap contributors, [Open Database License (ODbL)](https://www.openstreetmap.org/copyright).
- Granice państw w szerszym kontekście (`dane/geo/kontekst.geojson`): [Natural Earth](https://www.naturalearthdata.com), domena publiczna.
- [D3](https://d3js.org) 7.9.0, licencja ISC: `assets/vendor/`.
- Opisy wydarzeń to własne parafrazy; krótkie cytaty podano ze źródłem na podstronie każdego wydarzenia.

Bez kont, kluczy i płatnych usług: strona nie pobiera nic spoza repozytorium.
