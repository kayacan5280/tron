@echo off
setlocal
chcp 65001 >nul
title RenPy Turkce Ceviri Motoru
cd /d "%~dp0"

rem Oyun klasorunu bu dosyanin uzerine surukleyip birakirsaniz dogrudan o oyun cevrilir.

py -3 --version >nul 2>nul
if not errorlevel 1 (
    py -3 "%~dp0ceviri.py" %*
    goto son
)

python --version >nul 2>nul
if not errorlevel 1 (
    python "%~dp0ceviri.py" %*
    goto son
)

echo.
echo  [HATA] Python bulunamadi.
echo.
echo  1) https://www.python.org/downloads/ adresinden Python'u indirin.
echo  2) Kurulumun ILK ekraninda "Add python.exe to PATH" kutusunu MUTLAKA isaretleyin.
echo  3) Kurulum bitince bu dosyayi (BASLAT.bat) tekrar calistirin.
echo.

:son
echo.
pause
