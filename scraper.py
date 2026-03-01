"""
Scraper module for Cousinade Planner.
Scrapes REAL gîtes de groupe from multiple French accommodation websites.
Uses Playwright for JavaScript-heavy sites and requests for static HTML.
NO DEMO DATA — only real listings.
"""

import json
import os
import re
import time
import random
import logging
from typing import Optional

import requests
from bs4 import BeautifulSoup
from deps_map import GG_DEPARTMENTS, XXL_DEPARTMENTS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CACHE_FILE = os.path.join(DATA_DIR, "cache_gites.json")
CACHE_DURATION = 86400  # 24 hours cache

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

REQUEST_TIMEOUT = 20

# ─── Source definitions ──────────────────────────────────────────────────────
SOURCES = {
    "grandsgites": {"name": "GrandsGites.com", "color": "#6366f1"},
    "gitesxxl": {"name": "GitesXXL.fr", "color": "#ec4899"},
    "gigalocation": {"name": "Giga-Location", "color": "#3b82f6"},
    "gitesdefrance": {"name": "Gîtes de France", "color": "#059669"},
}


def extract_number(text: str) -> Optional[int]:
    """Extract the first integer from a string."""
    if not text:
        return None
    cleaned = text.replace("\xa0", "").replace(" ", "").replace("€", "")
    match = re.search(r"\d+", cleaned)
    return int(match.group()) if match else None


def extract_department(text: str) -> str:
    """Extract department number from text like 'Gite de groupe Dordogne' or URL like 'gite-24-...'."""
    # Try from URL pattern: gite-XX-
    match = re.search(r"gite-(\d{1,2}[AB]?)-", text)
    if match:
        return match.group(1)
    # Try department number in parentheses (24)
    match = re.search(r"\((\d{1,2}[AB]?)\)", text)
    if match:
        return match.group(1)
    return ""


def detect_animaux(text: str) -> bool:
    """Detect if pets are accepted from text content."""
    keywords = ["animaux", "animal", "chien", "chat", "pet friendly", "acceptés"]
    return any(kw in text.lower() for kw in keywords)


def get_cache_file(departement: Optional[str]) -> str:
    if departement:
        return os.path.join(DATA_DIR, f"cache_gites_{departement}.json")
    return CACHE_FILE

def load_cache(departement: Optional[str] = None) -> Optional[dict]:
    """Load cached results if fresh enough."""
    cfile = get_cache_file(departement)
    try:
        if os.path.exists(cfile):
            with open(cfile, "r", encoding="utf-8") as f:
                cache = json.load(f)
            if time.time() - cache.get("timestamp", 0) < CACHE_DURATION:
                logger.info(f"Using cache ({len(cache['gites'])} gîtes, {int(time.time() - cache['timestamp'])}s old)")
                return cache["gites"]
    except Exception as e:
        logger.warning(f"Cache read error: {e}")
    return None


def save_cache(gites: list[dict], departement: Optional[str] = None) -> None:
    """Save results to cache."""
    cfile = get_cache_file(departement)
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(cfile, "w", encoding="utf-8") as f:
            json.dump({"timestamp": time.time(), "gites": gites}, f, ensure_ascii=False, indent=2)
        logger.info(f"Cached {len(gites)} gîtes")
    except Exception as e:
        logger.warning(f"Cache write error: {e}")


