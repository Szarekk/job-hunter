import aiohttp
import asyncio
from bs4 import BeautifulSoup
import json
import os
import time
from urllib.parse import urljoin
import re
from pypdf import PdfReader
import io

# Config
CONFIG_PATH = 'urls_config.json'
HISTORY_PATH = 'history.json'
DISCORD_WEBHOOK = os.getenv('DISCORD_WEBHOOK')

async def load_json(path, default):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

async def send_discord_notification(session, item):
    if not DISCORD_WEBHOOK:
        print(f"DEBUG: New item found: {item['title']} - {item['link']} @ {item.get('place')}")
        return

    payload = {
        "embeds": [{
            "title": f"NOWA OFERTA: {item['title']}",
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
    
    if item.get('pdf'):
        payload["embeds"][0]["description"] = f"[Pobierz PDF]({item['pdf']})"

    try:
        async with session.post(DISCORD_WEBHOOK, json=payload) as resp:
            if resp.status != 204:
                print(f"Discord error: {resp.status}")
    except Exception as e:
        print(f"Error sending to Discord: {e}")

def get_workplace(soup):
    breadcrumb = soup.select_one('.breadcrumb')
    if breadcrumb:
        items = breadcrumb.select('li')
        if len(items) >= 2: return items[-2].get_text(strip=True)
    footer = soup.select_one('footer') or soup.select_one('.component-footer') or soup.select_one('.footer')
    if footer:
        text = footer.get_text(strip=True)
        if '©' in text:
            copy_part = text.split('©')[-1].split('.')[0].strip()
            copy_part = re.sub(r'\d{4}', '', copy_part).strip()
            if copy_part: return copy_part
    return "BIP"

async def fetch_soup(session, url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        async with session.get(url, headers=headers, timeout=15) as resp:
            text = await resp.text()
            return BeautifulSoup(text, 'lxml')
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

def is_junior_role(title):
    title_l = title.lower()
    return any(x in title_l for x in ['referent', 'podinspektor'])

async def scrape_bialystok(session, url):
    soup = await fetch_soup(session, url)
    if not soup: return []
    workplace = get_workplace(soup)
    items = []
    for div in soup.select('.item'):
        a = div.select_one('h3 a')
        if not a: continue
        title = a.get_text(strip=True)
        if is_junior_role(title): continue
        link = urljoin(url, a['href'])
        items.append({'id': link, 'title': title, 'link': link, 'place': workplace, 'system': 'Białystok BIP'})
    return items

async def scrape_wrota(session, url):
    soup = await fetch_soup(session, url)
    if not soup: return []
    workplace = get_workplace(soup)
    items = []
    seen_ids = set()
    links = soup.select('.component-page-list .component-item a') or soup.select('.component-item a')
    job_keywords = ['nabór', 'konkurs', 'stanowisko', 'praca', 'zatrudnię', 'oferta', 'ogłoszenie', 'inspektor', 'podinspektor', 'specjalista', 'referent', 'dyrektor', 'kierownik']
    garbage = ['redakcja', 'instrukcja', 'mapa', 'szukaj', 'zaloguj', 'kontakt', 'deklaracja', 'statut', 'regulamin', 'metryka']

    for a in links:
        link = urljoin(url, a['href'])
        title = a.get_text(strip=True)
        if not title or len(title) < 10: continue
        if is_junior_role(title): continue
        title_l = title.lower()
        if not any(k in title_l for k in job_keywords): continue
        if any(g == title_l or g in title_l[:len(g)+1] for g in garbage): continue
        if link not in seen_ids:
            items.append({'id': link, 'title': title, 'link': link, 'place': workplace, 'system': 'Wrota Podlasia'})
            seen_ids.add(link)
    return items

async def scrape_podlaskie(session, url):
    soup = await fetch_soup(session, url)
    if not soup: return []
    workplace = get_workplace(soup)
    items = []
    table = soup.select_one('table tbody')
    if not table: return []
    for tr in table.select('tr'):
        tds = tr.select('td')
        if len(tds) < 3: continue
        a = tds[0].select_one('a')
        if not a: continue
        title = a.select_one('strong').get_text(strip=True) if a.select_one('strong') else a.get_text(strip=True)
        if is_junior_role(title): continue
        link = urljoin(url, a['href'])
        items.append({'id': link, 'title': title, 'link': link, 'place': f"{workplace} - {tds[1].get_text(strip=True)}", 'deadline': tds[2].get_text(strip=True).replace('Do:', '').strip(), 'system': 'Podlaskie.eu'})
    return items

async def scrape_sokolka(session, url):
    soup = await fetch_soup(session, url)
    if not soup: return []
    workplace = get_workplace(soup)
    items = []
    for article in soup.select('article'):
        a = article.select_one('h2 a') or (article.select_one('.entry-title a') if article.select_one('.entry-title') else None)
        if not a: continue
        title = a.get_text(strip=True)
        if is_junior_role(title): continue
        link = urljoin(url, a['href'])
        items.append({'id': link, 'title': title, 'link': link, 'place': workplace, 'system': 'Sokółka BIP'})
    return items

async def get_details(session, item):
    soup = await fetch_soup(session, item['link'])
    if not soup: return
    
    if item['system'] == 'Białystok BIP':
        d = soup.select_one('#PAGE_SEARCH_TYPE_PARAM_DEADLINE')
        if d: item['deadline'] = d.get_text(strip=True)
        pdf = soup.select_one('.piwik_download[href$=".pdf"]')
        if pdf: item['pdf'] = urljoin(item['link'], pdf['href'])
    elif item['system'] == 'Wrota Podlasia':
        pdf = soup.select_one('.matomo_download[href$=".pdf"]')
        if pdf: item['pdf'] = urljoin(item['link'], pdf['href'])

async def process_url(session, entry, history):
    url, system = entry['url'], entry['system']
    print(f"Scraping {url}...")
    
    if system == 'bialystok': items = await scrape_bialystok(session, url)
    elif system == 'wrota': items = await scrape_wrota(session, url)
    elif system == 'podlaskie': items = await scrape_podlaskie(session, url)
    elif system == 'sokolka': items = await scrape_sokolka(session, url)
    else: items = []
    
    new_found = []
    for item in items:
        if item['id'] not in history:
            await get_details(session, item)
            await send_discord_notification(session, item)
            new_found.append(item)
    return new_found

async def main():
    urls = await load_json(CONFIG_PATH, [])
    history = await load_json(HISTORY_PATH, {})
    
    async with aiohttp.ClientSession() as session:
        tasks = [process_url(session, entry, history) for entry in urls]
        results = await asyncio.gather(*tasks)
        
        all_new = [item for sublist in results for item in sublist]
        for item in all_new:
            history[item['id']] = int(time.time())
            
    save_json(HISTORY_PATH, history)

if __name__ == "__main__":
    asyncio.run(main())
