import aiohttp
import asyncio
from bs4 import BeautifulSoup
import json
import os
import time
from urllib.parse import urljoin
import re
from ollamafreeapi import OllamaFreeAPI
from pypdf import PdfReader
import io

# Config
CONFIG_PATH = 'urls_config.json'
HISTORY_PATH = 'history.json'
DISCORD_WEBHOOK = os.getenv('DISCORD_WEBHOOK')

# AI Profiles and Rules
PARENTS_PROFILE_PL = """
Profil Kandydatów (Rodzice):
- Staż pracy: 20 lat.
- Wykształcenie: Wyższe magisterskie (oboje Administracja, mama dodatkowo Filologia Polska).
- Doświadczenie Tata: Zamówienia publiczne, faktury, administracja.
- Doświadczenie Mama: Nauczycielka j. polskiego (3 lata), praca kancelaryjna w notariacie (sekretariat, pisanie aktów notarialnych).
- Znajomość ustaw: Wszystkie wymagane w administracji publicznej.

Kryteria selekcji:
1. Płaca: Minimum 6000 zł brutto podstawy. 
   - Jeśli brak kwoty: Referent/Podinspektor = ODRZUĆ. Inspektor/Specjalista/Starszy Inspektor = AKCEPTUJ (zakładamy >6000).
2. Wykształcenie: Musi być Administracja, Prawo lub Filologia Polska (dla mamy). Inne niepokrewne = ODRZUĆ.
3. Doświadczenie: Odrzuć jeśli wymagany jest konkretny staż w księgowości (stanowiska księgowego).
4. Rodzaj pracy: Biurowa lub kancelaryjna. Odrzuć sprzątaczy, konserwatorów itp. Sekretariat jest OK.
5. Staż w administracji publicznej: Jeśli jest warunkiem koniecznym, a kandydaci go nie mają (tata ma 20 lat w zamówieniach, mama w notariacie - oceń czy pasuje).
"""

PROMPT_TEMPLATE = """
Przeanalizuj poniższą ofertę pracy pod kątem profilu moich rodziców.
{profile}

TREŚĆ OFERTY:
{content}

Zwróć odpowiedź w formacie JSON:
{{
  "decision": "TAK" lub "NIE",
  "reason": "krótkie uzasadnienie po polsku",
  "extracted_deadline": "data składania dokumentów jeśli znajdziesz",
  "extracted_pay": "kwota wynagrodzenia jeśli znajdziesz",
  "extracted_place": "dokładne miejsce pracy"
}}
Tylko czysty JSON, bez dodatkowego tekstu.
"""

async def load_json(path, default):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

async def send_discord_notification(session, item, ai_analysis):
    if not DISCORD_WEBHOOK:
        print(f"DEBUG: {item['title']} -> {ai_analysis['decision']} ({ai_analysis.get('reason')})")
        return

    if ai_analysis.get('decision') != 'TAK':
        return

    payload = {
        "embeds": [{
            "title": f"DOPASOWANO: {item['title']}",
            "url": item['link'],
            "color": 65280, # Green
            "description": f"**Uzasadnienie AI:** {ai_analysis.get('reason')}",
            "fields": [
                {"name": "Miejsce", "value": ai_analysis.get('extracted_place') or item.get('place', 'N/A'), "inline": True},
                {"name": "Termin", "value": ai_analysis.get('extracted_deadline') or item.get('deadline', 'N/A'), "inline": True},
                {"name": "Wynagrodzenie", "value": ai_analysis.get('extracted_pay') or item.get('pay', 'N/A'), "inline": True},
            ],
            "footer": {"text": f"System: {item['system']}"}
        }]
    }
    
    if item.get('pdf'):
        payload["embeds"][0]["description"] += f"\n\n[Pobierz PDF]({item['pdf']})"

    try:
        async with session.post(DISCORD_WEBHOOK, json=payload) as resp:
            if resp.status != 204:
                print(f"Discord error: {resp.status}")
    except Exception as e:
        print(f"Error sending to Discord: {e}")

