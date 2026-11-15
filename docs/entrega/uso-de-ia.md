# Uso de inteligencia artificial (ES / EN)

**Por qué existe este texto.** Las preguntas frecuentes de Space Apps 2026 exigen que la entrega
«must include a description of how SI tools were used during the development of their project»
(ficha `space-apps-2026-participant-faqs` en `backend/app/data/evidence_refs.json`; SI es el nombre
que esa página da a la inteligencia artificial). `compliance/challenge-coverage.md` §4 lo marca
como asunto **del equipo**: el software no lo puede cubrir.

Borrador del 2026-11-02, puesto al día el 2026-11-05. Lo escribió un asistente de código a partir del repositorio, y por eso
**lo que solo sabe el equipo va en huecos [EQUIPO: …]** que hay que rellenar o borrar antes de
entregar. No se ha inventado ningún uso: cada línea dice de dónde sale.

Dos cosas distintas que no se mezclan:

- **A. IA usada para desarrollar EMMA** (lo que pide la regla del concurso).
- **B. IA que forma parte de EMMA** (funciones del producto, que corren en local en la nave).

---

## Castellano

### A. IA usada para desarrollar EMMA

**1. Ideación y especificación: un asistente conversacional de IA.**
El equipo exploró los retos de Space Apps con un asistente conversacional. Esa conversación
(`docs/contexto/conversacion-ideacion-v1.md`) analizó el reto, propuso la arquitectura de gemelos
(astronauta, hábitat, misión, contramedidas) y redactó, a petición del equipo, la especificación
técnica v1.1 (`docs/contexto/especificacion-tecnica-v1.1.md`) y la base de conocimiento
(`docs/contexto/knowledge-base-v1.md`) que se dieron después al asistente de código como contexto.
[EQUIPO: nombre y versión de la herramienta (p. ej. ChatGPT), fechas, y qué decidió o escribió el
equipo frente a lo que propuso la herramienta.]

**2. Implementación, pruebas, documentación y revisión: Claude Code (Anthropic).**
Casi todo el código y la documentación de EMMA se escribió con Claude Code como asistente de
programación: 830 de los 869 commits del repositorio llevan la línea `Co-Authored-By: Claude …`
(`git log`, contado el 2026-11-05), con los modelos Claude Opus 5.5 y Claude Fable 5.1. Desde el
2026-11-03 se trabajó sobre todo con varios agentes de Claude Code en paralelo, cada uno en su
propia copia de trabajo de git (local) y con un encargo acotado, y con agentes aparte que revisaban
cada cambio antes de fusionarlo; la fusión y las decisiones siguieron siendo de la persona. Se usó
para:

- escribir el backend (Python/FastAPI), la interfaz (React/TypeScript) y la aplicación de
  escritorio (Electron), con sus pruebas;
- escribir los documentos de `compliance/` y mantenerlos al día con el código;
- leer fuentes publicadas (fichas de LOINC, páginas de NASA, artículos) y registrar en cada ficha
  qué se leyó, cuándo y con qué cita literal, o marcarla «sin verificar» si no se leyó;
- revisar el propio código de forma adversaria (revisiones que buscan fallos y afirmaciones sin
  respaldo);
- redactar borradores de los textos de la entrega, entre ellos este.

Cómo se controló lo que escribía la IA:

- **Reglas escritas que la IA tiene que cumplir** (`CLAUDE.md`): no inventar códigos LOINC, la unidad
  sigue a la propiedad LOINC, las pruebas no tocan la red, toda observación pasa por el registro
  firmado, falsa alarma y sensibilidad se reportan juntas, el alcance se declara con precisión, y
  ningún texto suena a orden médica.
- **Las reglas tienen prueba.** La suite falla si se añade un indicador sin justificar su código; las
  puertas de calidad (`ruff`, `mypy --strict`, `tsc`, `npm test`) se mantienen en verde; y las
  campañas de mutantes (`backend/scripts/mutants.py`, `backend/tests/mutants/`) comprueban que cada
  defensa tiene una prueba que la vigila.
- **Las decisiones son del equipo.** Umbrales, cambios del motor y adopciones quedan escritos como
  «decisión del usuario» con su fecha (por ejemplo, en `compliance/external-validation.md`); lo que
  la IA midió y el equipo no adoptó queda «medido y sin adoptar».
- **La validación es contra datos reales, no contra lo que la IA genera:** MMASH y LifeSnaps
  (fisiología humana real, en Tierra) y HC18 (ecografía), en `compliance/external-validation.md`.
