// Przenosi widok mapy i zakres lat między podstronami, żeby „wróć do mapy” wracało do tego samego miejsca.
(function () {
  var h = location.hash.slice(1);
  if (!/(^|&)w=/.test(h)) return;
  document.querySelectorAll('a[data-z-stanem]').forEach(function (a) {
    a.setAttribute('href', a.getAttribute('href').split('#')[0] + '#' + h);
  });
})();
