"""Kör kalite testi.

Oyundan seçilen aynı satırlar iki farklı yolla çevrilir (ör. Gemini ile Claude,
ya da kayıtlı çeviriler ile başka bir model). Sonuçlar, hangisinin hangi modele
ait olduğu gizlenerek bir HTML sayfasında yan yana gösterilir. Kullanıcı her
satırda daha doğal olanı seçer; sonunda hangi modelin kazandığı açıklanır.
Böylece "hangi yapay zeka bu oyun için daha iyi Türkçe yazıyor" sorusu
önyargısız biçimde cevaplanır.
"""

import html
import json
import random
import threading

from . import koruma
from . import proje as proje_mod

MEVCUT = "mevcut"   # projede kayıtlı çeviriler


class BellekProje(proje_mod.Proje):
    """Diske çeviri yazmayan geçici proje: test çevirileri gerçek çevirilere karışmaz.

    Örnek dışındaki satırların (bağlam) çevirisi gerçek projeden okunur.
    """

    def __init__(self, gercek, ornek_kaynaklar):
        self.__dict__.update({k: v for k, v in gercek.__dict__.items() if k.endswith("_yolu") or k == "klasor"})
        self._gercek = gercek
        self._ornek = set(ornek_kaynaklar)
        self._kilit = threading.RLock()
        self.ceviriler = {}
        self._kirli = 0

    def ceviri_al(self, kaynak):
        if kaynak in self._ornek:
            return proje_mod.Proje.ceviri_al(self, kaynak)
        return self._gercek.ceviri_al(kaynak)

    def elle_duzeltilenler(self, en_fazla=None):
        return self._gercek.elle_duzeltilenler(en_fazla)

    def kaydet(self, zorla=False):
        self._kirli = 0


