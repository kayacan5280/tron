# RenPy Turkce Ceviri Motoru - TURKCE YAMA
#
# Bu dosya oyunu Turkce gosterir. Ceviriler "trceviri/ceviri.json" dosyasindadir.
# Yamayi kaldirmak icin bu dosyayi (ve .rpyc halini) ve "trceviri" klasorunu
# silmeniz yeterlidir; motorun "Yamayi kaldir" secenegi bunu otomatik yapar.
#
# Oyun icinde Alt+T (varsayilan) ile Turkce / orijinal metin arasinda gecis yapilir.
#
# Ren'Py 6.99 / 7.x (Python 2) ve 8.x (Python 3) ile uyumlu yazilmistir.
# Bu dosya hicbir durumda oyunu cokertmemek uzere tasarlanmistir: bir sorun
# olursa sessizce devre disi kalir ve oyun orijinal haliyle calisir.

init 999 python in trceviri:

    try:
        import builtins as _y
    except ImportError:
        import __builtin__ as _y

    import json as _json
    import store as _store

    try:
        _metin_turleri = (_y.str, _y.unicode)
    except AttributeError:
        _metin_turleri = (_y.str,)

    def _metin_mi(x):
        return isinstance(x, _metin_turleri)

    class _Durum(_y.object):
        pass

    _durum = _Durum()
    _durum.diyalog = _y.dict()
    _durum.diyalog_n = _y.dict()
    _durum.metinler = _y.dict()
    _durum.duz = _y.dict()
    _durum.eklenen = _y.dict()
    _durum.eksik_fontlar = _y.set()
    _durum.yedek = "DejaVuSans.ttf"
    _durum.yedek_kalin = "DejaVuSans-Bold.ttf"
    _durum.hazir = False
    _durum.hata = None

    def _normal(s):
        try:
            return u" ".join(s.split())
        except Exception:
            return s

    def _yukle():
        f = renpy.file("trceviri/ceviri.json")
        try:
            ham = f.read()
        finally:
            f.close()
        if isinstance(ham, _y.bytes):
            # Not: Ren'Py'in Python 2 surumunde "utf-8-sig" kodlamasi yoktur.
            ham = ham.decode("utf-8")
        if ham[:1] == u"\ufeff":
            ham = ham[1:]
        return _json.loads(ham)

    def _etkin():
        try:
            return not _store.persistent._trceviri_kapali
        except Exception:
            return True

    # ------------------------------------------------------------------
    # Turkce ek uyumu: "[name]{ek=in} odasi" -> oyuncunun adina gore
    # "Ali'nin odasi", "Elif'in odasi", "Mike'in odasi". Asagidaki kod motorun
    # ekler.py dosyasindan kurulum sirasinda otomatik eklenir.
    # ------------------------------------------------------------------

    # @@EKLER@@

    def _deger_bul(token):
        try:
            return renpy.substitute(token, translate=False)
        except TypeError:
            return renpy.substitute(token)

    def _ekleri_coz(t):
        if u"{ek=" not in t:
            return t
        try:
            return isaretleri_coz(t, _deger_bul)
        except Exception:
            pass
        try:
            return isaretleri_sabitle(t)
        except Exception:
            pass
        try:
            import re as _re
            return _re.sub(u"\\{ek=[^{}]*\\}", u"", t)
        except Exception:
            return t

    # ------------------------------------------------------------------
    # Diyalog ve secenekler (say / menu)
    # ------------------------------------------------------------------

    def _diyalog_bul(s):
        if not _metin_mi(s):
            return None
        t = _durum.diyalog.get(s)
        if t is None:
            t = _durum.diyalog_n.get(_normal(s))
        return t

    _eski_filtre = renpy.config.say_menu_text_filter

    def filtre(s):
        try:
            if _etkin():
                t = _diyalog_bul(s)
                if t is not None:
                    t = _ekleri_coz(t)
                    if _eski_filtre is not None:
                        return _eski_filtre(t)
                    return t
                if _eski_filtre is not None:
                    s2 = _eski_filtre(s)
                    t2 = _diyalog_bul(s2)
                    if t2 is not None:
                        return _ekleri_coz(t2)
                    return s2
        except Exception:
            pass
        if _eski_filtre is not None:
            return _eski_filtre(s)
        return s

    # ------------------------------------------------------------------
    # Arayuz metinleri (Ren'Py'in kendi metin ceviri tablosuna eklenir)
    # ------------------------------------------------------------------

    def _hedef_diller():
        diller = [None]
        for d in (getattr(renpy.config, "language", None), getattr(renpy.config, "default_language", None)):
            if d and d not in diller:
                diller.append(d)
        return diller

    _YOK = _Durum()

    def _cakisma_korumasi(dil, stl):
        # Oyun daha sonra (or. dil degisiminde yuklenen bir dosyada) bizim de
        # ekledigimiz bir metni tanimlarsa Ren'Py "zaten var" hatasiyla coker.
        # Bunu onlemek icin o metnin yeni degeri yedege alinir ve hata verilmez.
        try:
            eski_ekle = stl.add
            if getattr(eski_ekle, "_trceviri", False):
                return

            def ekle(old, new, newloc=None, _eski=eski_ekle, _dil=dil):
                yedek = _durum.eklenen.get(_dil)
                if yedek is not None and old in yedek:
                    yedek[old] = new
                    return
                return _eski(old, new, newloc)

            ekle._trceviri = True
            stl.add = ekle
        except Exception:
            pass

    def _metinleri_uygula(ac):
        # Orijinal dil (None) tablosundaki kayitlarin ustune yazilir; cogu oyunda
        # tl/None/common.rpym dosyasi metinleri "degismeden" tanimlar. Eski
        # degerler saklanir ve ceviri kapatildiginda geri yuklenir. Oyunun gercek
        # bir dili zorla secilmisse o dilin mevcut cevirilerine dokunulmaz.
        try:
            tl = renpy.game.script.translator
        except Exception:
            return

        for dil in _hedef_diller():
            try:
                stl = tl.strings[dil]
                tablo = stl.translations
            except Exception:
                continue

            _cakisma_korumasi(dil, stl)
            yedek = _durum.eklenen.setdefault(dil, _y.dict())

            if ac:
                for k, v in _durum.metinler.items():
                    eski = tablo.get(k, _YOK)
                    if dil is not None and eski is not _YOK:
                        continue
                    if k not in yedek:
                        yedek[k] = eski
                    tablo[k] = v
            else:
                for k, eski in _y.list(yedek.items()):
                    try:
                        if eski is _YOK:
                            tablo.pop(k, None)
                        else:
                            tablo[k] = eski
                    except Exception:
                        pass
                yedek.clear()

    _eski_degistir = getattr(renpy.config, "replace_text", None)

    def degistir(s):
        if _eski_degistir is not None:
            s = _eski_degistir(s)
        try:
            if _etkin():
                t = _durum.duz.get(s)
                if t is not None:
                    return t
        except Exception:
            pass
        return s

    # ------------------------------------------------------------------
    # Turkce harf (g, s, i, I...) icermeyen fontlarin yedek fontla degistirilmesi
    # ------------------------------------------------------------------

    class _FontHaritasi(_y.dict):

        def get(self, anahtar, varsayilan=None):
            r = _y.dict.get(self, anahtar, None)
            if r is not None:
                return r
            try:
                fn, kalin, egik = anahtar
                if _metin_mi(fn) and _durum.eksik_fontlar:
                    ad = fn.replace("\\", "/").split("/")[-1].lower()
                    if ad in _durum.eksik_fontlar:
                        if kalin and _durum.yedek_kalin:
                            return (_durum.yedek_kalin, False, egik)
                        return (_durum.yedek, kalin, egik)
            except Exception:
                pass
            return varsayilan

    # ------------------------------------------------------------------
    # Ac / kapat
    # ------------------------------------------------------------------

    def ac_kapa():
        try:
            kapali = not _etkin()
            _store.persistent._trceviri_kapali = not kapali
            _metinleri_uygula(kapali)
            if kapali:
                renpy.notify(u"Türkçe çeviri: AÇIK")
            else:
                renpy.notify(u"Türkçe çeviri: KAPALI (orijinal metin)")
            renpy.restart_interaction()
        except Exception:
            pass

    def _kur():
        veri = _yukle()

        diyalog = veri.get("diyalog") or {}
        for k, v in diyalog.items():
            if _metin_mi(k) and _metin_mi(v) and v:
                _durum.diyalog[k] = v
        for k, v in _durum.diyalog.items():
            n = _normal(k)
            if n not in _durum.diyalog_n:
                _durum.diyalog_n[n] = v

        metinler = veri.get("metinler") or {}
        for k, v in metinler.items():
            if _metin_mi(k) and _metin_mi(v) and v:
                _durum.metinler[k] = v

        if veri.get("yedek_katman", True):
            for k, v in _durum.metinler.items():
                if "[" in k or "{" in k or "\n" in k or "[" in v or "{" in v:
                    continue
                _durum.duz[k] = v

        for fn in (veri.get("eksik_fontlar") or []):
            if _metin_mi(fn) and fn:
                _durum.eksik_fontlar.add(fn.replace("\\", "/").split("/")[-1].lower())

        try:
            for k, v in (veri.get("ek_istisnalari") or {}).items():
                if _metin_mi(k) and _metin_mi(v) and k and v:
                    OZEL_OKUNUS[k] = v
        except Exception:
            pass

        if _metin_mi(veri.get("yedek_font")) and veri.get("yedek_font"):
            _durum.yedek = veri["yedek_font"]
        if _metin_mi(veri.get("yedek_font_kalin")):
            _durum.yedek_kalin = veri["yedek_font_kalin"] or None

        renpy.config.say_menu_text_filter = filtre

        if _etkin():
            _metinleri_uygula(True)

        if _durum.duz:
            renpy.config.replace_text = degistir

        if _durum.eksik_fontlar:
            yeni = _FontHaritasi()
            try:
                for k, v in renpy.config.font_replacement_map.items():
                    yeni[k] = v
            except Exception:
                pass
            renpy.config.font_replacement_map = yeni

        kisayol = veri.get("kisayol", "alt_K_t")
        if kisayol:
            try:
                renpy.config.underlay.append(renpy.Keymap(**{_y.str(kisayol): ac_kapa}))
            except Exception:
                pass

        _durum.hazir = True

    try:
        _kur()
    except Exception:
        import traceback as _tb
        _durum.hata = _tb.format_exc()
        try:
            import os as _os
            _f = open(_os.path.join(renpy.config.basedir, "trceviri_hata.txt"), "wb")
            try:
                _f.write(_durum.hata.encode("utf-8") if not isinstance(_durum.hata, _y.bytes) else _durum.hata)
            finally:
                _f.close()
        except Exception:
            pass
