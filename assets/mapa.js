/* Mapa wydarzeń: SVG rysowane z własnych plików GeoJSON. Zależność: d3 (tylko zoom i selekcje). */
(function () {
  'use strict';
  var K = window.KONFIG;
  var LON0 = 19.53, LAT0 = 49.89, RKM = 6371, RAD = Math.PI / 180, COS0 = Math.cos(LAT0 * RAD);
  // Świat w kilometrach od punktu odniesienia: skala zoomu to wprost piksele na kilometr.
  function rzut(ll) { return [RKM * (ll[0] - LON0) * RAD * COS0, -RKM * (ll[1] - LAT0) * RAD]; }
  function odrzut(p) { return [p[0] / (RKM * RAD * COS0) + LON0, -p[1] / (RKM * RAD) + LAT0]; }

  var gKrawedz = d3.select('#e-krawedz');
  var sv = d3.select('#plotno'), swiat = d3.select('#swiat');
  var gMiejsca = d3.select('#e-miejsca'), gLinie = d3.select('#e-linie'), gEtykiety = d3.select('#e-etykiety'), gKropki = d3.select('#e-kropki');
  var dymek = document.getElementById('dymek'), listaGrupy = document.getElementById('lista-grupy');
  var dotyk = window.matchMedia('(pointer: coarse)').matches;
  var stan = { od: 0, do: 1945, c: false, d: false, obszary: true };
  var D = {}, tr = d3.zoomIdentity, W = 0, H = 0, zakresSwiata = null, widokStartowy = null, doWidoku = null;
  var zoom = d3.zoom();

  /* ---------- pomiary tekstu ---------- */
  var ctx = document.createElement('canvas').getContext('2d'), pamiec = {};
  function szer(t, font) {
    var kl = font + '|' + t;
    if (pamiec[kl] === undefined) { ctx.font = font; pamiec[kl] = ctx.measureText(t).width; }
    return pamiec[kl];
  }
  var F = K.czcionka;
  var FONT = {
    etykieta: dotyk ? '600 13px ' + F : '600 13.5px ' + F,
    grupa: '700 15px ' + F, miasto: '600 15px ' + F, wies: '400 12.5px ' + F,
    przysiolek: '400 11px ' + F, gmina: '400 11px ' + F
  };
  function zawijaj(tekst, maks) {
    var w = tekst.split(' '), lin = [], b = '';
    w.forEach(function (s) {
      if (b && (b + ' ' + s).length > maks) { lin.push(b); b = s; } else { b = b ? b + ' ' + s : s; }
    });
    if (b) lin.push(b);
    return lin;
  }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function odmiana(n) {
    if (n === 1) return '1 wydarzenie';
    var r10 = n % 10, r100 = n % 100;
    return n + (r10 >= 2 && r10 <= 4 && (r100 < 12 || r100 > 14) ? ' wydarzenia' : ' wydarzeń');
  }

  /* ---------- geometria ---------- */
  function sciezka(geom) {
    var cz = [];
    function pierscien(r, zamknij) {
      cz.push(r.map(function (ll, i) { var p = rzut(ll); return (i ? 'L' : 'M') + p[0].toFixed(3) + ' ' + p[1].toFixed(3); }).join('') + (zamknij ? 'Z' : ''));
    }
    if (geom.type === 'Polygon') geom.coordinates.forEach(function (r) { pierscien(r, true); });
    else if (geom.type === 'MultiPolygon') geom.coordinates.forEach(function (p) { p.forEach(function (r) { pierscien(r, true); }); });
    else if (geom.type === 'LineString') pierscien(geom.coordinates);
    else if (geom.type === 'MultiLineString') geom.coordinates.forEach(function (l) { pierscien(l); });
    return cz.join('');
  }
  function bbox(cechy) {
    var x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    function pkt(ll) { var p = rzut(ll); if (p[0] < x0) x0 = p[0]; if (p[0] > x1) x1 = p[0]; if (p[1] < y0) y0 = p[1]; if (p[1] > y1) y1 = p[1]; }
    function chodz(c) { if (typeof c[0] === 'number') pkt(c); else c.forEach(chodz); }
    cechy.forEach(function (f) { chodz(f.geometry.coordinates); });
    return [x0, y0, x1, y1];
  }

  /* ---------- filtr ---------- */
  // Zjawiska obszarowe są widoczne także przy pewności C; wydarzenia punktowe o pewności C wymagają przełącznika.
  function pewnoscOk(e) { return e.pewnosc === 'A' || e.pewnosc === 'B' || (e.pewnosc === 'C' && (stan.c || e.obszarowe)) || (e.pewnosc === 'D' && stan.d); }
  function wZakresie(e) {
    if (e.rok_od === null) return false;
    if (e.lata) return e.lata.some(function (r) { return r >= stan.od && r <= stan.do; });
    var pelny = stan.od <= D.epoki[0].od && stan.do >= D.epoki[D.epoki.length - 1].do;
    return pelny || (e.rok_od <= stan.do && e.rok_do >= stan.od);
  }
  // „Zjawisko obszarowe” dla przełącznika: wszystko, co nie jest zwykłą kropką, także strzałki zjawisk spoza mapy.
  function czyObszarowe(e) { return e.rodzaj !== 'punkt' || e.obszarowe; }
  function naMapie(e) { return e.na_mapie && pewnoscOk(e) && wZakresie(e) && (stan.obszary || !czyObszarowe(e)); }
  var RANGA = { A: 0, B: 1, C: 2, D: 3 };
  // Etykiety: wyższa pewność, potem nowsze. Obszar dostaje podpis przed kropkami tej samej pewności, bo sam nie ma znacznika.
  function ranga(e) { return RANGA[e.pewnosc] - (e.rodzaj !== 'punkt' ? 0.5 : 0); }
  function priorytet(a, b) { return ranga(a) - ranga(b) || (b.rok_od - a.rok_od) || (a.id < b.id ? -1 : 1); }

  /* ---------- warstwy statyczne ---------- */
  function rysujPodklad() {
    d3.select('#w-powiat').attr('d', sciezka(D.powiat.features[0].geometry));
    var gminy = D.gminy.features.filter(function (f) { return K.gminyWewnetrzne || !f.properties.w_powiecie; });
    d3.select('#w-gminy').selectAll('path').data(gminy).join('path').attr('d', function (f) { return sciezka(f.geometry); });
    d3.select('#przyciecie-sciezka').attr('d', sciezka(D.zasieg.features[0].geometry));
    var klasy = ['droga-0', 'droga-1', 'droga-2', 'droga-3', 'droga-4'];
    d3.select('#w-drogi').selectAll('path.droga').data(D.drogi.features).join('path')
      .attr('class', function (f) { return 'droga ' + klasy[f.properties.klasa]; })
      .attr('d', function (f) { return sciezka(f.geometry); });
    var uzyte = {};
    D.events.forEach(function (e) { if (e.obszar) { (uzyte[e.obszar] = uzyte[e.obszar] || []).push(e); } });
    D.obszaryWgId = {};
    D.obszary.features.forEach(function (f) { D.obszaryWgId[f.properties.id] = f; });
    // Pliki mogą chwilowo pochodzić z różnych publikacji (pamięć podręczna). Bez geometrii wydarzenie zostaje na liście.
    D.events.forEach(function (e) { if (e.obszar && !D.obszaryWgId[e.obszar]) e.na_mapie = false; });
    // Epidemia leży na spodzie; zaraza bydła i głód na tym samym obszarze rysują się na niej kreskowaniem.
    var kolejnosc = { inne: -2, osadnictwo: -1, epidemia: 0, epizootia: 1, glod: 2 };
    var obs = D.events.filter(function (e) { return e.rodzaj === 'obszar' && e.na_mapie; })
      .sort(function (a, b) { return kolejnosc[a.typ] - kolejnosc[b.typ]; });
    d3.select('#w-obszary').selectAll('path').data(obs, function (e) { return e.id; }).join('path')
      .attr('class', function (e) { return 'obszar obszar-' + e.typ + (e.pewnosc === 'C' || e.hipoteza || e.data_szacowana ? ' obszar-c' : ''); })
      .attr('d', function (e) { return sciezka(D.obszaryWgId[e.obszar].geometry); })
      .attr('tabindex', 0).attr('role', 'link')
      .attr('aria-label', function (e) { return e.tytul + ', ' + e.data + ', pewność ' + e.pewnosc; })
      .on('click', function (ev, e) {
        var nakladki = widoczne().filter(function (x) { return x.obszar === e.obszar; });
        if (nakladki.length > 1) { pokazListe('Obszar: ' + e.miejsce_obszaru, nakladki, ev.clientX, ev.clientY); }
        else { idz(e); }
      })
      .on('keydown', function (ev, e) { if (ev.key === 'Enter') idz(e); })
      .on('mouseenter focus', function (ev, e) { pokazDymek(e, ev); })
      .on('mouseleave blur', schowajDymek);
    rysujLinie();
    d3.select('#w-nak-region').attr('d', sciezka(D.zasieg.features[0].geometry));
    d3.select('#w-nak-powiat').attr('d', sciezka(D.powiat.features[0].geometry));
    d3.selectAll('#w-nakladki path').on('click', function (ev) {
      var n = widoczne().filter(function (e) { return e.rodzaj === 'nakladka' && (this.id === 'w-nak-region' ? e.nakladka === 'region' : e.nakladka === 'powiat'); }, this);
      if (n.length === 1) idz(n[0]); else ustawPanel(true);
    });
  }
  function rysujLinie() {
    var linie = D.events.filter(function (e) { return e.rodzaj === 'linia' && e.na_mapie; });
    var g = d3.select('#w-linie').selectAll('g').data(linie, function (e) { return e.id; }).join('g')
      .attr('class', function (e) { return 'linia linia-' + e.linia_typ + (e.hipoteza ? ' linia-hip' : ''); })
      .attr('tabindex', 0).attr('role', 'link')
      .attr('aria-label', function (e) { return e.tytul + ', ' + e.data + ', pewność ' + e.pewnosc; })
      .on('click', function (ev, e) { idz(e); })
      .on('keydown', function (ev, e) { if (ev.key === 'Enter') idz(e); })
      .on('mouseenter focus', function (ev, e) { pokazDymek(e, ev); })
      .on('mouseleave blur', schowajDymek);
    g.selectAll('path').data(function (e) { var d = sciezka(D.obszaryWgId[e.obszar].geometry); return [{ k: 'linia-traf', d: d }, { k: 'linia-kreska', d: d }]; })
      .join('path').attr('class', function (x) { return x.k; }).attr('d', function (x) { return x.d; });
  }
  function idz(e) { zapiszStan(); location.href = e.url + '#' + kodStanu(); }

  /* ---------- stan w adresie ---------- */
  function kodStanu() {
    var cz = [];
    var c = odrzut(tr.invert([W / 2, H / 2]));
    cz.push('w=' + c[0].toFixed(4) + ',' + c[1].toFixed(4) + ',' + tr.k.toFixed(1));
    if (stan.od > 0 || stan.do < 1945) cz.push('lata=' + stan.od + '-' + stan.do);
    if (stan.c) cz.push('c=1');
    if (stan.d) cz.push('d=1');
    if (stan.kontekst) cz.push('k=1');
    if (!stan.obszary) cz.push('o=0');
    return cz.join('&');
  }
  var zapisCzasomierz = 0;
  function zapiszStan() { history.replaceState(null, '', '#' + kodStanu()); }
  function zapiszPozniej() { clearTimeout(zapisCzasomierz); zapisCzasomierz = setTimeout(zapiszStan, 250); }
  function czytajStan() {
    var h = {};
    location.hash.slice(1).split('&').forEach(function (p) { var i = p.indexOf('='); if (i > 0) h[p.slice(0, i)] = p.slice(i + 1); });
    if (h.lata && /^\d+-\d+$/.test(h.lata)) { var l = h.lata.split('-').map(Number); stan.od = Math.max(0, l[0]); stan.do = Math.min(1945, l[1]); }
    else if (K.domyslneLata) { stan.od = K.domyslneLata[0]; stan.do = K.domyslneLata[1]; }
    stan.c = h.c === '1'; stan.d = h.d === '1'; stan.kontekst = h.k === '1'; stan.obszary = h.o !== '0';
    if (h.w) { var v = h.w.split(',').map(Number); if (v.length === 3 && v.every(isFinite) && v[2] > 0) doWidoku = v; }
  }

  /* ---------- szerszy kontekst ---------- */
  var kKontekst = 1, widokKontekstu = null, kontekstDane = null, ruszona = false;
  function doczytajKontekst() {
    if (kontekstDane) return Promise.resolve();
    return Promise.all([json('dane/geo/kontekst.geojson'), json('dane/kontekst_miejsca.json')]).then(function (w) {
      kontekstDane = w[1];
      d3.select('#w-kontekst').selectAll('path').data(w[0].features).join('path').attr('d', function (f) { return sciezka(f.geometry); });
      zaplanujUklad();
    });
  }
  function ustawKontekst(wlacz, animuj) {
    stan.kontekst = wlacz;
    if (animuj) ruszona = true;
    var b = document.querySelector('.kontekst-btn');
    b.textContent = wlacz ? 'Wróć do powiatu' : 'Pokaż szerszy kontekst';
    b.setAttribute('aria-pressed', wlacz);
    d3.select('#w-kontekst').attr('display', wlacz ? null : 'none');
    if (wlacz) doczytajKontekst();
    ustawWymiary(false);
    if (animuj) sv.transition().duration(500).call(zoom.transform, wlacz ? widokKontekstu : widokStartowy);
    zapiszPozniej();
  }

  /* ---------- panel zjawisk obejmujących cały region ---------- */
  var KOLORY = { migracja_ludow: '#7d5ba6', szlak_handlowy: '#b0892f', wyprawa: '#b5473c', osadnictwo: '#6f9a5a', zmiana_wladzy_granic: '#4f6d8f',
    kwaterunek_rekwizycje: '#a0623a', przemarsz: '#c0504a', najazd: '#c0504a', powstanie_bunt: '#a33a5a', epidemia: '#d9b300', epizootia: '#e8791e', glod: '#8a5a2b', inne: '#7a7a7a' };
  function kolor(e) { return KOLORY[e.typ] || KOLORY.inne; }
  var panelRecznie = false, podpisNakladek = '';
  function ustawPanel(otwarty, reczny) {
    if (reczny !== false) panelRecznie = true;
    var el = document.querySelector('.panel-region');
    el.classList.toggle('otwarta', otwarty);
    el.querySelector('button').setAttribute('aria-expanded', otwarty);
    zaplanujUklad();
  }
  function odswiezNakladki(evs, k) {
    var lista = evs.filter(function (e) { return e.rodzaj === 'nakladka'; }).sort(function (a, b) { return a.rok_od - b.rok_od || (a.id < b.id ? -1 : 1); });
    d3.selectAll('.kreski-n').attr('patternTransform', 'scale(' + (1 / k).toFixed(5) + ') rotate(45)');
    var podpis = lista.map(function (e) { return e.id; }).join();
    if (podpis === podpisNakladek) return;
    podpisNakladek = podpis;
    [['region', '#pasy-region', '#w-nak-region'], ['powiat', '#pasy-powiat', '#w-nak-powiat']].forEach(function (x) {
      var w = lista.filter(function (e) { return e.nakladka === x[0]; }), wz = d3.select(x[1]), szer = 11;
      wz.attr('width', Math.max(1, w.length) * szer).attr('height', 8);
      wz.selectAll('rect').data(w, function (e) { return e.id; }).join('rect')
        .attr('x', function (e, i) { return i * szer; }).attr('y', 0).attr('width', szer).attr('height', 8).attr('fill', kolor);
      d3.select(x[2]).attr('display', w.length ? null : 'none');
    });
    var el = document.querySelector('.panel-region');
    el.hidden = !lista.length;
    el.querySelector('button').textContent = 'Zjawiska obejmujące cały region (' + lista.length + ')';
    el.querySelector('ul').innerHTML = lista.map(function (e) {
      var tagi = (e.hipoteza ? '<span class="tag">hipoteza</span>' : '') + (e.nieokreslony ? '<span class="tag">zasięg nieokreślony</span>' : '') + (e.nakladka === 'powiat' && !e.nieokreslony ? '<span class="tag">powiat</span>' : '');
      return '<li><a href="' + esc(e.url) + '" class="link-wydarzenia"><i class="pr-kolor" style="background:' + kolor(e) + '"></i><span class="pz pz-' + e.pewnosc + '" aria-label="pewność ' + e.pewnosc + '">' + e.pewnosc + '</span> <span class="lw-data">' + esc(e.data) + '</span> ' + esc(e.etykieta) + ' ' + tagi + '</a></li>';
    }).join('');
    if (!panelRecznie) ustawPanel(lista.length > 0 && lista.length <= K.panelOtwartyDo, false);
    ustawPrzyciski();
  }

  /* ---------- znaczniki na krawędzi: zdarzenia poza widokiem ---------- */
  function rysujKrawedz(zn, zajete) {
    var u = polozenia(), leg = document.querySelector('.legenda').getBoundingClientRect();
    var x0 = 22, y0 = u.gora + 22, x1 = (W >= 700 ? leg.left : W) - 22, y1 = H - u.dol - 22, cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    var uloz = zn.map(function (m) {
      var dx = m.s[0] - cx, dy = m.s[1] - cy;
      var t = Math.min(dx > 0 ? (x1 - cx) / dx : dx < 0 ? (x0 - cx) / dx : 9e9, dy > 0 ? (y1 - cy) / dy : dy < 0 ? (y0 - cy) / dy : 9e9);
      return { e: m.e, kat: Math.atan2(dy, dx) * 180 / Math.PI, x: cx + dx * t, y: cy + dy * t };
    }).sort(function (a, b) { return a.y - b.y || a.x - b.x; });
    // Panel „Zjawiska obejmujące cały region” stoi w lewym dolnym rogu: znacznik pod nim byłby niewidoczny i nieklikalny.
    var pan = document.querySelector('.panel-region'), pr = pan && !pan.hidden ? pan.getBoundingClientRect() : null;
    if (pr) uloz.forEach(function (m) { if (m.x > pr.left - 14 && m.x < pr.right + 14 && m.y > pr.top - 14 && m.y < pr.bottom + 14) m.y = Math.max(y0, pr.top - 18); });
    uloz.sort(function (a, b) { return a.y - b.y || a.x - b.x; });
    uloz.forEach(function (m, i) { // kilka zdarzeń w tym samym kierunku: rozsuwamy wzdłuż krawędzi
      for (var j = 0; j < i; j++) { if (Math.abs(uloz[j].x - m.x) < 24 && Math.abs(uloz[j].y - m.y) < 24) m.y = uloz[j].y + 24; }
      m.y = Math.min(m.y, y1);
    });
    var font = FONT.etykieta, lh = 16, asc = 12.5;
    uloz.forEach(function (m) { zajete.push([m.x - 11, m.y - 11, m.x + 11, m.y + 11]); });
    uloz.forEach(function (m) {
      var tekst = m.e.etykieta + ', ' + m.e.data_krotka + ' (' + m.e.kontekst + ')';
      var w0 = zawijaj(tekst, W < 700 ? 22 : 30), w = 0;
      w0.forEach(function (t) { w = Math.max(w, szer(t, font)); });
      var h = w0.length * lh + 1, naLewo = m.x > cx;
      var r = naLewo ? prost(m.x - 13, m.y, w + 2, h, 'r', 'm') : prost(m.x + 13, m.y, w + 2, h, 'l', 'm');
      m.wiersze = w0; m.po = naLewo ? 'r' : 'l';
      if (wEkranie(r) && wolne(r, zajete)) { zajete.push(r); m.r = r; }
    });
    var sel = gKrawedz.selectAll('a').data(uloz, function (m) { return m.e.id; });
    var nowe = sel.enter().append('a').attr('class', 'krawedz');
    nowe.append('circle').attr('class', 'traf').attr('r', 12);
    nowe.append('path').attr('class', 'strzalka').attr('d', 'M9 0 L-6 -6.5 L-6 6.5 Z');
    nowe.append('text').attr('class', 'krawedz-tekst');
    sel.exit().remove();
    nowe.merge(sel).attr('href', function (m) { return m.e.url; })
      .attr('aria-label', function (m) { return m.e.tytul + ', ' + m.e.data + ', poza mapą: ' + m.e.kontekst + ', pewność ' + m.e.pewnosc; })
      .on('mouseenter focus', function (ev, m) { pokazDymek(m.e, ev); }).on('mouseleave blur', schowajDymek)
      .each(function (m) {
        var a = d3.select(this);
        a.select('.traf').attr('cx', m.x).attr('cy', m.y);
        a.select('.strzalka').attr('transform', 'translate(' + m.x.toFixed(1) + ' ' + m.y.toFixed(1) + ') rotate(' + m.kat.toFixed(1) + ')')
          .attr('class', 'strzalka' + (m.e.pewnosc === 'C' || m.e.hipoteza ? ' strzalka-obrys' : ''));
        var t = a.select('.krawedz-tekst');
        if (m.r) { t.attr('display', null); wpiszLinie(t, m.wiersze, m.r, m.po, lh, asc); } else { t.attr('display', 'none'); }
      });
  }

  /* ---------- wymiary i zoom ---------- */
  // Przyciski i legenda stoją nad panelem suwaka, którego wysokość zależy od zawijania tekstu.
  function ustawPrzyciski() {
    var dol = window.innerHeight - document.querySelector('.suwak-panel').getBoundingClientRect().top;
    document.querySelector('.zoom').style.bottom = (dol + 10) + 'px';
    document.querySelector('.legenda').style.bottom = window.innerWidth < 700 ? (dol + 10) + 'px' : '';
    document.querySelector('.kontekst-btn').style.bottom = (dol + 10) + 'px';
    document.querySelector('.panel-region').style.bottom = (window.innerWidth < 700 ? dol + 58 : dol + 10) + 'px';
  }
  function przeszkodyUi() {
    var r = [];
    document.querySelectorAll('.naglowek, .legenda, .suwak-panel, .zoom, .kontekst-btn, .panel-region').forEach(function (el) {
      var b = el.getBoundingClientRect();
      if (b.width) r.push([b.left - 4, b.top - 4, b.right + 4, b.bottom + 4]);
    });
    return r;
  }
  function polozenia() {
    var gora = document.querySelector('.naglowek').getBoundingClientRect().bottom;
    var dol = H - document.querySelector('.suwak-panel').getBoundingClientRect().top;
    return { gora: gora, dol: dol };
  }
  function ustawWymiary(zachowaj) {
    var srodek = (zachowaj && W) ? tr.invert([W / 2, H / 2]) : null;
    var staryK = tr.k;
    W = window.innerWidth; H = window.innerHeight;
    sv.attr('width', W).attr('height', H).attr('viewBox', '0 0 ' + W + ' ' + H);
    var u = polozenia(), m = W < 700 ? 10 : 34;
    // W ukrytym lub bardzo małym oknie dostępna wysokość bywa ujemna: skala musi zostać dodatnia.
    var uzytW = Math.max(40, W - 2 * m), uzytH = Math.max(40, H - u.gora - u.dol - 2 * m);
    var pw = bbox(D.powiat.features), za = bbox(D.zasieg.features);
    var kStart = Math.min(uzytW / (pw[2] - pw[0]), uzytH / (pw[3] - pw[1]));
    var kCaly = Math.min(uzytW / (za[2] - za[0]), uzytH / (za[3] - za[1]));
    var kMin = Math.min(kStart, kCaly);
    widokStartowy = d3.zoomIdentity.translate(
      m + uzytW / 2 - kStart * (pw[0] + pw[2]) / 2,
      u.gora + m + uzytH / 2 - kStart * (pw[1] + pw[3]) / 2).scale(kStart);
    var zapas = 300 / kMin;
    zakresSwiata = [[za[0] - zapas, za[1] - zapas - u.gora / kMin], [za[2] + zapas, za[3] + zapas + u.dol / kMin]];
    // Szerszy kontekst: to samo okno, ale z dostępem do Europy Środkowej.
    var ko0 = rzut([K.kontekstOkno[0], K.kontekstOkno[3]]), ko1 = rzut([K.kontekstOkno[2], K.kontekstOkno[1]]);
    var lg = W >= 700 ? document.querySelector('.legenda').getBoundingClientRect().width + 12 : 0, wK = Math.max(40, uzytW - lg);
    kKontekst = Math.min(wK / (ko1[0] - ko0[0]), uzytH / (ko1[1] - ko0[1]));
    widokKontekstu = d3.zoomIdentity.translate(
      m + wK / 2 - kKontekst * (ko0[0] + ko1[0]) / 2,
      u.gora + m + uzytH / 2 - kKontekst * (ko0[1] + ko1[1]) / 2).scale(kKontekst);
    if (stan.kontekst) {
      var z = 300 / kKontekst;
      zakresSwiata = [[ko0[0] - z, ko0[1] - z - u.gora / kKontekst], [ko1[0] + z, ko1[1] + z + u.dol / kKontekst]];
      kMin = kKontekst;
    }
    zoom.scaleExtent([kMin, kStart * K.maxPrzyblizenie]).extent([[0, 0], [W, H]]).translateExtent(zakresSwiata);
    if (srodek) {
      sv.call(zoom.transform, d3.zoomIdentity.translate(W / 2 - staryK * srodek[0], H / 2 - staryK * srodek[1]).scale(staryK));
    }
  }

  /* ---------- układ etykiet ---------- */
  function wolne(r, zajete) {
    for (var i = 0; i < zajete.length; i++) {
      var z = zajete[i];
      if (r[0] < z[2] && r[2] > z[0] && r[1] < z[3] && r[3] > z[1]) return false;
    }
    return true;
  }
  function wEkranie(r) { return r[0] >= 2 && r[1] >= 2 && r[2] <= W - 2 && r[3] <= H - 2; }
  function prost(ax, ay, w, h, po, pi) {
    var x = ax - (po === 'c' ? w / 2 : po === 'r' ? w : 0);
    var y = ay - (pi === 'b' ? h : pi === 'm' ? h / 2 : 0);
    return [x, y, x + w, y + h];
  }
  // Kandydaci na położenie etykiety kropki stojącej osobno: najpierw nad kropką.
  function kandydaciPojedyncza(d, w, h) {
    return [
      { r: prost(d[0], d[1] - 7, w, h, 'c', 'b'), po: 'c' },
      { r: prost(d[0] + 9, d[1], w, h, 'l', 'm'), po: 'l' },
      { r: prost(d[0] - 9, d[1], w, h, 'r', 'm'), po: 'r' },
      { r: prost(d[0], d[1] + 7, w, h, 'c', 't'), po: 'c' }
    ];
  }
  // Etykieta kropki w grupie stoi poza grupą, z cienką linią do kropki.
  function kandydaciGrupa(s, R, d, w, h) {
    var phi = Math.atan2(d[1] - s[1], d[0] - s[0]);
    if (Math.abs(d[0] - s[0]) + Math.abs(d[1] - s[1]) < 0.5) phi = -Math.PI / 2;
    var out = [];
    [R + 9, R + 26, R + 48].forEach(function (rr) { // dalej etykieta traci związek z kropką: pojawi się po przybliżeniu
      var katy = [];
      for (var i = 0; i < 12; i++) {
        var a = -Math.PI / 2 + i * Math.PI / 6, roz = Math.abs(Math.atan2(Math.sin(a - phi), Math.cos(a - phi)));
        katy.push([a, roz]);
      }
      katy.sort(function (x, y) { return x[1] - y[1]; });
      katy.forEach(function (k) {
        var c = Math.cos(k[0]), n = Math.sin(k[0]);
        var ax = s[0] + rr * c, ay = s[1] + rr * n;
        var po = c > 0.3 ? 'l' : c < -0.3 ? 'r' : 'c', pi = n < -0.3 ? 'b' : n > 0.3 ? 't' : 'm';
        out.push({ r: prost(ax, ay, w, h, po, pi), po: po, linia: [d[0], d[1], ax, ay] });
      });
    });
    return out;
  }
  function kandydaciObszar(p, w, h) {
    var przes = [[0, 0], [0, -38], [0, 38], [-84, 0], [84, 0], [0, -70], [0, 70], [-110, -44], [110, -44], [-110, 44], [110, 44], [0, -108], [0, 108]];
    return przes.map(function (o) {
      var ax = p[0] + o[0], ay = p[1] + o[1];
      return { r: prost(ax, ay, w, h, 'c', 'm'), po: 'c', linia: (o[0] || o[1]) ? [p[0], p[1], ax, ay] : null };
    });
  }
  // Rysuje blok wielowierszowy w elemencie <text>.
  function wpiszLinie(sel, wiersze, r, po, lh, asc) {
    var x = po === 'c' ? (r[0] + r[2]) / 2 : po === 'r' ? r[2] : r[0];
    var kotwica = po === 'c' ? 'middle' : po === 'r' ? 'end' : 'start';
    sel.attr('text-anchor', kotwica);
    sel.selectAll('tspan').data(wiersze).join('tspan')
      .attr('x', x).attr('y', function (w, i) { return r[1] + asc + i * lh; }).text(function (w) { return w; });
  }
  function widoczne() { return D.events.filter(naMapie); }

  var ramka = 0;
  function zaplanujUklad() { if (!ramka) ramka = requestAnimationFrame(function () { ramka = 0; uklad(); }); }

  function uklad() {
    var k = tr.k, ekr = function (p) { return [p[0] * k + tr.x, p[1] * k + tr.y]; };
    swiat.attr('transform', tr.toString());
    if (k >= K.pxKmDrobneDrogi) doczytajDrobne();
    if (k >= K.pxKmPrzysiolki) doczytajPrzysiolki();
    d3.select('#w-drogi').classed('z-drobnymi', k >= K.pxKmDrobneDrogi);

    var evs = widoczne();
    odswiezNakladki(evs, k);
    // Ten sam typ na tym samym obszarze rysujemy raz: nakładanie przezroczystości udawałoby natężenie.
    var narysowane = {};
    d3.select('#w-obszary').selectAll('path').attr('display', function (e) {
      if (!naMapie(e) || narysowane[e.obszar + e.typ]) return 'none';
      narysowane[e.obszar + e.typ] = true;
      return null;
    });
    d3.select('#w-obszary').selectAll('path').style('fill', function (e) {
      return e.typ !== 'epidemia' && narysowane[e.obszar + 'epidemia'] ? 'url(#kreski-' + e.typ + ')' : null;
    }).style('fill-opacity', function (e) {
      return e.typ !== 'epidemia' && narysowane[e.obszar + 'epidemia'] ? 1 : null;
    });
    d3.select('#w-linie').selectAll('g').attr('display', function (e) { return naMapie(e) ? null : 'none'; });
    d3.selectAll('.kreski').attr('patternTransform', 'scale(' + (1 / k).toFixed(5) + ') rotate(45)');

    /* grupy: wszystkie kropki jednej miejscowości */
    var grupy = {}, poKrawedzi = [];
    evs.forEach(function (e) {
      e._krawedz = false;
      if (e.rodzaj !== 'punkt') return;
      if (e.kontekst) { // poza widokiem: znacznik na krawędzi zamiast kropki
        var sk = ekr(rzut(D.miejsca[e.grupa])), ug = polozenia();
        if (sk[0] < 0 || sk[0] > W || sk[1] < ug.gora || sk[1] > H - ug.dol) { e._krawedz = true; poKrawedzi.push({ e: e, s: sk }); return; }
      }
      (grupy[e.grupa] = grupy[e.grupa] || { nazwa: e.grupa, lista: [], s: ekr(rzut(D.miejsca[e.grupa])) }).lista.push(e);
    });
    var wgMiejsca = {};
    evs.forEach(function (e) {
      if (e._krawedz) return;
      var n = e.kontekst || e.miejscowosc;
      if (n && D.miejsca[n]) wgMiejsca[n] = (wgMiejsca[n] || 0) + 1;
    });

    var odstep = Math.max(dotyk ? 15 : 11.5, Math.min(24, 10 + (k - 18) * 0.16));
    var zajete = przeszkodyUi();
    var zwin = k < K.pxKmGrupy;
    var kropki = [], znaczki = [];
    Object.keys(grupy).forEach(function (n) {
      var g = grupy[n];
      g.lista.sort(function (a, b) { return a.rok_od - b.rok_od || (a.id < b.id ? -1 : 1); });
      g.R = g.lista.length > 1 ? odstep * 0.62 * Math.sqrt(g.lista.length) + 2 : 0;
      g.zwinieta = zwin && g.lista.length > 1;
      if (g.zwinieta) {
        g.R = 9;
        znaczki.push(g);
        zajete.push([g.s[0] - 10, g.s[1] - 10, g.s[0] + 10, g.s[1] + 10]);
      } else {
        g.lista.forEach(function (e, i) {
          var r = g.lista.length > 1 ? odstep * 0.62 * Math.sqrt(i + 0.5) : 0, a = i * 2.39996 - Math.PI / 2;
          var d = [g.s[0] + r * Math.cos(a), g.s[1] + r * Math.sin(a)];
          e._d = d; e._g = g;
          kropki.push(e);
          zajete.push([d[0] - 6, d[1] - 6, d[0] + 6, d[1] + 6]);
        });
      }
    });
    function drukujKropki() {
      var sel = gKropki.selectAll('a.kropka').data(kropki, function (e) { return e.id; });
      var nowe = sel.enter().append('a').attr('class', 'kropka');
      nowe.append('circle').attr('class', 'traf').attr('r', dotyk ? 13 : 9);
      nowe.append('circle').attr('class', 'pierscien').attr('r', 7.6);
      nowe.append('circle').attr('class', 'pkt');
      sel.exit().remove();
      var wsz = nowe.merge(sel);
      wsz.attr('href', function (e) { return e.url; })
        .attr('aria-label', function (e) { return e.tytul + ', ' + e.data + ', ' + (e.miejscowosc || '') + ', pewność ' + e.pewnosc; })
        .attr('transform', function (e) { return 'translate(' + e._d[0].toFixed(1) + ' ' + e._d[1].toFixed(1) + ')'; });
      wsz.select('.pierscien').attr('display', function (e) { return e.data_szacowana || e.hipoteza ? null : 'none'; });
      wsz.select('.pkt').attr('r', 4.6).attr('class', function (e) {
        return 'pkt ' + (e.szara ? 'pkt-szara ' : '') + (e.pewnosc === 'C' ? 'pkt-obrys' : e.pewnosc === 'D' ? 'pkt-legenda' : 'pkt-pelna');
      });
      wsz.on('mouseenter focus', function (ev, e) { pokazDymek(e, ev); }).on('mouseleave blur', schowajDymek)
        .order();
    }
    drukujKropki();
    rysujKrawedz(poKrawedzi, zajete);

    var zn = gKropki.selectAll('g.znaczek').data(znaczki, function (g) { return g.nazwa; });
    var znN = zn.enter().append('g').attr('class', 'znaczek').attr('tabindex', 0).attr('role', 'button');
    znN.append('circle').attr('r', 10.5);
    znN.append('text').attr('text-anchor', 'middle').attr('dy', '0.35em');
    zn.exit().remove();
    znN.merge(zn).attr('transform', function (g) { return 'translate(' + g.s[0].toFixed(1) + ' ' + g.s[1].toFixed(1) + ')'; })
      .attr('aria-label', function (g) { return g.nazwa + ': ' + odmiana(wgMiejsca[g.nazwa]) + ', pokaż listę'; })
      .on('click', function (ev, g) { pokazListeMiejsca(g.nazwa, ev.clientX, ev.clientY); })
      .on('keydown', function (ev, g) { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); var b = this.getBoundingClientRect(); pokazListeMiejsca(g.nazwa, b.right, b.top); } })
      .select('text').text(function (g) { return wgMiejsca[g.nazwa]; });

    /* etykiety miejscowości z wydarzeniami: uchwyt listy */
    var miejscaUkl = [];
    var nazwyGrup = Object.keys(wgMiejsca).filter(function (n) { return wgMiejsca[n] > 1 || (grupy[n] && grupy[n].lista.length > 1); });
    nazwyGrup.sort(function (a, b) { return wgMiejsca[b] - wgMiejsca[a]; });
    var wyswietlane = {};
    nazwyGrup.forEach(function (n) {
      var s = ekr(rzut(D.miejsca[n])), g = grupy[n], R = g ? g.R : 0;
      var t = n + ' · ' + wgMiejsca[n], w = szer(t, FONT.grupa) + 2, h = 18;
      var kand = [prost(s[0], s[1] + R + 6, w, h, 'c', 't'), prost(s[0], s[1] - R - 6, w, h, 'c', 'b'), prost(s[0] + R + 8, s[1], w, h, 'l', 'm'), prost(s[0] - R - 8, s[1], w, h, 'r', 'm')];
      for (var i = 0; i < kand.length; i++) {
        if (wEkranie(kand[i]) && wolne(kand[i], zajete)) {
          zajete.push(kand[i]);
          miejscaUkl.push({ id: 'g:' + n, kl: 'm-grupa', t: t, r: kand[i], nazwa: n, grupa: true });
          wyswietlane[n] = true;
          break;
        }
      }
    });

    /* etykiety wydarzeń: wyższa pewność, potem nowsze */
    var etyk = [], linie = [];
    var lh = 16, asc = 12.5;
    evs.slice().sort(priorytet).forEach(function (e) {
      if (e.rodzaj === 'nakladka' || e._krawedz) return;
      var g = e.rodzaj === 'punkt' ? grupy[e.grupa] : null;
      if (g && g.zwinieta && g._opisana) return;
      var tekst = e.etykieta + ', ' + e.data_krotka + (e.legenda ? ' (legenda)' : '') + (e.hipoteza && !/hipote/i.test(e.etykieta) ? ' (hipoteza)' : '');
      var szerokosc = (W < 700 ? 22 : 30) + Math.min(10, Math.max(0, (k - 40) / 12));
      var wiersze = zawijaj(tekst, szerokosc);
      var w = 0; wiersze.forEach(function (t) { w = Math.max(w, szer(t, FONT.etykieta)); });
      w += 2;
      var h = wiersze.length * lh + 1, kand;
      if (e.rodzaj !== 'punkt') {
        kand = kandydaciObszar(ekr(rzut(e.etykieta_xy)), w, h);
      } else if (g.zwinieta) {
        kand = kandydaciPojedyncza(g.s, w, h);
      } else if (g.lista.length === 1) {
        kand = kandydaciPojedyncza(e._d, w, h);
      } else {
        kand = kandydaciGrupa(g.s, g.R, e._d, w, h);
      }
      for (var i = 0; i < kand.length; i++) {
        var c = kand[i];
        if (wEkranie(c.r) && wolne(c.r, zajete)) {
          zajete.push(c.r);
          etyk.push({ e: e, wiersze: wiersze, r: c.r, po: c.po });
          if (c.linia) linie.push({ id: e.id, l: c.linia });
          if (g && g.zwinieta) g._opisana = true;
          break;
        }
      }
    });
    Object.keys(grupy).forEach(function (n) { delete grupy[n]._opisana; });

    var et = gEtykiety.selectAll('a.etykieta').data(etyk, function (x) { return x.e.id; });
    var etN = et.enter().append('a').attr('class', 'etykieta').attr('tabindex', -1).attr('aria-hidden', 'true');
    etN.append('text');
    et.exit().remove();
    etN.merge(et).attr('href', function (x) { return x.e.url; })
      .classed('etykieta-szara', function (x) { return x.e.szara; })
      .each(function (x) { wpiszLinie(d3.select(this).select('text'), x.wiersze, x.r, x.po, lh, asc); })
      .on('mouseenter', function (ev, x) { pokazDymek(x.e, ev); }).on('mouseleave', schowajDymek);

    gLinie.selectAll('line').data(linie, function (x) { return x.id; }).join('line')
      .attr('x1', function (x) { return x.l[0]; }).attr('y1', function (x) { return x.l[1]; })
      .attr('x2', function (x) { return x.l[2]; }).attr('y2', function (x) { return x.l[3]; });

    /* nazwy miejscowości i gmin przyległych */
    function dodaj(id, kl, t, font, s, h) {
      var w = szer(t, font) + 2;
      var kand = [prost(s[0], s[1], w, h, 'c', 'm'), prost(s[0], s[1] - 12, w, h, 'c', 'm'), prost(s[0], s[1] + 12, w, h, 'c', 'm')];
      for (var i = 0; i < kand.length; i++) {
        if (wEkranie(kand[i]) && wolne(kand[i], zajete)) { zajete.push(kand[i]); miejscaUkl.push({ id: id, kl: kl, t: t, r: kand[i] }); return; }
      }
    }
    if (stan.kontekst && kontekstDane) {
      Object.keys(kontekstDane).forEach(function (n) {
        if (!wyswietlane[n]) dodaj('k:' + n, 'm-miasto m-poza', n, FONT.miasto, ekr(rzut([kontekstDane[n].lon, kontekstDane[n].lat])), 18);
      });
      K.kontekstKraje.forEach(function (x) { dodaj('kr:' + x[0], 'm-gmina m-kraj', x[0].toUpperCase(), FONT.gmina, ekr(rzut([x[1], x[2]])), 14); });
    }
    D.miejscowosciPosort.forEach(function (m) {
      if (k < 8 && m.nazwa !== 'Wadowice') return;
      if (m.miasto && !wyswietlane[m.nazwa] && m.widok) { dodaj('p:' + m.id, 'm-miasto' + (m.wew ? '' : ' m-poza'), m.nazwa, FONT.miasto, ekr(m.xy), 18); }
    });
    if (k >= 8) D.gminyEtykiety.forEach(function (g) {
      var s = ekr(g.xy), blisko = miejscaUkl.some(function (m) {
        return m.t === g.nazwa && Math.abs((m.r[0] + m.r[2]) / 2 - s[0]) < 110 && Math.abs((m.r[1] + m.r[3]) / 2 - s[1]) < 60;
      });
      if (!blisko) dodaj('n:' + g.nazwa, 'm-gmina', g.nazwa.toUpperCase(), FONT.gmina, s, 14);
    });
    D.miejscowosciPosort.forEach(function (m) {
      if (m.miasto || wyswietlane[m.nazwa] || !m.widok) return;
      if (m.typ === 'hamlet' ? k < K.pxKmPrzysiolki : k < K.pxKmWsie) return;
      dodaj('p:' + m.id, (m.typ === 'hamlet' ? 'm-przysiolek' : 'm-wies') + (m.wew ? '' : ' m-poza'), m.nazwa, m.typ === 'hamlet' ? FONT.przysiolek : FONT.wies, ekr(m.xy), m.typ === 'hamlet' ? 13 : 15);
    });

    var ms = gMiejsca.selectAll('text').data(miejscaUkl, function (m) { return m.id; });
    ms.exit().remove();
    ms.enter().append('text').merge(ms)
      .attr('class', function (m) { return m.kl; })
      .attr('x', function (m) { return (m.r[0] + m.r[2]) / 2; })
      .attr('y', function (m) { return (m.r[1] + m.r[3]) / 2; })
      .attr('dy', '0.35em').attr('text-anchor', 'middle')
      .attr('tabindex', function (m) { return m.grupa ? 0 : null; })
      .attr('role', function (m) { return m.grupa ? 'button' : null; })
      .attr('aria-label', function (m) { return m.grupa ? m.nazwa + ': ' + odmiana(wgMiejsca[m.nazwa]) + ', pokaż listę' : null; })
      .text(function (m) { return m.t; })
      .on('click', function (ev, m) { if (m.grupa) pokazListeMiejsca(m.nazwa, ev.clientX, ev.clientY); })
      .on('keydown', function (ev, m) { if (m.grupa && (ev.key === 'Enter' || ev.key === ' ')) { ev.preventDefault(); var b = this.getBoundingClientRect(); pokazListeMiejsca(m.nazwa, b.left, b.bottom); } });

    odczyt(evs);
  }

  /* ---------- odczyt, komunikat, licznik poza mapą ---------- */
  function odczyt(evs) {
    var o = stan.od + '–' + stan.do;
    document.getElementById('lata-odczyt').textContent = 'Lata ' + o + ': ' + odmiana(evs.length) + ' na mapie';
    var pusto = document.getElementById('pusto');
    if (!evs.length) {
      var pokrywa = D.epoki.filter(function (e) { return e.gotowa && e.od < stan.do && e.do > stan.od; });
      var bezPunktow = pokrywa.filter(function (e) { return !e.na_mapie; });
      if (!pokrywa.length) pusto.textContent = 'Epoki z tego zakresu są w przygotowaniu.';
      else if (bezPunktow.length === pokrywa.length) pusto.textContent = 'Epoka ' + bezPunktow.map(function (e) { return e.od + '–' + e.do; }).join(', ') + ' jest opracowana, ale w sprawdzonych źródłach nie ma w niej zdarzeń, które można wskazać na mapie. To brak dowodu, a nie dowód, że nic się nie działo.';
      else pusto.textContent = 'W tym zakresie lat nie ma wydarzeń przy obecnych ustawieniach.';
      var wZakr = D.epoki.filter(function (e) { return e.od < stan.do && e.do > stan.od; });
      function dodajLink(adres, tekst) {
        var a = document.createElement('a');
        a.href = adres; a.textContent = tekst;
        pusto.appendChild(document.createTextNode(' '));
        pusto.appendChild(a);
      }
      if (wZakr.some(function (e) { return e.ile > e.na_mapie; })) dodajLink('wydarzenia/#poza-mapa', 'Zjawiska obszarowe.');
      if (wZakr.some(function (e) { return e.hipotezy; })) dodajLink('wydarzenia/#hipotezy', 'Hipotezy.');
      pusto.hidden = false;
    } else { pusto.hidden = true; }
    var poza = D.events.filter(function (e) { return pewnoscOk(e) && !e.na_mapie && !e.hipoteza; }).length;
    var lp2 = document.getElementById('link-poza-mapa');
    lp2.textContent = 'Tylko na liście: ' + poza;
    lp2.parentNode.hidden = !poza;
    var hipotezy = D.events.filter(function (e) { return e.hipoteza; }).length;
    var lh2 = document.getElementById('link-hipotezy');
    lh2.textContent = 'Hipotezy, lista: ' + hipotezy;
    lh2.parentNode.hidden = !hipotezy;
  }

  /* ---------- dymek ---------- */
  function pokazDymek(e, ev) {
    dymek.innerHTML = '<strong>' + esc(e.tytul) + '</strong><br>' + esc(e.data) + (e.miejscowosc ? ' · ' + esc(e.miejscowosc) : '') + ' · pewność ' + e.pewnosc;
    dymek.hidden = false;
    var x, y;
    if (ev.type === 'focus' || ev.type === 'focusin') { var b = ev.currentTarget.getBoundingClientRect(); x = b.right; y = b.top; }
    else { x = ev.clientX; y = ev.clientY; }
    var br = dymek.getBoundingClientRect();
    dymek.style.left = Math.max(6, Math.min(W - br.width - 6, x + 12)) + 'px';
    dymek.style.top = Math.max(6, Math.min(H - br.height - 6, y - br.height - 10)) + 'px';
  }
  function schowajDymek() { dymek.hidden = true; }

  /* ---------- lista grupy ---------- */
  var powrotFokus = null;
  function pozycjaEl(e) {
    return '<li><a href="' + esc(e.url) + '" class="link-wydarzenia"><span class="pz pz-' + e.pewnosc + '" aria-label="pewność ' + e.pewnosc + '">' + e.pewnosc + '</span> <span class="lw-data">' + esc(e.data) + '</span> ' + esc(e.tytul) + '</a></li>';
  }
  function pokazListe(tytul, lista, x, y, bezDaty) {
    powrotFokus = document.activeElement;
    lista = lista.slice().sort(function (a, b) { return a.rok_od - b.rok_od || (a.id < b.id ? -1 : 1); });
    var html = '<div class="lg-naglowek"><h2 id="lista-grupy-tytul">' + esc(tytul) + '</h2><button type="button" id="lg-zamknij" aria-label="Zamknij listę">×</button></div>';
    html += '<p class="lg-licznik">' + odmiana(lista.length) + ' w wybranym zakresie lat</p><ul>' + lista.map(pozycjaEl).join('') + '</ul>';
    if (bezDaty && bezDaty.length) html += '<p class="lg-licznik">Bez daty, poza mapą:</p><ul>' + bezDaty.map(pozycjaEl).join('') + '</ul>';
    listaGrupy.innerHTML = html;
    listaGrupy.hidden = false;
    if (W >= 700) {
      var b = listaGrupy.getBoundingClientRect();
      listaGrupy.style.left = Math.max(8, Math.min(W - b.width - 8, x + 14)) + 'px';
      listaGrupy.style.top = Math.max(60, Math.min(H - b.height - 90, y - 30)) + 'px';
    } else { listaGrupy.style.left = ''; listaGrupy.style.top = ''; }
    document.getElementById('lg-zamknij').addEventListener('click', zamknijListe);
    document.getElementById('lg-zamknij').focus();
  }
  function pokazListeMiejsca(nazwa, x, y) {
    var w = widoczne().filter(function (e) { return e.miejscowosc === nazwa || e.kontekst === nazwa; });
    var bd = D.events.filter(function (e) { return e.miejscowosc === nazwa && e.rok_od === null && pewnoscOk(e); });
    pokazListe(nazwa, w, x, y, bd);
  }
  function zamknijListe() {
    listaGrupy.hidden = true;
    if (powrotFokus && powrotFokus.focus) powrotFokus.focus();
  }

  /* ---------- suwak: skala kawałkami liniowa, każda epoka ma własny odcinek ---------- */
  var odcinki = [];
  function budujSkale() {
    var suma = 0;
    // Szerszy odcinek dostają tylko epoki z większą liczbą wydarzeń do wskazania na suwaku.
    D.epoki.forEach(function (e) { e.waga = e.gotowa && e.na_mapie >= 5 ? 3 : 1; suma += e.waga; });
    var p = 0;
    odcinki = D.epoki.map(function (e) { var o = { od: e.od, do: e.do, p0: p, p1: p + e.waga / suma, e: e }; p = o.p1; return o; });
  }
  function rokNaPoz(r) {
    for (var i = 0; i < odcinki.length; i++) {
      var o = odcinki[i];
      if (r <= o.do) return o.p0 + (o.p1 - o.p0) * (r - o.od) / (o.do - o.od);
    }
    return 1;
  }
  function pozNaRok(p) {
    for (var i = 0; i < odcinki.length; i++) {
      var o = odcinki[i];
      if (p <= o.p1) return Math.round(o.od + (o.do - o.od) * (p - o.p0) / (o.p1 - o.p0));
    }
    return odcinki[odcinki.length - 1].do;
  }
  var uOd = document.getElementById('uchwyt-od'), uDo = document.getElementById('uchwyt-do'), elSuwak = document.getElementById('suwak');
  function odswiezSuwak() {
    var a = rokNaPoz(stan.od) * 100, b = rokNaPoz(stan.do) * 100;
    uOd.style.left = a + '%'; uDo.style.left = b + '%';
    var z = document.getElementById('suwak-zakres'); z.style.left = a + '%'; z.style.width = (b - a) + '%';
    [[uOd, stan.od], [uDo, stan.do]].forEach(function (u) {
      u[0].setAttribute('aria-valuemin', 0); u[0].setAttribute('aria-valuemax', 1945);
      u[0].setAttribute('aria-valuenow', u[1]); u[0].setAttribute('aria-valuetext', 'rok ' + u[1]);
    });
  }
  function ustawLata(od, do_) {
    stan.od = Math.max(0, Math.min(od, do_)); stan.do = Math.min(1945, Math.max(od, do_));
    odswiezSuwak(); zaplanujUklad(); zapiszPozniej();
  }
  function rysujSuwak() {
    budujSkale();
    d3.select('#suwak-epoki').selectAll('button').data(odcinki).join('button')
      .attr('type', 'button').attr('tabindex', -1)
      .attr('class', function (o) { return 'epoka ' + (o.e.gotowa ? 'epoka-gotowa' : 'epoka-wkrotce'); })
      .style('left', function (o) { return o.p0 * 100 + '%'; }).style('width', function (o) { return (o.p1 - o.p0) * 100 + '%'; })
      .attr('title', function (o) { return o.od + '–' + o.do + ': ' + (!o.e.gotowa ? 'w przygotowaniu' : o.e.na_mapie ? 'opracowane' : 'opracowane, bez zdarzeń na mapie'); })
      .attr('aria-label', function (o) { return 'Pokaż lata ' + o.od + '–' + o.do; })
      .on('click', function (ev, o) { ustawLata(o.od, o.do); });
    var lata = {};
    D.events.forEach(function (e) { if (e.rok_od !== null && e.na_mapie && !e.data_szacowana) (e.lata || [e.rok_od]).forEach(function (r) { lata[r] = 1; }); });
    var szac = D.events.filter(function (e) { return e.data_szacowana && e.na_mapie; });
    d3.select('#suwak-znaczniki').selectAll('i').data(Object.keys(lata).map(Number)).join('i').style('left', function (r) { return rokNaPoz(r) * 100 + '%'; });
    d3.select('#suwak-znaczniki').selectAll('b').data(szac).join('b')
      .attr('title', function (e) { return e.data; })
      .style('left', function (e) { return rokNaPoz(e.rok_od) * 100 + '%'; })
      .style('width', function (e) { return (rokNaPoz(e.rok_do) - rokNaPoz(e.rok_od)) * 100 + '%'; });
    rysujLataSuwaka();
    odswiezSuwak();
    function przeciagnij(u, ktory) {
      u.addEventListener('pointerdown', function (ev) { u.setPointerCapture(ev.pointerId); ev.preventDefault(); u.focus(); });
      u.addEventListener('pointermove', function (ev) {
        if (!u.hasPointerCapture(ev.pointerId)) return;
        var b = elSuwak.getBoundingClientRect(), p = Math.max(0, Math.min(1, (ev.clientX - b.left) / b.width)), r = pozNaRok(p);
        if (ktory === 0) ustawLata(Math.min(r, stan.do), stan.do); else ustawLata(stan.od, Math.max(r, stan.od));
      });
      u.addEventListener('keydown', function (ev) {
        var kr = { ArrowLeft: -1, ArrowDown: -1, ArrowRight: 1, ArrowUp: 1, PageDown: -25, PageUp: 25 }[ev.key];
        var v = ktory === 0 ? stan.od : stan.do;
        if (ev.key === 'Home') v = ktory === 0 ? 0 : stan.od;
        else if (ev.key === 'End') v = ktory === 0 ? stan.do : 1945;
        else if (kr) v += kr; else return;
        ev.preventDefault();
        if (ktory === 0) ustawLata(Math.min(Math.max(0, v), stan.do), stan.do); else ustawLata(stan.od, Math.max(Math.min(1945, v), stan.od));
      });
    }
    przeciagnij(uOd, 0); przeciagnij(uDo, 1);
  }
  function rysujLataSuwaka() {
    var host = document.getElementById('suwak-lata'), szerS = elSuwak.getBoundingClientRect().width;
    var wart = {}; odcinki.forEach(function (o) { wart[o.od] = o.e.gotowa ? 2 : 0; wart[o.do] = Math.max(wart[o.do] || 0, o.e.gotowa ? 2 : 0); });
    wart[0] = Math.max(wart[0], 1); wart[1945] = Math.max(wart[1945], 1);
    var lista = Object.keys(wart).map(Number).sort(function (a, b) { return wart[b] - wart[a] || a - b; });
    var zaj = [], wyj = [];
    lista.forEach(function (r) {
      var x = rokNaPoz(r) * szerS, w = 30;
      var kol = zaj.some(function (z) { return Math.abs(z - x) < w; });
      if (!kol) { zaj.push(x); wyj.push(r); }
    });
    d3.select(host).selectAll('span').data(wyj, function (r) { return r; }).join('span')
      .style('left', function (r) { return rokNaPoz(r) * 100 + '%'; })
      .classed('rok-mocny', function (r) { return wart[r] === 2; })
      .text(function (r) { return r; });
  }

  /* ---------- zdarzenia ---------- */
  function podepnij() {
    zoom.on('zoom', function (ev) { if (ev.sourceEvent) ruszona = true; tr = ev.transform; schowajDymek(); zaplanujUklad(); zapiszPozniej(); });
    sv.call(zoom);
    document.getElementById('zoom-plus').addEventListener('click', function () { ruszona = true; sv.transition().duration(200).call(zoom.scaleBy, 1.6); });
    document.getElementById('zoom-minus').addEventListener('click', function () { ruszona = true; sv.transition().duration(200).call(zoom.scaleBy, 1 / 1.6); });
    document.getElementById('mapa').addEventListener('keydown', function (ev) {
      if (ev.target.id !== 'mapa') return;
      ruszona = true;
      var kr = 70 / tr.k, m = { ArrowLeft: [kr, 0], ArrowRight: [-kr, 0], ArrowUp: [0, kr], ArrowDown: [0, -kr] }[ev.key];
      if (m) { ev.preventDefault(); sv.call(zoom.translateBy, m[0], m[1]); }
      if (ev.key === '+' || ev.key === '=') sv.call(zoom.scaleBy, 1.4);
      if (ev.key === '-') sv.call(zoom.scaleBy, 1 / 1.4);
    });
    gKropki.on('click', function (ev) { przekazStan(ev); });
    gEtykiety.on('click', function (ev) { przekazStan(ev); });
    function przekazStan(ev) {
      var a = ev.target.closest('a'); if (!a) return;
      zapiszStan();
      var h = a.getAttribute('href').split('#')[0];
      a.setAttribute('href', h + '#' + kodStanu());
    }
    document.getElementById('pokaz-c').addEventListener('change', function (ev) { stan.c = ev.target.checked; zaplanujUklad(); zapiszPozniej(); });
    document.getElementById('pokaz-obszary').addEventListener('change', function (ev) { stan.obszary = ev.target.checked; zaplanujUklad(); zapiszPozniej(); });
    document.getElementById('pokaz-d').addEventListener('change', function (ev) { stan.d = ev.target.checked; zaplanujUklad(); zapiszPozniej(); });
    document.querySelector('.kontekst-btn').addEventListener('click', function () { ustawKontekst(!stan.kontekst, true); });
    document.querySelector('.panel-region button').addEventListener('click', function () { ustawPanel(!document.querySelector('.panel-region').classList.contains('otwarta')); });
    gKrawedz.on('click', function (ev) { przekazStan(ev); });
    var lp = document.getElementById('legenda-przelacz');
    lp.addEventListener('click', function () {
      var ot = document.getElementById('legenda').classList.toggle('otwarta');
      lp.setAttribute('aria-expanded', ot);
      zaplanujUklad();
    });
    document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape' && !listaGrupy.hidden) zamknijListe(); });
    document.addEventListener('pointerdown', function (ev) {
      if (!listaGrupy.hidden && !listaGrupy.contains(ev.target) && !ev.target.closest('.m-grupa, .znaczek')) { listaGrupy.hidden = true; }
    });
    ustawPrzyciski();
    if (window.ResizeObserver) new ResizeObserver(ustawPrzyciski).observe(document.querySelector('.suwak-panel'));
    var opoz = 0;
    window.addEventListener('resize', function () { clearTimeout(opoz); opoz = setTimeout(function () {
        // Dopóki nikt nie ruszał mapą, po zmianie rozmiaru okna wracamy do widoku startowego.
        if (ruszona || doWidoku) ustawWymiary(true);
        else { ustawWymiary(false); sv.call(zoom.transform, stan.kontekst ? widokKontekstu : widokStartowy); }
        rysujLataSuwaka(); zaplanujUklad();
      }, 120); });
    window.addEventListener('pageshow', function (ev) { if (ev.persisted) zaplanujUklad(); });
  }

  /* ---------- start ---------- */
  function json(u) { return fetch(u).then(function (r) { if (!r.ok) throw new Error(u + ': ' + r.status); return r.json(); }); }
  function doczytajPrzysiolki() {
    if (D.przysiolki) return;
    D.przysiolki = true;
    json('dane/geo/przysiolki.geojson').then(function (g) {
      D.miejscowosciPosort = D.miejscowosciPosort.concat(g.features.map(function (f, i) {
        var p = f.properties;
        return { id: 'h' + i, nazwa: p.nazwa, typ: p.typ, wew: p.w_powiecie, miasto: false, xy: rzut(f.geometry.coordinates), lud: 0, widok: true };
      }));
      zaplanujUklad();
    }).catch(function () { /* mapa działa bez przysiółków */ });
  }
  function doczytajDrobne() {
    if (D.drobne) return;
    D.drobne = true;
    json('dane/geo/drogi_drobne.geojson').then(function (g) {
      d3.select('#w-drogi').selectAll('path.drobna').data(g.features).join('path').attr('class', 'drobna').attr('d', function (f) { return sciezka(f.geometry); });
    }).catch(function () { /* brak drobnych dróg nie przeszkadza w mapie */ });
  }
  Promise.all([
    json('dane/events.json'), json('dane/geo/powiat.geojson'), json('dane/geo/gminy.geojson'), json('dane/geo/zasieg.geojson'),
    json('dane/geo/drogi.geojson'), json('dane/geo/miejscowosci.geojson'), json('dane/geo/obszary.geojson')
  ]).then(function (w) {
    D = { events: w[0].wydarzenia, epoki: w[0].epoki, miejsca: w[0].miejsca, powiat: w[1], gminy: w[2], zasieg: w[3], drogi: w[4], miejscowosci: w[5], obszary: w[6] };
    document.getElementById('wygenerowano').textContent = 'dane z ' + w[0].wygenerowano;
    D.miejscowosciPosort = w[5].features.map(function (f, i) {
      var p = f.properties;
      return { id: i, nazwa: p.nazwa, typ: p.typ, wew: p.w_powiecie, miasto: p.typ === 'town' || p.typ === 'city', xy: rzut(f.geometry.coordinates), lud: p.ludnosc || 0, widok: true };
    }).sort(function (a, b) { return (b.wew ? 1 : 0) - (a.wew ? 1 : 0) || b.lud - a.lud || (a.nazwa < b.nazwa ? -1 : 1); });
    D.gminyEtykiety = w[2].features.filter(function (f) { return !f.properties.w_powiecie || K.gminyWewnetrzne; })
      .map(function (f) { return { nazwa: f.properties.nazwa, xy: rzut(f.properties.etykieta) }; });
    if (D.events.some(function (e) { return e.pewnosc === 'D'; })) {
      document.getElementById('klucz-d').hidden = false; document.getElementById('etykieta-d').hidden = false;
    }
    czytajStan();
    document.getElementById('pokaz-c').checked = stan.c; document.getElementById('pokaz-d').checked = stan.d; document.getElementById('pokaz-obszary').checked = stan.obszary;
    rysujPodklad();
    ustawWymiary(false);
    podepnij();
    rysujSuwak();
    if (stan.kontekst) ustawKontekst(true, false);
    if (doWidoku) {
      var c = rzut([doWidoku[0], doWidoku[1]]), kk = doWidoku[2];
      sv.call(zoom.transform, d3.zoomIdentity.translate(W / 2 - kk * c[0], H / 2 - kk * c[1]).scale(kk));
    } else {
      sv.call(zoom.transform, stan.kontekst ? widokKontekstu : widokStartowy);
    }
    uklad();
  }).catch(function (b) {
    var p = document.getElementById('pusto');
    p.textContent = 'Nie udało się wczytać danych mapy (' + b.message + '). Lista wydarzeń działa bez mapy.';
    p.hidden = false;
    console.error(b);
  });
})();
