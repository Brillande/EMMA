# Tecnologías de EMMA

Qué usamos y para qué. Las versiones exactas no se copian aquí (se desactualizarían): están en
`backend/pyproject.toml`, `frontend/package.json` y `desktop/package.json`.

## Interfaz (consola de tripulación y consola de Tierra)

- **React + TypeScript** : las dos consolas, la de a bordo y la de Tierra con el retardo de luz aplicado.
- **Vite** : servidor de desarrollo y compilación del frontend.
- **Vitest** : pruebas de la interfaz, entre ellas las reglas de NASA-STD-3001 Vol 2 Apéndice F.
- **uPlot** : gráficas de series fisiológicas en tiempo real.
- **three.js** : escenas 3D de la interfaz.
- **NiiVue** : visor 3D de volúmenes médicos (TAC/RM) de referencia, sobre el visor de Polaris.
- **MediaPipe Tasks Vision** : visión por computador en el navegador, sin nube.
- **Vosk (vosk-browser)** : reconocimiento de voz local en el navegador, sin red.
- **Web Bluetooth** : conexión directa con wearables BLE.
- **IBM Plex Sans / Mono** : tipografía de la consola, empaquetada (sin fuentes remotas).

## Servidor y análisis

- **Python** : lenguaje del backend.
- **FastAPI + Uvicorn** : API que sirve datos, análisis y recomendaciones a las dos consolas.
- **Pydantic / pydantic-settings** : validación de datos y configuración (`backend/.env`, prefijo `EMMA_`).
- **NumPy, Pandas, SciPy** : preprocesamiento de señales, línea base personal, tendencia y riesgo.
- **SQLAlchemy + SQLite** : almacén *append-only* de observaciones.
- **cryptography** : ledger de integridad, log encadenado por hash y firmado.
- **httpx** : cliente HTTP, siempre a través del control de salida `core/egress.py`.

## Estándares de datos de salud

- **HL7 FHIR R4 (fhir.resources)** : modelo canónico; todo dato entra como `Observation`.
- **LOINC** : códigos verificados de cada indicador; el resto, sistema propio justificado.
- **DICOM (pydicom)** : ecografía: lectura, calibración y des-identificación.
- **NIfTI (nibabel) + scikit-image** : volúmenes TAC/RM y mallas 3D (marching cubes).

## APIs externas y fuentes de NASA

Toda salida a internet pasa por `backend/app/core/egress.py`, con una lista blanca de hosts por
propósito; esa lista es la fuente de verdad. En modo sin red (`EMMA_OFFLINE=true`, el nominal de
misión) no sale nada y se trabaja con la caché.

Entorno espacial:

- **JPL Horizons** (`ssd.jpl.nasa.gov`, vía `astroquery.jplhorizons`) : efemérides para el tiempo
  de luz Tierra-nave.
- **SPICE de NAIF** (`naif.jpl.nasa.gov`, spiceypy, opcional) : se bajan los núcleos una vez y el
  tiempo de luz y la elongación solar se calculan en local, sin red.
- **NASA DONKI** (`api.nasa.gov`) : eventos de clima espacial.
- **CCMC iSWA** (`iswa.gsfc.nasa.gov`, HAPI, sin clave) : series de protones y viento solar.
- **SSCweb** (`sscweb.gsfc.nasa.gov`) : posición de la ISS para el perfil de órbita baja.
- **RadLab / DosTel** (`visualization.osdr.nasa.gov`) : dosis de radiación medida en vuelo.

Evidencia que citan las recomendaciones:

- **NASA OSDR** (`visualization.osdr.nasa.gov`) : ficha de los estudios citados; solo sale el
  identificador público del estudio (OSD-288…).
- **NASA Human Research Program (HRP)** : riesgos y evidencia del programa; se enlazan, no se
  consultan por API.
- **NASA NTRS** (`ntrs.nasa.gov`) : informes técnicos por su número.
- **Crossref, DataCite y doi.org** : comprueban que un DOI (el identificador permanente de un
  artículo o un dataset, p. ej. `10.5281/zenodo.7229547`) está registrado de verdad, para que no
  se cite nada mal copiado o inventado. Se pregunta en ese orden y solo cuenta como inexistente si
  los tres dicen que no; se recupera el título, no se descarga el artículo. Ocurre al firmar un
  borrador que cita una fuente (no bloquea la firma) y en las pruebas `live`; sin red, la cita
  queda «no comprobable», no falsa.
- **PubMed (NCBI E-utilities)** y **ClinicalTrials.gov** : artículos y ensayos citados.

Otras:

- **Zenodo** (`zenodo.org`) : solo los guiones de validación descargan datasets; la aplicación no.
- **ZenQuotes** y **Wikipedia «tal día como hoy»** (inglés y castellano) : cita y efemérides de la
  hoja diaria de Marplanner; solo salen la fecha y el idioma, y nunca en modo sin red.

## Documentos, imagen e IA local (todo sin nube)

- **Tesseract** : OCR local de informes escaneados.
- **pypdfium2, pypdf, ReportLab** : rasterizar, leer y generar PDF.
- **Pillow** : descodificar fotogramas de imagen y servirlos como PNG.
- **Transformers + PyTorch + Hugging Face Hub (entorno aparte, opcional)** : NER para
  des-identificar informes; el modelo se baja una vez con su huella comprobada.
