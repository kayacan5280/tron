# RenPy Turkce Ceviri Motoru - metin cikarici (GECICI DOSYA)
#
# Bu dosyayi ceviri motoru oyuna gecici olarak koyar ve is bitince siler.
# Sadece motor tarafindan olusturulan isaret dosyasi (trceviri_cikar.txt)
# veya TRCEVIRI_CIKTI ortam degiskeni varsa calisir; yoksa hicbir sey yapmaz.
#
# Ren'Py 6.99 / 7.x (Python 2) ve 8.x (Python 3) ile uyumlu yazilmistir.

init 999 python in trceviri_cikarici:

    def _calistir():
        import os
        import sys
        import re
        import json
        import traceback
        import ast as pyast
        import store

        # Ren'Py, oyun kodundaki list/dict/set adlarini kendi geri alinabilir
        # turleriyle degistirir. Gercek yerlesik turleri buradan aliyoruz.
        try:
            import builtins as _y
        except ImportError:
            import __builtin__ as _y

        gamedir = renpy.config.gamedir
        bayrak = os.path.join(gamedir, "trceviri_cikar.txt")

        ortam = os.environ.get("TRCEVIRI_CIKTI", "")
        bayrak_var = os.path.exists(bayrak)

        if not ortam and not bayrak_var:
            return

        # Yarida kalmis eski bir islemden kalan isaret dosyasi (or. elektrik kesintisi):
        # oyun normal acildiginda kapanmasin; isareti sil ve hicbir sey yapma.
        if bayrak_var and not ortam:
            try:
                import time
                if time.time() - os.path.getmtime(bayrak) > 2 * 3600:
                    os.remove(bayrak)
                    return
            except Exception:
                pass

        # Cikti yolu once isaret dosyasindan (UTF-8) okunur; Python 2'de ortam
        # degiskenindeki Turkce karakterli yollar bozulabildigi icin bu daha guvenlidir.
        hedefler = []
        if bayrak_var:
            try:
                f = open(bayrak, "rb")
                try:
                    yol = f.read().decode("utf-8", "replace").strip()
                finally:
                    f.close()
                if yol:
                    hedefler.append(yol)
            except Exception:
                pass
        if not hedefler and ortam and ortam != "1":
            try:
                if isinstance(ortam, bytes):
                    ortam = ortam.decode("utf-8", "replace")
                hedefler.append(ortam)
            except Exception:
                pass
        # Her durumda oyun klasorune de yazmayi dene (yedek yol).
        hedefler.append(os.path.join(gamedir, "trceviri_cikti.json"))

        try:
            metin_turleri = (str, unicode)  # Python 2
        except NameError:
            metin_turleri = (str,)  # Python 3

        def metin_mi(x):
            return isinstance(x, metin_turleri)

        PY3 = sys.version_info[0] >= 3

        def uni(x):
            # Python 2'de bytes == str oldugu icin iki durum ayri ele alinir.
            if isinstance(x, bytes):
                return x.decode("utf-8", "replace")
            return x

        def dosya_adi(n):
            fn = getattr(n, "filename", None) or ""
            try:
                fn = uni(fn)
            except Exception:
                fn = ""
            return fn.replace("\\", "/")

        def satir(n):
            try:
                return int(getattr(n, "linenumber", 0) or 0)
            except Exception:
                return 0

        def atlanacak_dosya(fn):
            k = fn.lower()
            if k.startswith("tl/") or "/tl/" in k:
                return True
            if k.startswith("renpy/") or "/renpy/common/" in k or k.startswith("common/"):
                return True
            if "trceviri" in k:
                return True
            return False

        sonuc = {
            "surum": 1,
            "hata": None,
            "renpy_surumu": "",
            "python": sys.version_info[0],
            "oyun_adi": "",
            "ogeler": [],
            "metinler": [],
            "karakterler": [],
            "fontlar": [],
            "diller": [],
            "uyarilar": [],
            "eski_filtre": False,
            "eski_replace_text": False,
        }

        uyarilar = sonuc["uyarilar"]

        def uyar(m):
            if len(uyarilar) < 200:
                uyarilar.append(uni(m))

        try:
            try:
                sonuc["renpy_surumu"] = uni(renpy.version())
            except Exception:
                sonuc["renpy_surumu"] = ""

            try:
                ad = renpy.config.name
                if metin_mi(ad):
                    sonuc["oyun_adi"] = uni(ad)
            except Exception:
                pass

            sonuc["eski_filtre"] = renpy.config.say_menu_text_filter is not None
            sonuc["eski_replace_text"] = getattr(renpy.config, "replace_text", None) is not None

            # Mevcut diller.
            try:
                sonuc["diller"] = sorted([uni(i) for i in renpy.game.script.translator.languages if i])
            except Exception:
                pass

            script = renpy.game.script
            tum = _y.list(getattr(script, "all_stmts", None) or [])
            if not tum:
                try:
                    tum = _y.list(script.namemap.values())
                except Exception:
                    tum = _y.list()

            gorulen = _y.set()
            dugumler = _y.list()
            for n in tum:
                if id(n) in gorulen:
                    continue
                gorulen.add(id(n))
                dugumler.append(n)

            rast = renpy.ast

            # Baska dillere ait ceviri bloklarinin icindeki dugumleri atla.
            atla = _y.set()
            for n in dugumler:
                if isinstance(n, rast.Translate) and getattr(n, "language", None) is not None:
                    for b in (getattr(n, "block", None) or []):
                        try:
                            b.get_children(lambda x: atla.add(id(x)))
                        except Exception:
                            atla.add(id(b))

            store_sozluk = vars(store)

            def literal(kaynak):
                try:
                    v = pyast.literal_eval(kaynak.strip())
                except Exception:
                    return None
                if metin_mi(v) or isinstance(v, bytes):
                    return uni(v)
                return None

            isim_onbellek = _y.dict()

            def konusan(n):
                who = getattr(n, "who", None)
                if not who:
                    return u""
                who = uni(who).strip()
                if who in isim_onbellek:
                    return isim_onbellek[who]

                sonuc_ad = who
                try:
                    if who[:1] in ("\"", "'"):
                        v = literal(who)
                        if v is not None:
                            sonuc_ad = v
                    elif re.match(r"^[A-Za-z_][A-Za-z0-9_.]*$", who):
                        obj = eval(who, store_sozluk)
                        if metin_mi(obj):
                            sonuc_ad = uni(obj)
                        else:
                            ad = getattr(obj, "name", None)
                            if metin_mi(ad) and ad:
                                if getattr(obj, "dynamic", False):
                                    sonuc_ad = u"[" + uni(ad) + u"]"
                                else:
                                    sonuc_ad = uni(ad)
                except Exception:
                    pass

                isim_onbellek[who] = sonuc_ad
                return sonuc_ad

            ogeler = sonuc["ogeler"]

            for n in dugumler:
                if id(n) in atla:
                    continue

                fn = dosya_adi(n)
                if atlanacak_dosya(fn):
                    continue

                if isinstance(n, rast.Say):
                    if getattr(n, "language", None) is not None:
                        continue
                    what = getattr(n, "what", None)
                    if not metin_mi(what):
                        continue
                    who = getattr(n, "who", None)
                    ogeler.append({
                        "m": uni(what),
                        "tur": "diyalog",
                        "k": konusan(n),
                        "w": uni(who).strip() if who else u"",
                        "d": fn,
                        "s": satir(n),
                    })

                elif isinstance(n, rast.Menu):
                    for item in (getattr(n, "items", None) or []):
                        try:
                            etiket = item[0]
                            blok = item[2]
                        except Exception:
                            continue
                        if not metin_mi(etiket) or not etiket:
                            continue
                        ogeler.append({
                            "m": uni(etiket),
                            "tur": "secenek" if blok is not None else "menu_basligi",
                            "k": u"",
                            "w": u"",
                            "d": fn,
                            "s": satir(n),
                        })

            # ---------------------------------------------------------
            # Arayuz / python metinleri
            # ---------------------------------------------------------

            metinler = _y.dict()

            def metin_ekle(m, tur, fn, ln):
                if not metin_mi(m):
                    return
                m = uni(m)
                if not m or not m.strip():
                    return
                if len(m) > 4000:
                    return
                eski = metinler.get(m)
                oncelik = {"cevir": 3, "ekran": 2, "isim": 2, "python": 1}
                if eski is not None and oncelik.get(eski["tur"], 0) >= oncelik.get(tur, 0):
                    return
                metinler[m] = {"m": m, "tur": tur, "d": fn, "s": ln}

            resim_adlari = _y.set()
            try:
                for k in renpy.display.image.images.keys():
                    try:
                        resim_adlari.add(u" ".join([uni(i) for i in k]))
                    except Exception:
                        pass
            except Exception:
                pass

            uzanti_re = re.compile(r"\.(png|jpe?g|webp|gif|bmp|avif|svg|ogg|opus|mp3|wav|flac|webm|mp4|mkv|avi|ogv|ttf|otf|ttc|rpy|rpyc|rpym|rpa|json|txt|py|csv|xml|html?)\b", re.I)
            tek_kelime_re = re.compile(u"^[^\\W\\d_](?:[^\\W_]|')*[.!?…]*$", re.U)
            harf_re = re.compile(r"[^\W\d_]", re.U)

            def dogal_dil_mi(s):
                if not s or len(s) > 2000:
                    return False
                t = s.strip()
                if not t:
                    return False
                if not harf_re.search(t):
                    return False
                if t in resim_adlari:
                    return False
                if uzanti_re.search(t):
                    return False
                if ("/" in t or "\\" in t) and " " not in t:
                    return False
                if re.match(r"^#[0-9a-fA-F]{3,8}$", t):
                    return False
                if not re.search(r"\s", t):
                    # Tek parca metin: sadece buyuk harfle baslayan duz bir kelime
                    # (ornegin "Envanter" gibi bir arayuz yazisi) olabilir.
                    if len(t) < 2 or not t[:1].isupper() or not tek_kelime_re.match(t):
                        return False
                if re.match(r"^[a-z0-9_]+( [a-z0-9_]+){0,3}$", t) and not re.search(r"[.!?,;:]", t):
                    # "bg room", "eileen happy" gibi resim/etiket adlari
                    return False
                if re.search(r"[=(){}]\s*$", t) and " " not in t:
                    return False
                # Python bicim kaliplari ("{}", "{0}", "%r") ve regex kaliplari gelistirici metnidir.
                if re.search(r"\{\d*\}|%r|\{![rsa]\}", t) or re.search(r"\\[swdbSWDB]", t):
                    return False
                if re.match(r"^\{[^{}]*\}$", t):
                    return False
                if t.startswith("{#") and t.endswith("}") and t.count("{") == 1:
                    return False
                return True

            cevir_isimleri = ("_", "__", "_p", "_t")

            def fonk_adi(f):
                if isinstance(f, pyast.Name):
                    return f.id
                if isinstance(f, pyast.Attribute):
                    return f.attr
                return None

            def sabit_metin(d):
                Constant = getattr(pyast, "Constant", None)
                if Constant is not None and isinstance(d, Constant):
                    v = d.value
                    if metin_mi(v) or isinstance(v, bytes):
                        return uni(v)
                    return None
                Str = getattr(pyast, "Str", None)
                if Str is not None and isinstance(d, Str):
                    return uni(d.s)
                return None

            def p_bicimle(s):
                try:
                    return uni(store_sozluk["_p"](s))
                except Exception:
                    return s

            def python_tara(kaynak, fn, ln, kip, sezgisel=True):
                if not metin_mi(kaynak) or not kaynak.strip():
                    return
                try:
                    agac = pyast.parse(kaynak, mode=kip)
                except Exception:
                    try:
                        agac = pyast.parse(kaynak.strip(), mode=kip)
                    except Exception:
                        return

                isaretli = _y.set()
                for d in pyast.walk(agac):
                    if isinstance(d, pyast.Call):
                        ad = fonk_adi(d.func)
                        if ad in cevir_isimleri and d.args:
                            v = sabit_metin(d.args[0])
                            if v is not None:
                                isaretli.add(id(d.args[0]))
                                if ad == "_p":
                                    v = p_bicimle(v)
                                metin_ekle(v, "cevir", fn, ln)
                        elif ad in ("Character", "DynamicCharacter", "ADVCharacter", "NVLCharacter") and d.args:
                            v = sabit_metin(d.args[0])
                            if v is not None:
                                isaretli.add(id(d.args[0]))
                                if ad != "DynamicCharacter":
                                    metin_ekle(v, "isim", fn, ln)

                if not sezgisel:
                    return

                # Belge dizgilerini (docstring) atla.
                belge = _y.set()
                for d in pyast.walk(agac):
                    govde = getattr(d, "body", None)
                    if isinstance(govde, _y.list) and govde:
                        ilk = govde[0]
                        if isinstance(ilk, pyast.Expr):
                            belge.add(id(ilk.value))

                # Oyuncuya hic gosterilmeyen gelistirici metinlerini atla: hata
                # mesajlari (raise, XxxError(...)), regex kaliplari (re.*), gunluk/print.
                def alt_dugumleri_isaretle(kok):
                    for x in pyast.walk(kok):
                        belge.add(id(x))

                for d in pyast.walk(agac):
                    if isinstance(d, pyast.Raise):
                        alt_dugumleri_isaretle(d)
                    elif isinstance(d, pyast.Assert):
                        alt_dugumleri_isaretle(d)
                    elif isinstance(d, pyast.Call):
                        ad = fonk_adi(d.func) or ""
                        sahip = ""
                        if isinstance(d.func, pyast.Attribute) and isinstance(d.func.value, pyast.Name):
                            sahip = d.func.value.id
                        if ad.endswith(("Error", "Exception", "Warning")) or ad in ("print", "log", "debug", "warning", "info", "open", "compile", "getattr", "setattr", "hasattr", "startswith", "endswith", "split", "join", "replace", "format") \
                                or sahip in ("re", "os", "logging", "sys", "json", "path"):
                            for a in _y.list(d.args) + [k.value for k in d.keywords]:
                                alt_dugumleri_isaretle(a)

                for d in pyast.walk(agac):
                    if id(d) in isaretli or id(d) in belge:
                        continue
                    v = sabit_metin(d)
                    if v is None:
                        continue
                    if dogal_dil_mi(v):
                        metin_ekle(v, "python", fn, ln)

            PyNode = _y.tuple([c for c in (getattr(rast, "Python", None), getattr(rast, "EarlyPython", None), getattr(rast, "Define", None), getattr(rast, "Default", None)) if c is not None])

            for n in dugumler:
                if id(n) in atla:
                    continue
                if not PyNode or not isinstance(n, PyNode):
                    continue
                fn = dosya_adi(n)
                if atlanacak_dosya(fn):
                    continue
                kod = getattr(n, "code", None)
                kaynak = getattr(kod, "source", None)
                if not metin_mi(kaynak):
                    continue
                kip = "exec"
                if isinstance(n, _y.tuple([c for c in (getattr(rast, "Define", None), getattr(rast, "Default", None)) if c is not None])):
                    kip = "eval"
                try:
                    python_tara(uni(kaynak), fn, satir(n), kip)
                except Exception:
                    pass

            # Oyunun "translate None strings" ile degistirdigi arayuz metinleri
            # (orn. "Quit" yerine "Leave"): ekranda gorunen deger cevrilmelidir.
            none_ozel = _y.dict()
            TS = getattr(rast, "TranslateString", None)
            if TS is not None:
                for n in dugumler:
                    if not isinstance(n, TS) or getattr(n, "language", None) is not None:
                        continue
                    eski = getattr(n, "old", None)
                    yeni = getattr(n, "new", None)
                    if metin_mi(eski) and metin_mi(yeni) and eski != yeni and yeni.strip():
                        none_ozel[uni(eski)] = uni(yeni)
                        metin_ekle(uni(yeni), "cevir", dosya_adi(n), satir(n))
            sonuc["none_ozel"] = none_ozel

            # Ekranlar (screen language 2).
            def ekran_ifadeleri(dugum, ziyaret, derinlik=0):
                if derinlik > 200 or id(dugum) in ziyaret:
                    return
                ziyaret.add(id(dugum))

                modul = getattr(type(dugum), "__module__", "") or ""
                if not modul.startswith("renpy.sl2"):
                    return

                yer = getattr(dugum, "location", None)
                fn = u""
                ln = 0
                try:
                    fn = uni(yer[0]).replace("\\", "/")
                    ln = int(yer[1])
                except Exception:
                    pass

                if fn and atlanacak_dosya(fn):
                    return

                metin_benzeri = False
                disp = getattr(dugum, "displayable", None)
                if disp is not None:
                    dad = getattr(disp, "__name__", "") or ""
                    if dad in ("Text", "_textbutton", "_label", "_text"):
                        metin_benzeri = True

                pozisyonel = getattr(dugum, "positional", None)
                if isinstance(pozisyonel, (_y.list, _y.tuple)):
                    for i, ifade in enumerate(pozisyonel):
                        if not metin_mi(ifade):
                            continue
                        if metin_benzeri and i == 0:
                            v = literal(uni(ifade))
                            if v is not None:
                                metin_ekle(v, "ekran", fn, ln)
                                continue
                        python_tara(uni(ifade), fn, ln, "eval", sezgisel=False)

                anahtarlar = getattr(dugum, "keyword", None)
                if isinstance(anahtarlar, (_y.list, _y.tuple)):
                    for kv in anahtarlar:
                        try:
                            k, ifade = kv[0], kv[1]
                        except Exception:
                            continue
                        if not metin_mi(ifade):
                            continue
                        if k in ("tooltip", "text", "caption", "prompt", "title", "message"):
                            v = literal(uni(ifade))
                            if v is not None and dogal_dil_mi(v):
                                metin_ekle(v, "ekran", fn, ln)
                                continue
                        python_tara(uni(ifade), fn, ln, "eval", sezgisel=False)

                kod = getattr(dugum, "code", None)
                kaynak = getattr(kod, "source", None)
                if metin_mi(kaynak):
                    python_tara(uni(kaynak), fn, ln, "exec")

                for ad in ("children", "entries", "block", "ast"):
                    alt = getattr(dugum, ad, None)
                    if alt is None:
                        continue
                    if isinstance(alt, (_y.list, _y.tuple)):
                        for a in alt:
                            if isinstance(a, (_y.list, _y.tuple)):
                                for b in a:
                                    if b is not None and not metin_mi(b):
                                        ekran_ifadeleri(b, ziyaret, derinlik + 1)
                            elif a is not None and not metin_mi(a):
                                ekran_ifadeleri(a, ziyaret, derinlik + 1)
                    elif not metin_mi(alt):
                        ekran_ifadeleri(alt, ziyaret, derinlik + 1)

            try:
                ziyaret = _y.set()
                for ekran in _y.list(renpy.display.screen.screens.values()):
                    agac = getattr(ekran, "ast", None)
                    if agac is not None:
                        try:
                            ekran_ifadeleri(agac, ziyaret)
                        except Exception:
                            uyar(u"Ekran taranamadi: " + uni(repr(getattr(ekran, "name", "?"))))
            except Exception:
                uyar(u"Ekranlar taranamadi.")

            # Karakter isimleri.
            karakterler = sonuc["karakterler"]
            try:
                ADV = renpy.character.ADVCharacter
                for k, v in _y.list(store_sozluk.items()):
                    if isinstance(v, ADV):
                        ad = getattr(v, "name", None)
                        if metin_mi(ad) and ad and not getattr(v, "dynamic", False):
                            karakterler.append({"deg": uni(k), "ad": uni(ad)})
                            metin_ekle(uni(ad), "isim", u"", 0)
            except Exception:
                uyar(u"Karakterler okunamadi.")

            # Oyunun adi ceviriye girmesin.
            if sonuc["oyun_adi"] and sonuc["oyun_adi"] in metinler:
                del metinler[sonuc["oyun_adi"]]

            sonuc["metinler"] = _y.list(metinler.values())

            # ---------------------------------------------------------
            # Fontlar: Turkce harf destegi kontrolu
            # ---------------------------------------------------------
            import struct

            gerekli = u"çÇğĞıİöÖşŞüÜ"

            def font_kontrol(veri):
                def u16(o):
                    return struct.unpack(">H", veri[o:o + 2])[0]

                def u32(o):
                    return struct.unpack(">I", veri[o:o + 4])[0]

                bas = 0
                if veri[0:4] == b"ttcf":
                    bas = u32(12)

                tablo_sayisi = u16(bas + 4)
                cmap = None
                for i in range(tablo_sayisi):
                    kayit = bas + 12 + 16 * i
                    if veri[kayit:kayit + 4] == b"cmap":
                        cmap = u32(kayit + 8)
                        break

                if cmap is None:
                    return None

                alt_sayisi = u16(cmap + 2)
                aday12 = None
                aday4 = None
                for i in range(alt_sayisi):
                    pid = u16(cmap + 4 + 8 * i)
                    eid = u16(cmap + 6 + 8 * i)
                    ofs = cmap + u32(cmap + 8 + 8 * i)
                    bicim = u16(ofs)
                    unicode_mu = (pid == 0) or (pid == 3 and eid in (1, 10))
                    if not unicode_mu:
                        continue
                    if bicim == 12 and aday12 is None:
                        aday12 = ofs
                    elif bicim == 4 and aday4 is None:
                        aday4 = ofs

                def var12(ofs, cp):
                    grup = u32(ofs + 12)
                    for g in range(grup):
                        o = ofs + 16 + 12 * g
                        if u32(o) <= cp <= u32(o + 4):
                            return True
                    return False

                def var4(ofs, cp):
                    segx2 = u16(ofs + 6)
                    son_kod = ofs + 14
                    bas_kod = son_kod + segx2 + 2
                    delta = bas_kod + segx2
                    aralik = delta + segx2
                    for s in range(segx2 // 2):
                        son = u16(son_kod + 2 * s)
                        if cp > son:
                            continue
                        basla = u16(bas_kod + 2 * s)
                        if cp < basla:
                            return False
                        d = u16(delta + 2 * s)
                        ro_adr = aralik + 2 * s
                        ro = u16(ro_adr)
                        if ro == 0:
                            glif = (cp + d) & 0xFFFF
                        else:
                            glif = u16(ro_adr + ro + 2 * (cp - basla))
                            if glif:
                                glif = (glif + d) & 0xFFFF
                        return glif != 0
                    return False

                if aday12 is not None:
                    kontrol = lambda cp: var12(aday12, cp)
                elif aday4 is not None:
                    kontrol = lambda cp: var4(aday4, cp)
                else:
                    return None

                eksik = u""
                for h in gerekli:
                    if not kontrol(ord(h)):
                        eksik += h
                return eksik

            try:
                dosyalar = renpy.list_files()
            except Exception:
                dosyalar = _y.list()

            for fn in dosyalar:
                fnu = uni(fn).replace("\\", "/")
                if not re.search(r"\.(ttf|otf|ttc)$", fnu, re.I):
                    continue
                kayit = {"dosya": fnu, "eksik": None}
                try:
                    f = renpy.file(fn)
                    try:
                        veri = f.read()
                    finally:
                        f.close()
                    kayit["eksik"] = font_kontrol(veri)
                except Exception:
                    kayit["eksik"] = None
                sonuc["fontlar"].append(kayit)

            # gui icindeki font adlari (stil tarafinda nasil yazildigini bilmek icin)
            gui_fontlari = _y.list()
            try:
                for k, v in _y.list(vars(store_sozluk["gui"]).items()):
                    if metin_mi(v) and re.search(r"\.(ttf|otf|ttc)$", v, re.I):
                        gui_fontlari.append(uni(v))
            except Exception:
                pass
            sonuc["gui_fontlari"] = sorted(set(gui_fontlari))

        except Exception:
            sonuc["hata"] = uni(traceback.format_exc())

        # Sonucu yaz (once gecici dosyaya, sonra yerine tasi). Ilk basarili hedefte dur.
        try:
            veri = json.dumps(sonuc, ensure_ascii=True)
        except Exception:
            veri = json.dumps({"surum": 1, "hata": uni(traceback.format_exc())}, ensure_ascii=True)
        if not isinstance(veri, bytes):
            veri = veri.encode("ascii")

        for hedef in hedefler:
            try:
                klasor = os.path.dirname(hedef)
                if klasor and not os.path.isdir(klasor):
                    os.makedirs(klasor)
                gecici = hedef + ".yaziliyor"
                f = open(gecici, "wb")
                try:
                    f.write(veri)
                finally:
                    f.close()
                if os.path.exists(hedef):
                    os.remove(hedef)
                os.rename(gecici, hedef)
                break
            except Exception:
                continue

        try:
            if bayrak_var:
                os.remove(bayrak)
        except Exception:
            pass

        # Oyunu kapat. Init asamasinda en guvenilir yol surecten cikmaktir.
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass
        os._exit(0)

    _calistir()
