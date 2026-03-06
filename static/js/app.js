/**
 * Cousinade Planner — Frontend Application
 * Interactive SPA for planning a family reunion in France.
 */

const API_BASE = '';

// ─── Source colors & names ──────────────────────────────────────────────────
const SOURCE_INFO = {
  grandsgites: { name: 'GrandsGites', color: '#6366f1' },
  gitesxxl: { name: 'GitesXXL', color: '#ec4899' },
  gigalocation: { name: 'Giga-Location', color: '#3b82f6' },
  gitesdefrance: { name: 'Gîtes de France', color: '#059669' },
  manuel: { name: 'Ajout Manuel', color: '#f59e0b' },
};

// ─── State ──────────────────────────────────────────────────────────────────
let state = {
  gites: [],
  participants: [],
  totals: { total_adultes: 0, total_enfants: 0, total_bebes: 0, total_personnes: 0, nb_foyers: 0 },
  currentTab: 'search',
  simulation: null,
  selectedRegions: new Set(),
  sortBy: '',
  viewMode: 'grid',
  showFavOnly: false,
  mapVisible: true
};

// ─── Map Data & Config ──────────────────────────────────────────────────────
const REGIONS_DEPTS = {
  "Auvergne-Rhône-Alpes": ["01", "03", "07", "15", "26", "38", "42", "43", "63", "69", "73", "74"],
  "Bourgogne-Franche-Comté": ["21", "25", "39", "58", "70", "71", "89", "90"],
  "Bretagne": ["22", "29", "35", "56"],
  "Centre-Val de Loire": ["18", "28", "36", "37", "41", "45"],
  "Corse": ["2A", "2B"],
  "Grand Est": ["08", "10", "51", "52", "54", "55", "57", "67", "68", "88"],
  "Hauts-de-France": ["02", "59", "60", "62", "80"],
  "Île-de-France": ["75", "77", "78", "91", "92", "93", "94", "95"],
  "Normandie": ["14", "27", "50", "61", "76"],
  "Nouvelle-Aquitaine": ["16", "17", "19", "23", "24", "33", "40", "47", "64", "79", "86", "87"],
  "Occitanie": ["09", "11", "12", "30", "31", "32", "34", "46", "48", "65", "66", "81", "82"],
  "Pays de la Loire": ["44", "49", "53", "72", "85"],
  "Provence-Alpes-Côte d'Azur": ["04", "05", "06", "13", "83", "84"]
};

let franceMap = null;
let geoJsonLayer = null;

// ─── Initialization ─────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  loadParticipants();
  showInitialEmptyState();
  setupParticipantForm();
  setupSimulator();
  initMap();
});

// ─── Tab Navigation ─────────────────────────────────────────────────────────
function initTabs() {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const tab = btn.dataset.tab;
      switchTab(tab);
    });
  });
}

function switchTab(tabName) {
  state.currentTab = tabName;

  document.querySelectorAll('.tab-btn, .bottom-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tabName);
  });

  document.querySelectorAll('.tab-panel').forEach(panel => {
    panel.classList.toggle('active', panel.id === `panel-${tabName}`);
  });

  if (tabName === 'participants') {
    loadParticipants();
  } else if (tabName === 'simulator') {
    loadParticipants();
    populateGiteSelect();
  }
}

