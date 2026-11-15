# Polaris, copiado tal cual

SPDX-License-Identifier: AGPL-3.0-or-later

`tools/`, `tests/`, `evals/` y `docs/` son copia **byte a byte** de Polaris
(github.com/BeyondTheProtocol/polaris, commit `20527939e00b9ebc063a0024210e6f9df663d989`,
AGPL-3.0-or-later), sacada de los objetos de git del commit (no de una copia de trabajo, que en
Windows se convierte a CRLF). Hasta el 2026-10-01 era el commit `7bf4725`; Polaris se republicó
sin historia común y la copia pasó a `e3b588d` (qué cambió: `docs/polaris-divergencias.md` §12).
El 2026-10-04 pasó de `e3b588d` a `0e629e4` (§15 del mismo documento) y el 2026-10-07 a `849989f`
(§17: solo cambia `tools/normas.json`). El 2026-10-08 pasó a `2052793` (§18: cambian `tools/salida.py`
y `tools/visor3d.py`, en funciones que EMMA no llama) y entraron 35 herramientas locales más, sin
uso; el 2026-10-09 se retiraron cuatro de ellas (§18, «Remate»). El commit vigente lo fija
`ADOPTADO.txt`; `backend/tests/test_polaris_copy.py` falla si este párrafo cita otro.

**Regla del proyecto:** adoptar Polaris es copiarlo tal cual. Los cambios se deciden después, uno a
uno, con el usuario, y se anotan abajo como cambios (AGPL §5a). Nada de EMMA vive en esta carpeta.

- `ADOPTADO.txt`: qué herramientas se piden. `backend/scripts/polaris_sync.py` copia esas y todas
  las que importan (cierre de imports), más los datos que leen.
- `MANIFEST.sha256`: la huella de cada fichero. `backend/tests/test_polaris_copy.py` falla si uno
  cambia, falta o sobra.
- `LICENSE`, `NOTICE`, `CITATION.cff`, `README.md` y `CHANGELOG.md`: los de Polaris, sin tocar. Sus
  avisos legales viajan con su código (AGPL) y `CITATION.cff` es cómo pide que se le cite. Su
  `CLAUDE.md` y su `AGENTS.md` **no** se copian a propósito: son instrucciones para el asistente
  de su autora, y Claude Code las cargaría al trabajar aquí (lo vigila `test_polaris_copy.py`).
- `ESTADO.md`: qué herramientas cargan en esta máquina, el motivo de las que no, y qué pegamento
  de `compat/` hay (lo genera `backend/scripts/polaris_estado.py`; no se edita a mano).
- `tests/`: las pruebas de Polaris que solo usan lo copiado (`tests auto` en `ADOPTADO.txt`), con
  sus ayudantes y campañas de mutantes; `evals/`: sus conjuntos de evaluación; `docs/`: dos
  documentos suyos sobre lo copiado. No viajan en el instalador.
- `PRUEBAS.md`: el resultado de esas pruebas aquí, sin red y con el adaptador de EMMA
  (`backend/scripts/polaris_tests.py`, con `--mutantes` también sus campañas). No entran en la
  suite de EMMA: un rojo es información para decidir, no se arregla tocando la copia.

## Pegamento de EMMA, fuera de esta carpeta

- `backend/app/polaris/`: único punto de entrada. Fija `BTP_REPO`/`BTP_STATE_DIR` a un directorio de
  estado de EMMA (Polaris no escribe fuera de él) y `BTP_PERIPHERIES` a un registro que genera en
  ese directorio con un solo cerebro: el `local-ollama` de Polaris, con la URL y el modelo de EMMA.
  En Windows pone su carpeta `compat/` al final de `sys.path`. Ahí está lo que a la copia le falta
  fuera de Unix y macOS, módulo a módulo (qué es cada uno lo dice su docstring y lo lista
  `ESTADO.md`; `backend/tests/test_polaris_texts.py` falla si aquí falta alguno):
  - `compat/fcntl.py`: el `fcntl.flock` que importan las herramientas.
  - `compat/memguard.py`: las mediciones de `guarda_memoria` con la API de Windows.
  - `compat/winlock.py`: la sonda de proceso y el soltar del candado de `_lock`.
  - `compat/resource.py` y `compat/sitecustomize.py`: solo para las pruebas de la copia
    (`backend/scripts/polaris_tests.py` pone la carpeta en su `PYTHONPATH`): el `resource` que
    importa una de ellas, y el arranque que activa `winlock` en sus procesos.
- `frontend/scripts/build-polaris.mjs`: compila `tools/visor3d_web` con su propio lockfile.
- `backend/app/volumes/polaris_web.py`: sirve ese visor con los datos del ledger.

## Cambios

Solo los que decide el usuario, uno a uno. Cada uno está en `CAMBIOS.json` (fichero, fecha, motivo
y el texto exacto antes y después), lo aplica `polaris_sync.py` tras copiar el original, el
manifiesto guarda al lado la huella del original, y el fichero lleva dentro el aviso
"Modificado por EMMA" (AGPL §5a).

- `tools/visor3d_web/index.html`, `tools/visor3d_web/main.js` y `tools/visor3d_web/render.js`
  (2026-09-29): colores y textos de EMMA en el visor del preset hígado. Lesión candidata en
  amarillo y seleccionada en verde, en vez de coral y amarillo (NASA-STD-3001 Vol 2 F.5-1); el
  cursor en verde; fuera los textos del caso original (TC portal, informe y marcas del
  radiólogo, PET) y las columnas vacías que los mostraban. La forma, el render y la lógica son
  los de Polaris.
- `tools/deid.py` (2026-10-01): `_python_ner()` busca también `Scripts/python.exe`, la ruta del
  Python de un entorno virtual en Windows; sin ello la capa NER, que el usuario decidió instalar,
  se daba siempre por no disponible. El resto del fichero es el de Polaris.
- `tools/transcribe_audios.py` (2026-10-01): `SRC` y `OUT` se pueden dar por variable de entorno
  (`BTP_AUDIO_SRC`, `BTP_AUDIO_OUT`); sin ellas, los valores de siempre. Sin esto escribía dentro
  de `polaris/`. El resto del fichero es el de Polaris.
- `tools/estado_actual.py` (2026-10-20): la orden `cotejado` importaba `fecha_cotejo` de la prueba
  `tests/test_perfil_clinico_al_dia.py`, y las pruebas no viajan con la aplicación instalada, así
  que allí fallaría. La función, tal cual, pasa a la herramienta y `cotejado` deja de importar la
  prueba (que sigue con la suya, sin tocar); el propio docstring de la herramienta ya lo dice: «Un
  test no se importa desde `tools/`; al revés sí». El fichero lleva además su línea SPDX. El resto
  es el de Polaris.
