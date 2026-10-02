# TEST AMACLIDIR - oyunlara konmaz.
# Oyuncunun adi gibi degiskenlere gelen Turkce eklerin (Elif'in, Mike'in, Ali'nin)
# oyun sirasinda dogru cozuldugunu sinar. zzzzz_test_kaydedici.rpy ile birlikte kullanilir.

default ek_oyuncu = "Elif"
default ek_arkadas = "Mike"
define ek_s = Character("Sylvie")

label ek_testi:
    ek_s "[ek_oyuncu]'s room is upstairs."
    "[ek_arkadas]'s car is red."
    $ ek_oyuncu = "Ali"
    ek_s "[ek_oyuncu]'s room is upstairs."
    $ ek_oyuncu = "Kate"
    ek_s "[ek_oyuncu]'s room is upstairs."
    jump start