async def extract_pdf_text(session, url):
    try:
        async with session.get(url, timeout=20) as resp:
            if resp.status == 200:
                content = await resp.read()
                f = io.BytesIO(content)
                reader = PdfReader(f)
                text = ""
                for page in reader.pages[:5]: # First 5 pages usually enough
                    text += page.extract_text() + "\n"
                return text
    except Exception as e:
        print(f"PDF error {url}: {e}")
    return ""

async def analyze_with_ai(content):
    client = OllamaFreeAPI()
    prompt = PROMPT_TEMPLATE.format(profile=PARENTS_PROFILE_PL, content=content[:8000]) # Limit content
    try:
        # Using a reliable model like llama3.2 or mistral
        response = client.chat(model="llama3.2:3b", prompt=prompt)
        # Try to find JSON in response
        match = re.search(r'\{.*\}', response, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except Exception as e:
        print(f"AI error: {e}")
    return {"decision": "NIE", "reason": "Błąd analizy AI"}

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

async def scrape_bialystok(session, url):
    soup = await fetch_soup(session, url)
    if not soup: return []
    workplace = get_workplace(soup)
    items = []
    for div in soup.select('.item'):
        a = div.select_one('h3 a')
        if not a: continue
        link = urljoin(url, a['href'])
        items.append({'id': link, 'title': a.get_text(strip=True), 'link': link, 'place': workplace, 'system': 'Białystok BIP'})
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
        link = urljoin(url, a['href'])
        title = a.select_one('strong').get_text(strip=True) if a.select_one('strong') else a.get_text(strip=True)
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
        link = urljoin(url, a['href'])
        items.append({'id': link, 'title': a.get_text(strip=True), 'link': link, 'place': workplace, 'system': 'Sokółka BIP'})
    return items

async def process_item(session, item, history):
    if item['id'] in history: return None
    
    print(f"Analyzing: {item['title']}")
    # 1. Fetch detail page HTML
    soup = await fetch_soup(session, item['link'])
    if not soup: return None
    
    content = soup.get_text(separator=' ', strip=True)
    
    # 2. Extract PDF text if present
    pdf_url = None
    if item['system'] == 'Białystok BIP':
        pdf_a = soup.select_one('.piwik_download[href$=".pdf"]')
        if pdf_a: pdf_url = urljoin(item['link'], pdf_a['href'])
    elif item['system'] == 'Wrota Podlasia':
        pdf_a = soup.select_one('.matomo_download[href$=".pdf"]')
        if pdf_a: pdf_url = urljoin(item['link'], pdf_a['href'])
    
    if pdf_url:
        item['pdf'] = pdf_url
        pdf_text = await extract_pdf_text(session, pdf_url)
        content += "\n--- PDF CONTENT ---\n" + pdf_text
    
    # 3. AI Analysis
    analysis = await analyze_with_ai(content)
    await send_discord_notification(session, item, analysis)
    return item

async def main():
    urls = await load_json(CONFIG_PATH, [])
    history = await load_json(HISTORY_PATH, {})
    
    async with aiohttp.ClientSession() as session:
        # Scrape lists first
        list_tasks = []
        for entry in urls:
            url, system = entry['url'], entry['system']
            if system == 'bialystok': list_tasks.append(scrape_bialystok(session, url))
            elif system == 'wrota': list_tasks.append(scrape_wrota(session, url))
            elif system == 'podlaskie': list_tasks.append(scrape_podlaskie(session, url))
            elif system == 'sokolka': list_tasks.append(scrape_sokolka(session, url))
        
        all_items_lists = await asyncio.gather(*list_tasks)
        all_items = [item for sublist in all_items_lists for item in sublist]
        
        # Process new items (AI & Details) - process in small batches to avoid overloading AI API
        batch_size = 5
        for i in range(0, len(all_items), batch_size):
            batch = all_items[i:i+batch_size]
            process_tasks = [process_item(session, item, history) for item in batch]
            processed = await asyncio.gather(*process_tasks)
            for item in processed:
                if item:
                    history[item['id']] = int(time.time())
            # Save history incrementally
            save_json(HISTORY_PATH, history)

if __name__ == "__main__":
    asyncio.run(main())
