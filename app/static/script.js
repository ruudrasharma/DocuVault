/* ============================================================
   DOCUVault — Enhanced Frontend Engine
   Sentinel UI · Premium Interactions
   ============================================================ */

'use strict';

// ── State ───────────────────────────────────────────────────
const state = {
  currentRole: '',
  activePanel: 'upload',
  activeVerifyMode: 'digital',
  isLoading: false,
  uploadedFiles: [],
};

// ── SVG Icons ───────────────────────────────────────────────
const Icons = {
  shieldCheck:  `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>`,
  shieldAlert:  `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
  fileCheck:    `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="15" x2="15" y2="15"/><polyline points="9 12 11 14 15 10"/></svg>`,
  fileX:        `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="15" x2="15" y2="9"/><line x1="15" y1="15" x2="9" y2="9"/></svg>`,
  alertTriangle:`<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
  clock:        `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
  upload:       `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/><path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/></svg>`,
  copy:         `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`,
  check:        `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`,
  link:         `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>`,
  users:        `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>`,
  fingerprint:  `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12C2 6.5 6.5 2 12 2a10 10 0 0 1 8 4"/><path d="M5 19.5C5.5 18 6 15 6 12c0-.7.12-1.37.34-2"/><path d="M17.29 21.02c.12-.6.43-2.3.5-3.02"/><path d="M12 10a2 2 0 0 0-2 2c0 1.02-.1 2.51-.26 4"/><path d="M8.65 22c.21-.66.45-1.32.57-2"/><path d="M14 13.12c0 2.38 0 6.38-1 8.88"/><path d="M2 16h.01"/><path d="M21.8 16c.2-2 .131-5.354 0-6"/><path d="M9 6.8a6 6 0 0 1 9 5.2c0 .47 0 1.17-.02 2"/></svg>`,
  search:       `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>`,
  command:      `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 3a3 3 0 0 0-3 3v12a3 3 0 0 0 3 3 3 3 0 0 0 3-3 3 3 0 0 0-3-3H6a3 3 0 0 0-3 3 3 3 0 0 0 3 3 3 3 0 0 0 3-3V6a3 3 0 0 0-3-3 3 3 0 0 0-3 3 3 3 0 0 0 3 3h12a3 3 0 0 0 3-3 3 3 0 0 0-3-3z"/></svg>`,
  x:            `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
  info:         `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
  plus:         `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>`,
  key:          `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>`,
  logout:       `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>`,
  grid:         `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>`,
  doc:          `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>`,
  settings:     `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`,
};

// ── Toast System ────────────────────────────────────────────
const Toast = {
  container: null,

  init() {
    this.container = document.getElementById('toast-container');
    if (!this.container) {
      this.container = document.createElement('div');
      this.container.id = 'toast-container';
      document.body.appendChild(this.container);
    }
  },

  show(message, type = 'info', duration = 3500) {
    const iconMap = {
      success: Icons.shieldCheck,
      error:   Icons.shieldAlert,
      warning: Icons.alertTriangle,
      info:    Icons.info,
    };

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.style.position = 'relative';
    toast.innerHTML = `
      <span class="toast-icon">${iconMap[type] || iconMap.info}</span>
      <span style="flex:1;font-size:13px">${message}</span>
      <button onclick="this.closest('.toast').remove()" style="background:none;border:none;cursor:pointer;color:var(--text-muted);display:flex;align-items:center;padding:0">${Icons.x}</button>
      <div class="toast-bar"></div>
    `;

    this.container.appendChild(toast);

    setTimeout(() => {
      toast.classList.add('removing');
      setTimeout(() => toast.remove(), 300);
    }, duration);
  },

  success: (msg) => Toast.show(msg, 'success'),
  error:   (msg) => Toast.show(msg, 'error'),
  warning: (msg) => Toast.show(msg, 'warning'),
  info:    (msg) => Toast.show(msg, 'info'),
};

