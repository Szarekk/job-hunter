# minify.py
import sys
import requests
from bs4 import BeautifulSoup

def minify_html(target):
    if target.startswith('http'):
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(target, headers=headers)
        response.encoding = response.apparent_encoding
        html_content = response.text
    else:
        with open(target, 'r', encoding='utf-8') as f:
            html_content = f.read()
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 1. Nuke the garbage tags
    for tag in soup(['script', 'style', 'svg', 'noscript', 'meta', 'link', 'header', 'footer', 'iframe']):
        tag.decompose()
        
    # 2. Keep only structural attributes needed for BeautifulSoup scraping
    allowed_attrs = ['id', 'class', 'href']
    for tag in soup.find_all(True):
        attrs = dict(tag.attrs)
        for attr in attrs:
            if attr not in allowed_attrs:
                del tag[attr]
                
    # 3. Optional: Remove completely empty tags to save even more context space
    for tag in soup.find_all():
        if len(tag.get_text(strip=True)) == 0 and not tag.find('a'):
            tag.decompose()
            
    print(str(soup))

if __name__ == "__main__":
    if len(sys.argv) > 1:
        minify_html(sys.argv[1])
    else:
        print("Usage: python minify.py <URL>")
