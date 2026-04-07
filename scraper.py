import requests
from bs4 import BeautifulSoup
import json
import os
import time
from urllib.parse import urljoin

# Config will be loaded from external file
CONFIG_PATH = 'config.json'
HISTORY_PATH = 'history.json'
DISCORD_WEBHOOK = os.getenv('DISCORD_WEBHOOK')

def load_json(path, default):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def send_discord_notification(item):
    if not DISCORD_WEBHOOK:
        print(f"DEBUG: New item found: {item['title']} - {item['link']}")
        return

    payload = {
        "embeds": [{
            "title": item['title'],
            "url": item['link'],
            "color": 3447003,
            "fields": [
                {"name": "Miejsce", "value": item.get('place', 'N/A'), "inline": True},
                {"name": "Termin", "value": item.get('deadline', 'N/A'), "inline": True},
                {"name": "Wynagrodzenie", "value": item.get('pay', 'N/A'), "inline": True},
            ],
            "footer": {"text": f"System: {item['system']}"}
        }]
    }
    
    # Add PDF link if available
    if item.get('pdf'):
        payload["embeds"][0]["description"] = f"[Pobierz PDF]({item['pdf']})"

    try:
        response = requests.post(DISCORD_WEBHOOK, json=payload)
        response.raise_for_status()
    except Exception as e:
        print(f"Error sending to Discord: {e}")

def get_workplace(soup):
    # Try footer copyright first as it's often very clean
    footer = soup.select_one('footer') or soup.select_one('.component-footer') or soup.select_one('.footer')
    if footer:
        text = footer.get_text(strip=True)
        if '©' in text:
            copy_part = text.split('©')[-1].split('.')[0].strip()
            # Remove year if present
            import re
            copy_part = re.sub(r'\d{4}', '', copy_part).strip()
            if copy_part: return copy_part

    # Fallback to title
    title_tag = soup.select_one('title')
    if title_tag:
        title_text = title_tag.get_text(strip=True)
        # Handle "Biuletyn Informacji Publicznej - Urząd ..."
        for sep in [' - ', ' – ', ' | ', ': ']:
            if sep in title_text:
                parts = title_text.split(sep)
                # Pick the longest part that isn't "Biuletyn Informacji Publicznej"
                best_part = ""
                for p in parts:
                    p = p.strip()
                    if "Biuletyn" not in p and len(p) > len(best_part):
                        best_part = p
                if best_part: return best_part
        return title_text
    return "BIP"

def scrape_bialystok(url):
    items = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get(url, headers=headers)
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, 'html.parser')
        workplace = get_workplace(soup)
        
        for div in soup.select('.item'):
            a = div.select_one('h3 a')
            if not a: continue
            
            link = urljoin(url, a['href'])
            title = a.get_text(strip=True)
            
            items.append({
                'id': link,
                'title': title,
                'link': link,
                'place': workplace,
                'system': 'Białystok BIP'
            })
    except Exception as e:
        print(f"Error scraping Bialystok {url}: {e}")
    return items

def scrape_wrota(url):
    items = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get(url, headers=headers)
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, 'html.parser')
        workplace = get_workplace(soup)
        
        seen_ids = set()
        # Wrota can have list in different places
        
        # Priority 1: Page list
        links = soup.select('.component-page-list .component-item a')
        # Priority 2: Sidebar menu (like Grabowka) or generic component items
        if not links:
            links = soup.select('.component-item a')

        for a in links:
            link = urljoin(url, a['href'])
            title = a.get_text(strip=True)
            if not title or len(title) < 5: continue
            
            # Filter out common navigation garbage
            garbage = ['redakcja', 'instrukcja', 'mapa', 'szukaj', 'zaloguj', 'kontakt', 'deklaracja', 'statut', 'regulamin', 'podstawowe', 'prawny', 'kompetencje', 'majątek', 'kontrola', 'ogłoszenia', 'praca', 'start']
            if any(g == title.lower() or g in title.lower()[:len(g)+1] for g in garbage):
                continue
            
            if link not in seen_ids:
                items.append({
                    'id': link,
                    'title': title,
                    'link': link,
                    'place': workplace,
                    'system': 'Wrota Podlasia'
                })
                seen_ids.add(link)
    except Exception as e:
        print(f"Error scraping Wrota {url}: {e}")
    return items

