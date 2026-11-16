# Página del proyecto en Space Apps (EN, con traducción al castellano)

Borrador del 2026-11-02, puesto al día el 2026-11-05, escrito de nuevo a partir del repositorio (no copiado de ninguna
conversación). Lo escribió un asistente de código; el equipo lo revisa antes de publicarlo. Las
cifras son las del anexo de `presentacion.md` y **se vuelven a leer antes de publicar**.

Los apartados siguen los que suele tener la página de un proyecto de Space Apps; no se han leído en
el formulario de 2026. [EQUIPO: ajustar los títulos a los campos reales del formulario de entrega y
respetar sus límites de caracteres.]

---

## English

### Project name

EMMA — Environment and Medical Monitoring Assistant

### High-level summary

On November 14, 2026, a question from Mars to a flight surgeon takes about 22 minutes to go and come
back. On a long mission, the crew has to assess its own health on board. EMMA is decision-support
software that runs entirely offline: it gathers health indicators, compares each one with that same
crew member's personal baseline and trend, scales the risk by the light-time delay to Earth, and
explains every alert with its data and its evidence. It recommends; the crew decides, and every
observation and decision is written into a signed, hash-chained record. EMMA does not diagnose or
prescribe, and it does not replace the flight surgeon.

### What it does

- **Gathers indicators** from real wearables (BLE, Apple Health, Google Fit exports), a
  psychomotor vigilance test, a daily diary, a clickable pain body map, guided ultrasound
  measurements, scanned reports (local OCR and de-identification), capillary glucose from a meter
  and the scores of NASA's Cognition battery. The catalog holds 129 indicators in nine domains,
  including the six the challenge lists: blood pressure, heart rate, blood sugar, body
  temperature, sleep hours and mood. 77 use a LOINC code checked against its official entry; 52
  use EMMA's own code system, and each one states why no standard fits.
- **Normalizes everything to FHIR R4 `Observation`** and appends it to a signed log (Ed25519,
  SHA-256 chaining). There is no path that stores an observation around that log.
- **Compares each reading with the person**, by physiological context (sleep, rest, exertion),
  and with its trend; the risk level takes the communication delay into account, computed from JPL
  Horizons ephemerides.
- **Explains each alert** through seven questions — what changed, since when, against which
  baseline, what context changed, why it may matter, what to check, what evidence supports it — and
  links recommendations to NASA Human Research Program risks and OSDR studies, or labels them as
  demo.
- **Two consoles:** a crew console with a clickable human figure, and an Earth console that shows
  the same information only after the light delay. Both are laid out for tablets (touch targets of
  48 px), with a high-contrast mode for glare and screen-reader support.
- **A voice assistant, "EMMA", that runs locally:** the crew can talk to it hands-free (it listens
  for its name in the browser, offline), it reads the status aloud and announces new alerts, and it
  can act on the interface — any action that writes to the record needs the person's
  confirmation. Its language model (qwen3.5:9b through Ollama, on the same computer) never signs
  anything and never enters the analysis or an alert.
- **The mission environment** (Mars transit, low Earth orbit…) is declared at run time and signed
  into the record; a solar particle event can be replayed offline from a stored DONKI snapshot.
- **Offline is the nominal mode,** not a fallback. Every outbound connection goes through a single
  allow-listed gate. It ships as a Windows desktop app with the backend on loopback.

### How we know it works — and what we don't claim

We validated the engine against real human physiology, always on two axes together, because a 0%
false-alarm rate is easy to reach by switching the system off:

- **False alarms:** on MMASH (PhysioNet; 22 healthy people, 24 h, on Earth), 21 of 22 people get no
  alert at all, and the per-reading false-alarm rate went from 17.07% to 0.18%.
- **Sensitivity:** on that same physiology, with injected deterioration, sustained tachycardia is
  detected in 95.5% of subjects and an acute episode in 90.9% — but slow drift only in 31.8% and
  HRV collapse in 13.6%. A 24-hour dataset can't validate a slow drift, and we say so.
- With several weeks per person (LifeSnaps, 71 people, free living on Earth, not screened as
  healthy), the false-alarm rate rises to 3.53% of readings once the personal baseline is fully
  active — about 19 times the MMASH figure, which comes from an engine that barely used the personal
  baseline in 24 hours. It is an upper bound, it is measured and published, and reducing it is our
  next piece of work.

What EMMA does **not** claim:

- It is **developed in accordance with IEC 62304 Class B**, with the local language-model draft at
  Class C and segregated from alerts. It is **not certified**.
- There is no public API of astronaut vital signs; EMMA uses a deterministic simulator — every
  drift parameter declares whether its magnitude is documented, only its direction, or contested —
  and real wearables.
- Ground validation does not validate space physiology.
- OSD-288 is a mouse study (spleen, 35 days on the ISS): it supports immunology context, it is not
  telemetry.
