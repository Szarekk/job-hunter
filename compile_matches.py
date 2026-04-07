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
from scraper import PARENTS_PROFILE_PL, PROMPT_TEMPLATE, get_workplace, fetch_soup, scrape_bialystok, scrape_wrota, scrape_podlaskie, scrape_sokolka, extract_pdf_text, analyze_with_ai

CONFIG_PATH = 'urls_config.json'

async def process_item_full(session, item):
    print(f"Analizuję: {item['title']} ({item['place']})")
    soup = await fetch_soup(session, item['link'])
    if not soup: return None
    
    content = soup.get_text(separator=' ', strip=True)
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
    
    analysis = await analyze_with_ai(content)
    if analysis.get('decision') == 'TAK':
        item['analysis'] = analysis
        return item
    return None

async def main():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        urls = json.load(f)
    
    async with aiohttp.ClientSession() as session:
        print("Pobieram listy ofert...")
        list_tasks = []
        for entry in urls:
            url, system = entry['url'], entry['system']
            if system == 'bialystok': list_tasks.append(scrape_bialystok(session, url))
            elif system == 'wrota': list_tasks.append(scrape_wrota(session, url))
            elif system == 'podlaskie': list_tasks.append(scrape_podlaskie(session, url))
            elif system == 'sokolka': list_tasks.append(scrape_sokolka(session, url))
        
        all_items_lists = await asyncio.gather(*list_tasks)
        all_items = [item for sublist in all_items_lists for item in sublist]
        
        print(f"Znaleziono łącznie {len(all_items)} ofert. Rozpoczynam głęboką analizę AI (może to chwilę potrwać)...")
        
        matches = []
        batch_size = 3 # Small batch for AI API
        for i in range(0, len(all_items), batch_size):
            batch = all_items[i:i+batch_size]
            tasks = [process_item_full(session, item) for item in batch]
            results = await asyncio.gather(*tasks)
            for res in results:
                if res:
                    matches.append(res)
                    print(f"!!! DOPASOWANO: {res['title']}")
            
        print("\n" + "="*50)
        print("LISTA DOPASOWANYCH OFERT DLA RODZICÓW:")
        print("="*50)
        
        with open('matched_jobs.txt', 'w', encoding='utf-8') as f_out:
            f_out.write("LISTA DOPASOWANYCH OFERT DLA RODZICÓW\n")
            f_out.write("="*50 + "\n")
            if not matches:
                f_out.write("Brak dopasowanych ofert w tym momencie.\n")
                print("Brak dopasowanych ofert w tym momencie.")
            for m in matches:
                out = f"\nTYTUŁ: {m['title']}\n"
                out += f"MIEJSCE: {m['analysis'].get('extracted_place') or m['place']}\n"
                out += f"PŁACA: {m['analysis'].get('extracted_pay', 'N/A')}\n"
                out += f"TERMIN: {m['analysis'].get('extracted_deadline', 'N/A')}\n"
                out += f"LINK: {m['link']}\n"
                out += f"DLACZEGO: {m['analysis'].get('reason')}\n"
                f_out.write(out)
                print(out)
        print("="*50)
        print("Wyniki zapisano do matched_jobs.txt")

if __name__ == "__main__":
    asyncio.run(main())
