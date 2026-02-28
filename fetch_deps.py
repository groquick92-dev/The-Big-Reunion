import requests
from bs4 import BeautifulSoup
import re
import json

HEADERS = {'User-Agent': 'Mozilla/5.0'}

# GrandsGites
text = requests.get('https://www.grandsgites.com/', headers=HEADERS).text
soup = BeautifulSoup(text, 'lxml')
gg_map = {}
for a in soup.select('a'):
    h = str(a.get('href'))
    text_content = a.text.strip()
    m = re.match(r'^((?:0[1-9]|[1-8][0-9]|9[0-5]|2A|2B|97[1-6]))\s+(.*)', text_content)
    if 'gite-groupe-' in h and m:
        gg_map[m.group(1)] = h.replace('.htm', '')

# GitesXXL
textXXL = requests.get('https://www.gitesxxl.fr/grand-gite-groupe/', headers=HEADERS).text
soupXXL = BeautifulSoup(textXXL, 'lxml')
xxl_map = {}
for a in soupXXL.select('a'):
    h = str(a.get('href'))
    if 'grand-gite-groupe-' in h:
        m = re.search(r'grand-gite-groupe-(.+)-(\d{2})/?$', h.strip())
        if m:
            xxl_map[m.group(2)] = f"{m.group(1)}-{m.group(2)}"

with open('deps_map.py', 'w', encoding='utf-8') as f:
    f.write(f"GG_DEPARTMENTS = {json.dumps(gg_map, indent=4, ensure_ascii=False)}\n\n")
    f.write(f"XXL_DEPARTMENTS = {json.dumps(xxl_map, indent=4, ensure_ascii=False)}\n")