// ── Command Palette ─────────────────────────────────────────
const CommandPalette = {
  overlay: null,
  input: null,
  items: [],
  focusedIndex: -1,

  commands: [
    { label: 'Upload Document',       meta: 'Institution',      icon: Icons.upload,      action: () => switchPanel('upload'),        role: ['institution','admin'] },
    { label: 'Verify Document',       meta: 'Blockchain check', icon: Icons.shieldCheck, action: () => switchPanel('verify'),        role: ['verifier','admin'] },
    { label: 'Admin Panel',           meta: 'User management',  icon: Icons.settings,    action: () => switchPanel('admin'),         role: ['admin'] },
    { label: 'List All Users',        meta: 'Admin action',     icon: Icons.users,       action: () => getUsers(),                   role: ['admin'] },
    { label: 'Recover 2FA Secret',    meta: 'Admin action',     icon: Icons.key,         action: () => recover2FA(),                 role: ['admin'] },
    { label: 'Sign Out',             meta: 'Logout',           icon: Icons.logout,      action: () => logout(),                     role: ['institution','verifier','admin'] },
  ],

  init(overlay) {
    this.overlay = overlay;
    this.input   = overlay.querySelector('.cmd-input');
    this.renderItems(this.commands.filter(c => c.role.includes(state.currentRole)));

    this.input.addEventListener('input', () => this.filter());
    this.input.addEventListener('keydown', (e) => this.handleKey(e));
    overlay.addEventListener('click', (e) => { if (e.target === overlay) this.close(); });
  },

  open() {
    this.overlay.classList.add('open');
    this.input.focus();
    this.input.value = '';
    this.filter();
    this.focusedIndex = -1;
  },

  close() {
    this.overlay.classList.remove('open');
    this.input.value = '';
  },

  filter() {
    const q = this.input.value.toLowerCase();
    const filtered = this.commands
      .filter(c => c.role.includes(state.currentRole))
      .filter(c => !q || c.label.toLowerCase().includes(q) || c.meta.toLowerCase().includes(q));
    this.renderItems(filtered);
    this.focusedIndex = -1;
  },

  renderItems(commands) {
    const container = this.overlay.querySelector('.cmd-items');
    if (!commands.length) {
      container.innerHTML = `<div style="padding:24px;text-align:center;color:var(--text-muted);font-size:13px">No commands found</div>`;
      return;
    }
    container.innerHTML = commands.map((c, i) => `
      <div class="cmd-item" data-index="${i}" onclick="CommandPalette.execute(${i})">
        <div class="cmd-item-icon">${c.icon}</div>
        <div>
          <div class="cmd-item-label">${c.label}</div>
          <div class="cmd-item-meta">${c.meta}</div>
        </div>
      </div>
    `).join('');
    this.items = commands;
  },

  execute(index) {
    const cmd = this.items[index];
    if (cmd) { this.close(); setTimeout(() => cmd.action(), 100); }
  },

  handleKey(e) {
    const items = this.overlay.querySelectorAll('.cmd-item');
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      this.focusedIndex = Math.min(this.focusedIndex + 1, items.length - 1);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      this.focusedIndex = Math.max(this.focusedIndex - 1, 0);
    } else if (e.key === 'Enter' && this.focusedIndex >= 0) {
      this.execute(this.focusedIndex);
    } else if (e.key === 'Escape') {
      this.close();
    }
    items.forEach((el, i) => el.classList.toggle('focused', i === this.focusedIndex));
    if (this.focusedIndex >= 0) items[this.focusedIndex]?.scrollIntoView({ block: 'nearest' });
  },
};

// ── Drag-and-Drop Upload Zone ───────────────────────────────
function initUploadZone(zoneEl, inputEl, listEl) {
  if (!zoneEl || !inputEl) return;

  const updateList = () => {
    const files = Array.from(inputEl.files);
    state.uploadedFiles = files;
    if (listEl) {
      listEl.innerHTML = files.map(f => `
        <li class="upload-file-chip">
          ${Icons.doc}
          <span>${f.name}</span>
          <span style="color:var(--text-muted)">${(f.size/1024).toFixed(0)}KB</span>
        </li>
      `).join('');
    }
  };

  inputEl.addEventListener('change', updateList);

  ['dragover', 'dragenter'].forEach(evt => {
    zoneEl.addEventListener(evt, (e) => {
      e.preventDefault();
      zoneEl.classList.add('drag-over');
    });
  });

  ['dragleave', 'drop'].forEach(evt => {
    zoneEl.addEventListener(evt, (e) => {
      e.preventDefault();
      zoneEl.classList.remove('drag-over');
    });
  });

  zoneEl.addEventListener('drop', (e) => {
    const dt = e.dataTransfer;
    if (dt.files.length) {
      const container = new DataTransfer();
      Array.from(dt.files).forEach(f => container.items.add(f));
      inputEl.files = container.files;
      updateList();
    }
  });
}