# ─── SCRAPER 1: GrandsGites.com (HTML statique — requests + BS4) ─────────
def scrape_grandsgites(capacite_min: int = 10, departement: Optional[str] = None) -> list[dict]:
    """
    Scrape GrandsGites.com — the #1 source for group gîtes in France.
    This site serves static HTML — no JavaScript needed.
    Real HTML structure:
      div.fichecourte → contains each listing
        div.t_img > a > img (lazy: data-original) → photo
        div.t_donnees > span.maj > a → name & URL
        div.t_donnees > span.gris2 → address & department
        span.or4 → "Jusqu'à X personnes"
        div.t_txt_pres > span.desc_gite → description
        span.picto_liste → equipment icons (c_piscine, c_salle, etc.)
    """
    gites = []
    MAX_PER_RUN = 100  # Limit to keep response time reasonable
    
    # Only scrape capacity ranges that match the filter
    if departement and departement in GG_DEPARTMENTS:
        pages = [("DEPT", GG_DEPARTMENTS[departement])]
    elif capacite_min > 80:
        pages = [("E", "80+")]
    elif capacite_min > 59:
        pages = [("D", "60 à 80"), ("E", "80+")]
    elif capacite_min > 39:
        pages = [("C", "40 à 59"), ("D", "60 à 80"), ("E", "80+")]
    elif capacite_min > 24:
        pages = [("B", "25 à 39"), ("C", "40 à 59"), ("D", "60 à 80"), ("E", "80+")]
    elif capacite_min > 15:
        pages = [("Abis", "16 à 24"), ("B", "25 à 39"), ("C", "40 à 59"), ("D", "60 à 80"), ("E", "80+")]
    else:
        pages = [("A", "12 à 15"), ("Abis", "16 à 24"), ("B", "25 à 39"), ("C", "40 à 59"), ("D", "60 à 80"), ("E", "80+")]
    
    for suffix, label in pages:
        if len(gites) >= MAX_PER_RUN:
            break
        try:
            if suffix == "DEPT":
                url = f"https://www.grandsgites.com/{label}.htm"
                logger.info(f"Scraping GrandsGites: Département {departement} — {url}")
            else:
                url = f"https://www.grandsgites.com/gite-grande-capacite-{suffix}.htm"
                logger.info(f"Scraping GrandsGites: {label} personnes — {url}")
            
            response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "lxml")
            
            # Each listing is in a div.fichecourte
            cards = soup.select("div.fichecourte")
            logger.info(f"  Found {len(cards)} cards on page {suffix}")
            
            for card in cards:
                if len(gites) >= MAX_PER_RUN:
                    break
                try:
                    # ── Name & URL from div.t_donnees > span.maj > a
                    name_el = card.select_one("div.t_donnees span.maj a")
                    if not name_el:
                        continue
                    nom = name_el.get_text(strip=True)
                    href = name_el.get("href", "")
                    if not nom or not href:
                        continue
                    full_url = f"https://www.grandsgites.com/{href}"
                    
                    # ── Photo from div.t_img img (lazy loaded via data-original)
                    img_el = card.select_one("div.t_img img")
                    photo = ""
                    if img_el:
                        photo = img_el.get("data-original") or img_el.get("src", "")
                        # Keep -pt (thumbnail) version — full-size doesn't exist on server
                    
                    # ── Address & Department from FIRST span.gris2 only
                    # Structure: <span class="gris2">27260 Asnières<br>Eure</span>
                    # The SECOND span.gris2 is the formula (e.g. "Gestion libre") — skip it
                    addr_els = card.select("div.t_donnees span.gris2")
                    departement = ""
                    localisation = ""
                    if addr_els:
                        first_gris = addr_els[0]
                        # Get all text parts (split by <br>)
                        texts = []
                        for child in first_gris.children:
                            if isinstance(child, str) and child.strip():
                                texts.append(child.strip())
                        if not texts:
                            texts = [t.strip() for t in first_gris.get_text("\n").split("\n") if t.strip()]
                        
                        ville = ""
                        dept_name = ""
                        for t in texts:
                            cp_match = re.match(r"^(\d{5})\s+(.+)", t)
                            if cp_match:
                                departement = cp_match.group(1)[:2]
                                ville = cp_match.group(2)
                            elif not any(c.isdigit() for c in t) and len(t) > 2:
                                # Skip formulas
                                if t.lower() not in ("gestion libre", "demi-pension", "pension complète", "pt déj."):
                                    dept_name = t
                        
                        if dept_name and departement:
                            localisation = f"{dept_name} ({departement})"
                        elif ville and departement:
                            localisation = f"{ville} ({departement})"
                        elif dept_name:
                            localisation = dept_name
                        else:
                            localisation = "France"
                    else:
                        localisation = "France"
                    
                    # ── Capacity from span.or4 ("Jusqu'à X personnes")
                    cap_el = card.select_one("span.or4")
                    capacite = 0
                    if cap_el:
                        cap_match = re.search(r"(\d+)", cap_el.get_text())
                        capacite = int(cap_match.group(1)) if cap_match else 0
                    
                    # ── Description
                    desc_el = card.select_one("span.desc_gite")
                    description = desc_el.get_text(strip=True)[:300] if desc_el else ""
                    
                    # ── Equipment from span.picto_liste
                    equipements = []
                    for equip_cls, equip_name in [
                        ("c_piscine", "Piscine"),
                        ("c_salle", "Salle de réception"),
                        ("c_handicap", "Accès handicapé"),
                    ]:
                        if card.select_one(f"span.{equip_cls}"):
                            equipements.append(equip_name)
                    # Max couchages
                    cap_badge = card.select_one("span.picto_cap3")
                    if cap_badge:
                        equipements.append(cap_badge.get_text(strip=True))
                    
                    # ── Detect pets from description
                    card_text = card.get_text().lower()
                    animaux = detect_animaux(card_text)
                    
                    gite = {
                        "nom": nom,
                        "url": full_url,
                        "capacite": capacite,
                        "prix_semaine": None,
                        "localisation": localisation,
                        "departement": departement,
                        "description": description,
                        "equipements": equipements,
                        "photo": photo,
                        "note": None,
                        "animaux": animaux,
                        "source": "grandsgites",
                    }
                    gites.append(gite)
                    
                except Exception as e:
                    logger.warning(f"  Card parse error: {e}")
                    continue
                    
        except requests.RequestException as e:
            logger.error(f"Network error scraping GrandsGites ({label}): {e}")
        except Exception as e:
            logger.error(f"Error scraping GrandsGites ({label}): {e}")
    
    logger.info(f"✅ GrandsGites.com: {len(gites)} real listings scraped")
    return gites


