#!/bin/sh
# Ren'Py Türkçe Çeviri Motoru - Linux / macOS başlatıcı
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
    exec python3 ceviri.py "$@"
elif command -v python >/dev/null 2>&1; then
    exec python ceviri.py "$@"
else
    echo "Python 3 bulunamadı. Lütfen https://www.python.org/downloads/ adresinden kurun."
    exit 1
fi
