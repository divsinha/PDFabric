import { downloadBlob, makeUploadZone, toast, formatBytes } from './app.js';
import { PDFViewer } from './pdf-viewer.js';

export function init(container) {
  container.innerHTML = `
    <div class="panel">
      <h2 class="panel-title">Add Signature</h2>
      <p class="panel-desc">Upload a signature image and place it on any page of your PDF.</p>

      <div class="form-group">
        <label class="form-label">1. Upload PDF</label>
        <div class="upload-zone" id="sig-pdf-zone">
          <input type="file" id="sig-pdf-input" accept=".pdf" />
          <div class="upload-icon">📄</div>
          <p>Drop PDF here or <strong>browse</strong></p>
        </div>
      </div>

      <div class="form-group hidden" id="sig-image-group">
        <label class="form-label">2. Upload Signature Image</label>
        <div class="upload-zone" id="sig-img-zone">
          <input type="file" id="sig-img-input" accept=".png,.jpg,.jpeg" />
          <div class="upload-icon">✍️</div>
          <p>Drop PNG/JPEG here or <strong>browse</strong></p>
        </div>
      </div>

      <div class="hidden" id="sig-editor">
        <label class="form-label">3. Position signature on page</label>
        <div class="pdf-controls">
          <button class="btn btn-secondary btn-sm" id="sig-prev">◀</button>
          <span id="sig-page-info">Page 1 / 1</span>
          <button class="btn btn-secondary btn-sm" id="sig-next">▶</button>
          <span class="text-muted" style="margin-left:auto">Drag signature to position, drag corner to resize</span>
        </div>
        <div style="position:relative;display:inline-block;" id="sig-viewer-wrap">
          <div id="sig-viewer" class="pdf-viewer-wrap" style="max-height:none;overflow:visible;"></div>
          <img id="sig-overlay" class="sig-overlay-img hidden" src="" alt="signature" />
        </div>
        <button class="btn btn-primary mt-4" id="sig-submit">✍️ Apply Signature</button>
      </div>
    </div>
  `;

  // Load PDF.js
  if (!window.pdfjsLib) {
    const s = document.createElement('script');
    s.src = '/lib/pdf.min.js';
    s.onload = () => { window.pdfjsLib.GlobalWorkerOptions.workerSrc = '/lib/pdf.worker.min.js'; };
    document.head.appendChild(s);
  }

  let pdfFile = null;
  let sigFile = null;
  let viewer = null;
  const overlay = container.querySelector('#sig-overlay');

  // PDF upload
  makeUploadZone(
    container.querySelector('#sig-pdf-zone'),
    container.querySelector('#sig-pdf-input'),
    async files => {
      const f = files[0];
      if (!f || !f.name.toLowerCase().endsWith('.pdf')) { toast('Please select a PDF', 'error'); return; }
      pdfFile = f;
      container.querySelector('#sig-pdf-zone').querySelector('p').textContent = `Loaded: ${f.name}`;
      container.querySelector('#sig-image-group').classList.remove('hidden');
      await loadViewer(f);
    }
  );

  // Signature image upload
  makeUploadZone(
    container.querySelector('#sig-img-zone'),
    container.querySelector('#sig-img-input'),
    files => {
      const f = files[0];
      if (!f) return;
      const ext = f.name.substring(f.name.lastIndexOf('.')).toLowerCase();
      if (!['.png', '.jpg', '.jpeg'].includes(ext)) { toast('Please select PNG or JPEG', 'error'); return; }
      sigFile = f;
      const url = URL.createObjectURL(f);
      overlay.src = url;
      overlay.classList.remove('hidden');
      overlay.style.left = '20px';
      overlay.style.top = '20px';
      overlay.style.width = '150px';
      overlay.style.height = 'auto';
      container.querySelector('#sig-editor').classList.remove('hidden');
    }
  );

  async function loadViewer(file) {
    const viewerEl = container.querySelector('#sig-viewer');
    viewer = new PDFViewer(viewerEl, { scale: 1.5 });
    const buf = await file.arrayBuffer();
    await viewer.loadPDF(new Uint8Array(buf));
    updatePageInfo();
  }

  function updatePageInfo() {
    if (!viewer) return;
    container.querySelector('#sig-page-info').textContent =
      `Page ${viewer.currentPage} / ${viewer.pageCount}`;
  }

  container.querySelector('#sig-prev').addEventListener('click', async () => {
    if (viewer && viewer.currentPage > 1) { await viewer.renderPage(viewer.currentPage - 1); updatePageInfo(); }
  });
  container.querySelector('#sig-next').addEventListener('click', async () => {
    if (viewer && viewer.currentPage < viewer.pageCount) { await viewer.renderPage(viewer.currentPage + 1); updatePageInfo(); }
  });

  // Drag overlay to reposition
  let dragging = false, dragOffX = 0, dragOffY = 0;
  let resizing = false, resizeStartX = 0, resizeStartW = 0;

  overlay.addEventListener('mousedown', e => {
    if (e.target === resizeHandle) return;
    dragging = true;
    dragOffX = e.clientX - overlay.getBoundingClientRect().left;
    dragOffY = e.clientY - overlay.getBoundingClientRect().top;
    e.preventDefault();
  });

  // Resize handle
  const resizeHandle = document.createElement('div');
  resizeHandle.className = 'sig-resize-handle';
  overlay.appendChild(resizeHandle);

  resizeHandle.addEventListener('mousedown', e => {
    resizing = true;
    resizeStartX = e.clientX;
    resizeStartW = overlay.offsetWidth;
    e.preventDefault();
    e.stopPropagation();
  });

  document.addEventListener('mousemove', e => {
    if (dragging) {
      const parent = container.querySelector('#sig-viewer-wrap').getBoundingClientRect();
      overlay.style.left = (e.clientX - parent.left - dragOffX) + 'px';
      overlay.style.top = (e.clientY - parent.top - dragOffY) + 'px';
    }
    if (resizing) {
      const newW = Math.max(40, resizeStartW + (e.clientX - resizeStartX));
      overlay.style.width = newW + 'px';
      overlay.style.height = 'auto';
    }
  });

  document.addEventListener('mouseup', () => { dragging = false; resizing = false; });

  container.querySelector('#sig-submit').addEventListener('click', async () => {
    if (!pdfFile || !sigFile || !viewer) { toast('Upload both a PDF and signature image first', 'error'); return; }

    const wrap = container.querySelector('#sig-viewer-wrap');
    const wrapRect = wrap.getBoundingClientRect();
    const overlayRect = overlay.getBoundingClientRect();

    // Canvas coordinates of overlay
    const canvasX = overlayRect.left - wrapRect.left;
    const canvasY = overlayRect.top - wrapRect.top;
    const canvasW = overlay.offsetWidth;
    const canvasH = overlay.offsetHeight;

    const pageNum = viewer.currentPage;
    const pdfRect = viewer.canvasRectToPageRect(pageNum, canvasX, canvasY, canvasW, canvasH);

    const fd = new FormData();
    fd.append('file', pdfFile);
    fd.append('signature', sigFile);
    fd.append('page_num', pageNum - 1); // 0-based
    fd.append('rect', JSON.stringify(pdfRect));

    const btn = container.querySelector('#sig-submit');
    btn.disabled = true;
    btn.textContent = 'Applying…';
    try {
      const res = await fetch('/api/signature/', { method: 'POST', body: fd });
      if (!res.ok) { const j = await res.json(); throw new Error(j.error || 'Failed'); }
      const blob = await res.blob();
      downloadBlob(blob, 'signed.pdf');
      toast('Signature applied! Downloading…', 'success');
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = '✍️ Apply Signature';
    }
  });
}
