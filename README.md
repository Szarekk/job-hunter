# Job Hunter BIP Scraper

Zautomatyzowany system monitorowania ofert pracy w sektorze publicznym (BIP i strony uczelni) dla regionu Białegostoku i okolic.

## Funkcje
- **Obsługa wielu systemów**: Białystok BIP, Wrota Podlasia, Podlaskie.eu, WordPress BIP, Lavina, systemy tabelaryczne oraz strony uczelni (PB, UwB, UMB).
- **Inteligentne Filtrowanie**: Automatycznie odrzuca stanowiska juniorskie (referent, podinspektor) oraz księgowe.
- **Ekstrakcja Danych**: Pobiera nazwę miejsca pracy, widełki płacowe (regex) oraz terminy składania dokumentów.
- **Powiadomienia Discord**: Wysyła estetyczne powiadomienia z linkami do ofert i plików PDF.
- **System Monitoringu**: Powiadamia na Discordzie o błędach wymagających interwencji oraz wysyła cotygodniowy raport o działaniu systemu (w niedziele).

## Utrzymanie (Maintenance)

### Dodawanie nowych stron
Aby dodać nową stronę do monitorowania, edytuj plik `urls_config.json`:
1. Dodaj obiekt: `{"url": "LINK_DO_LISTY_OFERT", "system": "TYP_SYSTEMU"}`.
2. Dostępne systemy: `bialystok`, `wrota`, `podlaskie`, `sokolka`, `lavina`, `joboffers`, `pb`, `uwb`, `umb`.

### Zmiana filtrów
Słowa kluczowe do odrzucania ofert znajdują się w `scraper.py` w funkcji `should_skip_role`.

### Rozwiązywanie problemów
Jeśli otrzymasz powiadomienie **"ZADANIE WYMAGA KONSERWACJI"**:
1. Sprawdź logi w zakładce "Actions" na GitHubie.
2. Najczęstsze przyczyny to zmiana struktury HTML strony lub błąd certyfikatu SSL.

## Konfiguracja GitHub Actions
Skraper uruchamia się automatycznie raz dziennie o **17:00 czasu polskiego**.
Wymaga zdefiniowania sekretu `DISCORD_WEBHOOK` w ustawieniach repozytorium (Settings -> Secrets and variables -> Actions).
