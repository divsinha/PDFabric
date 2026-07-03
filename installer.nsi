; PDFabric Full Edition Installer (NSIS script)
; Bundles PDFabric.exe + LibreOffice Portable
;
; Prerequisites before running makensis:
;   1. Build PDFabric.exe via build.bat (output in dist/)
;   2. Download LibreOffice Portable from PortableApps.com
;   3. Extract it to build_full/LibreOfficePortable/
;
; Build: makensis installer.nsi

!include "MUI2.nsh"

Name "PDFabric"
OutFile "dist\PDFabric-Setup.exe"
InstallDir "$LOCALAPPDATA\PDFabric"
RequestExecutionLevel user
SetCompressor /SOLID lzma

; UI
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Section "Install"
    SetOutPath "$INSTDIR"
    File "dist\PDFabric.exe"

    SetOutPath "$INSTDIR\LibreOfficePortable"
    File /r "build_full\LibreOfficePortable\*.*"

    ; Start menu shortcut
    CreateDirectory "$SMPROGRAMS\PDFabric"
    CreateShortCut "$SMPROGRAMS\PDFabric\PDFabric.lnk" "$INSTDIR\PDFabric.exe"
    CreateShortCut "$SMPROGRAMS\PDFabric\Uninstall.lnk" "$INSTDIR\Uninstall.exe"

    WriteUninstaller "$INSTDIR\Uninstall.exe"
SectionEnd

Section "Uninstall"
    RMDir /r "$INSTDIR"
    RMDir /r "$SMPROGRAMS\PDFabric"
SectionEnd