// ─── Toast Notifications ────────────────────────────────────────────────────
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const icons = { success: '✅', error: '❌', info: 'ℹ️' };
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<span>${icons[type] || ''}</span><span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.animation = 'toastOut 0.3s ease-in forwards';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// ─── API Calls ──────────────────────────────────────────────────────────────
async function apiGet(endpoint) {
  const res = await fetch(`${API_BASE}${endpoint}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function apiPost(endpoint, data) {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return res.json();
}

async function apiDelete(endpoint) {
  const res = await fetch(`${API_BASE}${endpoint}`, { method: 'DELETE' });
  return res.json();
}

// ─── Gîtes Loading ──────────────────────────────────────────────────────────
function showInitialEmptyState() {
  const grid = document.getElementById('gites-grid');
  if (!grid) return;
  const toolbar = document.getElementById('gites-toolbar');
  if (toolbar) toolbar.style.display = 'none';
  grid.innerHTML = `
    <div class="empty-state" style="grid-column: 1 / -1;">
      <div class="empty-state-icon">🗺️</div>
      <div class="empty-state-title">Choisissez une région</div>
      <div class="empty-state-text">Cliquez sur une ou plusieurs régions sur la carte ci-dessus, ou utilisez le bouton <strong>Toute la France</strong>, puis lancez la recherche.</div>
    </div>
  `;
}

function showLoadingSkeleton() {
  const grid = document.getElementById('gites-grid');
  if (!grid) return;
  const toolbar = document.getElementById('gites-toolbar');
  if (toolbar) toolbar.style.display = 'none';
  grid.innerHTML = Array(6).fill(0).map(() => `
    <div class="gite-card skeleton-card">
      <div class="skeleton-img"></div>
      <div class="gite-body" style="padding: 1.25rem;">
        <div class="skeleton-line sk-title"></div>
        <div class="skeleton-line sk-short"></div>
        <div class="skeleton-line sk-medium"></div>
        <div class="skeleton-line sk-short" style="margin-top:0.5rem;"></div>
      </div>
    </div>
  `).join('');
}

function toggleSource(btn) {
  btn.classList.toggle('inactive');
  btn.classList.toggle('active');
  renderGites(); // Client-side filter, no re-fetch needed
}

// ─── Map Logic ──────────────────────────────────────────────────────────────
async function initMap() {
  const mapContainer = document.getElementById('france-map');
  if (!mapContainer || typeof L === 'undefined') return;

  franceMap = L.map('france-map', {
    zoomControl: false,
    attributionControl: false,
    dragging: false,
    scrollWheelZoom: false,
    doubleClickZoom: false,
    boxZoom: false
  }).setView([46.603354, 1.888334], 5.5);

  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; <a href="https://carto.com/">CartoDB</a>',
    subdomains: 'abcd',
    maxZoom: 19
  }).addTo(franceMap);

  try {
    const res = await fetch('./static/regions.geojson');
    const geoData = await res.json();

    geoJsonLayer = L.geoJSON(geoData, {
      style: feature => {
        const isSelected = state.selectedRegions.has(feature.properties.nom);
        return {
          fillColor: isSelected ? '#6366f1' : '#1e293b',
          weight: isSelected ? 2 : 1.5,
          opacity: 1,
          color: isSelected ? '#818cf8' : '#334155',
          fillOpacity: isSelected ? 0.6 : 0.4,
          className: 'region-polygon'
        };
      },
      onEachFeature: (feature, layer) => {
        layer.bindTooltip(feature.properties.nom, { sticky: true, className: 'region-tooltip' });

        layer.on({
          mouseover: e => {
            const l = e.target;
            const isSelected = state.selectedRegions.has(feature.properties.nom);
            l.setStyle({
              fillColor: isSelected ? '#6366f1' : '#4f46e5',
              fillOpacity: isSelected ? 0.8 : 0.5,
              weight: 2,
              color: '#818cf8'
            });
            l.bringToFront();
          },
          mouseout: e => {
            geoJsonLayer.resetStyle(e.target);
          },
          click: e => toggleRegion(feature.properties.nom, e.target)
        });
      }
    }).addTo(franceMap);

    franceMap.fitBounds(geoJsonLayer.getBounds());

  } catch (err) {
    console.error('Erreur chargement carte:', err);
  }
}

function toggleRegion(regionName, layer) {
  if (state.selectedRegions.has(regionName)) {
    state.selectedRegions.delete(regionName);
    if (layer && geoJsonLayer) geoJsonLayer.resetStyle(layer);
  } else {
    state.selectedRegions.add(regionName);
    if (layer) {
      layer.setStyle({
        fillColor: '#6366f1',
        weight: 2,
        color: '#ffffff',
        dashArray: '',
        fillOpacity: 0.8
      });
      layer.bringToFront();
    }
  }

  updateDepartementsInput();
  renderSelectedRegionsChips();
}

function removeRegion(regionName) {
  state.selectedRegions.delete(regionName);

  if (geoJsonLayer) {
    geoJsonLayer.eachLayer(layer => {
      if (layer.feature.properties.nom === regionName) {
        geoJsonLayer.resetStyle(layer);
      }
    });
  }

  updateDepartementsInput();
  renderSelectedRegionsChips();
}

function selectAllRegions() {
  Object.keys(REGIONS_DEPTS).forEach(region => state.selectedRegions.add(region));

  if (geoJsonLayer) {
    geoJsonLayer.eachLayer(layer => {
      layer.setStyle({
        fillColor: '#6366f1',
        weight: 2,
        color: '#ffffff',
        dashArray: '',
        fillOpacity: 0.8
      });
    });
  }

  updateDepartementsInput();
  renderSelectedRegionsChips();
}

function renderSelectedRegionsChips() {
  const container = document.getElementById('selected-regions-chips');
  if (!container) return;

  container.innerHTML = Array.from(state.selectedRegions).map(region => `
    <div class="region-chip">
      ${region}
      <span class="region-chip-remove" onclick="removeRegion('${region.replace(/'/g, "\\'")}')">×</span>
    </div>
  `).join('');
}

function updateDepartementsInput() {
  let allDepts = [];
  state.selectedRegions.forEach(region => {
    if (REGIONS_DEPTS[region]) {
      allDepts = allDepts.concat(REGIONS_DEPTS[region]);
    }
  });

  const input = document.getElementById('filter-departement');
  if (input) {
    input.value = allDepts.length > 0 ? allDepts.join(', ') : '';
  }
}

async function loadGites() {
  const animauxChecked = document.getElementById('filter-animaux')?.checked || false;

  const activeSources = Array.from(document.querySelectorAll('.source-chip.active'))
    .map(btn => btn.dataset.source)
    .filter(Boolean);

  const params = new URLSearchParams({
    capacite_min: document.getElementById('filter-capacite')?.value || '10',
    departement: document.getElementById('filter-departement')?.value || '',
    budget_max: document.getElementById('filter-budget')?.value || '',
    animaux: animauxChecked ? 'true' : '',
  });

  if (activeSources.length > 0) {
    params.append('sources', activeSources.join(','));
  }

  try {
    const data = await apiGet(`/api/gites?${params}`);
    if (data.success) {
      state.gites = data.gites;
      renderGites();
      updateBadges();
    }
  } catch (err) {
    console.error('Failed to load gîtes:', err);
    const grid = document.getElementById('gites-grid');
    if (grid) {
      grid.innerHTML = `
        <div class="empty-state" style="grid-column: 1 / -1;">
          <div class="empty-state-icon">⚠️</div>
          <div class="empty-state-title">Erreur de chargement</div>
          <div class="empty-state-text">Impossible de contacter le serveur. Vérifiez que l'application est bien démarrée.</div>
        </div>
      `;
    }
    showToast('Erreur lors du chargement des gîtes', 'error');
  }
}

function searchGites() {
  if (state.selectedRegions.size === 0) {
    showToast('Veuillez sélectionner au moins une région sur la carte', 'error');
    return;
  }

  const btn = document.getElementById('btn-search');
  btn.classList.add('loading');
  btn.innerHTML = '<span class="spinner"></span> Recherche...';
  btn.disabled = true;

  showLoadingSkeleton();

  const activeSources = Array.from(document.querySelectorAll('.source-chip.active'))
    .map(b => b.dataset.source).filter(Boolean);
  showScrapingProgress(activeSources);

  let srcIdx = 0;
  const srcTimer = setInterval(() => {
    if (srcIdx < activeSources.length) {
      updateScrapingProgress(srcIdx, activeSources);
      srcIdx++;
    } else {
      clearInterval(srcTimer);
    }
  }, 5000);

  loadGites().finally(() => {
    clearInterval(srcTimer);
    hideScrapingProgress(activeSources);
    btn.classList.remove('loading');
    btn.innerHTML = '🔍 Lancer la recherche';
    btn.disabled = false;
    showToast(`${state.gites.length} gîte${state.gites.length !== 1 ? 's' : ''} trouvé${state.gites.length !== 1 ? 's' : ''} !`, 'success');
  });
}

function triggerDeepScan() {
  const btn = document.getElementById('btn-deep-scan');
  btn.innerHTML = '🕰️ Lancement...';
  btn.disabled = true;

  const capacite = document.getElementById('filter-capacite').value || 10;

  const activeSources = Array.from(document.querySelectorAll('.source-chip.active'))
    .map(btn => btn.dataset.source)
    .filter(Boolean);

  apiPost('/api/deep-scan', {
    capacite_min: capacite,
    sources: activeSources
  })
    .then(data => {
      if (data && data.success) {
        showToast(data.message, 'success');
        btn.innerHTML = '✅ Scan Démarré !';
        setTimeout(() => {
          btn.innerHTML = '🕰️ Scan approfondi';
          btn.disabled = false;
        }, 5000);
      } else {
        throw new Error(data ? data.error : 'Erreur réseau');
      }
    })
    .catch(error => {
      showToast('Erreur: ' + error.message, 'error');
      btn.innerHTML = '🕰️ Scan approfondi';
      btn.disabled = false;
    });
}

function clearCache() {
  if (!confirm("Vider le cache ? Les résultats enregistrés seront effacés et la prochaine recherche sera plus longue.")) return;

  apiPost('/api/clear-cache', {})
    .then(data => {
      if (data && data.success) {
        showToast(data.message, 'success');
        state.gites = [];
        renderGites();
        updateBadges();
      } else {
        throw new Error(data ? data.error : 'Erreur réseau');
      }
    })
    .catch(error => {
      showToast('Erreur lors du vidage du cache: ' + error.message, 'error');
    });
}

// ─── Amenity helpers ─────────────────────────────────────────────────────────
function matchesAmenity(gite, ...keywords) {
  const haystack =
    (gite.equipements || []).join(' ').toLowerCase() + ' ' +
    (gite.description || '').toLowerCase() +
    (gite.nom || '').toLowerCase();
  return keywords.some(kw => haystack.includes(kw));
}

// ─── Sort ────────────────────────────────────────────────────────────────────
function applySort() {
  const select = document.getElementById('sort-select');
  state.sortBy = select ? select.value : '';
  renderGites();
}

// ─── Render Gîtes ───────────────────────────────────────────────────────────
function renderGites() {
  const grid = document.getElementById('gites-grid');
  if (!grid) return;

  const favorites = getFavorites();
  grid.className = `gites-grid${state.viewMode === 'list' ? ' gites-list-view' : ''}`;

  // Client-side source filtering
  const activeSources = new Set(
    Array.from(document.querySelectorAll('.source-chip.active'))
      .map(b => b.dataset.source)
      .filter(Boolean)
  );

  let gites = activeSources.size > 0
    ? state.gites.filter(g => !g.source || activeSources.has(g.source))
    : [...state.gites];

  // Client-side amenity filters
  if (document.getElementById('filter-piscine')?.checked)
    gites = gites.filter(g => matchesAmenity(g, 'piscine'));
  if (document.getElementById('filter-salle')?.checked)
    gites = gites.filter(g => matchesAmenity(g, 'salle de réception', 'salle reception', 'salle de fête', 'salle fete'));
  if (document.getElementById('filter-barbecue')?.checked)
    gites = gites.filter(g => matchesAmenity(g, 'barbecue', 'plancha', 'brasero'));
  if (document.getElementById('filter-pmr')?.checked)
    gites = gites.filter(g => matchesAmenity(g, 'handicap', 'pmr', 'accessible', 'mobilité réduite'));
  if (document.getElementById('filter-jardin')?.checked)
    gites = gites.filter(g => matchesAmenity(g, 'jardin', 'terrain', 'parc', 'prairie', 'espace extérieur'));

  // Fav filter
  if (state.showFavOnly) {
    gites = gites.filter(g => favorites.has(String(g.id)));
  }

  // Apply sort
  if (state.sortBy === 'price-asc') {
    gites.sort((a, b) => (a.prix_semaine || Infinity) - (b.prix_semaine || Infinity));
  } else if (state.sortBy === 'price-desc') {
    gites.sort((a, b) => (b.prix_semaine || 0) - (a.prix_semaine || 0));
  } else if (state.sortBy === 'capacity-desc') {
    gites.sort((a, b) => (b.capacite || 0) - (a.capacite || 0));
  } else if (state.sortBy === 'rating-desc') {
    gites.sort((a, b) => (b.note || 0) - (a.note || 0));
  }

  // Toolbar
  const toolbar = document.getElementById('gites-toolbar');
  const toolbarCount = document.getElementById('toolbar-count');
  if (toolbar) toolbar.style.display = state.gites.length > 0 ? 'flex' : 'none';
  if (toolbarCount) {
    const filtered = gites.length < state.gites.length;
    toolbarCount.textContent = filtered
      ? `${gites.length} / ${state.gites.length} gîtes affichés`
      : `${gites.length} gîte${gites.length !== 1 ? 's' : ''} trouvé${gites.length !== 1 ? 's' : ''}`;
  }

  if (!gites.length) {
    grid.innerHTML = `
      <div class="empty-state" style="grid-column: 1 / -1;">
        <div class="empty-state-icon">🏡</div>
        <div class="empty-state-title">${state.gites.length > 0 ? 'Aucun gîte pour ces sources' : 'Aucun gîte trouvé'}</div>
        <div class="empty-state-text">${state.gites.length > 0 ? 'Activez d\'autres sources de données ci-dessus.' : 'Modifiez vos filtres de recherche ou essayez une capacité plus petite.'}</div>
      </div>
    `;
    return;
  }

  grid.innerHTML = gites.map(gite => {
    const src = SOURCE_INFO[gite.source] || { name: 'Autre', color: '#64748b' };
    const isFav = favorites.has(String(gite.id));
    const FALLBACK_IMG = 'https://images.unsplash.com/photo-1600585154340-be6161a56a0c?w=600&h=400&fit=crop';
    let photoUrl = FALLBACK_IMG;
    if (gite.photo) {
      if (gite.photo.startsWith('http')) {
        photoUrl = `/api/proxy-image?url=${encodeURIComponent(gite.photo)}`;
      } else {
        photoUrl = gite.photo;
      }
    }

    // Price per person estimate if participants known
    let pricePerPersonHtml = '';
    if (gite.prix_semaine && state.totals.total_personnes > 0) {
      const ppp = Math.round(gite.prix_semaine / state.totals.total_personnes);
      pricePerPersonHtml = `<div class="gite-ppp">≈ ${ppp}€/pers.</div>`;
    }

    return `
    <div class="gite-card" data-id="${gite.id}">
      <div class="gite-image-wrap">
        <img class="gite-image" src="${photoUrl}"
             alt="${gite.nom}" loading="lazy"
             onerror="this.src='${FALLBACK_IMG}'">
        <div class="gite-capacity-badge">👥 ${gite.capacite} pers.</div>
        ${gite.note ? `<div class="gite-badge">⭐ ${gite.note}</div>` : ''}
        <div class="gite-source-badge" style="background: ${src.color}">${src.name}</div>
        ${gite.animaux ? '<div class="gite-pet-badge">🐾</div>' : ''}
      </div>
      <div class="gite-body">
        <div class="gite-name">${gite.nom}</div>
        <div class="gite-location">📍 ${gite.localisation}</div>
        <div class="gite-description">${gite.description || 'Magnifique gîte de groupe pour votre cousinade.'}</div>
        <div class="gite-tags">
          ${(gite.equipements || []).slice(0, 4).map(eq => `<span class="gite-tag">${eq}</span>`).join('')}
        </div>
        <div class="gite-footer">
          <div class="gite-price-wrap">
            <div class="gite-price">
              ${gite.prix_semaine ? `${gite.prix_semaine.toLocaleString('fr-FR')}€ <small>/semaine</small>` : '<small>Prix sur demande</small>'}
            </div>
            ${pricePerPersonHtml}
          </div>
          <div class="gite-actions">
            <button class="btn-fav-action ${isFav ? 'is-fav' : ''}" onclick="toggleFavorite(${gite.id})" title="${isFav ? 'Retirer des favoris' : 'Ajouter aux favoris'}">${isFav ? '❤️' : '🤍'}</button>
            <button class="btn-gite btn-gite-primary" onclick="selectGiteForSimulation(${gite.id})">
              💰 Simuler
            </button>
            <a class="btn-gite btn-gite-outline" href="${gite.url}" target="_blank" rel="noopener">
              🔗 Voir
            </a>
          </div>
        </div>
      </div>
    </div>
  `;
  }).join('');
}

function selectGiteForSimulation(giteId) {
  switchTab('simulator');
  setTimeout(() => {
    const select = document.getElementById('sim-gite-select');
    if (select) {
      select.value = giteId;
      updateSimPriceFromSelect();
    }
  }, 100);
}

// ─── Participants ───────────────────────────────────────────────────────────
async function loadParticipants() {
  try {
    const data = await apiGet('/api/participants');
    if (data.success) {
      state.participants = data.participants;
      state.totals = data.totals;
      renderParticipants();
      renderTribeSummary();
      updateBadges();
    }
  } catch (err) {
    console.error('Failed to load participants:', err);
  }
}

function setupParticipantForm() {
  const form = document.getElementById('participant-form');
  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const formData = {
        nom_foyer: document.getElementById('input-foyer').value.trim(),
        adultes: parseInt(document.getElementById('input-adultes').value) || 1,
        enfants: parseInt(document.getElementById('input-enfants').value) || 0,
        bebes: parseInt(document.getElementById('input-bebes').value) || 0,
      };

      if (!formData.nom_foyer) {
        showToast('Veuillez saisir le nom du foyer', 'error');
        return;
      }

      try {
        const data = await apiPost('/api/participants', formData);
        if (data.success) {
          showToast(`Famille ${formData.nom_foyer} ajoutée ! 🎉`, 'success');
          form.reset();
          document.getElementById('input-adultes').value = '1';
          document.getElementById('input-enfants').value = '0';
          document.getElementById('input-bebes').value = '0';
          loadParticipants();
        } else {
          showToast(data.error || 'Erreur lors de l\'ajout', 'error');
        }
      } catch (err) {
        showToast('Erreur réseau', 'error');
      }
    });
  }
}

async function deleteParticipant(id, name) {
  if (!confirm(`Supprimer le foyer "${name}" ?`)) return;

  try {
    const data = await apiDelete(`/api/participants/${id}`);
    if (data.success) {
      showToast(`Foyer ${name} supprimé`, 'info');
      loadParticipants();
    }
  } catch (err) {
    showToast('Erreur lors de la suppression', 'error');
  }
}

function renderParticipants() {
  const list = document.getElementById('participants-list');
  if (!list) return;

  if (!state.participants.length) {
    list.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">👨‍👩‍👧‍👦</div>
        <div class="empty-state-title">Aucun foyer inscrit</div>
        <div class="empty-state-text">Ajoutez les foyers de la famille pour commencer à planifier votre cousinade !</div>
      </div>
    `;
    return;
  }

  list.innerHTML = state.participants.map(p => {
    const initials = p.nom_foyer.split(' ').map(w => w[0]).join('').substring(0, 2).toUpperCase();
    const totalFoyer = p.adultes + p.enfants + p.bebes;
    return `
      <div class="participant-item">
        <div class="participant-info">
          <div class="participant-avatar">${initials}</div>
          <div>
            <div class="participant-name">${p.nom_foyer}</div>
            <div class="participant-details">
              <span class="participant-detail">🧑 ${p.adultes} adulte${p.adultes > 1 ? 's' : ''}</span>
              ${p.enfants ? `<span class="participant-detail">👧 ${p.enfants} enfant${p.enfants > 1 ? 's' : ''}</span>` : ''}
              ${p.bebes ? `<span class="participant-detail">👶 ${p.bebes} bébé${p.bebes > 1 ? 's' : ''}</span>` : ''}
              <span class="participant-detail" style="color: var(--primary-light); font-weight: 600;">= ${totalFoyer} pers.</span>
            </div>
          </div>
        </div>
        <button class="btn-delete" onclick='deleteParticipant(${p.id}, ${JSON.stringify(p.nom_foyer).replace(/'/g, "&#39;")})'>🗑</button>
      </div>
    `;
  }).join('');
}

