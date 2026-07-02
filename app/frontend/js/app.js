// SPA router + shared API client

const features = {
  split: () => import('./split-ui.js'),
  merge: () => import('./merge-ui.js'),
  redact: () => import('./redact-ui.js'),
  convert: () => import('./convert-ui.js'),
  signature: () => import('./signature-ui.js'),
};

let currentFeature = null;

async function navigate(feature) {
  const navItems = document.querySelectorAll('.nav-item');
  navItems.forEach(el => el.classList.toggle('active', el.dataset.feature === feature));

  const container = document.getElementById('app-content');
  container.innerHTML = '';

  try {
    const mod = await features[feature]();
    currentFeature = feature;
    mod.init(container);
  } catch (err) {
    container.innerHTML = `<div class="panel"><p class="text-muted">Failed to load: ${err.message}</p></div>`;
  }
}

// API client
export async function api(path, formData) {
  const res = await fetch(path, { method: 'POST', body: formData });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { const j = await res.json(); msg = j.error || msg; } catch {}
    throw new Error(msg);
  }
  return res;
}

export async function apiJSON(path, formData) {
  const res = await api(path, formData);
  return res.json();
}

export async function apiBlob(path, formData) {
  const res = await api(path, formData);
  return res.blob();
}

// Download helper
export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

// Toast
export function toast(msg, type = 'info', duration = 3500) {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(() => el.remove(), duration);
}

// Upload zone helper: drag-and-drop + click
export function makeUploadZone(zoneEl, inputEl, onFiles) {
  zoneEl.addEventListener('click', () => inputEl.click());
  inputEl.addEventListener('change', () => onFiles(Array.from(inputEl.files)));
  zoneEl.addEventListener('dragover', e => { e.preventDefault(); zoneEl.classList.add('dragover'); });
  zoneEl.addEventListener('dragleave', () => zoneEl.classList.remove('dragover'));
  zoneEl.addEventListener('drop', e => {
    e.preventDefault();
    zoneEl.classList.remove('dragover');
    onFiles(Array.from(e.dataTransfer.files));
  });
}

export function formatBytes(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// Init
document.querySelectorAll('.nav-item').forEach(btn => {
  btn.addEventListener('click', () => navigate(btn.dataset.feature));
});

navigate('split');
