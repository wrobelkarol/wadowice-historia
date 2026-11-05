// Filtr tekstowy listy wydarzeń; ignoruje wielkość liter i polskie znaki.
(function () {
  function norm(t) {
    return t.toLowerCase().replace(/ł/g, 'l').normalize('NFD').replace(/[̀-ͯ]/g, '');
  }
  var pole = document.getElementById('filtr'), licznik = document.getElementById('licznik');
  var pozycje = Array.prototype.map.call(document.querySelectorAll('.lista-wszystkich li'), function (li) {
    return { li: li, tekst: norm(li.getAttribute('data-szukaj')), hipoteza: !!li.closest('#hipotezy') };
  });
  var sekcje = document.querySelectorAll('.sekcja-wykaz');
  function odmiana(n) {
    if (n === 1) return '1 wydarzenie';
    var a = n % 10, b = n % 100;
    return n + (a >= 2 && a <= 4 && (b < 12 || b > 14) ? ' wydarzenia' : ' wydarzeń');
  }
  function filtruj() {
    var slowa = norm(pole.value).split(/\s+/).filter(Boolean), ile = 0, hip = 0;
    pozycje.forEach(function (p) {
      var ok = slowa.every(function (s) { return p.tekst.indexOf(s) >= 0; });
      p.li.hidden = !ok;
      if (ok) { if (p.hipoteza) hip++; else ile++; }
    });
    sekcje.forEach(function (s) { s.hidden = !s.querySelector('li:not([hidden])'); });
    licznik.textContent = odmiana(ile) + (hip ? ' i hipotezy: ' + hip : '');
  }
  pole.addEventListener('input', filtruj);
  filtruj();
})();