def ornek_sec(diyalog_sira, adet=30, parca=10, tohum=None):
    """Oyunun farklı yerlerinden, art arda gelen satırlardan oluşan örnek gruplar seçer."""
    uygun = [o for o in diyalog_sira
             if o.tur == "diyalog" and koruma.cevrilecek_mi(o.m) and 12 <= len(koruma.duz_metin(o.m)) <= 260]
    if len(uygun) <= adet:
        return uygun
    rnd = random.Random(tohum)
    grup = max(1, adet // parca)
    secilen = []
    dilim = len(uygun) / float(grup)
    for g in range(grup):
        bas = int(g * dilim)
        son = max(bas, int((g + 1) * dilim) - parca)
        b = rnd.randint(bas, son) if son > bas else bas
        secilen.extend(uygun[b:b + parca])
    return secilen[:adet]


def html_yaz(yol, oyun_adi, satirlar, ad1, ad2, tohum=None):
    """satirlar: [(konuşan, kaynak, çeviri1, çeviri2)]. A/B sırası her satırda rastgele karışır."""
    rnd = random.Random(tohum)
    veri = []
    for konusan, kaynak, c1, c2 in satirlar:
        ters = rnd.random() < 0.5
        a, b = (c2, c1) if ters else (c1, c2)
        veri.append({"k": konusan or "", "m": kaynak, "a": a, "b": b, "ters": ters})
    adlar = [ad1, ad2]
    satir_html = []
    for i, v in enumerate(veri):
        satir_html.append(
            '<div class="satir" id="s{i}">'
            '<div class="kaynak"><span class="no">{n}.</span> {k}<span class="en">{m}</span></div>'
            '<label class="secenek" data-i="{i}" data-s="a"><input type="radio" name="r{i}" value="a">'
            '<span class="harf">A</span><span class="tr">{a}</span><span class="model"></span></label>'
            '<label class="secenek" data-i="{i}" data-s="b"><input type="radio" name="r{i}" value="b">'
            '<span class="harf">B</span><span class="tr">{b}</span><span class="model"></span></label>'
            '<label class="esit"><input type="radio" name="r{i}" value="e"> İkisi de aynı kalitede</label>'
            '</div>'.format(
                i=i, n=i + 1,
                k=('<b>%s:</b> ' % html.escape(v["k"])) if v["k"] else "<i>(anlatıcı)</i> ",
                m=html.escape(v["m"]), a=html.escape(v["a"]), b=html.escape(v["b"])))
    gizli = json.dumps({"adlar": adlar, "ters": [v["ters"] for v in veri]}, ensure_ascii=False)
    sayfa = SABLON.replace("@@BASLIK@@", html.escape(oyun_adi or "Oyun")) \
        .replace("@@SATIRLAR@@", "\n".join(satir_html)) \
        .replace("@@ADET@@", str(len(veri))) \
        .replace("@@VERI@@", gizli.replace("</", "<\\/"))
    with open(yol, "w", encoding="utf-8") as f:
        f.write(sayfa)
    return len(veri)


SABLON = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kör Çeviri Testi</title>
<style>
:root { --zemin:#f6f4ef; --kart:#fff; --yazi:#1e1e1e; --soluk:#6b6b6b; --vurgu:#b4441c; --cizgi:#ddd8cc; --secili:#fbe9df; --kazanan:#e5f3e3; }
@media (prefers-color-scheme: dark) { :root { --zemin:#17181a; --kart:#212226; --yazi:#ececec; --soluk:#9a9a9a; --vurgu:#f08a5d; --cizgi:#34363b; --secili:#3a2a22; --kazanan:#203320; } }
* { box-sizing:border-box; }
body { margin:0; background:var(--zemin); color:var(--yazi); font:16px/1.5 system-ui, "Segoe UI", sans-serif; }
main { max-width:900px; margin:0 auto; padding:24px 16px 120px; }
h1 { font-size:1.5rem; margin:0 0 4px; }
p.aciklama { color:var(--soluk); margin:0 0 20px; }
.satir { background:var(--kart); border:1px solid var(--cizgi); border-radius:10px; padding:14px 16px; margin:0 0 14px; }
.kaynak { margin-bottom:10px; }
.kaynak .no { color:var(--soluk); margin-right:4px; }
.kaynak .en { display:block; color:var(--soluk); font-style:italic; margin-top:2px; }
.secenek { display:flex; gap:10px; align-items:flex-start; border:1px solid var(--cizgi); border-radius:8px; padding:8px 10px; margin:6px 0; cursor:pointer; }
.secenek:has(input:checked) { background:var(--secili); border-color:var(--vurgu); }
.secenek input, .esit input { margin-top:5px; }
.harf { font-weight:700; color:var(--vurgu); min-width:1em; }
.tr { flex:1; }
.model { font-size:.8rem; color:var(--soluk); white-space:nowrap; }
.esit { display:block; color:var(--soluk); font-size:.9rem; margin-top:4px; cursor:pointer; }
.kazandi { background:var(--kazanan); }
#alt { position:fixed; left:0; right:0; bottom:0; background:var(--kart); border-top:1px solid var(--cizgi); padding:12px 16px; }
#alt div { max-width:900px; margin:0 auto; display:flex; gap:12px; align-items:center; flex-wrap:wrap; }
button { background:var(--vurgu); color:#fff; border:0; border-radius:8px; padding:10px 18px; font:inherit; cursor:pointer; }
#sonuc { font-weight:600; }
</style></head><body><main>
<h1>Kör çeviri testi — @@BASLIK@@</h1>
<p class="aciklama">Her satırda size daha doğal, daha "Türkçe" gelen çeviriyi seçin. Hangi çevirinin hangi
yapay zekaya ait olduğu gizlidir ve A/B sırası her satırda rastgele değişir. Bitirince alttaki düğmeye basın.</p>
@@SATIRLAR@@
</main>
<div id="alt"><div><button id="goster">Sonucu göster</button><span id="durum">0 / @@ADET@@ seçildi</span><span id="sonuc"></span></div></div>
<script>
var VERI = @@VERI@@;
function secimler() {
  var s = [];
  for (var i = 0; i < VERI.ters.length; i++) {
    var r = document.querySelector('input[name="r' + i + '"]:checked');
    s.push(r ? r.value : null);
  }
  return s;
}
document.addEventListener("change", function () {
  var n = secimler().filter(function (x) { return x; }).length;
  document.getElementById("durum").textContent = n + " / " + VERI.ters.length + " seçildi";
});
document.getElementById("goster").addEventListener("click", function () {
  var s = secimler(), puan = [0, 0], esit = 0, bos = 0;
  for (var i = 0; i < s.length; i++) {
    var ters = VERI.ters[i];
    var adA = VERI.adlar[ters ? 1 : 0], adB = VERI.adlar[ters ? 0 : 1];
    var etiketler = document.querySelectorAll('#s' + i + ' .model');
    etiketler[0].textContent = adA; etiketler[1].textContent = adB;
    if (s[i] === "a" || s[i] === "b") {
      var kazanan = (s[i] === "a") !== ters ? 0 : 1;
      puan[kazanan]++;
      document.querySelector('#s' + i + ' label[data-s="' + s[i] + '"]').classList.add("kazandi");
    } else if (s[i] === "e") { esit++; } else { bos++; }
  }
  var metin = VERI.adlar[0] + ": " + puan[0] + "  |  " + VERI.adlar[1] + ": " + puan[1] + "  |  eşit: " + esit;
  if (bos) metin += "  |  boş: " + bos;
  if (puan[0] !== puan[1]) metin += "  →  Kazanan: " + VERI.adlar[puan[0] > puan[1] ? 0 : 1];
  document.getElementById("sonuc").textContent = metin;
});
</script></body></html>
"""
