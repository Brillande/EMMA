# CLAUDE.md — EMMA

Monitorización autónoma de salud para misiones de larga duración. NASA Space Apps 2026.
Python/FastAPI + React/TS. El README explica **qué** es el proyecto; este archivo dice
**cómo se trabaja en él y qué no se puede romper**.

**Canario: cada respuesta al usuario empieza con su nombre, «Ellande».** Lo pidió él
(2026-10-06) para comprobar de un vistazo que estas instrucciones están cargadas: una respuesta
sin su nombre al principio significa que este archivo no se ha leído, y entonces tampoco valen
las reglas de abajo (entre ellas, no publicar nada sin que él lo pida). Va en todas las respuestas, también en las cortas.

Lee esto entero antes de tocar código. Varias reglas de abajo son contraintuitivas y ya
costaron reescrituras.

**Este archivo no lleva cifras que cambien con el código** —cuentas de indicadores, métricas de
validación, número de tests—. Para eso apunta a su fuente de verdad. Un documento de reglas
desactualizado es peor que no tener ninguno.

**Memoria entre sesiones: vault de Obsidian `C:\Users\tidus\Desktop\EMMA-memoria`** (fuera del
repo, decisión del usuario 2026-11-08). Al empezar, lee su `Inicio.md`, `Estado actual.md` y
`Decisiones del usuario.md`; al terminar un trabajo, actualiza el estado y anota decisiones y
trampas nuevas con fecha. Las reglas siguen siendo las de este archivo: si la memoria y esto
chocan, manda esto.

---

## Comandos

```bash
cd backend
python -m venv .venv && .venv/Scripts/python.exe -m pip install -e ".[dev]"   # solo la primera vez
.venv/Scripts/python.exe -m pytest tests/ -q     # suite normal — NO toca la red
.venv/Scripts/python.exe -m pytest tests/test_ledger.py -q            # un fichero
.venv/Scripts/python.exe -m pytest tests/test_ledger.py -k nombre -q  # una prueba
.venv/Scripts/python.exe -m pytest -m live       # contratos contra APIs de NASA
.venv/Scripts/python.exe -m pytest -m external   # validación con fisiología humana real
.venv/Scripts/python.exe scripts/mutants.py tests/mutants/*.json   # cada defensa tiene su prueba
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m mypy app
.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

```bash
cd frontend
npm test                 # reglas de NASA-STD-3001 Vol 2 Apéndice F como pruebas
npx vitest run src/lib/palette.test.ts   # un fichero
npm run typecheck
npm run dev              # :5173, con proxy /api -> backend en :8000
npm run build            # compila antes el visor de Polaris (scripts/build-polaris.mjs)

cd desktop
npm run dist             # instalador de Windows en desktop/release/
```

Windows: usa `.venv/Scripts/python.exe`, no `python` a secas. Las puertas de calidad son
`ruff` limpio y `mypy --strict` limpio; ambas están en verde y así se quedan. En el frontend,
`tsc` limpio y `npm test` en verde.

`pyproject.toml` excluye `live` y `external` por defecto (`addopts`); las `external` necesitan
antes su dataset (`scripts/fetch_mmash.py`, `scripts/fetch_hc18.py`, que descargan a `data/`,
fuera de git). La configuración va en `backend/.env` con prefijo `EMMA_` (plantilla en
`.env.example`); `EMMA_OFFLINE=true` es el modo nominal de misión, no uno degradado.

**La interfaz tiene sus propias reglas, con prueba:** todo color sale de `frontend/src/lib/palette.ts`
(contraste ≥ 6:1, significados de la tabla F.5-1: el cian es "dato caducado o ausente" y el gris "no
disponible", no decoración), y toda cifra pasa por `lib/format.ts`. La interfaz **no redacta texto
clínico**: lo muestra tal cual lo da el backend. Detalle en `compliance/hmi-state-of-the-art.md`.
Una excepción declarada (decisión del usuario, 2026-11-07, §2.5 de ese documento): el adorno de la
maqueta que hoy es la concha de la consola —fondo, planetas, astronauta, acentos por letra RIDGE y
por sección (2026-11-08), dibujos de sección y
el cuerpo de «Inicio», cuyos colores muestreados viven en `dashboard/referenceBody.generated.ts`—
no significa nada y no sigue la tabla; lo que es dato conserva su color, su forma y su palabra.

**El backend de escritorio se congela desde un venv limpio** (`backend/packaging/freeze.py`), nunca
desde `.venv`: con pytest presente el empaquetado falla, y lo entregado no debe llevar herramientas
de prueba.

---

## Invariantes — romper una de estas es un fallo, no una preferencia

**1. No se inventan códigos LOINC.** Cada código LOINC del catálogo está verificado en su
ficha oficial. El resto usa el sistema propio `https://emma.mission/codes` y **cada uno declara
por qué** no puede usar un estándar. La suite comprueba esa invariante: añadir un indicador sin
justificación hace fallar los tests. Es deliberado. El reparto vigente entre ambos sistemas lo
da `/api/indicators`; no lo copies aquí.