function renderTribeSummary() {
  const container = document.getElementById('tribe-summary');
  if (!container) return;

  const t = state.totals;
  container.innerHTML = `
    <div class="tribe-stat stat-foyers">
      <div class="tribe-stat-icon">🏠</div>
      <div class="tribe-stat-value">${t.nb_foyers}</div>
      <div class="tribe-stat-label">Foyers</div>
    </div>
    <div class="tribe-stat stat-adultes">
      <div class="tribe-stat-icon">🧑</div>
      <div class="tribe-stat-value">${t.total_adultes}</div>
      <div class="tribe-stat-label">Adultes</div>
    </div>
    <div class="tribe-stat stat-enfants">
      <div class="tribe-stat-icon">👧</div>
      <div class="tribe-stat-value">${t.total_enfants}</div>
      <div class="tribe-stat-label">Enfants</div>
    </div>
    <div class="tribe-stat stat-bebes">
      <div class="tribe-stat-icon">👶</div>
      <div class="tribe-stat-value">${t.total_bebes}</div>
      <div class="tribe-stat-label">Bébés</div>
    </div>
    <div class="tribe-stat stat-total">
      <div class="tribe-stat-icon">👨‍👩‍👧‍👦</div>
      <div class="tribe-stat-value">${t.total_personnes}</div>
      <div class="tribe-stat-label">Total</div>
    </div>
  `;
}

