// Shared PDF.js viewer component
// PDF.js uses legacy build (global pdfjsLib injected via script tag in each feature UI)

export class PDFViewer {
  constructor(container, options = {}) {
    this.container = container;
    this.options = { scale: 1.5, ...options };
    this.pdfDoc = null;
    this.currentPage = 1;
    this.totalPages = 0;
    this.pageCache = new Map(); // pageNum -> {canvas, viewport}
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
    // source: ArrayBuffer | Uint8Array | URL string
    const lib = window.pdfjsLib;
    if (!lib) throw new Error('pdfjsLib not loaded');

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

    // Remove existing canvas
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
   * Convert canvas pixel coords → PDF point coords (72 dpi space).
   * PDF Y-axis is bottom-up; canvas Y-axis is top-down.
   */
  canvasToPageCoords(pageNum, canvasX, canvasY) {
    const cached = this.pageCache.get(pageNum);
    if (!cached) return { x: 0, y: 0 };
    const { viewport } = cached;
    // viewport.transform: [scale, 0, 0, -scale, offsetX, offsetY]
    const scale = viewport.scale;
    const [,, , , offsetX, offsetY] = viewport.transform;
    const pdfX = (canvasX - offsetX) / scale;
    const pdfY = (offsetY - canvasY) / scale; // invert Y
    return { x: pdfX, y: pdfY };
  }

  /**
   * Convert canvas rect {x,y,width,height} → PDF rect in PDF point space.
   * Returns {x, y, width, height} where y is from bottom-left of page.
   */
  canvasRectToPageRect(pageNum, cx, cy, cw, ch) {
    const topLeft = this.canvasToPageCoords(pageNum, cx, cy);
    const bottomRight = this.canvasToPageCoords(pageNum, cx + cw, cy + ch);
    return {
      x: Math.min(topLeft.x, bottomRight.x),
      y: Math.min(topLeft.y, bottomRight.y),
      width: Math.abs(bottomRight.x - topLeft.x),
      height: Math.abs(bottomRight.y - topLeft.y),
    };
  }

  goToPage(pageNum) {
    return this.renderPage(pageNum);
  }

  get pageCount() { return this.totalPages; }
}