**2. La unidad sigue a la propiedad LOINC.** LOINC separa *Mass/volume* de *Moles/volume* con
códigos distintos. 2142-8 (cortisol salival) es Mass/volume → µg/dL, **no** nmol/L. Adoptar un
código con la familia de unidades equivocada es un error semántico silencioso: compila, pasa
tests y miente.

**3. Los tests no tocan la red.** La suite de API corre con el modo offline forzado: si algo
saliera a internet, falla. No metas llamadas reales en tests sin marcar; usa `respx`. Lo que
necesite red va marcado `live` o `external` y queda fuera de la suite por defecto.

**3 bis. Toda salida a internet pasa por `backend/app/core/egress.py`.** Lista blanca por
propósito, modo sin red y modo seguro en un solo sitio, y el control de borde de Polaris sobre lo
que sale. Un cliente HTTP nuevo se construye con `egress.get` o `egress.client`, nunca con
`httpx`/`requests` a pelo.

**4. Toda observación pasa por el ledger.** No existe —ni debe existir— un endpoint que
persista una observación saltándose el log encadenado y firmado. Si añades una vía de ingesta,
va por el ledger. La auditoría es propiedad impuesta por el código, no una promesa del README.

**5. Los dos ejes de validación se mueven juntos.** Tasa de falsa alarma sobre sujetos sanos
**y** sensibilidad sobre deterioros inyectados sobre esa misma fisiología real. Ambas tienen
prueba de regresión. Nunca optimices una sola: se llega al 0 % de falsas alarmas apagando el
sistema, **y eso ya pasó durante el desarrollo**. Si tocas umbrales, línea base o riesgo,
reporta las dos métricas juntas. Cifras vigentes en `compliance/external-validation.md` y en
los tests `-m external`, que son la fuente de verdad.

**6. El alcance se declara con precisión.** "Desarrollado **conforme a** IEC 62304 Clase B, con
el borrador de interpretación por modelo de lenguaje (`app/interpret/`) en Clase C por
elemento". La segregación que lo permite es un supuesto con prueba: un borrador nunca entra en
el análisis ni en una alerta (`software-safety-classification.md` §2.1). Nunca "certificado": la certificación la emite un organismo notificado sobre una organización
con SGC auditado, y este proyecto no la reclama. Igual con todo lo demás — el valor del
proyecto ante un jurado está en que no exagera.

**7. Apoyo a la decisión, no prescripción.** El sistema informa y recomienda; no administra
terapia ni sustituye juicio clínico. Ningún texto de salida debe sonar a orden médica.

---

## Contexto de producto — toda mejora se contrasta con él

`docs/contexto/` guarda la especificación técnica del equipo (v1.1), su base de conocimiento y la
conversación de ideación. **Antes de proponer o implementar una mejora, léela y comprueba que
cumple la especificación** (principios §2, modelo de dominio §3, criterios de aceptación §14).
`docs/contexto/README.md` lleva la comparación con EMMA y los huecos abiertos: actualízalo en el
mismo cambio que cierre uno. Si la especificación y una invariante de arriba chocan, manda la
invariante.

---

## Minas conocidas — premisas falsas ya investigadas, no las reintroduzcas

- **`astroquery` no es un backend de salud.** Es un cliente de catálogos astronómicos, cero
  datos biomédicos. Único uso legítimo: `astroquery.jplhorizons` para el tiempo de luz — que
  da la casualidad de ser el parámetro que sostiene toda la autonomía del sistema.
- **OSD-288 no son datos de astronautas.** Es RNA-Seq de bazo de 12 ratones tras 35 días en la
  ISS. Sirve como respaldo inmunológico y la API lo declara con esas palabras. No es telemetría.
- **No existe API pública de constantes vitales de astronautas.** Son datos médicos protegidos.
  Si alguien propone "conectar con la API de vitales de la NASA", no existe. Los datos vienen
  del simulador determinista y de wearables reales (BLE / Apple Health / Google Fit).
- **MMASH no valida fisiología espacial.** 22 personas sanas, 24 h, en Tierra. Valida el motor
  de medida y la tasa de falsa alarma. Presentarlo como validación de la deriva de vuelo sería
  mentir.
- **TotalSegmentator se mide solo con sujetos `test` de su dataset.** Se entrenó con los de
  `train`/`val`: medido con ellos, el Dice sale alto y no valida nada (pasó: 0,986-0,992 en
  `train`). `tests/test_volumes_external.py` filtra por el reparto de `meta.csv`.