- **Errores que la revisión encontró y se corrigieron**, también de la propia IA: la caída de SDNN en
  vuelo no estaba respaldada, la deriva de la frecuencia cardiaca en reposo era el doble de lo
  observado, y la dosis de radiación se integraba con factor de calidad 1 (`CLAUDE.md`).
- **Nada sale del equipo:** el repositorio es solo local, sin remoto, y un gancho `pre-push` rechaza
  cualquier subida.

[EQUIPO: quién revisó qué; si alguna parte se escribió sin asistente.]

**3. Transcripción de las notas de voz del equipo: Whisper, en local.**
Las 14 notas de voz del equipo del 2026-11-02 se transcribieron en el propio ordenador con Whisper
(modelo `base`), sin enviar el audio a ningún servicio, y se cruzaron con el código para ordenar las
prioridades del evento (`docs/contexto/prioridades-evento.md`).

**4. Logotipo e icono: dibujados como código, sin generador de imágenes.**
El borrador de marca (`desktop/build/brand/`, tres candidatas y su hoja de contactos) lo escribió
Claude Code el 2026-11-04 como SVG a mano —coordenadas y trazos en texto, con los colores de
`frontend/src/lib/palette.ts`—, y la versión de 16 px se dibujó píxel a píxel. No se usó ningún
generador de imágenes. Es un borrador: la candidata C está conectada al instalador, pero adoptarla
o sustituirla es del equipo (`desktop/build/brand/README.md`). [EQUIPO: confirmar qué marca se
adopta, o si se sustituye por una propia.]

**5. Ajuste fino del modelo del asistente: probado en local y no adoptado.**
El 2026-11-04 y 05 se probó un ajuste fino LoRA de Qwen3.5-9B, el modelo del asistente de voz, en el
propio ordenador. Los ejemplos de entrenamiento los genera el código de EMMA
(`backend/scripts/assistant_train_data.py`): la respuesta objetivo la compone EMMA —plantillas,
lecturas y textos fijos del turno—, nunca un modelo; un ejemplo solo se queda si el turno entero
pasa las cuatro barreras del asistente, y la batería de evaluación de 198 frases queda fuera del
entrenamiento, con la comprobación de que no se solapa. El entrenamiento y la evaluación se hicieron
con herramientas fuera del repositorio. Resultado: el modelo ajustado acertó 191 de 198 frente a
192 de 198 del modelo sin ajustar, así que **no se adoptó**; EMMA usa `qwen3.5:9b` tal cual.

**6. Otros usos.**
[EQUIPO: cualquier otra herramienta de IA usada en el desarrollo o en la entrega —generación o
retoque de imágenes, traducción, voz o subtítulos del vídeo, música—, o borrar este punto si no hubo
ninguna.]

### B. IA que forma parte de EMMA (funciones del producto)

Todas corren **en local**; ninguna envía datos clínicos fuera. Las que necesitan un entorno aparte
son opcionales: si faltan, EMMA lo dice y sigue funcionando.

