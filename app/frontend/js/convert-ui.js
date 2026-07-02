import { downloadBlob, makeUploadZone, toast, formatBytes } from './app.js';

export function init(container) {
  container.innerHTML = `
    <div class="panel">
      <h2 class="panel-title">Convert to PDF</h2>
      <p class="panel-desc">Convert Word or PowerPoint files to PDF using LibreOffice.</p>

      <div class="upload-zone" id="convert-zone">
        <input type="file" id="convert-input" accept=".docx,.doc,.pptx,.ppt" />
        <div class="upload-icon">🔄</div>
        <p>Drop your DOCX / PPTX here or <strong>browse</strong></p>
      </div>

      <div id="convert-info" class="hidden mt-4 text-muted"></div>

      <div id="convert-progress" class="hidden progress-wrap mt-4">
        <p class="text-muted" style="margin-bottom:6px">Converting… this may take a few seconds.</p>
        <div class="progress-bar"><div class="progress-fill" id="convert-fill" style="width:0%"></div></div>
      </div>

      <button class="btn btn-primary mt-4 hidden" id="convert-submit">🔄 Convert to PDF</button>
    </div>
  `;

  let selectedFile = null;
  let animFrame = null;

  const zone = container.querySelector('#convert-zone');
  const input = container.querySelector('#convert-input');
  const info = container.querySelector('#convert-info');
  const submitBtn = container.querySelector('#convert-submit');
  const progressWrap = container.querySelector('#convert-progress');
  const fill = container.querySelector('#convert-fill');

  const ALLOWED = ['.docx', '.doc', '.pptx', '.ppt'];

  makeUploadZone(zone, input, files => {
    const f = files[0];
    if (!f) return;
    const ext = f.name.substring(f.name.lastIndexOf('.')).toLowerCase();
    if (!ALLOWED.includes(ext)) { toast('Please select a DOCX, DOC, PPTX, or PPT file', 'error'); return; }
    selectedFile = f;
    info.textContent = `Selected: ${f.name} (${formatBytes(f.size)})`;
    info.classList.remove('hidden');
    submitBtn.classList.remove('hidden');
  });

  submitBtn.addEventListener('click', async () => {
    if (!selectedFile) return;
    const fd = new FormData();
    fd.append('file', selectedFile);

    submitBtn.classList.add('hidden');
    progressWrap.classList.remove('hidden');

    // Fake progress animation (real progress unknowable with fetch)
    let pct = 0;
    animFrame = setInterval(() => {
      pct = Math.min(pct + 2, 85);
      fill.style.width = pct + '%';
    }, 300);

    try {
      const res = await fetch('/api/convert/', { method: 'POST', body: fd });
      clearInterval(animFrame);
      fill.style.width = '100%';

      if (!res.ok) { const j = await res.json(); throw new Error(j.error || j.detail || 'Conversion failed'); }
      const blob = await res.blob();
      const stem = selectedFile.name.replace(/\.[^.]+$/, '');
      downloadBlob(blob, `${stem}.pdf`);
      toast('Conversion complete! Downloading…', 'success');
    } catch (err) {
      clearInterval(animFrame);
      toast(err.message, 'error');
      submitBtn.classList.remove('hidden');
    } finally {
      setTimeout(() => {
        progressWrap.classList.add('hidden');
        fill.style.width = '0%';
      }, 1000);
    }
  });
}