// ── Panel Switching ─────────────────────────────────────────
function switchPanel(panelName) {
  state.activePanel = panelName;
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  const panel = document.getElementById(`panel-${panelName}`);
  const tab   = document.querySelector(`[data-tab="${panelName}"]`);
  const navEl = document.querySelector(`[data-nav="${panelName}"]`);

  if (panel) panel.classList.add('active');
  if (tab)   tab.classList.add('active');
  if (navEl) navEl.classList.add('active');

  const titleMap = {
    upload:  'Upload Document',
    verify:  'Verify Document',
    admin:   'Admin Panel',
  };

  const eyebrowMap = {
    upload:  'Institution Workflow',
    verify:  'Document Intelligence',
    admin:   'System Administration',
  };

  const el = document.getElementById('topbar-title');
  const ey = document.getElementById('topbar-eyebrow');
  if (el) el.textContent = titleMap[panelName] || panelName;
  if (ey) ey.textContent = eyebrowMap[panelName] || '';
}

// ── Verify Mode Selector ────────────────────────────────────
function selectVerifyMode(mode) {
  state.activeVerifyMode = mode;
  document.querySelectorAll('.verify-mode-card').forEach(c => c.classList.remove('selected'));
  const card = document.querySelector(`[data-mode="${mode}"]`);
  if (card) card.classList.add('selected');

  ['digital-form', 'legacy-form', 'manual-form'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
  });

  const formMap = {
    digital: 'digital-form',
    legacy:  'legacy-form',
    manual:  'manual-form',
  };

  const target = document.getElementById(formMap[mode]);
  if (target) target.style.display = 'block';
}

// ── Upload File ─────────────────────────────────────────────
async function uploadFile() {
  const fileInput = document.getElementById('upload-file-input');
  if (!fileInput || !fileInput.files.length) {
    Toast.error('Please select at least one file.');
    return;
  }

  const btn = document.getElementById('upload-btn');
  setButtonLoading(btn, true, 'Uploading…');

  const formData = new FormData();
  Array.from(fileInput.files).forEach(f => formData.append('file', f));

  try {
    const res = await fetch('/upload', { method: 'POST', body: formData });
    const data = await res.json();

    if (data.error) {
      Toast.error(data.error);
      renderResults([{ error: data.error, valid: false, filename: 'N/A' }]);
    } else {
      Toast.success(`${data.results.length} file(s) uploaded successfully.`);
      renderResults(data.results, 'upload');
    }
  } catch (err) {
    Toast.error('Upload failed: ' + err.message);
  } finally {
    setButtonLoading(btn, false, 'Upload & Register');
  }
}

// ── Verify File ─────────────────────────────────────────────
async function verifyFile() {
  const mode = state.activeVerifyMode;
  const formData = new FormData();
  let url = '/verify';
  let validationPassed = true;

  if (mode === 'digital') {
    const files = document.getElementById('verify-file-input')?.files;
    if (!files?.length) { Toast.error('Please select a document to verify.'); return; }
    Array.from(files).forEach(f => formData.append('file', f));

  } else if (mode === 'legacy') {
    const files = document.getElementById('legacy-file-input')?.files;
    if (!files?.length) { Toast.error('Please select a legacy document.'); return; }
    Array.from(files).forEach(f => formData.append('file', f));
    url = '/verify-legacy';

  } else if (mode === 'manual') {
    const fields = ['name','roll','grade','id','institution','uid'];
    const data = {};
    for (const f of fields) {
      const el = document.getElementById(`manual-${f}`);
      data[f] = el?.value?.trim() || '';
    }
    if (!data.name || !data.roll || !data.grade) {
      Toast.error('Please fill Name, Roll Number, and Grade fields.');
      return;
    }
    Object.entries(data).forEach(([k, v]) => formData.append(k, v));
    formData.append('manual', 'true');
    // Route /verify handles manual entries and returns JSON
    url = '/verify';
  }

  const btn = document.getElementById('verify-btn');
  setButtonLoading(btn, true, 'Verifying…');

  try {
    const res = await fetch(url, { method: 'POST', body: formData });
    const data = await res.json();

    if (!data.results?.length) {
      Toast.error(data.error || 'No results returned.');
      return;
    }

    const allValid = data.results.every(r => r.valid);
    if (allValid) Toast.success('All documents verified successfully.');
    else Toast.warning('One or more documents failed verification.');

    renderResults(data.results, 'verify');
  } catch (err) {
    Toast.error('Verification failed: ' + err.message);
  } finally {
    setButtonLoading(btn, false, 'Verify Document');
  }
}

