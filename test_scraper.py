"""
Probe real GdF department listing pages and extract HTML structure.
"""
import requests
import re
import json
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8",
    "Referer": "https://www.google.fr/",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "cross-site",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

targets = [
    ("Ardèche GdF", "https://www.gites-de-france-ardeche.com/location-gites-de-groupe.html"),
    ("Deux-Sèvres GdF", "https://www.gites-de-france-deux-sevres.com/gites-groupe.html"),
    ("PACA GdF", "https://www.gites-de-france-paca.com/liste.html?gitegroupe=o"),
    ("Vendée GdF", "https://www.gites-de-france-vendee.com/fr/thematiques/gites-groupe-grande-capacite-vendee"),
    ("Drôme GdF", "https://www.gites-de-france-drome.com/hebergements-groupe-copains-drome.html"),
]

results = {}

for name, url in targets:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        code = resp.status_code
        print(f"\n{'='*60}")
        print(f"[{code}] {name}: {resp.url}")

        if code != 200:
            results[name] = {"status": code, "url": url}
            continue

        soup = BeautifulSoup(resp.text, "lxml")

        # Count possible listing cards
        card_selectors = [
            ".fiche", ".gite", ".hebergement", ".card", ".listing",
            "[class*='gite']", "[class*='fiche']", "[class*='logement']",
            "[class*='annonce']", "[class*='hebergement']",
            "article", ".item", ".result"
        ]
        found = {}
        for sel in card_selectors:
            items = soup.select(sel)
            if items:
                found[sel] = len(items)

        print(f"  CSS selectors with items: {found}")

        # Get first 300 chars of body text for identification
        body_text = soup.get_text(" ", strip=True)[:400]
        print(f"  Body preview: {body_text[:200]}")

        # Save a small HTML chunk (first listing container found)
        html_chunk = ""
        for sel, count in sorted(found.items(), key=lambda x: -x[1])[:1]:
            items = soup.select(sel)
            if items:
                html_chunk = str(items[0])[:1000]

        results[name] = {
            "status": code,
            "url": resp.url,
            "selectors": found,
            "html_chunk": html_chunk,
        }

    except Exception as e:
        print(f"  ERROR: {e}")
        results[name] = {"status": "ERROR", "error": str(e), "url": url}

with open("data/gdf_structure.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print("\nDone. See data/gdf_structure.json")