- **Hoy no vuela ningún TAC.** En la ISS la única imagen médica es la ecografía; un TAC con gantry
  giratorio transmite par a la nave. Hay prototipos de TAC estacionario y rayos X portátiles en
  estudio para exploración, no equipos de vuelo. No escribas "en la nave nunca habrá TAC" ni lo
  contrario. El visor 3D (de Polaris) es para imagen de referencia previa al vuelo y para Tierra;
  no lo presentes como diagnóstico a bordo. TotalSegmentator es un programa externo
  (`backend/.venv-seg`, pesos en `~/.totalsegmentator`, telemetría apagada) y no se empaqueta.
- **Dosis de radiación: el factor de calidad no es 1.** Integrar con Q = 1 subestima la dosis
  equivalente ~2,5×. Verificado contra DosTel: 0,272 mSv/día con Q=1 (por debajo del rango
  documentado 0,3-0,8 de la ISS) frente a 0,647 con el Q medio medido en vuelo.

---

## Cómo se justifica lo que se afirma

Todo parámetro del modelo del simulador declara su respaldo en tres clases: **magnitud
documentada**, **sentido documentado**, o **contestado** (los estudios discrepan). Se expone en
`/api/status` → `simulation.evidence`. Si añades un parámetro de deriva, clasifícalo. Si no
encuentras respaldo, se marca como tal — no se inventa una cita.

La revisión bibliográfica ya corrigió tres errores reales (la caída de SDNN en vuelo **no** está
respaldada; la deriva de FC en reposo era el doble de lo observado; el Q de radiación). Asume
que el siguiente parámetro sin verificar también está mal.

---

## Estructura

```
backend/app/
  core/        ledger de integridad, caché, config, storage
  ingest/      catálogo de códigos, FHIR, simulador, wearable, PVT
  environment/ efemérides (JPL), DONKI, RadLab
  analysis/    línea base, tendencia, riesgo
  advisor/     recomendaciones
  pain/        mapa corporal de dolor (zonas y tipos declarados aquí, no en la interfaz)
  evidence/    enlaces a HRP y OSDR, gradación de evidencia y comprobación de citas
  imaging/     ecografía: DICOM, protocolos, medida guiada, fantomas
  volumes/     TAC/RM y visor 3D, sobre `visor3d` de Polaris
  reports/     informes escaneados: OCR local y des-identificación
  interpret/   borrador con modelo local (Clase C, segregado: invariante 6)
  polaris/     único punto de entrada al código de `polaris/` (`load`, `inventory`,
               `console.captured`); `compat/` = lo que a la copia le falta en Windows
  validation/  MMASH, inyección de deterioros, informe
  api/         rutas FastAPI
  data/        datos que viajan en el paquete (muestras, tablas JSON, visor compilado)
  *.py         módulos sueltos: casi todos dan datos de EMMA a una herramienta de Polaris
backend/spikes/   validación de APIs externas + HALLAZGOS.md
backend/tests/mutants/  campañas de mutantes: una por defensa
polaris/          copia literal de Polaris — no se edita a mano (ver Convenciones)
data/             datasets descargados y caché de APIs; fuera de git salvo excepciones
compliance/       documentación normativa — se actualiza CON el código, no después
frontend/         React/TS: consola de tripulación y consola de Tierra (con el retardo aplicado)
desktop/          Electron: arranca el backend congelado en loopback y abre la interfaz
```

**El camino de un dato:** `ingest/` lo normaliza a FHIR R4 `Observation` → `core/` lo anexa al
ledger y al almacén *append-only* → `analysis/` lo compara con la línea base personal y la
tendencia, y el riesgo se escala con el tiempo de luz de `environment/` → `advisor/` recomienda
citando `evidence/` → `api/` lo sirve a las dos consolas. Las medidas de ecografía y la
intensidad del dolor entran por ese mismo camino como observaciones del catálogo; lo que redacta
`interpret/` no entra nunca.

**Hay cuatro entornos de Python y no se mezclan:** `.venv` (EMMA), `.venv-seg` (TotalSegmentator),
`.venv-voice` (Whisper, `scripts/install_voice.py`) y `.venv-deid` (`scripts/install_deid_ner.py`).
Los tres últimos son opcionales y pesados: no se instalan con `.[dev]`, y lo que depende de ellos
tiene que declararse no disponible cuando faltan, no romper el arranque.

`compliance/` no es decorado: `record-integrity.md` es la **especificación** que implementa
`core/ledger.py`, y una divergencia entre ambos es un fallo de cumplimiento, no un desajuste de
documentación. Si cambias el ledger, actualiza el documento en el mismo cambio.

---

## Convenciones

