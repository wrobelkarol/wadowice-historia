// Ustawienia mapy w jednym miejscu.
window.KONFIG = {
  gminyWewnetrzne: false,      // granice 10 gmin powiatu: domyślnie niewidoczne
  maxPrzyblizenie: 7,          // ile razy można przybliżyć względem widoku startowego
  pxKmGrupy: 13,               // poniżej tej skali (px na km) grupy miejscowości zwijają się do kropki z liczbą
  pxKmWsie: 11,                // od tej skali nazwy wsi
  pxKmPrzysiolki: 62,          // od tej skali nazwy przysiółków
  pxKmDrobneDrogi: 55,         // od tej skali drobniejsze drogi (doczytywane osobno)
  panelOtwartyDo: 5,           // panel zjawisk regionalnych otwiera się sam, gdy jest ich najwyżej tyle
  kontekstOkno: [14.0, 48.0, 21.6, 51.2], // szerszy kontekst: lon0, lat0, lon1, lat1
  kontekstKraje: [['Polska', 19.6, 50.9], ['Czechy', 15.6, 49.5], ['Słowacja', 19.4, 48.75]],
  domyslneLata: null,          // np. [1648, 1772]; null = cały zakres 0–1945
  czcionka: '"Helvetica Neue", Helvetica, Arial, "Liberation Sans", sans-serif'
};