| Función | Qué modelo | Dónde | Límite |
|---|---|---|---|
| Asistente de voz «EMMA» | `qwen3.5:9b` con la API de Ollama, solo en loopback | `backend/app/assistant/`, `frontend/src/assistant/` | **Clase C** (`compliance/software-safety-classification.md` §2.2): elige una intención de un catálogo cerrado; cada respuesta pasa cuatro barreras deterministas (linter de lenguaje, cifras que salen del contexto, no recetar y esquema) y, si una falla, habla un texto fijo del backend; **no firma nada**: lo que propone escribir lo firma una persona tras confirmarlo, y no entra en el análisis ni en una alerta |
| Escucha de la palabra «EMMA» | Vosk (`vosk-model-small-es-0.42`) con `vosk-browser`, en el navegador | `frontend/src/assistant/wake/` | Gramática cerrada: solo sabe cuándo empieza una frase, no la transcribe. Sin red (guarda en el trabajador) |
| Transcripción de lo que se le dice al asistente | El propio modelo del asistente si oye (p. ej. `gemma4:e4b`, Ollama en loopback); si no, Whisper, en el backend | `backend/app/api/assistant.py` (`_hear`), `backend/app/interpret/llm.py` (`transcribe`), `backend/app/assistant/audio.py` | `EMMA_ASSISTANT_HEARING` (`auto` o `whisper`). Whisper va en un entorno aparte y opcional; sin nadie que oiga, el asistente se usa por teclado |
| Vista que gira siguiendo la cara | MediaPipe Face Landmarker (`face_landmarker.task`), en el navegador | `frontend/src/lib/faceCamera.ts` | **Demostración sin validar**: solo gira la vista de una consola; no toca el registro, el análisis ni las alertas |
| Borrador de interpretación de medidas | Modelo de lenguaje local con la API de Ollama, solo en loopback | `backend/app/interpret/` | **Clase C, segregado** (`compliance/software-safety-classification.md` §2.1): recibe solo hechos del registro firmado; pasa seis barreras (salida estructurada, verificador adversarial, cifras que salen de los hechos, cotejo de signos, linter de lenguaje y firma humana); queda «sin validar» hasta que una persona lo acepta o lo rechaza, y **nunca entra en el análisis ni en una alerta** |
| Dictado de notas | Whisper (`base`), en un entorno aparte | `backend/app/voice.py`, `backend/scripts/install_voice.py` | Devuelve un borrador que la persona lee y corrige; solo se firma al enviar el informe, marcado como dictado y revisado |
| Desidentificación de informes | Capa NER opcional (modelo `BSC-NLP4BIA/bsc-bio-ehr-es-contacto-anon`), además de patrones | `backend/app/reports/deid.py`, `backend/scripts/install_deid_ner.py` | Entorno aparte, pesos comprobados por SHA-256, sin descargas con un informe esperando |
| OCR de informes escaneados | Tesseract, en local | `backend/app/reports/ocr.py` | Una página con confianza baja se marca |
| Búsqueda en la documentación sin red | e5-small (ONNX) sobre BM25 | `backend/app/kb.py` | Sin el modelo, cae a BM25 |
| Segmentación del visor 3D | TotalSegmentator, programa externo opcional | Entorno local `backend/.venv-seg`, fuera de git (no se empaqueta) | Medido solo con los sujetos de `test` de su conjunto; el visor es para imagen de referencia previa al vuelo y para Tierra |

**Lo que no es IA:** la línea base personal, la tendencia, el riesgo y las alertas
(`backend/app/analysis/`) son reglas estadísticas explícitas sobre los datos firmados, sin modelos
aprendidos. Son las que se validan en dos ejes en `compliance/external-validation.md`.

Varias de estas funciones vienen de Polaris (AGPL-3.0-or-later), copiado literal en `polaris/` y
declarado en `NOTICE`.

---

## English

### A. AI used to develop EMMA

**1. Ideation and specification: a conversational AI assistant.**
The team explored the Space Apps challenges with a conversational assistant. That conversation
(`docs/contexto/conversacion-ideacion-v1.md`) analyzed the challenge, proposed the twin architecture
(astronaut, habitat, mission, countermeasures) and, at the team's request, drafted the technical
specification v1.1 and the knowledge base that were later given to the coding assistant as context.
[TEAM: tool name and version (e.g. ChatGPT), dates, and what the team decided or wrote versus what
the tool proposed.]

**2. Implementation, testing, documentation and review: Claude Code (Anthropic).**
Almost all of EMMA's code and documentation was written with Claude Code as a programming assistant:
830 of the repository's 869 commits carry a `Co-Authored-By: Claude …` line (`git log`, counted on
2026-11-05), with the Claude Opus 5.5 and Claude Fable 5.1 models. From 2026-11-03 the work was done
mostly with several Claude Code agents in parallel, each in its own local git worktree with a
narrow task, plus separate agents that reviewed each change before it was merged; merging and
decisions stayed with the person. It was used to:

- write the backend (Python/FastAPI), the interface (React/TypeScript) and the desktop app
  (Electron), with their tests;
- write the `compliance/` documents and keep them in step with the code;
- read published sources (LOINC entries, NASA pages, papers) and record in each evidence entry what
  was read, when, and with which verbatim quote — or mark it "unverified" if it wasn't read;
- review its own code adversarially (reviews that look for bugs and unsupported claims);
- draft the submission texts, this one included.

How the AI's output was kept in check:

- **Written rules the AI must follow** (`CLAUDE.md`): no invented LOINC codes, units follow the LOINC
  property, tests never touch the network, every observation goes through the signed ledger, false
  alarms and sensitivity are always reported together, scope is stated precisely, and no output may
  read like a medical order.
- **The rules are tested.** The suite fails if an indicator is added without justifying its code;
  the quality gates (`ruff`, `mypy --strict`, `tsc`, `npm test`) stay green; and mutation campaigns
  check that every safeguard has a test watching it.
- **Decisions belong to the team.** Thresholds, engine changes and adoptions are recorded as "user
  decision" with a date; what the AI measured and the team didn't adopt stays "measured, not
  adopted".
