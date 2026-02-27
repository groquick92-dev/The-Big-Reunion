"""Debug - find which link contains the gite name/capacity text."""
import requests, re
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

url = "https://www.gites-de-france-drome.com/locations-de-vacances-grandes-capacites.html"
resp = requests.get(url, headers=HEADERS, timeout=20)
soup = BeautifulSoup(resp.text, "lxml")

vignettes = soup.select("div.vignette")
v = vignettes[0]

# Dump all links 
links = v.find_all("a")
print(f"Found {len(links)} links in first vignette:\n")
for i, a in enumerate(links):
    text = a.get_text(" ", strip=True)[:120]
    href = (a.get("href", ""))[:80]
    classes = a.get("class", [])
    print(f"  [{i}] class={classes} href={href}")
    if text: print(f"      text='{text}'")

# Also check for name in other elements
print("\n--- Checking for name elements ---")
for el in v.select("h1, h2, h3, h4, h5, .nom, .name, .title, [class*='nom'], [class*='title']"):
    print(f"  <{el.name} class={el.get('class',[])}> {el.get_text(strip=True)[:80]}")

# Check first img alt for name info
img = v.select_one("img[data-original]")
if img:
    print(f"\n--- First image alt ---")
    print(f"  alt: {img.get('alt', '')}")
    print(f"  src: {img.get('src', '')[:100]}")
    print(f"  data-original: {img.get('data-original', '')[:100]}")