- The 3D viewer is for pre-flight reference imaging and for the ground. On the ISS today, the
  medical imaging modality is ultrasound.

### NASA data

- **JPL Horizons** — Earth–Mars light time, the parameter behind the whole autonomy design.
- **DONKI** — space weather events (solar particle events) as mission context.
- **RadLab** — radiation environment, integrated with a quality factor different from 1.
- **NASA OSDR** — OSD-569 (Inspiration4 crew blood counts) and OSD-288 (mice, immunology support).
- **NASA Human Research Program** — risks and evidence that recommendations cite.
- **NASA-STD-3001 Vol. 2, Appendix F** — display rules (color meaning, contrast ≥ 6:1) enforced as
  frontend tests.

### Other data and resources

- **MMASH** (PhysioNet, ODbL v1.0) and **LifeSnaps** (Zenodo, CC BY 4.0) — validation on real
  physiology, on Earth.
- **HC18** (Zenodo, CC BY 4.0) — validation of the ultrasound measurement engine (scale and
  distance).
- **ESA** resources cited in the evidence registry.
- **Polaris** (AGPL-3.0-or-later) — EMMA reuses its 3D viewer, local OCR, offline documentation
  search, local voice transcription and the architecture of its interpretation draft. That is why
  EMMA is licensed AGPL-3.0-or-later.

### Use of artificial intelligence

See the full statement in `uso-de-ia.md` (English section). [TEAM: paste the English section into
the AI field of the form.]

### Team

[TEAM: names, roles, local event]

---

## Castellano (traducción)

### Nombre del proyecto

EMMA — Environment and Medical Monitoring Assistant

### Resumen

El 14 de noviembre de 2026, una pregunta desde Marte a un médico de vuelo tarda unos 22 minutos en
ir y volver. En una misión larga, la tripulación tiene que evaluar su salud a bordo. EMMA es software
de apoyo a la decisión que funciona entero sin red: recoge indicadores de salud, compara cada uno con
la línea base personal y la tendencia de ese mismo tripulante, escala el riesgo según el tiempo de
luz hasta la Tierra y explica cada alerta con sus datos y su evidencia. Recomienda; decide la
tripulación, y cada observación y cada decisión quedan escritas en un registro firmado y
encadenado. EMMA no diagnostica ni prescribe, y no sustituye al médico de vuelo.

### Qué hace

- **Recoge indicadores** de wearables reales (BLE, exportaciones de Apple Health y Google Fit), un
  test de vigilancia psicomotora, un diario, un mapa corporal de dolor clicable, medidas guiadas de
  ecografía, informes escaneados (OCR y desidentificación en local), glucosa capilar con
  glucómetro y las puntuaciones de la batería Cognition de NASA. El catálogo tiene 129 indicadores
  en nueve dominios, entre ellos los seis que nombra el reto: tensión arterial, pulso, glucosa,
  temperatura corporal, horas de sueño y ánimo. 77 llevan un código LOINC verificado en su ficha
  oficial; 52 usan el sistema propio de EMMA, y cada uno dice por qué no le sirve un estándar.
- **Lo normaliza todo a FHIR R4 `Observation`** y lo anexa a un registro firmado (Ed25519,
  encadenado con SHA-256). No hay ninguna vía que guarde una observación sin pasar por él.
- **Compara cada lectura con la persona**, por contexto fisiológico (sueño, reposo, esfuerzo), y
  con su tendencia; el nivel de riesgo tiene en cuenta el retardo de comunicaciones, calculado con
  efemérides de JPL Horizons.
- **Explica cada alerta** con siete preguntas —qué ha cambiado, desde cuándo, frente a qué base, qué
  contexto cambió, por qué puede importar, qué comprobar, qué evidencia lo respalda— y enlaza las
  recomendaciones con los riesgos del Human Research Program de NASA y estudios de OSDR, o las
  declara de demostración.
- **Dos consolas:** la de tripulación, con una figura humana clicable, y la de Tierra, que enseña lo
  mismo solo después del retardo de luz. Las dos están pensadas para tableta (objetivos táctiles de
  48 px), con un modo de alto contraste para el deslumbramiento y apoyo a lector de pantalla.
- **Un asistente de voz, «EMMA», que funciona en local:** la tripulación le habla con las manos
  libres (oye su nombre en el navegador, sin red), lee el estado en voz alta y avisa de cada alerta
  nueva, y puede manejar la interfaz; toda acción que escribe en el registro pide confirmación a la
  persona. Su modelo de lenguaje (qwen3.5:9b con Ollama, en el mismo ordenador) no firma nada y no
  entra nunca en el análisis ni en una alerta.
- **El entorno de la misión** (tránsito a Marte, órbita baja…) se declara en marcha y queda firmado
  en el registro; un evento de partículas solares se reproduce sin red desde una instantánea de
  DONKI.