// ── Result Renderer ─────────────────────────────────────────
function renderResults(results, context = 'verify') {
  // Each panel has its own result container to avoid duplicate-ID collisions
  const containerId = context === 'upload' ? 'result-container-upload' : 'result-container-verify';
  const container = document.getElementById(containerId);
  if (!container) return;

  container.innerHTML = '';
  container.style.display = 'flex';

  results.forEach((r, i) => {
    const isValid    = r.valid === true;
    const hasError   = !!r.error;
    const isTampered = r.error?.toLowerCase().includes('tamper') ||
                       r.error?.toLowerCase().includes('anomaly');

    let statusClass = isValid ? 'verified' : (isTampered ? 'tampered' : 'rejected');
    if (context === 'upload' && !hasError) statusClass = 'verified';

    const statusIconMap = {
      verified: Icons.shieldCheck,
      rejected: Icons.fileX,
      tampered: Icons.alertTriangle,
      pending:  Icons.clock,
    };

    const statusLabelMap = {
      verified: 'Document Verified',
      rejected: 'Verification Failed',
      tampered: 'Integrity Check Failed',
      pending:  'Pending',
    };

    const badgeClass = {
      verified: 'badge-verified',
      rejected: 'badge-rejected',
      tampered: 'badge-tampered',
      pending:  'badge-pending',
    }[statusClass];

    const hashValue = r.hash || r.encrypted_hash || 'N/A';
    const truncHash = hashValue !== 'N/A'
      ? hashValue.substring(0, 16) + '…' + hashValue.substring(hashValue.length - 8)
      : 'N/A';

    const card = document.createElement('div');
    card.className = `result-card ${statusClass}`;
    card.style.animationDelay = `${i * 60}ms`;

    const zkpSection = r.zkp ? `
      <div class="result-field">
        <span class="result-field-key">ZKP Proof</span>
        <span class="result-field-val"><span class="badge badge-info">✓ Valid</span></span>
      </div>` : '';

    const encSection = r.encrypted_hash ? `
      <div class="result-field">
        <span class="result-field-key">PQC Encrypted</span>
        <span class="result-field-val"><span class="badge badge-info">✓ Encrypted</span></span>
      </div>` : '';

    const errorSection = r.error ? `
      <div class="result-field">
        <span class="result-field-key">Reason</span>
        <span class="result-field-val" style="color:var(--danger);font-size:12px">${r.error}</span>
      </div>` : '';

    card.innerHTML = `
      <div class="result-card-header">
        <div class="result-card-status-icon">${statusIconMap[statusClass]}</div>
        <div class="result-card-info">
          <div class="result-card-filename">${r.filename || 'document'}</div>
          <div class="result-card-meta">${new Date().toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })}</div>
        </div>
        <span class="badge ${badgeClass}">${statusLabelMap[statusClass]}</span>
      </div>
      <div class="result-card-body">
        ${errorSection}
        ${zkpSection}
        ${encSection}
        ${hashValue !== 'N/A' ? `
        <div>
          <div class="text-label" style="margin-bottom:6px">SHA-256 Hash</div>
          <div class="result-hash">
            <span style="flex:1">${hashValue}</span>
            <button onclick="copyToClipboard('${hashValue}', this)" class="btn btn-ghost btn-sm btn-icon" title="Copy hash" style="padding:4px;border-radius:6px">
              ${Icons.copy}
            </button>
          </div>
        </div>` : ''}
        ${context === 'upload' && !r.error ? `
        <div class="chain-badge" style="align-self:flex-start">
          <div class="chain-badge-dot"></div>
          Registered on Blockchain
        </div>` : ''}
      </div>
    `;

    container.appendChild(card);
  });
}