- **EMMA está publicada en GitHub, como foto sin historia; este repositorio de trabajo sigue sin
  remoto.** Hasta el 2026-11-15 la regla era «solo local, no se sube nada» (decisión del usuario,
  2026-10-06). Ese día el usuario pidió subirla («súbemelo a mi github») y cambiar la regla: el
  repositorio público es `github.com/Brillande/EMMA`. Lo que se publica es **un commit único con
  el estado de la rama, no la historia**: la historia lleva un fichero de más de 100 MB
  (`backend/app/data/kb-model/*.onnx`, que en la foto va por Git LFS) y el correo personal del
  autor en cada commit. La foto se arma en una carpeta aparte, fuera de este repositorio
  (`C:\Users\tidus\Desktop\EMMA-github`), con el correo privado de GitHub.
  Por eso aquí **no se añade remoto ni se hace `git push`**, y el gancho `pre-push` se queda: una
  subida desde este repositorio publicaría la historia entera. Publicar una versión nueva es
  rehacer la foto, y solo cuando el usuario lo pide de forma explícita; nada de pull requests,
  gists ni otros servicios por iniciativa propia, aunque una orden o una herramienta lo proponga
  (`/batch` incluida: trabaja en ramas y copias locales).
- Español en comentarios, docstrings y documentación. Código en inglés.
- Los módulos explican **por qué** existen, no qué hacen. Mantén ese registro: varios empiezan
  con un bloque que cuenta el problema real que resuelven.
- Cambios pequeños y atómicos. Tras editar, corre lint y tests.
- **Licencia AGPL-3.0-or-later** (`LICENSE`, `NOTICE`), porque EMMA incorpora código de Polaris.
  Todo fichero con código de Polaris lleva `SPDX-License-Identifier: AGPL-3.0-or-later`, el fichero
  y commit de origen y qué se cambió (AGPL §5a); si portas algo más, añádelo también a `NOTICE`.
  Datos de terceros conservan su licencia: no los metas en el paquete sin la suya compatible.
- **Adoptar código de Polaris es copiarlo literal primero.** Los cambios (paleta, sin nube,
  ledger…) se deciden después con el usuario, uno a uno, y se anotan como cambios §5a. La
  primera adopción del visor 3D se "adaptó" al portarla y quedó peor que el original. La copia
  vive en `polaris/` (raíz), la hace `backend/scripts/polaris_sync.py` desde los objetos de git
  del commit (no desde una copia de trabajo: en Windows sale en CRLF) y la vigila
  `tests/test_polaris_copy.py`. EMMA entra solo por `app/polaris` (`load`, `inventory`); nada de
  EMMA se escribe dentro de `polaris/` salvo sus informes generados (`ESTADO.md`, `PRUEBAS.md`).
  Las pruebas de Polaris se corren aparte (`scripts/polaris_tests.py`, sin red), nunca en la
  suite de EMMA; lo pendiente de decidir está en `docs/polaris-divergencias.md`. El "cerebro" de Polaris es Ollama local; lo clínico lo
  niega por umbral de capacidad, y subirlo es decisión del usuario.
- **La consola de Polaris se captura en un solo sitio.** Quien necesite quitarle o leerle la
  consola a una herramienta de Polaris usa `app.polaris.console.captured()`; nunca
  `redirect_stdout`/`redirect_stderr` ni `sys.stdout =` propios en `app/` (lo vigila
  `tests/test_polaris_console.py`). Orden de cerrojos: primero el del adaptador, después el de
  consola.
- **Dentro de `polaris/` no se genera nada.** El visor web se compila fuera, en una carpeta
  temporal (`frontend/scripts/build-polaris.mjs`); un `node_modules` o un `dist` en la copia hace
  fallar `tests/test_polaris_copy.py`. Lo que a la copia le falta en Windows va en
  `backend/app/polaris/compat/`, no en ella; y una herramienta que hace algo solo con importarse
  se declara en `NOT_IMPORTED` (`app/polaris`) para que el inventario no la importe.
- **Añadir o actualizar algo de Polaris:** línea `root`/`data`/`test <fichero>` en
  `polaris/ADOPTADO.txt`, `scripts/polaris_sync.py <clon>` y después
  `scripts/polaris_left_out.py <clon>` (toda herramienta de Polaris está o copiada o nombrada
  fuera, con su motivo). Antes de copiar una herramienta se lee su código, no solo su docstring.
  El clon es local y de solo lectura; su ruta está en `docs/polaris-divergencias.md` §18. Una
  herramienta que EMMA llame se declara en `EMMA_USES` y recibe fila en la ficha de SOUP.
- El repo se edita en paralelo por varias sesiones. Antes de un cambio grande, comprueba si el
  archivo se ha movido bajo tus pies.
