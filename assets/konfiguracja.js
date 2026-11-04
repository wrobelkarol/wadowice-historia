// Ustawienia mapy w jednym miejscu.
window.KONFIG = {
  gminyWewnetrzne: false,      // granice 10 gmin powiatu: domyślnie niewidoczne
  maxPrzyblizenie: 7,          // ile razy można przybliżyć względem widoku startowego
  pxKmGrupy: 13,               // poniżej tej skali (px na km) grupy miejscowości zwijają się do kropki z liczbą
  pxKmWsie: 11,                // od tej skali nazwy wsi
  pxKmPrzysiolki: 62,          // od tej skali nazwy przysiółków
  pxKmDrobneDrogi: 55,         // od tej skali drobniejsze drogi (doczytywane osobno)
  domyslneLata: null,          // np. [1648, 1772]; null = cały zakres 0–1945
  czcionka: '"Helvetica Neue", Helvetica, Arial, "Liberation Sans", sans-serif'
};