function updateBadges() {
  const count = state.totals.total_personnes;
  const countGites = state.gites.length;
  ['badge-participants', 'bottom-badge-participants'].forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.textContent = count; el.style.display = count > 0 ? 'inline-block' : 'none'; }
  });
  ['badge-gites', 'bottom-badge-gites'].forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.textContent = countGites; el.style.display = countGites > 0 ? 'inline-block' : 'none'; }
  });
}

// ─── Cost Simulator ─────────────────────────────────────────────────────────
function setupSimulator() {
  const select = document.getElementById('sim-gite-select');
  if (select) {
    select.addEventListener('change', updateSimPriceFromSelect);
  }
}

function populateGiteSelect() {
  const select = document.getElementById('sim-gite-select');
  if (!select) return;

  const currentVal = select.value;
  select.innerHTML = '<option value="">— Choisir un gîte —</option>';

  state.gites.forEach(g => {
    const opt = document.createElement('option');
    opt.value = g.id;
    opt.textContent = `${g.nom} (${g.capacite} pers.) — ${g.prix_semaine ? g.prix_semaine.toLocaleString('fr-FR') + '€' : 'Prix N/C'}`;
    opt.dataset.prix = g.prix_semaine || 0;
    select.appendChild(opt);
  });

  if (currentVal) select.value = currentVal;
}