# ─── SCRAPER 2: TopLoc.com (Playwright — JavaScript rendered) ────────────
def scrape_toploc_sync(capacite_min: int = 10) -> list[dict]:
    """Scrape TopLoc.com using Playwright for JS rendering."""
    gites = []
    try:
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            url = "https://www.toploc.com/gite-de-groupe"
            logger.info(f"Scraping TopLoc: {url}")
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            
            html = page.content()
            browser.close()
        
        soup = BeautifulSoup(html, "lxml")
        
        # Find listing cards
        cards = soup.select("article, .card, .listing-card, .property-card, [class*='listing'], [class*='annonce']")
        if not cards:
            cards = soup.find_all("a", href=re.compile(r"/location/|/sejour/|/gite"))
        
        processed = set()
        for idx, card in enumerate(cards[:50]):
            try:
                # Get link
                link = card if card.name == "a" else card.find("a", href=True)
                if not link:
                    continue
                href = link.get("href", "")
                if href in processed or not href:
                    continue
                processed.add(href)
                
                full_url = f"https://www.toploc.com{href}" if not href.startswith("http") else href
                
                # Get name
                name_el = card.find(["h2", "h3", "h4"]) or card.find(class_=re.compile(r"title|name|nom"))
                nom = name_el.get_text(strip=True) if name_el else link.get_text(strip=True)[:80]
                if not nom or len(nom) < 3:
                    continue
                
                # Get image
                img = card.find("img")
                photo = ""
                if img:
                    photo = img.get("src") or img.get("data-src") or img.get("data-lazy", "")
                    if photo and not photo.startswith("http"):
                        photo = f"https://www.toploc.com{photo}"
                
                # Get price
                price_el = card.find(class_=re.compile(r"price|prix|tarif"))
                prix = extract_number(price_el.get_text() if price_el else "")
                
                # Get location
                loc_el = card.find(class_=re.compile(r"location|lieu|adresse|city"))
                localisation = loc_el.get_text(strip=True) if loc_el else "France"
                
                # Get capacity
                cap_el = card.find(string=re.compile(r"\d+\s*(pers|voyag|place|couchage)", re.I))
                capacite = extract_number(str(cap_el)) if cap_el else 20
                
                card_text = card.get_text()
                
                gite = {
                    "nom": nom,
                    "url": full_url,
                    "capacite": capacite or 20,
                    "prix_semaine": prix,
                    "localisation": localisation,
                    "departement": "",
                    "description": card_text[:200].strip() if card_text else "",
                    "equipements": [],
                    "photo": photo,
                    "note": None,
                    "animaux": detect_animaux(card_text),
                    "source": "toploc",
                }
                gites.append(gite)
                
            except Exception as e:
                logger.warning(f"TopLoc card parse error: {e}")
                continue
        
        logger.info(f"✅ TopLoc.com: {len(gites)} real listings scraped")
        
    except ImportError:
        logger.error("❌ TopLoc: Playwright not installed")
    except Exception as e:
        logger.error(f"❌ TopLoc scraping error: {e}")
    
    return gites


# ─── SCRAPER 3: GreenGo.voyage (Playwright) ──────────────────────────────
def scrape_greengo_sync(capacite_min: int = 10) -> list[dict]:
    """Scrape GreenGo.voyage using Playwright."""
    gites = []
    try:
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            url = f"https://www.greengo.voyage/locations-de-vacances?capacite_min={capacite_min}"
            logger.info(f"Scraping GreenGo: {url}")
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            
            html = page.content()
            browser.close()
        
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select("article, .card, [class*='listing'], [class*='property'], [class*='annonce']")
        if not cards:
            cards = soup.find_all("a", href=re.compile(r"/location/|/hebergement/"))
        
        processed = set()
        for card in cards[:50]:
            try:
                link = card if card.name == "a" else card.find("a", href=True)
                if not link:
                    continue
                href = link.get("href", "")
                if href in processed or not href:
                    continue
                processed.add(href)
                
                full_url = f"https://www.greengo.voyage{href}" if not href.startswith("http") else href
                
                name_el = card.find(["h2", "h3", "h4"])
                nom = name_el.get_text(strip=True) if name_el else link.get_text(strip=True)[:80]
                if not nom or len(nom) < 3:
                    continue
                
                img = card.find("img")
                photo = ""
                if img:
                    photo = img.get("src") or img.get("data-src", "")
                    if photo and not photo.startswith("http"):
                        photo = f"https://www.greengo.voyage{photo}"
                
                price_el = card.find(class_=re.compile(r"price|prix|tarif"))
                prix = extract_number(price_el.get_text() if price_el else "")
                
                loc_el = card.find(class_=re.compile(r"location|lieu|adresse"))
                localisation = loc_el.get_text(strip=True) if loc_el else "France"
                
                card_text = card.get_text()
                cap_match = re.search(r"(\d+)\s*(pers|voyag|place)", card_text, re.I)
                capacite = int(cap_match.group(1)) if cap_match else 15
                
                gite = {
                    "nom": nom,
                    "url": full_url,
                    "capacite": capacite,
                    "prix_semaine": prix,
                    "localisation": localisation,
                    "departement": "",
                    "description": card_text[:200].strip() if card_text else "",
                    "equipements": [],
                    "photo": photo,
                    "note": None,
                    "animaux": detect_animaux(card_text),
                    "source": "greengo",
                }
                gites.append(gite)
                
            except Exception as e:
                logger.warning(f"GreenGo card parse error: {e}")
        
        logger.info(f"✅ GreenGo: {len(gites)} real listings scraped")
        
    except Exception as e:
        logger.error(f"❌ GreenGo scraping error: {e}")
    
    return gites


# ─── SCRAPER 4: Gîtes de France — STEALTH (departmental bypass) ──────────
#
# Strategy: Hit departmental subdomains (gites-de-france-drome.com, etc.)
# instead of the central gites-de-france.com which has aggressive WAF.
# Departmental sites serve static HTML with no WAF protection.
#
def _get_stealth_headers(referer: str = "https://www.google.fr/") -> dict:
    """Generate high-fidelity browser headers with rotating User-Agent."""
    try:
        from fake_useragent import UserAgent
        ua = UserAgent(browsers=["chrome", "edge"], os=["windows", "macos"])
        user_agent = ua.random
    except Exception:
        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    
    return {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": referer,
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "cross-site" if "google" in referer else "same-origin",
        "Sec-Fetch-User": "?1",
        "Sec-CH-UA": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "Sec-CH-UA-Mobile": "?0",
        "Sec-CH-UA-Platform": '"Windows"',
        "Cache-Control": "max-age=0",
    }


# Departmental sites with group gîte pages
GDF_DEPARTMENTS = [
    ("drome", "Drôme", "26", "hebergements-groupe-copains-drome.html"),
    ("ardeche", "Ardèche", "07", "location-gites-de-groupe.html"),
    ("deux-sevres", "Deux-Sèvres", "79", "gites-groupe.html"),
    ("paca", "PACA", "83", "liste.html?gitegroupe=o"),
    ("vendee", "Vendée", "85", "fr/thematiques/gites-groupe-grande-capacite-vendee"),
    ("dordogne", "Dordogne", "24", "locations-de-vacances-grandes-capacites.html"),
    ("nievre", "Nièvre", "58", "locations-de-vacances-grandes-capacites.html"),
    ("finistere", "Finistère", "29", "locations-de-vacances-grandes-capacites.html"),
]