// ── Admin: Get Users ────────────────────────────────────────
async function getUsers() {
  const resultEl = document.getElementById('admin-result');
  if (resultEl) {
    resultEl.innerHTML = `
      <div class="skeleton" style="height:20px;margin-bottom:8px"></div>
      <div class="skeleton" style="height:20px;margin-bottom:8px;width:80%"></div>
      <div class="skeleton" style="height:20px;width:60%"></div>
    `;
  }

  try {
    const res  = await fetch('/admin/users');
    const users = await res.json();

    if (!resultEl) return;
    if (!users.length) {
      resultEl.innerHTML = `<p style="color:var(--text-muted);font-size:14px;padding:16px 0">No users found.</p>`;
      return;
    }

    resultEl.innerHTML = `
      <div class="card" style="overflow:hidden">
        <table class="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Username</th>
              <th>Role</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            ${users.map(u => `
              <tr>
                <td><span class="text-mono" style="color:var(--text-muted)">#${u.id}</span></td>
                <td><span style="font-weight:600">${u.username}</span></td>
                <td>
                  <span class="badge ${roleBadge(u.role)}">${u.role}</span>
                </td>
                <td><span class="badge badge-verified">Active</span></td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;
    Toast.success(`${users.length} user(s) loaded.`);
  } catch (err) {
    Toast.error('Failed to load users: ' + err.message);
  }
}

function roleBadge(role) {
  const map = { admin: 'badge-rejected', institution: 'badge-info', verifier: 'badge-verified' };
  return map[role] || 'badge-neutral';
}

// ── Admin: Recover 2FA ──────────────────────────────────────
async function recover2FA() {
  const userId = prompt('Enter the User ID to recover 2FA:');
  if (!userId?.trim()) return;

  try {
    const res  = await fetch('/admin/recover_2fa', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: parseInt(userId) }),
    });
    const data = await res.json();

    if (data.error) { Toast.error(data.error); return; }

    const resultEl = document.getElementById('admin-result');
    if (resultEl) {
      resultEl.innerHTML = `
        <div class="card" style="max-width:480px">
          <div class="card-header">
            <span style="color:var(--success)">${Icons.key}</span>
            <div>
              <div style="font-size:14px;font-weight:700">New 2FA Secret Generated</div>
              <div style="font-size:12px;color:var(--text-muted)">User ID: ${userId}</div>
            </div>
          </div>
          <div class="card-body">
            <div class="text-label" style="margin-bottom:6px">TOTP Secret</div>
            <div class="result-hash">
              <span style="flex:1;letter-spacing:0.1em">${data.new_secret}</span>
              <button onclick="copyToClipboard('${data.new_secret}', this)" class="btn btn-ghost btn-sm btn-icon">
                ${Icons.copy}
              </button>
            </div>
            <p style="margin-top:12px;font-size:12px;color:var(--text-muted)">
              Share this secret securely with the user to set up their authenticator app.
            </p>
          </div>
        </div>
      `;
    }
    Toast.success('2FA secret generated successfully.');
  } catch (err) {
    Toast.error('2FA recovery failed: ' + err.message);
  }
}

// ── Admin: Add Legacy Record ────────────────────────────────
async function addLegacyRecord() {
  const fields = ['name', 'roll', 'grade', 'id', 'institution', 'uid'];
  const data = {};
  for (const f of fields) {
    const val = prompt(`Enter ${f.charAt(0).toUpperCase() + f.slice(1)}:`);
    if (val === null) return;
    data[f] = val || (f === 'uid' ? `UID_${Date.now()}` : '');
  }

  try {
    const res  = await fetch('/admin/add_legacy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    const result = await res.json();
    Toast.success('Legacy record added: ' + JSON.stringify(result));
  } catch (err) {
    Toast.error('Failed to add legacy record: ' + err.message);
  }
}

// ── Logout ──────────────────────────────────────────────────
async function logout() {
  try {
    await fetch('/logout', { method: 'POST' });
    window.location.href = '/login';
  } catch {
    window.location.href = '/login';
  }
}

// ── Utilities ───────────────────────────────────────────────
function setButtonLoading(btn, loading, label) {
  if (!btn) return;
  btn.disabled = loading;
  const textEl = btn.querySelector('.btn-text') || btn;
  if (loading) {
    btn.dataset.originalText = textEl.textContent;
    textEl.textContent = label;
    btn.classList.add('loading');
  } else {
    textEl.textContent = btn.dataset.originalText || label;
    btn.classList.remove('loading');
  }
}

function copyToClipboard(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    if (btn) {
      const original = btn.innerHTML;
      btn.innerHTML = Icons.check;
      btn.style.color = 'var(--success)';
      setTimeout(() => {
        btn.innerHTML = original;
        btn.style.color = '';
      }, 1800);
    }
    Toast.success('Copied to clipboard.');
  }).catch(() => Toast.error('Failed to copy.'));
}

