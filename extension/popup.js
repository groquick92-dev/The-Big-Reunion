// ─── DOM helpers ────────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);

function setStatus(state, text) {
  const bar = $('status-bar');
  bar.className = `status-bar ${state}`;
  $('status-text').textContent = text;
}

function showToast(type, msg) {
  const t = $('toast');
  t.className = `toast ${type}`;
  t.textContent = msg;
  t.style.display = 'block';
  setTimeout(() => { t.style.display = 'none'; }, 4000);
}

function fillField(id, value) {
  if (value !== null && value !== undefined && value !== '') {
    $(id).value = value;
  }
}

function clearForm() {
  ['f-nom','f-url','f-capacite','f-prix','f-localisation','f-departement','f-photo','f-description']
    .forEach(id => { $(id).value = ''; });
  $('f-animaux').checked = false;
}

// ─── Page parsing (injected into the tab's page context) ─────────────────────
function parsePageData(href) {
  const host = window.location.hostname;

  function firstText(...selectors) {
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && el.innerText.trim()) return el.innerText.trim();
    }
    return '';
  }

  function firstAttr(attr, ...selectors) {
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el && el.getAttribute(attr)) return el.getAttribute(attr).trim();
    }
    return '';
  }

  function extractCapacity(text) {
    const m = text.match(/(\d+)\s*(voyageurs?|personnes?|guests?|pers\.)/i);
    return m ? parseInt(m[1]) : null;
  }

  function extractPrice(text) {
    // Remove currency symbols and spaces, then look for numbers ≥ 100
    const cleaned = text.replace(/[€$£\s\u00a0]/g, '');
    const m = cleaned.match(/(\d[\d\s,\.]*\d)/);
    if (!m) return null;
    return parseInt(m[1].replace(/[,\.]/g, '').replace(/\s/g, ''));
  }

  const bodyText = document.body?.innerText || '';
  const ogImage = document.querySelector('meta[property="og:image"]')?.content || '';
  const ogDesc = document.querySelector('meta[property="og:description"]')?.content || '';

  // ── Airbnb ────────────────────────────────────────────────────────────────
  if (host.includes('airbnb.')) {
    const nom = firstText(
      '[data-testid="listing-title"]',
      'h1._14i3z6h', 'h1._fecoyn', 'h1'
    ) || document.title;

    const capacite = extractCapacity(bodyText);

    // Nightly price → multiply by 7 for weekly estimate
    const priceText = firstText(
      '[data-testid="price-and-discounts-row"] span',
      '._1k4xcdh span', 'span._tyxjp1', '._ati8ih span'
    );
    const nightly = extractPrice(priceText);
    const prix_semaine = nightly && nightly < 5000 ? nightly * 7 : nightly;

    const photo = firstAttr('src',
      '[data-testid="photo-viewer-section"] img',
      'picture img', 'img[src*="muscache.com"]'
    ) || ogImage;

    const localisation = firstText(
      '[data-testid="listing-location"]', '._j5rmbs', '._1q2lt1'
    );

    return { nom, capacite, prix_semaine, photo, localisation, description: ogDesc, url: href };
  }

  // ── Abritel / VRBO ───────────────────────────────────────────────────────
  if (host.includes('abritel.') || host.includes('vrbo.')) {
    const nom = firstText(
      'h1.uitk-heading', 'h1[class*="heading"]', 'h1'
    ) || document.title;

    const capacite = extractCapacity(bodyText);

    const priceText = firstText(
      '[class*="price-lockup"] strong', '.uitk-price-lockup strong',
      '[data-stid*="price"]', '[class*="price"] strong'
    );
    const prix_semaine = extractPrice(priceText);

    const photo = firstAttr('src',
      '[class*="gallery"] img', '[class*="hero"] img', 'img[class*="photo"]'
    ) || ogImage;

    const localisation = firstText(
      '[data-stid="content-hotel-subname"]', '[class*="location"]', '._1mCbFK'
    );

    return { nom, capacite, prix_semaine, photo, localisation, description: ogDesc, url: href };
  }

  // ── Generic fallback ─────────────────────────────────────────────────────
  const nom = firstText('h1') || document.title;
  const capacite = extractCapacity(bodyText);
  const photo = firstAttr('src', 'img[class*="main"]', 'img[class*="hero"]') || ogImage;
  const localisation = '';
  let prix_semaine = null;

  // Try to find a price-ish number on the page
  const priceMatch = bodyText.match(/(\d[\s\d]{2,6})\s*€\s*(?:\/\s*semaine)?/i);
  if (priceMatch) prix_semaine = parseInt(priceMatch[1].replace(/\s/g, ''));

  return { nom, capacite, prix_semaine, photo, localisation, description: ogDesc, url: href };
}