function updateSimPriceFromSelect() {
  const select = document.getElementById('sim-gite-select');
  const priceInput = document.getElementById('sim-prix');
  if (select && priceInput) {
    const option = select.options[select.selectedIndex];
    if (option && option.dataset.prix) {
      priceInput.value = option.dataset.prix;
    }
  }
}

async function runSimulation() {
  const prixSemaine = parseFloat(document.getElementById('sim-prix')?.value) || 0;
  const fraisAdulte = parseFloat(document.getElementById('sim-frais-adulte')?.value) || 15;
  const fraisEnfant = parseFloat(document.getElementById('sim-frais-enfant')?.value) || 8;
  const nbJours = parseInt(document.getElementById('sim-jours')?.value) || 7;

  if (prixSemaine <= 0) {
    showToast('Veuillez renseigner le prix du gîte', 'error');
    return;
  }

  try {
    const data = await apiPost('/api/simulation', {
      prix_semaine: prixSemaine,
      frais_adulte: fraisAdulte,
      frais_enfant: fraisEnfant,
      nb_jours: nbJours,
    });

    if (data.success) {
      state.simulation = data;
      renderSimulationResults(data);
      showToast('Simulation calculée ! 🎯', 'success');
    } else {
      showToast(data.error || 'Erreur de simulation', 'error');
    }
  } catch (err) {
    showToast('Erreur réseau lors de la simulation', 'error');
  }
}