- **Whisper + soundfile (entorno aparte, opcional, PyTorch en CPU)** : transcripción de voz local.
- **TotalSegmentator (entorno aparte, opcional)** : segmentación de órganos en TAC de referencia.
- **ONNX Runtime + tokenizers (modelo e5-small)** : búsqueda semántica local en la biblioteca.
- **Ollama (qwen3.5:9b)** : modelo de lenguaje local para el asistente en lenguaje natural y para
  los borradores de interpretación (Clase C, segregado).

## Código adoptado

- **Polaris** : herramientas clínicas y visor 3D, copiados literalmente (AGPL-3.0).
- **Marplanner (Node.js)** : planificador de rutinas y tareas, servicio local en loopback (MIT).
  Su pila: Fastify, Drizzle ORM + better-sqlite3, Zod, Schedule-X (calendario), Radix UI y Tailwind.
- **planner-bridge (Node.js)** : puente propio entre Marplanner y EMMA; lleva sus asientos al
  ledger y su salida a internet por el mismo control de egress.

## Escritorio y empaquetado

- **Node.js** : compila el frontend, Marplanner y el instalador, y ejecuta Marplanner y su
  resumen para la consola de Tierra.
- **Electron** : aplicación de escritorio que arranca el backend en loopback y abre la interfaz.
- **electron-builder (NSIS)** : instalador de Windows.
- **Actualizaciones de GitHub Releases (propias, sin electron-updater)** : solo con botón, el
  backend lee `emma-update.json` de la última versión de `Brillande/EMMA` y baja el instalador por
  `core/egress.py` (propósito `app-update`) comprobando su SHA-256; Electron lo vuelve a comprobar
  y lo lanza. Sin dependencias nuevas (`docs/actualizaciones.md`).
- **PyInstaller** : congela el backend en un ejecutable desde un venv limpio.
- **bleak (opcional)** : escucha de balizas BLE de la nave.

## Calidad y validación

- **pytest + respx (+ pytest-asyncio, pytest-cov)** : pruebas del backend sin red (respx simula
  las APIs), asíncronas y con cobertura.
- **Ruff + mypy --strict** : lint y tipado estricto.
- **Campañas de mutantes** : cada defensa tiene una prueba que la rompe a propósito.
- **Banco del asistente** (`scripts/assistant_bench.py`) : acierto y latencia del asistente sobre
  frases naturales, para comparar prompts, modelos o enrutados.
- **MMASH** : fisiología real de personas sanas en Tierra; falsa alarma y sensibilidad a
  deterioros inyectados (no valida fisiología espacial).
- **LifeSnaps (Fitbit, Zenodo, CC BY 4.0)** : validación de la línea base.
- **HC18** : medida guiada de ecografía.
- **Dataset de TotalSegmentator (Zenodo, CC BY 4.0)** : volúmenes de muestra; el Dice se mide
  solo con sujetos `test`.

## Datos y wearables

- **Simulador determinista** : fisiología de vuelo con cada parámetro clasificado por su evidencia.
- **Apple Health / Google Fit / BLE** : datos de wearables reales.
- **CSV / JSON** : datasets descargados, tablas y muestras que viajan en el paquete.

## Licencias

Todo el software que EMMA ejecuta o empaqueta es de código abierto (revisado el 2026-11-15 sobre lo
instalado, dependencias indirectas incluidas):

- **Librerías de Python y de npm** : MIT, BSD, Apache-2.0, ISC, PSF-2.0 o MPL-2.0 (`@resvg/resvg-js`,
  dentro de Marplanner). PyInstaller es GPL-2.0 con excepción para el ejecutable que produce.
- **EMMA** : AGPL-3.0-or-later, porque incorpora código de Polaris (AGPL-3.0); Marplanner es MIT.
- **Programas externos** : Tesseract y sus datos de idioma (Apache-2.0), Ollama (MIT),
  TotalSegmentator (Apache-2.0; EMMA solo usa tareas de pesos libres, ninguna de las que piden
  licencia aparte).
- **Modelos** : Qwen 3.5 (Apache-2.0), multilingual-e5-small (MIT), Whisper (MIT), MediaPipe Face
  Landmarker (Apache-2.0) y Vosk `small-es-0.42` (Apache-2.0). Los tres últimos van en el paquete
  con su aviso de licencia.
- **Fuentes tipográficas** : IBM Plex Sans y Mono (OFL-1.1).
- **Web Bluetooth** : estándar abierto del W3C (borrador de su grupo comunitario).

Excepciones que no son software nuestro ni van en el paquete:

- **Modelo NER `BSC-NLP4BIA/bsc-bio-ehr-es-contacto-anon`** : de acceso restringido; su licencia no
  se ha podido verificar (Hugging Face responde 401). La capa es opcional y está apagada sin él; su
  hermano público `bsc-bio-ehr-es-carmen-anon` es CC BY 4.0.
- **ZenQuotes** : API gratuita pero propietaria (solo para la cita del día de Marplanner).
- **Apple Health y Google Fit** : plataformas propietarias; EMMA solo importa los datos que el
  usuario exporta de ellas.
- **Servicios de NASA, NCBI y ClinicalTrials.gov** : datos públicos del Gobierno de EE. UU.;
  Crossref y DataCite publican sus metadatos como CC0; Wikipedia, CC BY-SA.
- **Datasets** : MMASH (ODbL 1.0), HC18, LifeSnaps y el de TotalSegmentator (los tres CC BY 4.0);
  ninguno viaja en el paquete.
