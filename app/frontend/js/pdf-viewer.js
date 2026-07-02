// Shared PDF.js viewer component
// Dynamically imports PDF.js as an ES module

let pdfjsLib = null;
let pdfjsReady = null;

function ensurePdfjs() {
  if (pdfjsReady) return pdfjsReady;
  pdfjsReady = import('/lib/pdf.min.js').then(mod => {
    pdfjsLib = mod;
    pdfjsLib.GlobalWorkerOptions.workerSrc = '/lib/pdf.worker.min.js';
    return pdfjsLib;
  });
  return pdfjsReady;
}

export class PDFViewer {
  constructor(container, options = {}) {
    this.container = container;
    this.options = { scale: 1.5, ...options };
    this.pdfDoc = null;
    this.currentPage = 1;
    this.totalPages = 0;
    this.pageCache = new Map();
    this._listeners = {};
  }

  on(event, cb) {
    if (!this._listeners[event]) this._listeners[event] = [];
    this._listeners[event].push(cb);
    return this;
  }

  _emit(event, data) {
    (this._listeners[event] || []).forEach(cb => cb(data));
  }

  async loadPDF(source) {
    const lib = await ensurePdfjs();

    const loadingTask = typeof source === 'string'
      ? lib.getDocument(source)
      : lib.getDocument({ data: source });

    this.pdfDoc = await loadingTask.promise;
    this.totalPages = this.pdfDoc.numPages;
    this.currentPage = 1;
    this.pageCache.clear();
    this._emit('loaded', { totalPages: this.totalPages });
    await this.renderPage(1);
    return this.totalPages;
  }

  async renderPage(pageNum) {
    if (!this.pdfDoc) return;
    pageNum = Math.max(1, Math.min(pageNum, this.totalPages));
    this.currentPage = pageNum;

    const page = await this.pdfDoc.getPage(pageNum);
    const viewport = page.getViewport({ scale: this.options.scale });

    this.container.innerHTML = '';

    const wrapper = document.createElement('div');
    wrapper.className = 'pdf-page-container';
    wrapper.style.width = viewport.width + 'px';
    wrapper.style.height = viewport.height + 'px';

    const canvas = document.createElement('canvas');
    canvas.width = viewport.width;
    canvas.height = viewport.height;

    const ctx = canvas.getContext('2d');
    await page.render({ canvasContext: ctx, viewport }).promise;

    wrapper.appendChild(canvas);
    this.container.appendChild(wrapper);

    this.pageCache.set(pageNum, { canvas, viewport, page });
    this._emit('pageRendered', { pageNum, viewport, canvas, wrapper });
    return { canvas, viewport, wrapper };
  }

  getViewport(pageNum) {
    return this.pageCache.get(pageNum)?.viewport || null;
  }

  getWrapper(pageNum) {
    return this.pageCache.get(pageNum)?.wrapper || this.container.querySelector('.pdf-page-container');
  }

  /**
   * Convert canvas pixel coords to PDF point coords.
   * PDF.js viewport.transform = [scaleX, 0, 0, -scaleY, offsetX, offsetY]
   */
  canvasToPageCoords(pageNum, canvasX, canvasY) {
    const cached = this.pageCache.get(pageNum);
    if (!cached) return { x: 0, y: 0 };
    const { viewport } = cached;
    const scale = viewport.scale;
    const pdfX = canvasX / scale;
    const pdfY = canvasY / scale;
    return { x: pdfX, y: pdfY };
  }

  /**
   * Convert canvas rect {x,y,width,height} to PDF rect in PDF point space.
   * PDF.js uses top-left origin same as canvas, so no Y inversion needed.
   */
  canvasRectToPageRect(pageNum, cx, cy, cw, ch) {
    const cached = this.pageCache.get(pageNum);
    if (!cached) return { x: 0, y: 0, width: 0, height: 0 };
    const scale = cached.viewport.scale;
    return {
      x: cx / scale,
      y: cy / scale,
      width: cw / scale,
      height: ch / scale,
    };
  }

  goToPage(pageNum) {
    return this.renderPage(pageNum);
  }

  get pageCount() { return this.totalPages; }
}
