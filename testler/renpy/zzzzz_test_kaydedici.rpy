# TEST AMACLIDIR - oyunlara konmaz.
# Oyunu otomatik oynatir, ekrana gelen diyalog/secenekleri ve bazi arayuz
# metinlerinin cevirisini TRTEST_CIKTI ortam degiskenindeki dosyaya yazar.

init 1000 python:
    import os as _trt_os
    import json as _trt_json

    if _trt_os.environ.get("TRTEST_CIKTI"):
        _trt = {"say": [], "menu": [], "strings": {}, "font": None, "font_kalin": None, "kayit": None, "hata": None, "replace": {}}
        _trt_yol = _trt_os.environ["TRTEST_CIKTI"]

        def _trt_yaz():
            f = open(_trt_yol, "wb")
            try:
                v = _trt_json.dumps(_trt, ensure_ascii=True)
                if not isinstance(v, bytes):
                    v = v.encode("ascii")
                f.write(v)
            finally:
                f.close()

        if _trt_os.environ.get("TRTEST_CAKISMA"):
            # Yamadan SONRA ayni metni tanimlayan bir oyun dosyasini taklit et.
            try:
                renpy.translation.add_string_translation(None, "Load", "Load Game", None)
                _trt["cakisma"] = "ok"
            except Exception as _e:
                _trt["cakisma"] = "HATA %r" % _e

        for _k in ["Start", "Load", "Are you sure you want to quit?", "Sylvie", "Me", "{#month}January", "Yes", "Quick save complete.", "History"]:
            _trt["strings"][_k] = renpy.translation.translate_string(_k)

        for _k in ["Sylvie", "Quick save complete.", "Start"]:
            try:
                _trt["replace"][_k] = config.replace_text(_k) if config.replace_text else None
            except Exception as _e:
                _trt["replace"][_k] = "HATA %r" % _e

        # Alt+T gecisi: kapat -> orijinal, ac -> Turkce
        try:
            import store as _trt_store
            _trt_y = getattr(_trt_store, "trceviri", None)
            if _trt_y is not None:
                _ilk = config.say_menu_text_filter(u"Hello?")
                _trt_y.ac_kapa()
                _trt["gecis_kapali"] = [renpy.translation.translate_string("Load"), config.say_menu_text_filter(u"Hello?")]
                _trt_y.ac_kapa()
                _trt["gecis_acik"] = [renpy.translation.translate_string("Load"), config.say_menu_text_filter(u"Hello?")]
        except Exception as _e:
            _trt["gecis_hata"] = repr(_e)

        _trt["font"] = repr(config.font_replacement_map.get(("fonts/Test.ttf", False, False), None))
        _trt["font_kalin"] = repr(config.font_replacement_map.get(("test.ttf", True, False), None))
        _trt["font_dejavu"] = repr(config.font_replacement_map.get(("DejaVuSans.ttf", True, False), None))

        def _trt_say(who, what, *args, **kwargs):
            _trt["say"].append(what)
            if len(_trt["say"]) == 5:
                try:
                    renpy.save("1-1", "trtest")
                    _trt["kayit"] = "ok"
                except Exception as e:
                    _trt["kayit"] = "HATA %r" % e

        def _trt_menu(items, *args, **kwargs):
            _trt["menu"].append([i[0] for i in items])
            for i in items:
                if i[-1] is not None:
                    return i[-1]
            return None

        renpy.exports.say = _trt_say
        renpy.exports.menu = _trt_menu

        def _trt_bitir():
            _trt_yaz()
            _trt_os._exit(0)

label splashscreen:
    if _trt_os.environ.get("TRTEST_CIKTI"):
        jump start
    return

label main_menu:
    if _trt_os.environ.get("TRTEST_CIKTI"):
        $ _trt_bitir()
    return
