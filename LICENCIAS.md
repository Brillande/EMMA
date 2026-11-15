# Licencias

Resumen legible de la licencia de EMMA y de las licencias de todo lo que el repositorio usa. No
sustituye a los textos legales: el de EMMA está en [`LICENSE`](LICENSE), los avisos de terceros
incorporados en [`NOTICE`](NOTICE), y el texto completo de cada paquete que viaja en la aplicación
se genera al empaquetar (ver «Textos completos» al final).

Las licencias de las dependencias son las que **declara cada paquete en sus metadatos** (PyPI
`License`/`License-Expression`/clasificadores; npm `license` de su `package.json`), leídas el
2026-11-15 de las versiones instaladas. No se ha interpretado ninguna.

---

## La licencia de EMMA

EMMA es software libre bajo la **GNU Affero General Public License, versión 3 o posterior**
(`AGPL-3.0-or-later`). Texto completo: [`LICENSE`](LICENSE). Titular y avisos: [`NOTICE`](NOTICE).

- **Por qué AGPL:** EMMA incorpora código de Polaris, que es AGPL-3.0-or-later. Su obra derivada
  tiene que seguir bajo la misma licencia.
- **Qué implica:** puedes usar, estudiar, modificar y redistribuir EMMA. Si lo redistribuyes, o
  si ofreces una versión modificada a usuarios a través de una red, debes ofrecerles su código
  fuente bajo la misma licencia (AGPL §13) y conservar los avisos de copyright y licencia.
- **Sin garantía:** se distribuye «tal cual», sin garantía de ningún tipo (AGPL §15-16).
- **Ficheros con código de Polaris:** llevan `SPDX-License-Identifier: AGPL-3.0-or-later`, su
  fichero y commit de origen y qué se cambió (AGPL §5a). La lista está en `NOTICE`.
- `frontend/package.json` y `desktop/package.json` declaran también `AGPL-3.0-or-later`.
- La marca de EMMA (`desktop/build/brand/`) es obra propia del proyecto, con la misma licencia.

EMMA es una herramienta de apoyo a la decisión: no es un producto sanitario certificado, no
diagnostica ni prescribe, y no sustituye el juicio clínico. La licencia no cambia eso.

---

## Código de terceros copiado en el repositorio

| Proyecto | Dónde | Licencia | Avisos |
|---|---|---|---|
| Polaris (BeyondTheProtocol) | `polaris/` (copia literal) y ficheros adaptados listados en `NOTICE` | AGPL-3.0-or-later | `polaris/LICENSE`, `polaris/NOTICE`, `polaris/ORIGEN.md` |
| Marplanner (Diego Mariño) | `marplanner/` (copia literal) | MIT | `marplanner/LICENSE`, `marplanner/THIRD_PARTY_NOTICES.md` |

`planner-bridge/` es código de EMMA (AGPL-3.0-or-later) que une Marplanner con el backend.

---

## Backend (Python, `backend/pyproject.toml`)

### Dependencias de ejecución (viajan en la aplicación)

| Paquete | Versión instalada | Licencia declarada |
|---|---|---|
| fastapi | 0.141.1 | MIT |
| uvicorn | 0.53.0 | BSD-3-Clause |
| pydantic | 2.13.5 | MIT |
| pydantic-settings | 2.15.0 | MIT |
| fhir.resources | 8.3.0 | BSD |
| numpy | 2.5.3 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| pandas | 3.0.6 | BSD-3-Clause |
| scipy | 1.18.1 | BSD |
| httpx | 0.28.1 | BSD-3-Clause |
| astroquery | 0.4.11 | BSD |
| sqlalchemy | 2.0.54 | MIT |
| cryptography | 50.0.1 | Apache-2.0 OR BSD-3-Clause |
| pydicom | 3.0.2 | MIT |
| pillow | 12.3.0 | MIT-CMU |
| pypdfium2 | 5.13.0 | BSD-3-Clause, Apache-2.0 (y las de sus dependencias, PDFium) |
| nibabel | 5.4.2 | MIT |
| scikit-image | 0.26.0 | BSD |
| reportlab | 5.0.1 | BSD |
| pypdf | 6.19.0 | BSD-3-Clause |
| onnxruntime | 1.30.0 | MIT |
| tokenizers | 0.23.2 | Apache-2.0 |

### Extras opcionales

