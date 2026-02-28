/**
 * Cousinade Planner — Frontend Application
 * Interactive SPA for planning a family reunion in France.
 */

const API_BASE = '';

// ─── Source colors & names ──────────────────────────────────────────────────
const SOURCE_INFO = {
  grandsgites: { name: 'GrandsGites', color: '#6366f1' },
  gitesxxl: { name: 'GitesXXL', color: '#ec4899' },
  greengo: { name: 'GreenGo', color: '#10b981' },
  toploc: { name: 'TopLoc', color: '#f59e0b' },
  gigalocation: { name: 'Giga-Location', color: '#3b82f6' },
  abritel: { name: 'Abritel', color: '#ef4444' },
  gitesdefrance: { name: 'Gîtes de France', color: '#059669' },
  clevacances: { name: 'Clévacances', color: '#8b5cf6' },
};

// ─── State ──────────────────────────────────────────────────────────────────
let state = {
  gites: [],
  participants: [],
  totals: { total_adultes: 0, total_enfants: 0, total_bebes: 0, total_personnes: 0, nb_foyers: 0 },
  currentTab: 'search',
  simulation: null,
};

// ─── Initialization ─────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  loadParticipants();
  loadGites();
  setupParticipantForm();
  setupSimulator();
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

  // Update buttons
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tabName);
  });

  // Update panels
  document.querySelectorAll('.tab-panel').forEach(panel => {
    panel.classList.toggle('active', panel.id === `panel-${tabName}`);
  });

  // Refresh data on tab switch
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

// ─── Gîtes Search ───────────────────────────────────────────────────────────
function toggleSource(btn) {
  btn.classList.toggle('inactive');
  btn.classList.toggle('active');
}

async function loadGites() {
  const animauxChecked = document.getElementById('filter-animaux')?.checked || false;

  // Collect active sources
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
    showToast('Erreur lors du chargement des gîtes', 'error');
  }
}

function searchGites() {
  const btn = document.getElementById('btn-search');
  btn.classList.add('loading');
  btn.innerHTML = '<span class="spinner"></span> Recherche...';
  btn.disabled = true; // Disable button during search

  loadGites().finally(() => {
    btn.classList.remove('loading');
    btn.innerHTML = '🔍 Recherche Rapide';
    btn.disabled = false;
    showToast(`${state.gites.length} gîtes trouvés !`, 'success');
  });
}

function triggerDeepScan() {
  const btn = document.getElementById('btn-deep-scan');
  btn.innerHTML = '🕰️ Lancement...';
  btn.disabled = true;

  const capacite = document.getElementById('filter-capacite').value || 10;

  // Collect active sources
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
      showToast('❌ Erreur: ' + error.message, 'error');
      btn.innerHTML = '🕰️ Scan approfondi';
      btn.disabled = false;
    });
}

function clearCache() {
  if (!confirm("Voulez-vous vraiment vider le cache ? Cela effacera tous les résultats enregistrés et le prochain scan sera plus long.")) return;

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
      showToast('❌ Erreur lors du vidage du cache: ' + error.message, 'error');
    });
}

function renderGites() {
  const grid = document.getElementById('gites-grid');
  if (!state.gites.length) {
    grid.innerHTML = `
      <div class="empty-state" style="grid-column: 1 / -1;">
        <div class="empty-state-icon">🏡</div>
        <div class="empty-state-title">Aucun gîte trouvé</div>
        <div class="empty-state-text">Modifiez vos filtres de recherche ou essayez une capacité plus petite.</div>
      </div>
    `;
    return;
  }

  grid.innerHTML = state.gites.map(gite => {
    const src = SOURCE_INFO[gite.source] || { name: 'Autre', color: '#64748b' };
    const FALLBACK_IMG = 'https://images.unsplash.com/photo-1600585154340-be6161a56a0c?w=600&h=400&fit=crop';
    // Proxy external images through our server to bypass hotlink protection
    let photoUrl = FALLBACK_IMG;
    if (gite.photo) {
      if (gite.photo.startsWith('http')) {
        photoUrl = `/api/proxy-image?url=${encodeURIComponent(gite.photo)}`;
      } else {
        photoUrl = gite.photo;
      }
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
          <div class="gite-price">
            ${gite.prix_semaine ? `${gite.prix_semaine.toLocaleString('fr-FR')}€ <small>/semaine</small>` : '<small>Prix sur demande</small>'}
          </div>
          <div class="gite-actions">
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
  const badge = document.getElementById('badge-participants');
  if (badge) {
    badge.textContent = state.totals.total_personnes;
    badge.style.display = state.totals.total_personnes > 0 ? 'inline-block' : 'none';
  }
  const badgeGites = document.getElementById('badge-gites');
  if (badgeGites) {
    badgeGites.textContent = state.gites.length;
    badgeGites.style.display = state.gites.length > 0 ? 'inline-block' : 'none';
  }
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

  container.innerHTML = `
    <h3 style="font-family: 'Outfit', sans-serif; font-size: 1.4rem; margin-bottom: 1.5rem; display: flex; align-items: center; gap: 10px;">
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

    <div class="glass-card" style="margin-bottom: 1rem; padding: 1rem 1.25rem;">
      <div style="display: flex; gap: 2rem; flex-wrap: wrap; font-size: 0.85rem; color: var(--text-secondary);">
        <span>📋 <strong>${sim.totals.nb_foyers}</strong> foyers</span>
        <span>🧑 <strong>${sim.totals.total_adultes}</strong> adultes</span>
        <span>👧 <strong>${sim.totals.total_enfants}</strong> enfants</span>
        <span>👶 <strong>${sim.totals.total_bebes}</strong> bébés</span>
        <span>📅 <strong>${sim.nb_jours}</strong> jours</span>
        <span>🍽️ <strong>${sim.frais_adulte_jour}€</strong>/adulte/jour</span>
        <span>🧃 <strong>${sim.frais_enfant_jour}€</strong>/enfant/jour</span>
      </div>
    </div>

    <h4 style="font-family: 'Outfit', sans-serif; margin: 1.5rem 0 1rem; font-size: 1.1rem;">
      💸 Répartition par foyer
    </h4>

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
          <tr>
            <td class="td-foyer">${r.nom_foyer}</td>
            <td>${r.adultes}A ${r.enfants ? `+ ${r.enfants}E` : ''} ${r.bebes ? `+ ${r.bebes}B` : ''}</td>
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

// ─── Utility ────────────────────────────────────────────────────────────────
// Expose functions for inline handlers
window.searchGites = searchGites;
window.triggerDeepScan = triggerDeepScan;
window.clearCache = clearCache;
window.toggleSource = toggleSource;
window.deleteParticipant = deleteParticipant;
window.selectGiteForSimulation = selectGiteForSimulation;
window.runSimulation = runSimulation;
