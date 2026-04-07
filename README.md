# Job Hunter BIP Scraper

A Python-based scraper that monitors multiple BIP (Biuletyn Informacji Publicznej) sites for new job postings.

## Features
- Supports 4 major BIP systems: Bialystok.pl, Wrota Podlasia, Podlaskie.eu, and WordPress-based BIPs.
- Automatic workplace name, salary, submission deadline extraction.
- Notification via Discord Webhook.
- Runs once a day via GitHub Actions.
- Tracking history to prevent duplicate alerts.
- Filters out junior and accounting postions

## Configuration
- `urls_config.json`: List of URLs to monitor and their scraper system.
- `history.json`: Tracks already notified postings.
- `scraper.py`: Core scraping logic.
