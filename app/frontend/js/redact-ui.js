import { downloadBlob, makeUploadZone, toast, formatBytes } from './app.js';
import { PDFViewer } from './pdf-viewer.js';

export function init(container) {
  container.innerHTML = `
    <div class="panel">
      <h2 class="panel-title">Redact PDF</h2>
      <p class="panel-desc">Permanently remove text or areas from a PDF.</p>

      <div class="upload-zone" id="redact-zone">
        <input type="file" id="redact-input" accept=".pdf" />
        <div class="upload-icon">🔒</div>
        <p>Drop your PDF here or <strong>browse</strong></p>
      </div>

      <div id="redact-editor" class="hidden mt-4">
        <div class="tabs">
          <button class="tab-btn active" data-tab="text">Text Search</button>
          <button class="tab-btn" data-tab="area">Draw Areas</button>
        </div>

        <!-- Text mode -->
        <div id="tab-text">
          <div class="flex gap-2 items-center">
            <input class="form-input" id="redact-term" placeholder="Enter search term" style="flex:1" />
            <button class="btn btn-secondary btn-sm" id="redact-add-term">Add</button>
          </div>
          <div id="redact-terms" class="redact-term-list mt-2"></div>
          <label class="mt-2" style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer;">
            <input type="checkbox" id="redact-case" /> Case sensitive
          </label>
          <button class="btn btn-danger mt-4" id="redact-text-submit" disabled>🔒 Redact Text</button>
          <div id="redact-report" class="hidden mt-2 text-muted"></div>
        </div>

        <!-- Area mode -->
        <div id="tab-area" class="hidden">
          <p class="text-muted mt-2">Draw rectangles on the PDF preview below. All drawn areas will be redacted.</p>
          <div class="pdf-controls" id="redact-controls">
            <button class="btn btn-secondary btn-sm" id="redact-prev">◀</button>
            <span id="redact-page-info">Page 1 / 1</span>
            <button class="btn btn-secondary btn-sm" id="redact-next">▶</button>
            <button class="btn btn-secondary btn-sm" id="redact-clear-rects">Clear areas</button>
          </div>
          <div class="pdf-viewer-wrap" style="position:relative;">
            <div id="redact-viewer"></div>
            <canvas id="redact-overlay-canvas" class="redact-overlay" style="position:absolute;top:0;left:0;"></canvas>
          </div>
          <div id="redact-area-list" class="area-list mt-2"></div>
          <button class="btn btn-danger mt-4" id="redact-area-submit" disabled>🔒 Redact Areas</button>
        </div>
      </div>
    </div>
  `;

  let selectedFile = null;
  let viewer = null;
  let terms = [];
  let drawnAreas = [];
  let isDrawing = false;
  let drawStart = null;
  let activeTab = 'text';

  const zone = container.querySelector('#redact-zone');
  const input = container.querySelector('#redact-input');
  const editor = container.querySelector('#redact-editor');

  makeUploadZone(zone, input, async files => {
    const f = files[0];
    if (!f || !f.name.toLowerCase().endsWith('.pdf')) { toast('Please select a PDF', 'error'); return; }
    selectedFile = f;
    editor.classList.remove('hidden');
    zone.querySelector('p').textContent = `Loaded: ${f.name} (${formatBytes(f.size)})`;
    try {
      await loadPDFViewer(f);
    } catch (err) {
      console.error('PDF viewer load error:', err);
    }
  });

  // Tab switching
  container.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      activeTab = btn.dataset.tab;
      container.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b === btn));
      container.querySelector('#tab-text').classList.toggle('hidden', activeTab !== 'text');
      container.querySelector('#tab-area').classList.toggle('hidden', activeTab !== 'area');
      if (activeTab === 'area' && viewer) {
        setTimeout(() => setupOverlayCanvas(), 100);
      }
    });
  });

  // --- Text mode ---
  const termInput = container.querySelector('#redact-term');
  const termList = container.querySelector('#redact-terms');
  const textSubmit = container.querySelector('#redact-text-submit');

  container.querySelector('#redact-add-term').addEventListener('click', () => addTerm());
  termInput.addEventListener('keydown', e => { if (e.key === 'Enter') addTerm(); });

  function addTerm() {
    const val = termInput.value.trim();
    if (!val || terms.includes(val)) return;
    terms.push(val);
    termInput.value = '';
    renderTerms();
  }

  function renderTerms() {
    termList.innerHTML = terms.map((t, i) => `
      <div class="redact-term-item">
        <span>${t}</span>
        <button class="btn btn-secondary btn-sm" data-remove="${i}">✕</button>
      </div>
    `).join('');
    termList.querySelectorAll('[data-remove]').forEach(btn => {
      btn.addEventListener('click', () => { terms.splice(parseInt(btn.dataset.remove), 1); renderTerms(); });
    });
    textSubmit.disabled = terms.length === 0 || !selectedFile;
  }

  textSubmit.addEventListener('click', async () => {
    if (!selectedFile || !terms.length) return;
    const fd = new FormData();
    fd.append('file', selectedFile);
    fd.append('terms', JSON.stringify(terms));
    fd.append('case_sensitive', container.querySelector('#redact-case').checked ? '1' : '0');
    textSubmit.disabled = true;
    textSubmit.textContent = 'Redacting…';
    const reportEl = container.querySelector('#redact-report');
    reportEl.classList.add('hidden');
    try {
      const res = await fetch('/api/redact/text/download', { method: 'POST', body: fd });
      if (!res.ok) { const j = await res.json(); throw new Error(j.error || 'Redaction failed'); }
      const reportHeader = res.headers.get('X-Redaction-Report');
      const blob = await res.blob();
      downloadBlob(blob, 'redacted.pdf');

      if (reportHeader) {
        const report = JSON.parse(reportHeader);
        const totalRedactions = Object.values(report).reduce((a, b) => a + b, 0);
        if (totalRedactions > 0) {
          reportEl.textContent = `Redacted ${totalRedactions} occurrence(s) across ${Object.keys(report).length} page(s).`;
          reportEl.classList.remove('hidden');
          toast(`Redacted ${totalRedactions} occurrence(s)!`, 'success');
        } else {
          reportEl.textContent = 'No matches found for the given terms.';
          reportEl.classList.remove('hidden');
          toast('No matches found — try different search terms.', 'error');
        }
      } else {
        toast('Text redaction complete!', 'success');
      }
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      textSubmit.disabled = false;
      textSubmit.textContent = '🔒 Redact Text';
    }
  });

  // --- Area mode ---
  async function loadPDFViewer(file) {
    const viewerEl = container.querySelector('#redact-viewer');
    viewer = new PDFViewer(viewerEl, { scale: 1.5 });

    const buf = await file.arrayBuffer();
    await viewer.loadPDF(new Uint8Array(buf));

    updatePageInfo();
    if (activeTab === 'area') {
      setTimeout(() => setupOverlayCanvas(), 100);
    }
  }

  function updatePageInfo() {
    if (!viewer) return;
    container.querySelector('#redact-page-info').textContent =
      `Page ${viewer.currentPage} / ${viewer.pageCount}`;
  }

  container.querySelector('#redact-prev').addEventListener('click', async () => {
    if (viewer && viewer.currentPage > 1) {
      await viewer.renderPage(viewer.currentPage - 1);
      updatePageInfo(); setupOverlayCanvas();
    }
  });
  container.querySelector('#redact-next').addEventListener('click', async () => {
    if (viewer && viewer.currentPage < viewer.pageCount) {
      await viewer.renderPage(viewer.currentPage + 1);
      updatePageInfo(); setupOverlayCanvas();
    }
  });
  container.querySelector('#redact-clear-rects').addEventListener('click', () => {
    drawnAreas = drawnAreas.filter(a => a.page !== viewer.currentPage - 1);
    renderAreaList();
    redrawOverlay();
  });

  function setupOverlayCanvas() {
    const viewerEl = container.querySelector('#redact-viewer');
    const wrap = viewerEl.querySelector('.pdf-page-container');
    if (!wrap) return;
    const overlay = container.querySelector('#redact-overlay-canvas');
    overlay.width = wrap.offsetWidth;
    overlay.height = wrap.offsetHeight;
    overlay.style.width = wrap.offsetWidth + 'px';
    overlay.style.height = wrap.offsetHeight + 'px';

    const wrapRect = wrap.getBoundingClientRect();
    const parentRect = overlay.parentElement.getBoundingClientRect();
    overlay.style.left = (wrapRect.left - parentRect.left) + 'px';
    overlay.style.top = (wrapRect.top - parentRect.top) + 'px';

    redrawOverlay();
  }

  const overlayCanvas = container.querySelector('#redact-overlay-canvas');
  let currentRect = null;

  overlayCanvas.addEventListener('mousedown', e => {
    if (activeTab !== 'area') return;
    const r = overlayCanvas.getBoundingClientRect();
    drawStart = { x: e.clientX - r.left, y: e.clientY - r.top };
    isDrawing = true;
    currentRect = null;
  });

  overlayCanvas.addEventListener('mousemove', e => {
    if (!isDrawing) return;
    const r = overlayCanvas.getBoundingClientRect();
    const x = e.clientX - r.left;
    const y = e.clientY - r.top;
    currentRect = {
      x: Math.min(drawStart.x, x),
      y: Math.min(drawStart.y, y),
      width: Math.abs(x - drawStart.x),
      height: Math.abs(y - drawStart.y),
    };
    redrawOverlay();
  });

  overlayCanvas.addEventListener('mouseup', e => {
    if (!isDrawing || !currentRect || currentRect.width < 4 || currentRect.height < 4) {
      isDrawing = false; return;
    }
    isDrawing = false;
    const pageNum = viewer ? viewer.currentPage : 1;
    const pdfRect = viewer.canvasRectToPageRect(pageNum, currentRect.x, currentRect.y, currentRect.width, currentRect.height);
    drawnAreas.push({ page: pageNum - 1, ...pdfRect });
    currentRect = null;
    redrawOverlay();
    renderAreaList();
    container.querySelector('#redact-area-submit').disabled = drawnAreas.length === 0;
  });

  function redrawOverlay() {
    const ctx = overlayCanvas.getContext('2d');
    ctx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);

    const pageNum = viewer ? viewer.currentPage : 1;
    const viewport = viewer ? viewer.getViewport(pageNum) : null;
    if (viewport) {
      const scale = viewport.scale;
      drawnAreas.filter(a => a.page === pageNum - 1).forEach(a => {
        const cx = a.x * scale;
        const cy = a.y * scale;
        const cw = a.width * scale;
        const ch = a.height * scale;
        ctx.fillStyle = 'rgba(220,38,38,0.3)';
        ctx.strokeStyle = '#dc2626';
        ctx.lineWidth = 2;
        ctx.fillRect(cx, cy, cw, ch);
        ctx.strokeRect(cx, cy, cw, ch);
      });
    }

    if (currentRect) {
      ctx.fillStyle = 'rgba(220,38,38,0.2)';
      ctx.strokeStyle = '#dc2626';
      ctx.lineWidth = 2;
      ctx.setLineDash([4, 2]);
      ctx.fillRect(currentRect.x, currentRect.y, currentRect.width, currentRect.height);
      ctx.strokeRect(currentRect.x, currentRect.y, currentRect.width, currentRect.height);
      ctx.setLineDash([]);
    }
  }

  function renderAreaList() {
    const list = container.querySelector('#redact-area-list');
    list.innerHTML = drawnAreas.map((a, i) =>
      `<div>Area ${i + 1}: Page ${a.page + 1} — x:${a.x.toFixed(1)} y:${a.y.toFixed(1)} ${a.width.toFixed(1)}×${a.height.toFixed(1)} pts
        <button class="btn btn-secondary btn-sm" style="margin-left:8px" data-remove="${i}">✕</button></div>`
    ).join('');
    list.querySelectorAll('[data-remove]').forEach(btn => {
      btn.addEventListener('click', () => {
        drawnAreas.splice(parseInt(btn.dataset.remove), 1);
        renderAreaList(); redrawOverlay();
        container.querySelector('#redact-area-submit').disabled = drawnAreas.length === 0;
      });
    });
  }

  container.querySelector('#redact-area-submit').addEventListener('click', async () => {
    if (!selectedFile || !drawnAreas.length) return;
    const fd = new FormData();
    fd.append('file', selectedFile);
    fd.append('areas', JSON.stringify(drawnAreas));
    const btn = container.querySelector('#redact-area-submit');
    btn.disabled = true;
    btn.textContent = 'Redacting…';
    try {
      const res = await fetch('/api/redact/area', { method: 'POST', body: fd });
      if (!res.ok) { const j = await res.json(); throw new Error(j.error || 'Redaction failed'); }
      const blob = await res.blob();
      downloadBlob(blob, 'redacted.pdf');
      toast('Area redaction complete!', 'success');
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = '🔒 Redact Areas';
    }
  });
}