- **Sin red como modo nominal**, no como modo degradado. Toda conexión de salida pasa por un único
  punto con lista blanca. Se entrega como aplicación de escritorio para Windows con el backend en
  loopback.

### Cómo sabemos que funciona, y lo que no afirmamos

Validamos el motor contra fisiología humana real, siempre en dos ejes a la vez, porque un 0 % de
falsas alarmas se consigue apagando el sistema:

- **Falsas alarmas:** en MMASH (PhysioNet; 22 personas sanas, 24 h, en Tierra), 21 de 22 no reciben
  ninguna alerta, y la falsa alarma por lectura bajó del 17,07 % al 0,18 %.
- **Sensibilidad:** sobre esa misma fisiología, con deterioros inyectados, la taquicardia sostenida
  se detecta en el 95,5 % de los sujetos y el episodio agudo en el 90,9 %; la deriva lenta, solo en
  el 31,8 %, y el colapso de HRV en el 13,6 %. Un conjunto de 24 horas no puede validar una deriva
  lenta, y lo decimos.
- Con varias semanas por persona (LifeSnaps, 71 personas, vida libre en Tierra, sin cribado de
  salud), la falsa alarma sube al 3,53 % de las lecturas cuando la línea base personal trabaja de
  verdad: unas 19 veces la cifra de MMASH, que sale de un motor que en 24 horas apenas usaba la base
  personal. Es una cota por arriba, está medida y publicada, y bajarla es nuestro trabajo siguiente.

Lo que EMMA **no** afirma:

- Está **desarrollada conforme a IEC 62304 Clase B**, con el borrador del modelo de lenguaje local
  en Clase C y segregado de las alertas. **No está certificada.**
- No existe una API pública de constantes vitales de astronautas; EMMA usa un simulador
  determinista —cada parámetro de deriva declara si su magnitud está documentada, solo su sentido, o
  si está contestado— y wearables reales.
- La validación en Tierra no valida la fisiología espacial.
- OSD-288 es un estudio con ratones (bazo, 35 días en la ISS): respalda el contexto inmunológico, no
  es telemetría.
- El visor 3D es para imagen de referencia previa al vuelo y para Tierra. Hoy, en la ISS, la imagen
  médica es la ecografía.

### Datos de NASA

- **JPL Horizons** — tiempo de luz Tierra-Marte, el parámetro que sostiene todo el diseño de
  autonomía.
- **DONKI** — sucesos de meteorología espacial (eventos de partículas solares) como contexto.
- **RadLab** — entorno de radiación, integrado con un factor de calidad distinto de 1.
- **NASA OSDR** — OSD-569 (hemograma de la tripulación de Inspiration4) y OSD-288 (ratones, respaldo
  inmunológico).
- **Human Research Program de NASA** — riesgos y evidencia que citan las recomendaciones.
- **NASA-STD-3001 Vol. 2, Apéndice F** — reglas de pantalla (significado del color, contraste
  ≥ 6:1), convertidas en pruebas de la interfaz.

### Otros datos y recursos

- **MMASH** (PhysioNet, ODbL v1.0) y **LifeSnaps** (Zenodo, CC BY 4.0): validación con fisiología
  real, en Tierra.
- **HC18** (Zenodo, CC BY 4.0): validación del motor de medida ecográfica (escala y distancia).
- Recursos de la **ESA** citados en el registro de evidencia.
- **Polaris** (AGPL-3.0-or-later): EMMA reutiliza su visor 3D, el OCR local, la búsqueda en la
  documentación sin red, la transcripción de voz en local y la arquitectura de su borrador de
  interpretación. Por eso EMMA es AGPL-3.0-or-later.

### Uso de inteligencia artificial

Ver la declaración completa en `uso-de-ia.md`.

### Equipo

[EQUIPO: nombres, papeles, evento local]

---

## De dónde sale cada afirmación

| Afirmación | Fuente en el repositorio |
|---|---|
| Retardo del 14-nov-2026 | `backend/spikes/HALLAZGOS.md`, `backend/app/environment/ephemeris.py` |
| Catálogo y reparto LOINC / propio | `GET /api/indicators`, `backend/app/ingest/codes.py` |
| Registro firmado | `compliance/record-integrity.md`, `backend/app/core/ledger.py` |
| Sin red y punto único de salida | `backend/app/core/egress.py` |
| Siete preguntas | `backend/app/analysis/explain.py` |
| Validación en dos ejes | `compliance/external-validation.md` |
| Clase B / Clase C segregada | `compliance/software-safety-classification.md` §2.1 |
| Clases de respaldo del simulador | `backend/app/ingest/simulator.py`, `GET /api/status` → `simulation.evidence` |
| Datos de NASA y su uso | `compliance/challenge-coverage.md` §2 y §4 |
| HC18 y la ecografía | `compliance/external-validation.md`, `compliance/imaging-data-provenance.md` |
| Código de Polaris | `NOTICE`, `polaris/ADOPTADO.txt` |
