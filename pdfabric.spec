# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_all

pymupdf_datas, pymupdf_binaries, pymupdf_hidden = collect_all('pymupdf')
fitz_datas, fitz_binaries, fitz_hidden = collect_all('fitz')

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=pymupdf_binaries + fitz_binaries,
    datas=[
        ('app/frontend', 'app/frontend'),
    ] + pymupdf_datas + fitz_datas,
    hiddenimports=pymupdf_hidden + fitz_hidden + [
        'app.main',
        'app.core.config',
        'app.core.exceptions',
        'app.core.file_manager',
        'app.features.split',
        'app.features.merge',
        'app.features.redact',
        'app.features.convert',
        'app.features.signature',
        'app.features.pdf_to_office',
        'app.features.docx_list_fixer',
        'app.features.pdf_prescan',
        'pdf2docx',
        'pptx',
        'docx',
        'cv2',
        'numpy',
        'fire',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.loops.asyncio',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.http.httptools_impl',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.protocols.websockets.wsproto_impl',
        'uvicorn.protocols.websockets.websockets_impl',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'uvicorn.lifespan.off',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PDFabric',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
