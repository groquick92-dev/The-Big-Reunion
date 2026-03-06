const $ = id => document.getElementById(id);

function showToast(type, msg) {
  const t = $('toast');
  t.className = `toast ${type}`;
  t.textContent = msg;
  t.style.display = 'block';
  setTimeout(() => { t.style.display = 'none'; }, 4000);
}

// Load saved settings on page open
chrome.storage.local.get(['serverUrl', 'apiKey'], items => {
  $('serverUrl').value = items.serverUrl || 'http://localhost:5000';
  $('apiKey').value = items.apiKey || '';
});

function saveSettings() {
  const serverUrl = $('serverUrl').value.trim().replace(/\/$/, '');
  const apiKey = $('apiKey').value.trim();

  if (!serverUrl) {
    showToast('error', 'L\'URL du serveur est obligatoire.');
    return;
  }

  chrome.storage.local.set({ serverUrl, apiKey }, () => {
    showToast('success', '✅ Paramètres enregistrés !');
  });
}

async function testConnection() {
  const serverUrl = $('serverUrl').value.trim().replace(/\/$/, '');
  const apiKey = $('apiKey').value.trim();

  if (!serverUrl) {
    showToast('error', 'Entrez d\'abord l\'URL du serveur.');
    return;
  }

  try {
    const res = await fetch(`${serverUrl}/api/manual-gites`, {
      method: 'GET',
      headers: apiKey ? { 'X-API-Key': apiKey } : {},
    });

    if (res.ok) {
      const json = await res.json();
      showToast('success', `✅ Connexion OK — ${json.count ?? '?'} gîte(s) manuel(s) enregistré(s).`);
    } else {
      showToast('error', `❌ Serveur répond avec le code ${res.status}.`);
    }
  } catch (e) {
    showToast('error', `❌ Impossible de joindre ${serverUrl}. Vérifiez que Flask est démarré.`);
  }
}