| Paquete | Extra | Licencia declarada |
|---|---|---|
| spiceypy 8.3.0 (incluye CSPICE de NAIF/JPL) | `spice` | MIT; CSPICE según las reglas de NAIF (detalle y aviso de exportación en `NOTICE`) |
| bleak | `anchors` | MIT (según `pyproject.toml`; no instalado aquí) |
| pyinstaller 6.22.3 | `desktop` (solo construye) | GPL-2.0-or-later con excepción que permite distribuir el ejecutable sin arrastrar la GPL |

### Herramientas de desarrollo (no viajan)

| Paquete | Licencia declarada |
|---|---|
| pytest 9.1.1 | MIT |
| pytest-asyncio 1.4.0 | Apache-2.0 |
| pytest-cov 7.1.0 | MIT |
| respx 0.23.1 | BSD-3-Clause |
| ruff 0.16.8 | MIT |
| mypy 2.3.1 | MIT |

---

## Interfaz (npm, `frontend/package.json`)

### Dependencias de ejecución (viajan en la aplicación)

| Paquete | Versión | Licencia declarada |
|---|---|---|
| react, react-dom | 19.3.0 | MIT |
| three | 0.186.1 | MIT |
| uplot | 1.6.32 | MIT |
| @niivue/niivue | 0.69.0 | BSD-2-Clause |
| @mediapipe/tasks-vision | 1.2.2 | Apache-2.0 |
| vosk-browser | 0.0.8 | Apache-2.0 |
| @fontsource/ibm-plex-sans, @fontsource/ibm-plex-mono | 5.3.0 | OFL-1.1 |

### Herramientas de desarrollo (no viajan)

| Paquete | Licencia declarada |
|---|---|
| vite 8.3.0 | MIT |
| vitest 5.0.1 | MIT |
| @vitejs/plugin-react 6.1.1 | MIT |
| typescript 7.0.2 | Apache-2.0 |
| @types/* | MIT |

---

## Aplicación de escritorio (`desktop/package.json`)

| Paquete | Versión | Licencia declarada | ¿Viaja? |
|---|---|---|---|
| electron | 44.4.5 | MIT (incluye Chromium y Node.js, con sus propios avisos) | Sí |
| electron-builder | 26.15.3 | MIT | No, solo construye |

---

## Modelos, datos y programas externos

Su licencia, origen y huella están en [`NOTICE`](NOTICE) y en
[`compliance/imaging-data-provenance.md`](compliance/imaging-data-provenance.md); la revisión
completa de fuentes, en [`docs/fuentes-y-procedencia.md`](docs/fuentes-y-procedencia.md). Resumen:

| Qué | Licencia |
|---|---|
| Modelo multilingual-e5-small (búsqueda semántica) | MIT |
| Modelo MediaPipe Face Landmarker | Apache-2.0 |
| Modelo Vosk vosk-model-small-es-0.42 | Apache-2.0 |
| BodyParts3D (obra derivada en `backend/app/data/anatomy/`) | CC BY 4.0 |
| Ecografías de ejemplo (pulmón, hígado) y TAC de ejemplo de TotalSegmentator | CC BY 4.0 |
| Datos de NASA (OSDR, DONKI) y registros de PubMed | Obras del Gobierno de EE. UU. |
| Núcleos SPICE de NAIF | Redistribución permitida sin modificar (reglas de NAIF) |
| TotalSegmentator, tesseract (externos; van en el paquete de modelos, no en el instalador) | Apache-2.0 |
| Ollama (externo; va en el paquete de modelos con los modelos configurados) | MIT; los modelos locales, cada uno la suya (ver `docs/fuentes-y-procedencia.md`) |

---

## Textos completos

Las licencias MIT, BSD, Apache-2.0 y OFL piden que su texto acompañe a la redistribución. Por eso
el empaquetado los genera a partir de lo que trae cada paquete, sin resumirlos:

- **Backend:** `backend/packaging/third_party.py`, desde `freeze.py`, con todas las dependencias
  transitivas del ejecutable.
- **Interfaz:** `frontend/scripts/third-party.mjs` escribe `dist/THIRD_PARTY_LICENSES.txt` al
  compilar.
- **Modelos y fuentes de `frontend/public/`:** su licencia y su `ORIGEN.txt` van al lado.

Esta tabla cubre las dependencias **directas**; las transitivas están en esos ficheros generados.
Si añades o actualizas una dependencia, actualiza también esta página.
