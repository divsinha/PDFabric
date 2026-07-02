import { api, downloadBlob, makeUploadZone, toast, formatBytes } from './app.js';

export function init(container) {
  container.innerHTML = `
    <div class="panel">
      <h2 class="panel-title">Split PDF</h2>
      <p class="panel-desc">Split a PDF into multiple files by page ranges, every N pages, or individual pages.</p>

      <div class="upload-zone" id="split-zone">
        <input type="file" id="split-input" accept=".pdf" />
        <div class="upload-icon">📂</div>
        <p>Drop your PDF here or <strong>browse</strong></p>
      </div>

      <div id="split-file-info" class="hidden mt-4 text-muted"></div>

      <div id="split-options" class="hidden mt-4">
        <div class="form-group">
          <label class="form-label">Split mode</label>
          <select class="form-select" id="split-mode">
            <option value="ranges">By page ranges (e.g. 1-3, 5, 7-10)</option>
            <option value="every_n">Every N pages</option>
            <option value="individual">Individual pages</option>
          </select>
        </div>

        <div id="split-ranges-group" class="form-group">
          <label class="form-label">Page ranges</label>
          <input class="form-input" id="split-ranges" placeholder="e.g. 1-3, 5, 7-10" />
        </div>

        <div id="split-n-group" class="form-group hidden">
          <label class="form-label">Pages per chunk</label>
          <input class="form-input" type="number" id="split-n" value="2" min="1" />
        </div>

        <button class="btn btn-primary mt-4" id="split-submit">✂️ Split PDF</button>
      </div>
    </div>
  `;

  let selectedFile = null;

  const zone = container.querySelector('#split-zone');
  const input = container.querySelector('#split-input');
  const fileInfo = container.querySelector('#split-file-info');
  const options = container.querySelector('#split-options');
  const modeSelect = container.querySelector('#split-mode');
  const rangesGroup = container.querySelector('#split-ranges-group');
  const nGroup = container.querySelector('#split-n-group');
  const submitBtn = container.querySelector('#split-submit');

  makeUploadZone(zone, input, files => {
    const f = files[0];
    if (!f || !f.name.toLowerCase().endsWith('.pdf')) { toast('Please select a PDF file', 'error'); return; }
    selectedFile = f;
    fileInfo.textContent = `Selected: ${f.name} (${formatBytes(f.size)})`;
    fileInfo.classList.remove('hidden');
    options.classList.remove('hidden');
  });

  modeSelect.addEventListener('change', () => {
    const mode = modeSelect.value;
    rangesGroup.classList.toggle('hidden', mode !== 'ranges');
    nGroup.classList.toggle('hidden', mode !== 'every_n');
  });

  submitBtn.addEventListener('click', async () => {
    if (!selectedFile) { toast('No file selected', 'error'); return; }
    const mode = modeSelect.value;
    const fd = new FormData();
    fd.append('file', selectedFile);
    fd.append('mode', mode);
    if (mode === 'ranges') fd.append('ranges', container.querySelector('#split-ranges').value);
    if (mode === 'every_n') fd.append('n', container.querySelector('#split-n').value);

    submitBtn.disabled = true;
    submitBtn.textContent = 'Splitting…';
    try {
      const blob = await (await fetch('/api/split/', { method: 'POST', body: fd })).blob();
      const isZip = blob.type === 'application/zip' || blob.size > 0 && blob.type !== 'application/pdf';
      downloadBlob(blob, isZip ? 'split_pages.zip' : 'split.pdf');
      toast('Split complete! Downloading…', 'success');
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = '✂️ Split PDF';
    }
  });
}
