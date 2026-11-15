; Página del instalador: «Descargar también los modelos de IA».
;
; Decisión del usuario (2026-11-15): un solo ejecutable que deje EMMA y sus modelos listos. Los
; modelos (unos 33 GB) no caben en el instalador (NSIS y GitHub no pasan de 2 GB por fichero), así
; que el instalador solo deja la marca `descargar-modelos` junto al ejecutable; al abrir EMMA,
; `main.cjs` la ve y el backend baja el paquete (`app/models_download.py`), con el progreso en
; «Modelos de IA». Marcada por defecto; en una instalación silenciosa (/S) no se descarga nada.
; El texto va en inglés, como el resto de la concha de escritorio (idioma de partida).

!ifndef BUILD_UNINSTALLER
  !include nsDialogs.nsh
  !include LogicLib.nsh

  Var EmmaModelsCheckbox
  Var EmmaModelsWanted

  !macro customPageAfterChangeDir
    Page custom EmmaModelsPageCreate EmmaModelsPageLeave
  !macroend

  Function EmmaModelsPageCreate
    nsDialogs::Create 1018
    Pop $0
    ${If} $0 == error
      Abort
    ${EndIf}
    ${NSD_CreateLabel} 0 0 100% 60u "EMMA works without its AI models, but the language models, speech transcription, CT segmentation and scanned report reading need them.$\r$\n$\r$\nThey are about 33 GB. If you tick the box, EMMA downloads them from GitHub the first time it opens (internet needed) and checks every file. You can also do it later from $\"AI models$\", or install them from a USB with instalar.cmd."
    Pop $0
    ${NSD_CreateCheckbox} 0 70u 100% 12u "Also download the AI models (about 33 GB)"
    Pop $EmmaModelsCheckbox
    ${NSD_Check} $EmmaModelsCheckbox
    nsDialogs::Show
  FunctionEnd

  Function EmmaModelsPageLeave
    ${NSD_GetState} $EmmaModelsCheckbox $EmmaModelsWanted
  FunctionEnd
!endif

!macro customInstall
  ${If} $EmmaModelsWanted == ${BST_CHECKED}
    FileOpen $0 "$INSTDIR\descargar-modelos" w
    FileWrite $0 "1"
    FileClose $0
  ${Else}
    Delete "$INSTDIR\descargar-modelos"
  ${EndIf}
!macroend