def _save_gdf_incremental(gites: list[dict]):
    """Incremental save after each successful department extraction."""
    path = os.path.join(DATA_DIR, "gites_gdf.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(gites, f, ensure_ascii=False, indent=2)
        logger.info(f"  💾 Incremental save: {len(gites)} gîtes → gites_gdf.json")
    except Exception as e:
        logger.warning(f"  Save error: {e}")


def scrape_gitesdefrance_stealth(capacite_min: int = 10, departement: Optional[str] = None) -> list[dict]:
    """
    Stealth scraper for Gîtes de France — departmental bypass strategy.
    
    Instead of hitting the central gites-de-france.com (protected by WAF),
    targets departmental subdomains like gites-de-france-drome.com which
    serve static HTML without protection.
    
    Features:
    - Rotating User-Agent via fake_useragent
    - Full Sec-Fetch-* / Sec-CH-UA headers (Chrome fingerprint)
    - Random jitter delays (2-5s) between requests
    - Incremental saves after each department
    - Proper Referer chain (Google → homepage → group page)
    """
    gites = []
    MAX_PER_RUN = 80
    session = requests.Session()
    
    target_depts = [d for d in GDF_DEPARTMENTS if d[2] == departement] if departement else GDF_DEPARTMENTS
    if not target_depts:
        return []

    # Limit to 3 random departments if not using a specific one to keep it fast
    if not departement and len(target_depts) > 3:
        target_depts = random.sample(target_depts, 3)

    for dept_slug, dept_name, dept_num, page_path in target_depts:
        if len(gites) >= MAX_PER_RUN:
            break
        
        base_url = f"https://www.gites-de-france-{dept_slug}.com"
        group_url = f"{base_url}/{page_path}" if not page_path.startswith('http') else page_path
        
        try:
            logger.info(f"  🔍 Fetching group gîtes: {group_url}")
            page_headers = _get_stealth_headers(base_url + "/")
            page_headers["Sec-Fetch-Site"] = "none"
            
            resp = session.get(group_url, headers=page_headers, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            
            if resp.status_code == 404:
                # Try alternate URL patterns
                alt_urls = [
                    f"{base_url}/liste.html?instance=gites{dept_num}&critinit=o&c_groupe=n",
                    f"{base_url}/gites-de-groupe.html",
                    f"{base_url}/hebergement-groupe.html",
                ]
                for alt_url in alt_urls:
                    resp = session.get(alt_url, headers=page_headers, timeout=REQUEST_TIMEOUT)
                    if resp.status_code == 200:
                        logger.info(f"  ✅ Alternate URL worked: {alt_url}")
                        break
            
            if resp.status_code != 200:
                logger.warning(f"  {dept_name}: group page HTTP {resp.status_code}")
                continue
            
            soup = BeautifulSoup(resp.text, "lxml")
            
            # ── Parse listings from HTML
            # Structure: listing blocks contain links to individual gîte pages
            # with capacity, chambres, name, ville, note, prix
            listing_links = soup.find_all("a", href=re.compile(
                r"(gite-de-sejour|gites-etape-sejour|gite-etape|gite-a-|gite-groupe).*\.html"
            ))
            
            processed_urls = set()
            count_before = len(gites)
            
            for link in listing_links:
                if len(gites) >= MAX_PER_RUN:
                    break
                try:
                    href = link.get("href", "")
                    if not href or href in processed_urls:
                        continue
                    processed_urls.add(href)
                    
                    full_url = f"{base_url}/{href}" if not href.startswith("http") else href
                    
                    # Parse the listing block (content around the link)
                    # Get parent block that contains all listing info
                    parent = link.parent
                    for _ in range(5):
                        if parent and parent.parent:
                            text = parent.get_text(" ", strip=True)
                            if "personnes" in text.lower() or "chambres" in text.lower():
                                break
                            parent = parent.parent
                    
                    block_text = parent.get_text("\n", strip=True) if parent else ""
                    
                    # ── Extract name from link text
                    link_text = link.get_text("\n", strip=True)
                    lines = [l.strip() for l in link_text.split("\n") if l.strip()]
                    
                    # Name is usually in CAPS in the listing
                    nom = ""
                    ville = ""
                    capacite = 0
                    chambres = ""
                    note = None
                    
                    for line in lines:
                        # Capacity: "26 personnes"
                        cap_match = re.search(r"(\d+)\s*personnes?", line, re.IGNORECASE)
                        if cap_match:
                            capacite = int(cap_match.group(1))
                            continue
                        
                        # Chambres: "8 chambres"
                        ch_match = re.search(r"(\d+)\s*chambres?", line, re.IGNORECASE)
                        if ch_match:
                            chambres = f"{ch_match.group(1)} chambres"
                            continue
                        
                        # Note: "Superbe 5/5" or "Très bien 4.5/5"
                        note_match = re.search(r"(\d+\.?\d*)\s*/\s*5", line)
                        if note_match:
                            note = float(note_match.group(1))
                            continue
                        
                        # Location: "à Ville-NomDépartement"
                        loc_match = re.match(r"à\s+(.+?)(?:Drôme|Ardèche|Calvados|Morbihan|Finistère|Hérault|Vendée|Dordogne|Lozère|Deux-Sèvres|$)", line)
                        if loc_match:
                            ville = loc_match.group(1).strip()
                            continue
                        
                        # Name: usually the longest ALL-CAPS or title-case line
                        if len(line) > 3 and not line.startswith("A partir") and not line.startswith("Promotion"):
                            if not nom or (line.isupper() and len(line) > len(nom)):
                                nom = line
                    
                    # Fallback name extraction if nothing worked
                    if not nom:
                        for line in lines:
                            if len(line) > 5 and not re.search(r"\d+\s*(personnes|chambres|avis|€)", line, re.IGNORECASE):
                                nom = line
                                break
                    
                    if not nom or len(nom) < 3 or nom.lower().startswith("ajouter"):
                        continue
                    
                    # Clean name (remove leading/trailing junk)
                    nom = nom.strip().title() if nom.isupper() else nom.strip()
                    
                    if capacite > 0 and capacite < capacite_min:
                        continue
                    
                    # ── Extract price from block text
                    prix = None
                    prix_match = re.search(r"(\d[\d\s]*)€\s*/\s*sem", block_text)
                    if prix_match:
                        prix = int(prix_match.group(1).replace(" ", ""))
                    else:
                        prix_match2 = re.search(r"A partir de\s*(\d[\d\s]*)€", block_text)
                        if prix_match2:
                            prix = int(prix_match2.group(1).replace(" ", ""))
                    
                    # ── Extract photo URL (carousel first image)
                    img = None
                    # Look for img in the listing block
                    listing_container = link
                    for _ in range(8):
                        if listing_container and listing_container.parent:
                            listing_container = listing_container.parent
                            found_img = listing_container.find("img", src=True)
                            if found_img and "logo" not in (found_img.get("src", "") + found_img.get("alt", "")).lower():
                                img = found_img
                                break
                    
                    photo = ""
                    if img:
                        photo = img.get("src") or img.get("data-lazy") or img.get("data-src", "")
                        if photo and not photo.startswith("http"):
                            photo = f"{base_url}{photo}"
                    
                    # ── Equipments from block text
                    equipements = []
                    if "tout inclus" in block_text.lower():
                        equipements.append("Tout inclus")
                    if "piscine" in block_text.lower():
                        equipements.append("Piscine")
                    if chambres:
                        equipements.append(chambres)
                    
                    localisation = f"{ville} — {dept_name} ({dept_num})" if ville else f"{dept_name} ({dept_num})"
                    
                    gite = {
                        "nom": nom,
                        "url": full_url,
                        "capacite": capacite or capacite_min,
                        "prix_semaine": prix,
                        "localisation": localisation,
                        "departement": dept_num,
                        "description": "",
                        "equipements": equipements,
                        "photo": photo,
                        "note": note,
                        "animaux": detect_animaux(block_text),
                        "source": "gitesdefrance",
                    }
                    gites.append(gite)
                    
                except Exception as e:
                    logger.warning(f"  GdF parse error: {e}")
                    continue
            
            new_count = len(gites) - count_before
            logger.info(f"  ✅ {dept_name}: {new_count} gîtes extracted")
            
            # ── Incremental save after each department
            if gites:
                _save_gdf_incremental(gites)
            
            # ── Jitter before next department
            if dept_slug != GDF_DEPARTMENTS[-1][0]:
                jitter = random.uniform(2.0, 5.0)
                time.sleep(jitter)
                
        except requests.RequestException as e:
            logger.warning(f"  ⚠️ Network error for {dept_name}: {e}")
        except Exception as e:
            logger.error(f"  ❌ Unexpected error for {dept_name}: {e}")
    
    logger.info(f"✅ Gîtes de France (Stealth): {len(gites)} real listings from {len(GDF_DEPARTMENTS)} departments")
    return gites


# ─── SCRAPER 5: Abritel.fr (Playwright) ──────────────────────────────────
def scrape_abritel_sync(capacite_min: int = 10) -> list[dict]:
    """Scrape Abritel.fr (VRBO France) using Playwright."""
    gites = []
    try:
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            url = f"https://www.abritel.fr/search?adults={capacite_min}&destination=France&regionId=170&sort=RECOMMENDED"
            logger.info(f"Scraping Abritel: {url}")
            
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(5000)
            
            html = page.content()
            browser.close()
        
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select("[class*='listing'], [class*='property'], [class*='card'], article, [data-stid]")
        
        processed = set()
        for card in cards[:50]:
            try:
                link = card.find("a", href=True)
                if not link:
                    continue
                href = link.get("href", "")
                if href in processed or not href:
                    continue
                processed.add(href)
                
                full_url = f"https://www.abritel.fr{href}" if not href.startswith("http") else href
                
                name_el = card.find(["h2", "h3", "h4"])
                nom = name_el.get_text(strip=True) if name_el else ""
                if not nom or len(nom) < 3:
                    continue
                
                img = card.find("img")
                photo = img.get("src", "") if img else ""
                
                price_el = card.find(class_=re.compile(r"price|prix"))
                prix = extract_number(price_el.get_text() if price_el else "")
                
                card_text = card.get_text()
                
                gite = {
                    "nom": nom,
                    "url": full_url,
                    "capacite": capacite_min,
                    "prix_semaine": prix,
                    "localisation": "France",
                    "departement": "",
                    "description": card_text[:200].strip(),
                    "equipements": [],
                    "photo": photo,
                    "note": None,
                    "animaux": detect_animaux(card_text),
                    "source": "abritel",
                }
                gites.append(gite)
                
            except Exception as e:
                logger.warning(f"Abritel card error: {e}")
        
        logger.info(f"✅ Abritel: {len(gites)} listings scraped")
        
    except Exception as e:
        logger.error(f"❌ Abritel error: {e}")
    
    return gites


# ─── SCRAPER 6: Clévacances.com (Playwright) ─────────────────────────────
def scrape_clevacances_sync(capacite_min: int = 10) -> list[dict]:
    """Scrape Clévacances using Playwright."""
    gites = []
    try:
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            url = f"https://www.clevacances.com/fr/location-vacances-gite?nb_voyageurs={capacite_min}"
            logger.info(f"Scraping Clévacances: {url}")
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            
            html = page.content()
            browser.close()
        
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select("[class*='card'], [class*='listing'], article, [class*='result']")
        
        processed = set()
        for card in cards[:50]:
            try:
                link = card.find("a", href=True)
                if not link:
                    continue
                href = link.get("href", "")
                if href in processed or not href:
                    continue
                processed.add(href)
                
                full_url = f"https://www.clevacances.com{href}" if not href.startswith("http") else href
                
                name_el = card.find(["h2", "h3", "h4"])
                nom = name_el.get_text(strip=True) if name_el else ""
                if not nom or len(nom) < 3:
                    continue
                
                img = card.find("img")
                photo = img.get("src", "") if img else ""
                if photo and not photo.startswith("http"):
                    photo = f"https://www.clevacances.com{photo}"
                
                card_text = card.get_text()
                
                gite = {
                    "nom": nom,
                    "url": full_url,
                    "capacite": capacite_min,
                    "prix_semaine": None,
                    "localisation": "France",
                    "departement": "",
                    "description": card_text[:200].strip(),
                    "equipements": [],
                    "photo": photo,
                    "note": None,
                    "animaux": detect_animaux(card_text),
                    "source": "clevacances",
                }
                gites.append(gite)
                
            except Exception as e:
                logger.warning(f"Clévacances card error: {e}")
        
        logger.info(f"✅ Clévacances: {len(gites)} listings scraped")
        
    except Exception as e:
        logger.error(f"❌ Clévacances error: {e}")
    
    return gites


# ─── SCRAPER 7: Giga-Location.com (requests) ─────────────────────────────
def scrape_gigalocation(capacite_min: int = 10) -> list[dict]:
    """Scrape Giga-Location.com using POST request and extracting from specific containers."""
    gites = []
    try:
        url = "https://www.giga-location.com/gite-de-groupe/"
        logger.info(f"Scraping Giga-Location via POST: {url} with capacite_min={capacite_min}")
        
        # Giga-location uses a POST request with 'send=1' and 'nb_pers_min'
        data = {
            'send': '1',
            'nb_pers_min': str(capacite_min)
        }
        
        # Increase timeout slightly and allow redirects as it typically redirects to the search results page
        response = requests.post(url, data=data, headers=HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "lxml")
        
        # Listings are contained inside divs with class 'lacase'
        boxes = soup.find_all("div", class_="lacase")
        
        if not boxes:
            logger.warning("Giga-Location: Found NO 'lacase' boxes despite successful request.")
        
        processed = set()
        for box in boxes[:50]:
            try:
                # Get the link
                link_el = box.find("a", href=True)
                if not link_el:
                    continue
                href = link_el.get("href", "")
                if href in processed or not href:
                    continue
                processed.add(href)
                
                full_url = f"https://www.giga-location.com{href}" if not href.startswith("http") else href
                
                # Get name
                nom = "Gîte Giga-Location"
                title_el = box.find("div", class_="titre")
                if title_el:
                    nom = title_el.get_text(separator=' ', strip=True)
                
                if len(nom) < 3:
                    continue
                
                # Get photo
                img = box.find("img")
                photo = ""
                if img:
                    photo = img.get("data-src") or img.get("src", "")
                    if photo and not photo.startswith("http"):
                        photo = f"https://www.giga-location.com{photo}"
                
                # Parse text for capacity/price if possible
                box_text = box.get_text(" ", strip=True)
                capacite = capacite_min
                cap_match = re.search(r'(\d+)\s*personnes', box_text, re.I)
                if cap_match:
                    capacite = int(cap_match.group(1))
                
                gite = {
                    "nom": nom,
                    "url": full_url,
                    "capacite": capacite,
                    "prix_semaine": None, # Price usually requires looking into the ad details
                    "localisation": "France",
                    "departement": "",
                    "description": "",
                    "equipements": [],
                    "photo": photo,
                    "note": None,
                    "animaux": detect_animaux(box_text),
                    "source": "gigalocation",
                }
                gites.append(gite)
                
            except Exception as e:
                logger.warning(f"Giga-Location parse error for single box: {e}")
                continue
        
        logger.info(f"✅ Giga-Location: {len(gites)} listings scraped")
        
    except Exception as e:
        logger.error(f"❌ Giga-Location scraping error: {e}")
    
    return gites


# ─── SCRAPER 8: GitesXXL.fr (requests — department pages) ────────────────
def scrape_gitesxxl(capacite_min: int = 10, departement: Optional[str] = None) -> list[dict]:
    """
    Scrape GitesXXL.fr department pages for real gîte listings.
    Real HTML structure: .card elements with h3 (capacity), h4 (name), address text.
    Premium ads have photos in section#ads with Splide carousels.
    """
    gites = []
    MAX_PER_RUN = 60
    
    if departement and departement in XXL_DEPARTMENTS:
        departments = [(XXL_DEPARTMENTS[departement], XXL_DEPARTMENTS[departement].split("-")[0], departement)]
    elif departement:
        return []
    else:
        # Scrape several popular departments
        departments = [
            ("ardeche-07", "Ardèche", "07"),
            ("Dordogne-24", "Dordogne", "24"),
            ("Morbihan-56", "Morbihan", "56"),
            ("Calvados-14", "Calvados", "14"),
            ("Herault-34", "Hérault", "34"),
            ("Lozere-48", "Lozère", "48"),
            ("Cotes-d-Armor-22", "Côtes-d'Armor", "22"),
            ("Vendee-85", "Vendée", "85"),
        ]
    
    for dept_slug, dept_name, dept_num in departments:
        if len(gites) >= MAX_PER_RUN:
            break
        try:
            url = f"https://www.gitesxxl.fr/grand-gite-groupe-{dept_slug}/"
            logger.info(f"Scraping GitesXXL: {dept_name} — {url}")
            
            response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if response.status_code != 200:
                logger.warning(f"  GitesXXL {dept_name}: HTTP {response.status_code}")
                continue
            
            soup = BeautifulSoup(response.text, "lxml")
            
            # ── Method 1: Parse .card elements (simple listings)
            cards = soup.select(".card")
            for card in cards:
                if len(gites) >= MAX_PER_RUN:
                    break
                try:
                    # Capacity is in h3 (just a number)
                    h3 = card.find("h3")
                    if not h3 or not h3.get_text(strip=True).isdigit():
                        continue
                    capacite = int(h3.get_text(strip=True))
                    
                    if capacite < capacite_min:
                        continue
                    
                    # Name is in h4
                    h4 = card.find("h4")
                    nom = h4.get_text(strip=True) if h4 else ""
                    if not nom or len(nom) < 3:
                        continue
                    
                    # Get full text for address and description
                    card_text = card.get_text("\n", strip=True)
                    lines = [l.strip() for l in card_text.split("\n") if l.strip()]
                    
                    # Address is usually the line with a postal code (5 digits)
                    adresse = ""
                    for line in lines:
                        if re.search(r"\d{5}", line):
                            adresse = line
                            break
                    
                    # Description: lines after address that aren't capacity/name
                    desc_lines = []
                    for line in lines:
                        if line == str(capacite) or line == nom or line == adresse:
                            continue
                        if "Créez votre annonce" in line:
                            continue
                        if "Propriétaire de ce grand" in line:
                            continue
                        if len(line) > 10:
                            desc_lines.append(line)
                    description = " ".join(desc_lines[:3])[:300]
                    
                    # Equipment detection
                    equipements = []
                    text_lower = card_text.lower()
                    if "piscine" in text_lower:
                        equipements.append("Piscine")
                    if "salle" in text_lower:
                        equipements.append("Salle de réception")
                    
                    localisation = f"{dept_name} ({dept_num})"
                    if adresse:
                        localisation = f"{adresse} — {dept_name}"
                    
                    gite = {
                        "nom": nom,
                        "url": url,
                        "capacite": capacite,
                        "prix_semaine": None,
                        "localisation": localisation,
                        "departement": dept_num,
                        "description": description,
                        "equipements": equipements,
                        "photo": "",
                        "note": None,
                        "animaux": detect_animaux(text_lower),
                        "source": "gitesxxl",
                    }
                    gites.append(gite)
                    
                except Exception as e:
                    logger.warning(f"  GitesXXL card error: {e}")
                    continue
            
            # ── Method 2: Parse premium ads (section#ads with photos)
            ads_section = soup.select_one("section#ads")
            if ads_section:
                ad_blocks = ads_section.select(".col-12.col-lg-8")
                photo_blocks = ads_section.select(".col-12.col-lg-4")
                
                for i, ad in enumerate(ad_blocks):
                    if len(gites) >= MAX_PER_RUN:
                        break
                    try:
                        h2 = ad.find("h2")
                        nom = h2.get_text(strip=True) if h2 else ""
                        if not nom or len(nom) < 3:
                            continue
                        
                        if any(g["nom"].lower() == nom.lower() for g in gites):
                            continue
                        
                        ad_text = ad.get_text("\n", strip=True)
                        
                        prix = None
                        prix_match = re.search(r"(\d+)\s*€\s*/\s*nuit", ad_text)
                        if prix_match:
                            prix = int(prix_match.group(1)) * 7
                        
                        cap_match = re.search(r"(\d+)\s*personne", ad_text)
                        capacite = int(cap_match.group(1)) if cap_match else 15
                        
                        photo = ""
                        if i < len(photo_blocks):
                            img = photo_blocks[i].find("img")
                            if img:
                                src = img.get("src") or img.get("data-splide-lazy", "")
                                if src:
                                    photo = f"https://www.gitesxxl.fr{src}" if not src.startswith("http") else src
                        
                        desc_el = ad.find("p", class_="text-dark")
                        description = desc_el.get_text(strip=True)[:300] if desc_el else ""
                        
                        gite = {
                            "nom": nom,
                            "url": url,
                            "capacite": capacite,
                            "prix_semaine": prix,
                            "localisation": f"{dept_name} ({dept_num})",
                            "departement": dept_num,
                            "description": description,
                            "equipements": [],
                            "photo": photo,
                            "note": None,
                            "animaux": detect_animaux(ad_text.lower()),
                            "source": "gitesxxl",
                        }
                        gites.append(gite)
                        
                    except Exception as e:
                        logger.warning(f"  GitesXXL premium ad error: {e}")
            
        except requests.RequestException as e:
            logger.error(f"Network error scraping GitesXXL ({dept_name}): {e}")
        except Exception as e:
            logger.error(f"Error scraping GitesXXL ({dept_name}): {e}")
    
    logger.info(f"✅ GitesXXL.fr: {len(gites)} real listings scraped")
    return gites


# ─── Deep Scan (Playwright Sites) ──────────────────────────────────────────

def run_deep_scan(capacite_min: int = 10, sources: Optional[list[str]] = None):
    """
    Run scrapers that require Playwright/JS rendering.
    This takes a long time and is intended to be run in a background thread or cron job.
    Results are saved to data/deep_gites.json
    """
    deep_file = os.path.join(DATA_DIR, "deep_gites.json")
    logger.info(f"🚀 Starting deep scan for capacity {capacite_min} (sources: {sources})...")
    
    new_gites = []
    
    # Run TopLoc
    if not sources or "toploc" in sources:
        try:
            new_gites.extend(scrape_toploc_sync(capacite_min))
        except Exception as e:
            logger.error(f"Deep scan error (TopLoc): {e}")

    # Run GreenGo
    if not sources or "greengo" in sources:
        try:
            new_gites.extend(scrape_greengo_sync(capacite_min))
        except Exception as e:
            logger.error(f"Deep scan error (GreenGo): {e}")

    # Run Abritel
    if not sources or "abritel" in sources:
        try:
            new_gites.extend(scrape_abritel_sync(capacite_min))
        except Exception as e:
            logger.error(f"Deep scan error (Abritel): {e}")

    # Run Clévacances
    if not sources or "clevacances" in sources:
        try:
            new_gites.extend(scrape_clevacances_sync(capacite_min))
        except Exception as e:
            logger.error(f"Deep scan error (Clévacances): {e}")

    # Load existing results and merge
    gites = []
    try:
        if os.path.exists(deep_file):
            with open(deep_file, "r", encoding="utf-8") as f:
                existing = json.load(f)
            # Remove existing gites from the sources we just scanned
            scanned_sources = sources if sources else ["toploc", "greengo", "abritel", "clevacances"]
            gites = [g for g in existing if g.get("source") not in scanned_sources]
    except Exception as e:
        logger.error(f"Could not load existing deep_gites: {e}")
        
    gites.extend(new_gites)

    # Save to disk
    try:
        with open(deep_file, "w", encoding="utf-8") as f:
            json.dump(gites, f, ensure_ascii=False, indent=2)
        logger.info(f"✅ Deep scan complete: {len(gites)} gîtes saved to {deep_file}")
    except Exception as e:
        logger.error(f"Failed to save deep scan results: {e}")

    return gites

# ─── Main search function ───────────────────────────────────────────────────

def search_gites(
    capacite_min: int = 10,
    departements: Optional[list[str]] = None,
    budget_max: Optional[int] = None,
    animaux: Optional[bool] = None,
    sources: Optional[list[str]] = None,
) -> list[dict]:
    """
    Main search function. Scrapes REAL listings from all sources.
    Results are cached for 1 hour to avoid hammering servers.
    """
    all_gites = []
    depts_to_scrape = departements if departements else [None]
    
    for dept in depts_to_scrape:
        cached = load_cache(dept)
        if cached:
            all_gites.extend(cached)
            continue
            
        dept_gites = []
        source_status = {}
        
        # 1. GrandsGites (requests)
        if not sources or "grandsgites" in sources:
            try:
                result = scrape_grandsgites(capacite_min, departement=dept)
                dept_gites.extend(result)
                source_status["grandsgites"] = f"✅ {len(result)}"
            except Exception as e:
                source_status["grandsgites"] = f"❌ {e}"
        
        # 2. GitesXXL (requests)
        if not sources or "gitesxxl" in sources:
            try:
                result = scrape_gitesxxl(capacite_min, departement=dept)
                dept_gites.extend(result)
                source_status["gitesxxl"] = f"✅ {len(result)}"
            except Exception as e:
                source_status["gitesxxl"] = f"❌ {e}"
        
        # 3. Gîtes de France
        if not sources or "gitesdefrance" in sources:
            try:
                result = scrape_gitesdefrance_stealth(capacite_min, departement=dept)
                dept_gites.extend(result)
                source_status["gitesdefrance"] = f"✅ {len(result)}"
            except Exception as e:
                source_status["gitesdefrance"] = f"❌ {e}"
        
        # 4. Giga-Location
        if not sources or "gigalocation" in sources:
            try:
                result = scrape_gigalocation(capacite_min)
                dept_gites.extend(result)
                source_status["gigalocation"] = f"✅ {len(result)}"
            except Exception as e:
                source_status["gigalocation"] = f"❌ {e}"
                
        # 5. Load deep scan results if they exist
        deep_file = os.path.join(DATA_DIR, "deep_gites.json")
        if os.path.exists(deep_file):
            try:
                with open(deep_file, "r", encoding="utf-8") as f:
                    deep_results = json.load(f)
                dept_gites.extend(deep_results)
                source_status["deep_scan"] = f"✅ {len(deep_results)} loaded"
            except Exception as e:
                source_status["deep_scan"] = f"❌ {e}"
                
        # Cache results for this dept
        if dept_gites and not sources:
            save_cache(dept_gites, departement=dept)
            
        all_gites.extend(dept_gites)
        
    # Assign unique IDs
    for idx, g in enumerate(all_gites, start=1):
        g["id"] = idx
    
    # Apply filters
    filtered = []
    seen_urls = set()
    for g in all_gites:
        # Deduplicate by url — skip entries with no URL
        url = g.get("url") or ""
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        if sources and g.get("source") and g["source"] not in sources:
            continue
        if int(g.get("capacite") or 0) < capacite_min:
            continue
        if departements and g.get("departement") and g["departement"] not in departements:
            continue
        if budget_max and g.get("prix_semaine") and g["prix_semaine"] > budget_max:
            continue
        if animaux and not g.get("animaux", False):
            continue
        filtered.append(g)
    
    return filtered


if __name__ == "__main__":
    results = search_gites(capacite_min=20)
    print(f"\nFound {len(results)} real gîtes:")
    for g in results[:10]:
        pet = "🐾" if g.get("animaux") else "  "
        src = g.get("source", "?")
        prix = f"{g['prix_semaine']}€" if g.get("prix_semaine") else "N/C"
        print(f"  {pet} [{src}] {g['nom'][:50]} — {prix}")
