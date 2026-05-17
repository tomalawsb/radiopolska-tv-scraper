Import danych RadioPolska

W tej paczce baza data/transmitters.json została wygenerowana z pliku emisje_dvbt.json dostarczonego przez użytkownika.

Wynik:
- 587 emisji wejściowych,
- 274 obiekty nadawcze po pogrupowaniu po współrzędnych,
- 0 rekordów pominiętych z powodu braku współrzędnych.

Jak odtworzyć import:
1. Skopiuj nowy eksport RadioPolska jako emisje_dvbt.json.
2. Uruchom:
   python build_transmitters_from_radiopolska.py emisje_dvbt.json data/transmitters.json
3. Odśwież aplikację albo wyczyść cache PWA.

Nie wrzucać do repozytorium prywatnych plików config.json z kluczami API.