- **Validation is against real data, not against what the AI generates:** MMASH and LifeSnaps (real
  human physiology, on Earth) and HC18 (ultrasound).
- **Errors that review found and fixed,** the AI's own included: an in-flight SDNN drop that had no
  support, a resting heart-rate drift twice the observed value, and radiation dose integrated with a
  quality factor of 1.
- **Nothing leaves the team:** the repository is local-only, with no remote, and a `pre-push` hook
  rejects any push.

[TEAM: who reviewed what; whether any part was written without an assistant.]

**3. Transcribing the team's voice notes: Whisper, locally.**
The team's 14 voice notes of 2026-11-02 were transcribed on the team's own computer with Whisper
(`base` model), without sending the audio to any service, and cross-checked against the code to set
the event priorities.

**4. Logo and icon: drawn as code, no image generator.**
The brand draft (`desktop/build/brand/`, three candidates and a contact sheet) was written by Claude
Code on 2026-11-04 as hand-written SVG — coordinates and strokes as text, using colors from
`frontend/src/lib/palette.ts` — and the 16 px version was drawn pixel by pixel. No image generator
was used. It is a draft: candidate C is wired into the installer, but adopting or replacing it is
the team's call. [TEAM: confirm which mark is adopted, or whether it is replaced by the team's own.]

**5. Fine-tuning the assistant's model: tried locally, not adopted.**
On 2026-11-04 and 05 a LoRA fine-tune of Qwen3.5-9B, the voice assistant's model, was tried on the
team's own computer. The training examples are generated by EMMA's own code
(`backend/scripts/assistant_train_data.py`): the target answer is composed by EMMA — templates,
readings and fixed texts — never by a model; an example is kept only if the whole turn passes the
assistant's four barriers, and the 198-phrase evaluation set is held out of training, with a check
that they don't overlap. Training and evaluation used tools outside the repository. Result: the
fine-tuned model got 191 of 198 right versus 192 of 198 for the base model, so it **was not
adopted**; EMMA uses `qwen3.5:9b` as is.

**6. Other uses.**
[TEAM: any other AI tool used in development or in the submission — image generation or editing,
translation, voice or subtitles for the video, music — or delete this item if there were none.]

### B. AI inside EMMA (product features)

All of it runs **locally**; none of it sends clinical data out. Features that need a separate
environment are optional: if missing, EMMA says so and keeps working.

- **Voice assistant "EMMA"** (`backend/app/assistant/`): `qwen3.5:9b` through the Ollama API,
  loopback only. **Class C**: it picks an intent from a closed catalog; every answer passes four
  deterministic barriers (language linter, numbers that must come from the context, no
  prescribing, schema), and if one fails the backend speaks a fixed text. **It never signs
  anything**: whatever it proposes to write is signed by a person after confirming, and it never
  enters the analysis or an alert.
- **Wake word "EMMA"** (`frontend/src/assistant/wake/`): Vosk (`vosk-model-small-es-0.42`) via
  `vosk-browser`, in the browser, with a closed grammar; it only detects when a phrase starts.
  Whisper, in the backend, transcribes what is said to the assistant.
- **View that turns with the viewer's face** (`frontend/src/lib/faceCamera.ts`): MediaPipe Face
  Landmarker, in the browser. **Unvalidated demonstration**: it only rotates one console's view.
- **Interpretation draft** (`backend/app/interpret/`): a local language model through the Ollama
  API, loopback only. **IEC 62304 Class C, segregated**: it receives only facts from the signed
  record, passes six barriers (structured output, adversarial verifier, numbers that must come from
  the facts, sign cross-check, language linter, human signature), stays "unvalidated" until a person
  accepts or rejects it, and **never enters the analysis or an alert**.
- **Voice dictation** (`backend/app/voice.py`): Whisper `base`; returns a draft the person reads and
  corrects before anything is signed.
- **Report de-identification** (`backend/app/reports/deid.py`): an optional NER model on top of
  patterns, with SHA-256-checked weights.
- **OCR of scanned reports** (`backend/app/reports/ocr.py`): Tesseract, locally.
- **Offline documentation search** (`backend/app/kb.py`): e5-small (ONNX) over BM25.
- **3D viewer segmentation**: TotalSegmentator, an optional external program, not bundled; the
  viewer is for pre-flight reference imaging and for the ground.

**What is not AI:** the personal baseline, trend, risk and alerts (`backend/app/analysis/`) are
explicit statistical rules over the signed data, with no learned models. They are what we validate
on two axes.

Several of these features come from Polaris (AGPL-3.0-or-later), copied verbatim into `polaris/`
and declared in `NOTICE`.