function renderSimulationResults(data) {
  const container = document.getElementById('simulation-results');
  if (!container) return;

  const sim = data.simulation;
  const rep = data.repartition;
  const maxCost = Math.max(...rep.map(r => r.cout_total));

  container.innerHTML = `
    <h3 class="sim-results-title">
      📊 Résultats de la simulation
    </h3>

    <div class="sim-summary">
      <div class="sim-summary-card">
        <div class="sim-summary-label">Coût Total Séjour</div>
        <div class="sim-summary-value cost-total">${sim.cout_total.toLocaleString('fr-FR')}€</div>
      </div>
      <div class="sim-summary-card">
        <div class="sim-summary-label">Hébergement</div>
        <div class="sim-summary-value cost-lodging">${sim.prix_gite.toLocaleString('fr-FR')}€</div>
      </div>
      <div class="sim-summary-card">
        <div class="sim-summary-label">Frais de Bouche</div>
        <div class="sim-summary-value cost-food">${sim.total_frais_bouche.toLocaleString('fr-FR')}€</div>
      </div>
    </div>

    <div class="sim-meta glass-card">
      <span>📋 <strong>${sim.totals.nb_foyers}</strong> foyers</span>
      <span>🧑 <strong>${sim.totals.total_adultes}</strong> adultes</span>
      <span>👧 <strong>${sim.totals.total_enfants}</strong> enfants</span>
      <span>👶 <strong>${sim.totals.total_bebes}</strong> bébés</span>
      <span>📅 <strong>${sim.nb_jours}</strong> jours</span>
      <span>🍽️ <strong>${sim.frais_adulte_jour}€</strong>/adulte/j</span>
      <span>🧃 <strong>${sim.frais_enfant_jour}€</strong>/enfant/j</span>
    </div>

    <h4 class="sim-section-title">💸 Répartition par foyer</h4>

    <table class="repartition-table">
      <thead>
        <tr>
          <th>Foyer</th>
          <th>Composition</th>
          <th>Parts</th>
          <th>Hébergement</th>
          <th>Bouche</th>
          <th>Total à payer</th>
        </tr>
      </thead>
      <tbody>
        ${rep.map(r => `
          <tr class="${r.cout_total === maxCost ? 'row-highlight' : ''}">
            <td class="td-foyer">${r.nom_foyer}</td>
            <td>${r.adultes}A${r.enfants ? ` + ${r.enfants}E` : ''}${r.bebes ? ` + ${r.bebes}B` : ''}</td>
            <td>${r.parts}</td>
            <td>${r.cout_hebergement.toLocaleString('fr-FR')}€</td>
            <td>${r.cout_bouche.toLocaleString('fr-FR')}€</td>
            <td class="td-cost">${r.cout_total.toLocaleString('fr-FR')}€</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

// ─── Map Toggle ──────────────────────────────────────────────────────────────
function toggleMap() {
  state.mapVisible = !state.mapVisible;
  const wrapper = document.getElementById('map-wrapper');
  const arrow = document.getElementById('map-toggle-arrow');
  if (wrapper) {
    wrapper.style.transition = 'height 0.4s cubic-bezier(0.4, 0, 0.2, 1), margin-top 0.3s ease';
    wrapper.style.overflow = 'hidden';
    if (state.mapVisible) {
      wrapper.style.setProperty('height', '400px', 'important');
      wrapper.style.marginTop = '1rem';
    } else {
      wrapper.style.setProperty('height', '0px', 'important');
      wrapper.style.marginTop = '0';
    }
  }
  if (arrow) arrow.textContent = state.mapVisible ? '▲' : '▼';
  if (state.mapVisible && franceMap) {
    setTimeout(() => franceMap.invalidateSize(), 450);
  }
}

// ─── Favorites ───────────────────────────────────────────────────────────────
function getFavorites() {
  try { return new Set(JSON.parse(localStorage.getItem('cousinade_favs') || '[]')); }
  catch { return new Set(); }
}

function saveFavorites(set) {
  localStorage.setItem('cousinade_favs', JSON.stringify(Array.from(set)));
}

function toggleFavorite(id) {
  const favs = getFavorites();
  const key = String(id);
  if (favs.has(key)) {
    favs.delete(key);
    showToast('Retiré des favoris', 'info');
  } else {
    favs.add(key);
    showToast('Ajouté aux favoris ❤️', 'success');
  }
  saveFavorites(favs);
  renderGites();
  updateFavFilterBtn();
}

function toggleFavFilter() {
  state.showFavOnly = !state.showFavOnly;
  updateFavFilterBtn();
  renderGites();
}

function updateFavFilterBtn() {
  const btn = document.getElementById('btn-fav-filter');
  if (!btn) return;
  const favCount = getFavorites().size;
  btn.classList.toggle('active', state.showFavOnly);
  btn.textContent = state.showFavOnly
    ? `❤️ Favoris (${favCount})`
    : `🤍 Favoris${favCount > 0 ? ` (${favCount})` : ''}`;
}

// ─── View Mode ───────────────────────────────────────────────────────────────
function setView(mode) {
  state.viewMode = mode;
  document.getElementById('btn-view-grid')?.classList.toggle('active', mode === 'grid');
  document.getElementById('btn-view-list')?.classList.toggle('active', mode === 'list');
  renderGites();
}

// ─── Scraping Progress ───────────────────────────────────────────────────────
const SOURCE_LABELS = {
  grandsgites: 'GrandsGites',
  gitesxxl: 'GitesXXL',
  gigalocation: 'Giga-Location',
  gitesdefrance: 'Gîtes de France'
};

function showScrapingProgress(activeSources) {
  const el = document.getElementById('scraping-progress');
  if (!el || !activeSources.length) return;
  el.style.display = 'block';
  const fill = document.getElementById('scraping-fill');
  if (fill) fill.style.width = '0%';
  const step = document.getElementById('scraping-step');
  if (step) step.textContent = `0 / ${activeSources.length}`;
  const label = document.getElementById('scraping-label');
  if (label) label.textContent = '🔍 Connexion aux sources...';
  const dots = document.getElementById('scraping-dots');
  if (dots) {
    dots.innerHTML = activeSources.map(s =>
      `<span class="scraping-source-dot pending" id="dot-${s}">⏳ ${SOURCE_LABELS[s] || s}</span>`
    ).join('');
  }
}

function updateScrapingProgress(idx, activeSources) {
  const fill = document.getElementById('scraping-fill');
  const label = document.getElementById('scraping-label');
  const step = document.getElementById('scraping-step');
  if (idx > 0) {
    const prev = document.getElementById(`dot-${activeSources[idx - 1]}`);
    if (prev) { prev.className = 'scraping-source-dot done'; prev.textContent = `✅ ${SOURCE_LABELS[activeSources[idx - 1]] || activeSources[idx - 1]}`; }
  }
  const cur = document.getElementById(`dot-${activeSources[idx]}`);
  if (cur) { cur.className = 'scraping-source-dot active'; cur.textContent = `⏳ ${SOURCE_LABELS[activeSources[idx]] || activeSources[idx]}`; }
  const pct = Math.round((idx / activeSources.length) * 80);
  if (fill) fill.style.width = `${pct}%`;
  if (step) step.textContent = `${idx} / ${activeSources.length}`;
  if (label) label.textContent = `🔍 Scraping ${SOURCE_LABELS[activeSources[idx]] || activeSources[idx]}...`;
}

function hideScrapingProgress(activeSources) {
  const fill = document.getElementById('scraping-fill');
  const label = document.getElementById('scraping-label');
  const step = document.getElementById('scraping-step');
  if (fill) fill.style.width = '100%';
  if (step) step.textContent = `${activeSources.length} / ${activeSources.length}`;
  if (label) label.textContent = '✅ Terminé !';
  activeSources.forEach(s => {
    const dot = document.getElementById(`dot-${s}`);
    if (dot) { dot.className = 'scraping-source-dot done'; dot.textContent = `✅ ${SOURCE_LABELS[s] || s}`; }
  });
  setTimeout(() => {
    const el = document.getElementById('scraping-progress');
    if (el) el.style.display = 'none';
  }, 2000);
}

// ─── Expose globals for inline handlers ─────────────────────────────────────
window.renderGites = renderGites;
window.searchGites = searchGites;
window.triggerDeepScan = triggerDeepScan;
window.clearCache = clearCache;
window.toggleSource = toggleSource;
window.deleteParticipant = deleteParticipant;
window.selectGiteForSimulation = selectGiteForSimulation;
window.runSimulation = runSimulation;
window.removeRegion = removeRegion;
window.selectAllRegions = selectAllRegions;
window.applySort = applySort;
window.toggleMap = toggleMap;
window.toggleFavorite = toggleFavorite;
window.toggleFavFilter = toggleFavFilter;
window.setView = setView;