function formatTimestamp(ts) {
  return new Date(ts * 1000).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' });
}

// ── Initialize Dashboard ────────────────────────────────────
async function initializeDashboard() {
  Toast.init();

  // Fetch role
  try {
    const res  = await fetch('/get_role');
    const data = await res.json();
    state.currentRole = data.role || '';

    const roleEl = document.getElementById('user-role-display');
    if (roleEl) {
      const roleLabels = { admin: 'Administrator', institution: 'Institution', verifier: 'Verifier' };
      roleEl.textContent = roleLabels[state.currentRole] || state.currentRole;
    }

    const roleBadgeEl = document.getElementById('nav-role-badge');
    if (roleBadgeEl) {
      roleBadgeEl.className = `badge ${roleBadge(state.currentRole)}`;
      roleBadgeEl.textContent = state.currentRole;
    }

    // Show/hide sections based on role
    showSectionsForRole(state.currentRole);

    // Set default panel
    const defaultPanel = state.currentRole === 'institution' ? 'upload'
                       : state.currentRole === 'admin'       ? 'verify'
                       : 'verify';
    switchPanel(defaultPanel);

  } catch (err) {
    console.error('Failed to get role:', err);
    Toast.error('Session error. Please log in again.');
    setTimeout(() => window.location.href = '/login', 2000);
  }

  // Command palette
  const cmdOverlay = document.getElementById('cmd-overlay');
  if (cmdOverlay) CommandPalette.init(cmdOverlay);

  // Global keyboard shortcuts
  document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault();
      CommandPalette.open();
    }
    if (e.key === 'Escape' && cmdOverlay?.classList.contains('open')) {
      CommandPalette.close();
    }
  });

  // Init upload zones
  initUploadZone(
    document.getElementById('upload-zone'),
    document.getElementById('upload-file-input'),
    document.getElementById('upload-file-list')
  );

  initUploadZone(
    document.getElementById('verify-zone'),
    document.getElementById('verify-file-input'),
    document.getElementById('verify-file-list')
  );

  initUploadZone(
    document.getElementById('legacy-zone'),
    document.getElementById('legacy-file-input'),
    document.getElementById('legacy-file-list')
  );

  // Verify mode cards
  document.querySelectorAll('.verify-mode-card').forEach(card => {
    card.addEventListener('click', () => selectVerifyMode(card.dataset.mode));
  });

  // Default verify mode
  selectVerifyMode('digital');
}

function showSectionsForRole(role) {
  const uploadTab   = document.querySelector('[data-tab="upload"]');
  const adminTab    = document.querySelector('[data-tab="admin"]');
  const uploadNav   = document.querySelector('[data-nav="upload"]');
  const adminNav    = document.querySelector('[data-nav="admin"]');
  const uploadPanel = document.getElementById('panel-upload');
  const adminPanel  = document.getElementById('panel-admin');

  // Hide (never remove) so panels can be shown again if role changes
  if (role !== 'institution' && role !== 'admin') {
    if (uploadTab)   uploadTab.style.display   = 'none';
    if (uploadNav)   uploadNav.style.display   = 'none';
    if (uploadPanel) uploadPanel.style.display = 'none';
  }

  if (role !== 'admin') {
    if (adminTab)   adminTab.style.display   = 'none';
    if (adminNav)   adminNav.style.display   = 'none';
    if (adminPanel) adminPanel.style.display = 'none';
  }
}

window.addEventListener('DOMContentLoaded', initializeDashboard);

// Expose globals for inline onclick handlers
window.uploadFile     = uploadFile;
window.verifyFile     = verifyFile;
window.getUsers       = getUsers;
window.recover2FA     = recover2FA;
window.addLegacyRecord = addLegacyRecord;
window.logout         = logout;
window.copyToClipboard = copyToClipboard;
window.switchPanel    = switchPanel;
window.selectVerifyMode = selectVerifyMode;
window.CommandPalette = CommandPalette;