def scrape_podlaskie(url):
    items = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get(url, headers=headers)
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, 'html.parser')
        workplace = get_workplace(soup)
        
        table = soup.select_one('table tbody')
        if not table: return items
        
        for tr in table.select('tr'):
            tds = tr.select('td')
            if len(tds) < 3: continue
            
            a = tds[0].select_one('a')
            if not a: continue
            
            link = urljoin(url, a['href'])
            title = a.select_one('strong').get_text(strip=True) if a.select_one('strong') else a.get_text(strip=True)
            
            # For Podlaskie, tds[1] is the department, but we can prepend the main workplace
            place = f"{workplace} - {tds[1].get_text(strip=True)}"
            deadline = tds[2].get_text(strip=True).replace('Do:', '').strip()
            
            items.append({
                'id': link,
                'title': title,
                'link': link,
                'place': place,
                'deadline': deadline,
                'system': 'Podlaskie.eu'
            })
    except Exception as e:
        print(f"Error scraping Podlaskie {url}: {e}")
    return items

def scrape_sokolka(url):
    items = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get(url, headers=headers)
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, 'html.parser')
        workplace = get_workplace(soup)
        
        for article in soup.select('article'):
            a = article.select_one('h2 a')
            if not a:
                title_div = article.select_one('.entry-title')
                if title_div: a = title_div.select_one('a')
            
            if not a: continue
            
            link = urljoin(url, a['href'])
            title = a.get_text(strip=True)
            
            items.append({
                'id': link,
                'title': title,
                'link': link,
                'place': workplace,
                'system': 'Sokółka BIP'
            })
    except Exception as e:
        print(f"Error scraping Sokolka {url}: {e}")
    return items

def get_details_bialystok(item):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get(item['link'], headers=headers)
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        deadline_div = soup.select_one('#PAGE_SEARCH_TYPE_PARAM_DEADLINE')
        if deadline_div:
            item['deadline'] = deadline_div.get_text(strip=True)
            
        pdf_a = soup.select_one('.piwik_download[href$=".pdf"]')
        if pdf_a:
            item['pdf'] = urljoin(item['link'], pdf_a['href'])
    except: pass

def get_details_wrota(item):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get(item['link'], headers=headers)
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        pdf_a = soup.select_one('.matomo_download[href$=".pdf"]')
        if pdf_a:
            item['pdf'] = urljoin(item['link'], pdf_a['href'])
        
        # Deadlines in Wrota are often in text or table, tricky without standard ID
        # Search for 'Termin' in text
        content = soup.get_text()
        if 'Termin' in content:
            # Simple heuristic
            pass
    except: pass

def main():
    urls = load_json('urls_config.json', [])
    history = load_json(HISTORY_PATH, {})
    new_history = history.copy()
    
    for entry in urls:
        url = entry['url']
        system = entry['system']
        print(f"Scraping {url} ({system})...")
        
        items = []
        if system == 'bialystok':
            items = scrape_bialystok(url)
        elif system == 'wrota':
            items = scrape_wrota(url)
        elif system == 'podlaskie':
            items = scrape_podlaskie(url)
        elif system == 'sokolka':
            items = scrape_sokolka(url)
            
        for item in items:
            if item['id'] not in history:
                print(f"New posting: {item['title']}")
                
                # Fetch more details if needed
                if system == 'bialystok':
                    get_details_bialystok(item)
                elif system == 'wrota':
                    get_details_wrota(item)
                
                send_discord_notification(item)
                new_history[item['id']] = int(time.time())
                
    save_json(HISTORY_PATH, new_history)

if __name__ == "__main__":
    main()