// ─── Main ────────────────────────────────────────────────────────────────────
let settings = { serverUrl: 'http://localhost:5000', apiKey: '' };

async function loadSettings() {
  return new Promise(resolve => {
    chrome.storage.local.get(['serverUrl', 'apiKey'], items => {
      if (items.serverUrl) settings.serverUrl = items.serverUrl;
      if (items.apiKey) settings.apiKey = items.apiKey;
      resolve();
    });
  });
}

async function injectAndParse(tab) {
  // Inject the parsing function into the page and retrieve results
  const results = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: parsePageData,
    args: [tab.url],
    world: 'MAIN',
  });
  return results?.[0]?.result || null;
}

async function init() {
  await loadSettings();

  // Show server URL hint
  const hint = settings.serverUrl.replace(/https?:\/\//, '');
  $('server-url-hint').textContent = hint;

  // Warn if API key not configured
  if (!settings.apiKey) {
    setStatus('error', '⚠️ Clé API non configurée — ouvrez les paramètres');
    $('btn-submit').disabled = true;
    return;
  }

  // Get current tab
  let tab;
  try {
    [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  } catch (e) {
    setStatus('error', 'Impossible de lire l\'onglet actif');
    return;
  }

  // Pre-fill URL
  fillField('f-url', tab.url);

  // Try to parse the page
  try {
    setStatus('loading', 'Analyse de la page en cours…');
    const data = await injectAndParse(tab);

    if (data) {
      fillField('f-nom', data.nom);
      fillField('f-url', data.url || tab.url);
      fillField('f-capacite', data.capacite);
      fillField('f-prix', data.prix_semaine);
      fillField('f-localisation', data.localisation);
      fillField('f-photo', data.photo);
      fillField('f-description', data.description);
      setStatus('ok', 'Page analysée — vérifiez et complétez les champs');
    } else {
      setStatus('ok', 'Page lue — remplissez les champs manuellement');
    }
  } catch (e) {
    // May fail on chrome:// or extension pages
    setStatus('ok', 'Remplissez les champs manuellement');
  }
}

async function submitGite() {
  const nom = $('f-nom').value.trim();
  if (!nom) {
    showToast('error', 'Le nom du gîte est obligatoire.');
    $('f-nom').focus();
    return;
  }

  const btn = $('btn-submit');
  btn.disabled = true;
  btn.textContent = '⏳ Envoi…';

  const payload = {
    nom,
    url: $('f-url').value.trim(),
    capacite: parseInt($('f-capacite').value) || 0,
    prix_semaine: parseFloat($('f-prix').value) || null,
    localisation: $('f-localisation').value.trim(),
    departement: $('f-departement').value.trim(),
    photo: $('f-photo').value.trim(),
    description: $('f-description').value.trim(),
    animaux: $('f-animaux').checked,
    source: 'manuel',
  };

  try {
    const res = await fetch(`${settings.serverUrl}/api/manual-gites`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': settings.apiKey,
      },
      body: JSON.stringify(payload),
    });

    const json = await res.json();

    if (res.ok && json.success) {
      showToast('success', `✅ "${nom}" ajouté au tableau de bord !`);
      clearForm();
      setStatus('ok', 'Gîte ajouté avec succès');
    } else if (res.status === 401) {
      showToast('error', '❌ Clé API invalide. Vérifiez les paramètres.');
    } else {
      showToast('error', `❌ Erreur : ${json.error || res.statusText}`);
    }
  } catch (e) {
    showToast('error', `❌ Impossible de joindre le serveur (${settings.serverUrl}). Est-il démarré ?`);
  } finally {
    btn.disabled = false;
    btn.textContent = '➕ Ajouter au tableau de bord';
  }
}

// Start
init();
