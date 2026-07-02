import { downloadBlob, makeUploadZone, toast, formatBytes } from './app.js';

export function init(container) {
  container.innerHTML = `
    <div class="panel">
      <h2 class="panel-title">Merge PDFs</h2>
      <p class="panel-desc">Combine multiple PDFs into one. Drag to reorder files.</p>

      <div class="upload-zone" id="merge-zone">
        <input type="file" id="merge-input" accept=".pdf" multiple />
        <div class="upload-icon">🔗</div>
        <p>Drop PDFs here or <strong>browse</strong> (select multiple)</p>
      </div>

      <div id="merge-file-list" class="file-list mt-4"></div>

      <button class="btn btn-primary mt-4 hidden" id="merge-submit">🔗 Merge PDFs</button>
    </div>
  `;

  let files = [];

  const zone = container.querySelector('#merge-zone');
  const input = container.querySelector('#merge-input');
  const list = container.querySelector('#merge-file-list');
  const submitBtn = container.querySelector('#merge-submit');

  makeUploadZone(zone, input, added => {
    const pdfs = added.filter(f => f.name.toLowerCase().endsWith('.pdf'));
    if (!pdfs.length) { toast('Please select PDF files', 'error'); return; }
    files = [...files, ...pdfs];
    render();
  });

  function render() {
    list.innerHTML = '';
    files.forEach((f, i) => {
      const item = document.createElement('div');
      item.className = 'file-item';
      item.draggable = true;
      item.dataset.index = i;
      item.innerHTML = `
        <span>☰</span>
        <span class="file-name">📄 ${f.name}</span>
        <span class="file-size">${formatBytes(f.size)}</span>
        <button class="btn btn-secondary btn-sm" data-remove="${i}">✕</button>
      `;
      item.addEventListener('dragstart', e => { e.dataTransfer.setData('text/plain', i); });
      item.addEventListener('dragover', e => { e.preventDefault(); item.classList.add('drag-over'); });
      item.addEventListener('dragleave', () => item.classList.remove('drag-over'));
      item.addEventListener('drop', e => {
        e.preventDefault();
        item.classList.remove('drag-over');
        const from = parseInt(e.dataTransfer.getData('text/plain'));
        const to = parseInt(item.dataset.index);
        const moved = files.splice(from, 1)[0];
        files.splice(to, 0, moved);
        render();
      });
      item.querySelector('[data-remove]').addEventListener('click', () => {
        files.splice(i, 1);
        render();
      });
      list.appendChild(item);
    });
    submitBtn.classList.toggle('hidden', files.length < 2);
  }

  submitBtn.addEventListener('click', async () => {
    if (files.length < 2) { toast('Need at least 2 PDFs', 'error'); return; }
    const fd = new FormData();
    files.forEach(f => fd.append('files', f));
    fd.append('order', JSON.stringify(files.map((_, i) => i)));
    fd.append('page_selections', '{}');

    submitBtn.disabled = true;
    submitBtn.textContent = 'Merging…';
    try {
      const res = await fetch('/api/merge/', { method: 'POST', body: fd });
      if (!res.ok) { const j = await res.json(); throw new Error(j.error || 'Merge failed'); }
      const blob = await res.blob();
      downloadBlob(blob, 'merged.pdf');
      toast('Merge complete! Downloading…', 'success');
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = '🔗 Merge PDFs';
    }
  });
}
