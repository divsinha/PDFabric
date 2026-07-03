import { downloadBlob, makeUploadZone, toast, formatBytes } from './app.js';

export function init(container) {
  container.innerHTML = `
    <div class="panel">
      <h2 class="panel-title">PDF to Office</h2>
      <p class="panel-desc">Convert PDF files to editable Word or PowerPoint format.</p>
      <p class="text-muted" style="font-size:12px;margin-top:-8px;">Best results with text-based PDFs. Scanned documents may not convert well.</p>

      <div class="upload-zone" id="pto-zone">
        <input type="file" id="pto-input" accept=".pdf" />
        <div class="upload-icon">📝</div>
        <p>Drop your PDF here or <strong>browse</strong></p>
      </div>

      <div id="pto-info" class="hidden mt-4 text-muted"></div>

      <div class="mt-4" id="pto-format-wrap" style="display:none;">
        <label style="font-weight:600;font-size:14px;display:block;margin-bottom:8px;">Output format:</label>
        <label style="display:inline-flex;align-items:center;gap:6px;margin-right:16px;cursor:pointer;font-size:14px;">
          <input type="radio" name="pto-format" value="docx" checked /> Word Document (.docx)
        </label>
        <label style="display:inline-flex;align-items:center;gap:6px;cursor:pointer;font-size:14px;">
          <input type="radio" name="pto-format" value="pptx" /> PowerPoint (.pptx)
        </label>
      </div>

      <div id="pto-progress" class="hidden progress-wrap mt-4">
        <p class="text-muted" style="margin-bottom:6px">Converting… this may take a moment.</p>
        <div class="progress-bar"><div class="progress-fill" id="pto-fill" style="width:0%"></div></div>
      </div>

      <button class="btn btn-primary mt-4" id="pto-submit" style="display:none;">📝 Convert</button>
    </div>
  `;

  let selectedFile = null;
  let animFrame = null;

  const zone = container.querySelector('#pto-zone');
  const input = container.querySelector('#pto-input');
  const info = container.querySelector('#pto-info');
  const formatWrap = container.querySelector('#pto-format-wrap');
  const submitBtn = container.querySelector('#pto-submit');
  const progressWrap = container.querySelector('#pto-progress');
  const fill = container.querySelector('#pto-fill');

  makeUploadZone(zone, input, files => {
    const f = files[0];
    if (!f) return;
    if (!f.name.toLowerCase().endsWith('.pdf')) { toast('Please select a PDF file', 'error'); return; }
    selectedFile = f;
    info.textContent = `Selected: ${f.name} (${formatBytes(f.size)})`;
    info.classList.remove('hidden');
    formatWrap.style.display = '';
    submitBtn.style.display = '';
  });

  submitBtn.addEventListener('click', async () => {
    if (!selectedFile) return;

    const fmt = container.querySelector('input[name="pto-format"]:checked').value;
    const fd = new FormData();
    fd.append('file', selectedFile);
    fd.append('format', fmt);

    submitBtn.style.display = 'none';
    progressWrap.classList.remove('hidden');

    let pct = 0;
    animFrame = setInterval(() => {
      pct = Math.min(pct + 1.5, 85);
      fill.style.width = pct + '%';
    }, 400);

    try {
      const res = await fetch('/api/pdf-to-office/', { method: 'POST', body: fd });
      clearInterval(animFrame);
      fill.style.width = '100%';

      if (!res.ok) { const j = await res.json(); throw new Error(j.error || j.detail || 'Conversion failed'); }
      const blob = await res.blob();
      const stem = selectedFile.name.replace(/\.[^.]+$/, '');
      downloadBlob(blob, `${stem}.${fmt}`);
      toast(`Conversion complete! Downloading ${fmt.toUpperCase()}…`, 'success');
    } catch (err) {
      clearInterval(animFrame);
      toast(err.message, 'error');
      submitBtn.style.display = '';
    } finally {
      setTimeout(() => {
        progressWrap.classList.add('hidden');
        fill.style.width = '0%';
      }, 1000);
    }
  });
}
