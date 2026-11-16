# Presentación — guion diapositiva a diapositiva (ES / EN)

Borrador del 2026-11-02 para el 14 y 15 de noviembre de 2026. Lo escribió un asistente de código a
partir del repositorio; el equipo lo revisa antes de usarlo. Cada diapositiva lleva el texto que se
ve (corto), las notas de quien habla y la fuente de lo que se afirma. Las cifras salen del anexo
del final, **que se vuelve a leer el día antes de presentar**.

Reglas que esta presentación no rompe (CLAUDE.md): «desarrollado conforme a IEC 62304 Clase B»,
nunca «certificado»; apoyo a la decisión, no prescripción; MMASH y LifeSnaps no validan fisiología
espacial; OSD-288 son ratones; no existe una API pública de constantes vitales de astronautas; hoy
no vuela ningún TAC.

Actualizado el **2026-11-05** con lo construido desde el 3 de noviembre (consola de tableta, voz y
asistente local, entorno declarable, alto contraste, «Qué se comparte y qué no», evento solar sin
red, glucosa capilar, Cognition). Las diapositivas de **visión** (13 a 15) llevan ese rótulo en
pantalla: son ideas, no funciones construidas.

**Número de diapositivas:** 16. Si el formulario de entrega o los organizadores fijan un máximo
[EQUIPO: comprobarlo en la pestaña «Resources» el 13 de noviembre], se funden la 6 con la 5, la 9
con la 8, y las tres de visión (13 a 15) en una sola.

---

## 1. Portada

**ES** — EMMA · Environment and Medical Monitoring Assistant. Vigilancia autónoma de la salud de la
tripulación en misiones largas. NASA Space Apps 2026 · reto «Create Health Monitoring Software for
Astronauts on Space Missions». [EQUIPO: nombres y ciudad del evento local]

**EN** — EMMA · Environment and Medical Monitoring Assistant. Autonomous crew health monitoring for
long-duration missions. NASA Space Apps 2026 · challenge "Create Health Monitoring Software for
Astronauts on Space Missions". [TEAM: names and local event]

*Notas:* 10 segundos. Nombre del reto tal cual (`compliance/challenge-coverage.md` §1).

---

## 2. El problema: la Tierra está a 22 minutos

**ES**
- 14 de noviembre de 2026: Marte a 1,324 UA. Una pregunta al médico de vuelo tarda 11 minutos en
  llegar y 22 en volver con respuesta.
- No hay consulta en directo. Lo que la tripulación necesita saber, lo tiene que saber a bordo.
- El reto lo dice así: «Astronauts must be capable of making health assessments on themselves».

**EN**
- November 14, 2026: Mars is 1.324 AU away. A question to the flight surgeon takes 11 minutes to
  arrive and 22 to come back answered.
- No live consultation. Whatever the crew needs to know, it has to know on board.
- In the challenge's words: "Astronauts must be capable of making health assessments on themselves".

*Notas:* el retardo no es un número de ejemplo: sale de las efemérides de JPL Horizons
(`backend/app/environment/ephemeris.py`; valor del día en `backend/spikes/HALLAZGOS.md`). Es el
parámetro que sostiene todo el diseño: el riesgo se escala con él (`backend/app/analysis/risk.py`).

---

## 3. Qué hace EMMA: el camino de un dato

**ES** — Una medida entra, se firma, se compara con la propia persona y acaba en una recomendación
con su evidencia, en la consola de a bordo y, con el retardo, en la de Tierra.

```
wearable · simulador · test PVT · diario · ecografía · informe escaneado
   → FHIR R4 Observation (ingest/)
   → registro encadenado y firmado (core/ledger.py)
   → línea base personal + tendencia + riesgo escalado con el tiempo de luz (analysis/, environment/)
   → recomendación que cita su evidencia (advisor/, evidence/)
   → consola de tripulación · consola de Tierra con el retardo aplicado (api/, frontend/)
```

**EN** — A measurement comes in, gets signed, is compared against that same person and ends up as
a recommendation with its evidence — on the crew console and, after the light delay, on the
Earth console.

```
wearable · simulator · PVT test · diary · ultrasound · scanned report
   → FHIR R4 Observation (ingest/)
   → hash-chained, signed ledger (core/ledger.py)
   → personal baseline + trend + risk scaled by light time (analysis/, environment/)
   → recommendation citing its evidence (advisor/, evidence/)
   → crew console · Earth console with the delay applied (api/, frontend/)
```

*Notas:* es el camino que describe `CLAUDE.md` («El camino de un dato»). Decir los cinco peligros
del HRP que el reto nombra y dónde entra cada uno (`compliance/challenge-coverage.md` §2, fila de
«five hazards»), sin pararse.

---

## 4. Qué indicadores

**ES**
- 129 indicadores en nueve dominios: cardiovascular, conductual, nutrición, genitourinario, óseo,
  radiación, inmune, musculoesquelético y neuro-ocular.
- Los seis que pone el reto como ejemplo están todos: tensión, pulso, glucosa, temperatura, horas
  de sueño y ánimo.
- 77 con código LOINC verificado en su ficha; 52 con un sistema propio, y cada uno dice por qué no
  puede usar un estándar.

**EN**
- 129 indicators across nine domains: cardiovascular, behavioral, nutrition, genitourinary, bone,
  radiation, immune, musculoskeletal and neuro-ocular.
- All six the challenge lists as examples are there: blood pressure, heart rate, blood sugar, body
  temperature, sleep hours and mood.
- 77 carry a LOINC code checked against its official entry; 52 use an own code system, and each
  one states why no standard fits.

*Notas:* las cifras son las de `GET /api/indicators` el 2026-11-02 (anexo). La unidad sigue a la
propiedad LOINC: el cortisol salival 2142-8 va en µg/dL, no en nmol/L (invariante 2). Decir de
dónde vienen los datos: del simulador determinista y de wearables reales; **no existe una API
pública de constantes vitales de astronautas**.

---

## 5. Qué la diferencia (1): el registro y la persona

**ES**
- **Registro firmado.** Toda observación entra por un registro encadenado y firmado (Ed25519,
  SHA-256). No hay ninguna vía que guarde un dato saltándoselo. Una alteración deja huella.
- **Línea base personal.** Cada medida se compara con la propia persona, por contexto (sueño,
  reposo, esfuerzo), no solo con un rango de población.
- **Sin red, como modo nominal.** Funciona sin internet; toda salida a la red pasa por un único
  punto con lista blanca.

**EN**
- **Signed ledger.** Every observation goes through a hash-chained, signed log (Ed25519, SHA-256).
  There is no path that stores data around it. Tampering leaves a trace.
- **Personal baseline.** Each reading is compared with that same person, by context (sleep, rest,
  exertion), not only with a population range.
- **Offline as the nominal mode.** It works without internet; every outbound call goes through a
  single allow-listed gate.

*Notas:* fuentes: `compliance/record-integrity.md` (especificación del registro, que implementa
`backend/app/core/ledger.py`), `backend/app/analysis/baseline.py`, `backend/app/core/egress.py`. La
utilidad de la línea base personal frente a los rangos de población es **una hipótesis de diseño sin
probar** (KB-H2 en `GET /api/framework`): decirlo así.

---

## 6. Qué la diferencia (2): dos ejes de validación, siempre juntos

**ES**
- En personas sanas reales (MMASH, 22 personas, 24 h, en Tierra): 21 de 22 sin ninguna alerta;
  falsa alarma por lectura del 17,07 % al 0,18 %.
- Sobre esa misma fisiología, con deterioros inyectados: taquicardia sostenida detectada en el
  95,5 %, episodio agudo en el 90,9 %… y la deriva lenta solo en el 31,8 %, el colapso de HRV en el
  13,6 %.
- Con semanas de datos por persona (LifeSnaps, 71 personas, en Tierra) la falsa alarma sube al
  3,53 % de las lecturas: el 0,18 % no es la tasa esperable en una misión larga. Está medido, y es
  el trabajo siguiente.
- Se enseñan las dos cosas a la vez: el 0 % de falsas alarmas se consigue apagando el sistema.

**EN**
- On real healthy people (MMASH, 22 people, 24 h, on Earth): 21 of 22 get no alert at all;
  per-reading false alarm rate from 17.07% down to 0.18%.
- On that same physiology, with injected deterioration: sustained tachycardia detected in 95.5%,
  acute episode in 90.9%… and slow drift only in 31.8%, HRV collapse in 13.6%.
- With weeks of data per person (LifeSnaps, 71 people, on Earth) false alarms rise to 3.53% of
  readings: 0.18% is not the rate to expect on a long mission. It is measured, and it is the next
  piece of work.
- We always show both: you get 0% false alarms by switching the system off.

*Notas:* cifras de `compliance/external-validation.md` (anexo). Decir en voz alta lo que **no**
demuestra: MMASH son 24 h en Tierra y no valida la deriva de vuelo; los deterioros son
paramétricos, no clínicos. LifeSnaps (hallazgo 31) es vida libre sin cribado: un catarro cuenta
como falsa alarma, así que el 3,53 % es una cota por arriba; pero el propio documento dice que el
0,18 % de MMASH es el de un motor que allí apenas usa la base personal. Decirlo antes de que lo
pregunten es una fortaleza ante el jurado, no un fallo que esconder.

---

## 7. Qué la diferencia (3): explica y deja decidir

**ES**
- Cada alerta contesta siete preguntas: qué ha cambiado, desde cuándo, frente a qué base, qué
  contexto cambió, por qué puede importar, qué comprobar y qué evidencia lo respalda.
- Cada recomendación cita su fuente (riesgos del HRP, estudios de OSDR) o se declara de
  demostración.
- La decisión es de la persona, y queda firmada. EMMA informa y recomienda; no diagnostica ni
  prescribe.

**EN**
- Every alert answers seven questions: what changed, since when, against which baseline, what
  context changed, why it may matter, what to check and what evidence supports it.
- Every recommendation cites its source (HRP risks, OSDR studies) or is labeled as demo.
- The decision belongs to the person, and it is signed. EMMA informs and recommends; it does not
  diagnose or prescribe.

*Notas:* `backend/app/analysis/explain.py`, `backend/app/advisor/recommendations.py`,
`backend/app/evidence/`. `backend/app/text_guard.py` impide que una salida suene a orden médica
(invariante 7). La mayoría de las contramedidas siguen marcadas `demo` hasta que las revise un
médico de vuelo (`docs/contexto/README.md`): decirlo si preguntan.

---

## 8. En la mano: una consola de tableta que se maneja sin mirar

**ES**
- **Hecha para tableta:** la franja común, compacta (de 368 a 216 px de alto a 1024×768 al tacto),
  los mandos de pantalla plegados en «Pantalla», objetivos de 48 px al dedo y el asistente acoplado
  en su columna (en vertical, hoja de abajo).
- **La vista gira contigo:** con el giroscopio, o siguiendo la cara de quien mira (demostración); la
  flecha de «Arriba real» señala el arriba real.
- **Sin mirar:** se deja leer con el lector de pantalla del sistema (las alertas se dicen), y un
  gesto de emergencia enciende la voz y lee el estado: Escape tres veces, tres dedos o Ctrl+Alt+V
  en escritorio.
- **Alto contraste** para el deslumbramiento: una segunda paleta, con las mismas reglas.

**EN**
- **Built for a tablet:** a compact common strip (from 368 to 216 px tall at 1024×768 on touch),
  display controls folded under «Pantalla», 48 px touch targets and the assistant docked in its own
  column (a bottom sheet in portrait).
- **The view turns with you:** following the gyroscope, or the viewer's face (demonstration); the
  «Arriba real» arrow points to the real up.
- **Eyes-free:** it works with the system screen reader (alerts are spoken), and an emergency
  gesture turns the voice on and reads the status: Escape three times, three fingers, or Ctrl+Alt+V
  on desktop.
- **High contrast** against glare: a second palette, under the same rules.

*Notas:* `compliance/hmi-state-of-the-art.md` §5.40 (la franja: 368 → 216 px a 1024×768, medida en
Chromium con tacto emulado; el resto de tamaños también está allí), §5.41 (lector de pantalla) y el
gesto de emergencia (Ctrl+Alt+V en la misma sección). El alto contraste es la segunda paleta de
`frontend/src/lib/palette.ts`, con su prueba de contraste. El giro por la cara es una demostración:
decirlo así. [EQUIPO: decidir si se enseña el giro en directo o solo en el vídeo.]

---

## 9. El asistente «EMMA»: se le habla, contesta y no firma solo

**ES**
- Se le llama por su nombre, «EMMA», y la palabra se reconoce **sin red**, dentro de la página.
  Entiende lenguaje de la calle sobre toda la interfaz: «¿cuánta radiación llevo?», «calla media
  hora», «estamos en la estación, no yendo a Marte».
- Medido con frases reales: de 15 a 31 de 32 en la batería de partida, y un 84 % (27 de 32) en
  frases escritas al final y nunca usadas para ajustar.
- **Nunca firma sin «confirmo».** Propone, lo dice en voz alta y solo se firma si la persona lo
  confirma. Lo que redacta el modelo no entra en el análisis ni en una alerta.
- Todo local: el modelo corre en el propio equipo.

**EN**
- You call it by name, «EMMA», and the wake word is recognised **offline**, inside the page. It
  understands everyday language across the whole interface: "how much radiation have I had?",
  "be quiet for half an hour", "we're on the station, not going to Mars".
- Measured on real phrases: from 15 to 31 of 32 on the starting set, and 84% (27 of 32) on phrases
  written at the end and never used for tuning.
- **It never signs without «confirmo».** It proposes, says it aloud, and only signs if the person
  confirms. What the model drafts never enters the analysis or an alert.
- All local: the model runs on the machine itself.

*Notas:* `compliance/hmi-state-of-the-art.md` §5.43 (tabla «Medido», 2026-11-04, batería
`backend/tests/data/assistant_nl_eval.json`): `baseline32` 15/32 → 31/32 en la cuenta completa (el «16/32» que circula es el de antes contado
solo por la intención; después, solo por la intención, 28/32: no mezclar columnas); `fresh` 24/32 → 27/32 (84 %). La cifra honesta de lo que generaliza es la de
`fresh`; el 99 % sobre `eval` está inflado por haber corregido sobre esas frases: **no citarlo**.
Palabra «EMMA»: Vosk en el navegador (§5.44), no el reconocimiento de Chrome, que sacaría audio
fuera. Modelo `qwen3.5:9b` en Ollama local, mediana 2,89 s por turno con modelo (§5.43, en una RTX
4070 de 8 GB). Segregación del borrador: invariante 6 y `software-safety-classification.md` §2.1.
[EQUIPO: volver a leer la tabla antes de presentar; la batería se puede repetir y cambiar.]

---

## 10. Lo que decide la tripulación: entorno, privacidad y lo que sale

**ES**
- **Entorno de la misión declarable y firmado:** de tránsito a Marte a órbita baja sin reiniciar; el
  cambio queda en el registro.
- **«Qué se comparte y qué no»:** una vista que dice qué datos salen hacia Tierra y cuáles no, y está
  cotejada con el código.
- **Cognition de NASA:** EMMA no reprograma la batería; registra, firmadas, las puntuaciones que da
  el programa oficial. Hemos pedido a Penn acceso y un fichero de ejemplo.
- **Glucosa capilar con glucómetro:** guía paso a paso y su indicador, LOINC 41653-7.

**EN**
- **Declarable, signed mission environment:** from Mars transit to low Earth orbit without a
  restart; the change is in the ledger.
- **"What is shared and what isn't":** a view stating which data goes to the ground and which
  doesn't, checked against the code.
- **NASA Cognition:** EMMA does not reimplement the battery; it records, signed, the scores the
  official software produces. We have asked Penn for access and a sample file.
- **Capillary glucose by glucometer:** step-by-step guide and its indicator, LOINC 41653-7.

*Notas:* entorno: commit «El entorno de la misión se declara en marcha, firmado» y
`compliance/hmi-state-of-the-art.md` §5.40. Vista de lo compartido: §5.45, declarada en el backend
(lo que sale lo decide `backend/app/core/egress.py`). Cognition: `backend/app/ingest/cognition.py`
y `docs/entrega/correo-penn-cognition.md` [EQUIPO: si el correo no se ha enviado el día 14, decir
«vamos a pedir», no «hemos pedido»]. Glucosa: `backend/app/data/instruments_read.json` y
`docs/contexto/README.md` (41653-7 es masa/volumen, en mg/dL: invariante 2; es descriptiva, el
estado no la lee; no es la glucosa de laboratorio 2345-7).

---

## 11. Lo que EMMA no afirma

**ES**
- No está certificada. Está **desarrollada conforme a IEC 62304 Clase B**, con el borrador del
  modelo de lenguaje local en Clase C, segregado: nunca entra en una alerta.
- No tiene datos de vuelo de astronautas: no existen en abierto. Usa un simulador con cada
  parámetro justificado y wearables reales.
- No valida la fisiología espacial: la validación con personas reales es en Tierra.
- OSD-288 son ratones (bazo, 35 días en la ISS): respaldo inmunológico, no telemetría.
- El visor 3D es para imagen de referencia previa al vuelo y para Tierra, no diagnóstico a bordo:
  hoy en la ISS la imagen médica es la ecografía.

**EN**
- It is not certified. It is **developed in accordance with IEC 62304 Class B**, with the local
  language-model draft at Class C, segregated: it never enters an alert.
- There is no astronaut flight data: none is public. It uses a simulator whose every parameter is
  justified, plus real wearables.
- It does not validate space physiology: validation on real people is on Earth.
- OSD-288 is mice (spleen, 35 days on the ISS): immunology support, not telemetry.
- The 3D viewer is for pre-flight reference imaging and for the ground, not on-board diagnosis:
  today the medical imaging on the ISS is ultrasound.

*Notas:* `compliance/software-safety-classification.md` §2.1; `backend/app/ingest/simulator.py`
(cada parámetro: magnitud documentada, sentido documentado o contestado; `GET /api/status` →
`simulation.evidence`). La revisión bibliográfica corrigió tres errores reales del propio modelo
(la caída de SDNN en vuelo no está respaldada, la deriva de la FC en reposo era el doble, el factor
de calidad de la radiación): contarlo como prueba de método.

---

## 12. Demo (en directo, sin red)

**ES** — Una tripulante, un evento de partículas solares sin internet, una decisión firmada y la
vuelta a la normalidad.

**EN** — One crew member, one solar particle event with no internet, one signed decision, and the
return to normal.

*Guion de la demo (unos 3 minutos). [EQUIPO: ensayarlo sobre la versión `demo-v1` y ajustar los
nombres de pantalla a los reales]:*

1. Abrir el instalador de escritorio con la red desactivada (`desktop/`: el backend arranca en
   loopback). Enseñar que no hay conexión. Si Windows avisa de que el instalador no está firmado,
   seguir la nota para la demo en directo de `docs/entrega/`.
2. Consola de tripulación en tableta: estado por dominio, la figura humana clicable
   (`frontend/src/anatomy/AnatomyPanel.tsx`) y una región con su cadena estado → variables →
   evidencia → tendencia → contramedida.
3. Cargar el escenario `spe-event-recovery` («Evento de partículas solares y vuelta a la
   normalidad»). Sin red no hay DONKI en vivo: la consola enseña la instantánea fechada de DONKI en
   cian («no en vivo»), y la dosis de a bordo por encima de su límite acorta las rutinas: la
   monitorización se intensifica. Aparece la alerta.
4. Decir «EMMA, ¿qué ha pasado?»: el asistente contesta en voz alta. Abrir la explicación de la
   alerta (las siete preguntas) y la recomendación con su fuente.
5. La tripulante decide; la decisión se firma (con el asistente, solo tras «confirmo»).
6. La línea temporal: comienzo, periodo intensificado y vuelta a nominal sin alertas.
7. Consola de Tierra (`frontend/src/ground/GroundConsole.tsx`): lo mismo, con el retardo de luz
   aplicado. Lo que Tierra ve llega tarde, y la interfaz lo dice. Panel de auditoría
   (`frontend/src/ground/AuditPanel.tsx`): la cadena del registro se verifica.

*Notas:* evento sin red y vuelta a la normalidad: `compliance/hmi-state-of-the-art.md` §5.40.4 y
`docs/contexto/README.md`. Hueco abierto según ese README: la instantánea de DONKI aún no está en el
paquete; hay que ejecutar `scripts/fetch_donki_snapshot.py` con red antes de `demo-v1`
(comprobado el 2026-11-05 sobre `b079df9`: `backend/app/data/donki_snapshot.json`, adonde escribe
`backend/scripts/fetch_donki_snapshot.py`, todavía no existe). El asistente necesita Ollama con su modelo en el equipo de la demo
[EQUIPO: decidir si se enseña en directo o solo en el vídeo]. Plan B si algo falla en directo: el
vídeo (`guion-video.md`).

---

## 13. VISIÓN (no construido) · Uso en Tierra: emergencias, montaña, inundaciones

**ES** — *Rótulo en pantalla: «Visión de producto: no es una función construida».*
Lo que sirve a 22 minutos de la Tierra sirve donde no llega la ayuda: emergencias, montaña,
inundaciones, zonas sin cobertura. La base ya está: EMMA funciona sin red (offline-first), y ese es
su modo nominal.

**EN** — *On-screen label: "Product vision: not a built feature".*
What works 22 minutes from Earth works wherever help can't reach: emergencies, mountains, floods,
areas without coverage. The foundation is there: EMMA is offline-first, and that is its nominal
mode.

*Notas:* `docs/contexto/prioridades-evento.md` §4 («ya es offline-first, así que una diapositiva
basta»). Lo que existe es el modo sin red (`EMMA_OFFLINE=true`, `backend/app/core/egress.py`); el
uso civil en Tierra no está construido ni validado para ese fin: no decir que «ya sirve para
rescates». La validación es con personas sanas en Tierra (MMASH, LifeSnaps), no con heridos.

---

## 14. VISIÓN (no construido) · Divulgación con colegios

**ES** — *Rótulo: «Visión».* Actividades de ejercicio físico con colegios, en la línea de los
programas de colaboración de NASA con escuelas, para explicar por qué importa la exploración
espacial y qué retos tiene para el cuerpo.

**EN** — *Label: "Vision".* Physical-activity sessions with schools, in the spirit of NASA's
programs with schools, to explain why space exploration matters and what it demands of the body.

*Notas:* `docs/contexto/prioridades-evento.md` §4 (idea 21). No citar un programa concreto de NASA
sin haberlo leído. [EQUIPO: si hay un centro concreto con el que hablar, nombrarlo; si no, no.]

---

## 15. VISIÓN (no construido) · Ruta según el estado médico, mercado de datos, protocolo de muestras

**ES** — *Rótulo: «Ideas para después del concurso, no construidas».*
- **Ruta según el estado médico:** que el plan de actividad tenga en cuenta el estado de cada
  tripulante.
- **Mercado de datos:** que la persona decida qué comparte con la investigación, con su
  consentimiento y con el registro firmado como prueba de procedencia.
- **Protocolo de muestras:** guiar la recogida y el seguimiento de muestras biológicas.

**EN** — *Label: "Ideas for after the challenge, not built".*
- **Route planning by medical status:** activity plans that take each crew member's status into
  account.
- **Data marketplace:** the person decides what to share with research, with consent, and the
  signed ledger as proof of provenance.
- **Sample protocol:** guiding the collection and follow-up of biological samples.

*Notas:* `docs/contexto/prioridades-evento.md` §4. Lo que sí existe y sostiene el «mercado de
datos»: la vista «Qué se comparte y qué no» (diapositiva 10) y `backend/app/core/egress.py`; nada
clínico sale por defecto. [EQUIPO: decidir si se dice «mercado» o «datos para investigación con
consentimiento»; lo segundo suena menos a vender datos de salud.] **Cuidado:** la firma inmune a
partir de OSD-288 está descartada, y OSD-288 son ratones (bazo, 35 días en la ISS): no presentar el
protocolo de muestras como apoyado en datos de astronautas.

---

## 16. Cierre

**ES** — EMMA no sustituye al médico de vuelo. Le da a la tripulación lo que necesita mientras la
respuesta viaja: qué ha cambiado, por qué importa y qué se puede hacer, con cada dato firmado.

> ¿Y si la tecnología pensada para alguien a 225 millones de kilómetros de un hospital pudiera
> ayudar también a alguien a 225 kilómetros de uno?

Código abierto, AGPL-3.0-or-later. [EQUIPO: contacto / enlace]

**EN** — EMMA does not replace the flight surgeon. It gives the crew what they need while the
answer is in transit: what changed, why it matters and what can be done, with every data point
signed.

> What if the technology designed for someone 225 million kilometers from a hospital could also
> help someone 225 kilometers from one?

Open source, AGPL-3.0-or-later. [TEAM: contact / link]

*Notas:* la frase en inglés es literal de `docs/contexto/conversacion-ideacion-v1.md` (la que
«cierra el círculo de Stuhlinger»); la española es traducción nuestra. La idea es la de la carta de
Ernst Stuhlinger (1970), registrada en `GET /api/context-sources`: los retos extremos del espacio
dan soluciones que vuelven a la Tierra. **La frase no es de Stuhlinger**: no atribuírsela. Los
225 millones de km son una cifra redonda de la ideación, no la del día: el 14 de noviembre Marte
está a 1,324 UA, unos 198 millones de km (anexo). [EQUIPO: dejar la frase, que es retórica, o
cambiarla a «200 millones».] EMMA incorpora código de Polaris (AGPL-3.0-or-later, `NOTICE`); si se
enseña el visor 3D o la transcripción por voz, decir que vienen de Polaris.

---

## Anexo: las cifras, de dónde salen y cuándo se leyeron

Leídas el **2026-11-02** sobre el commit `29aa2a1`. Las filas de la consola, el asistente, la glucosa, el evento solar y la frase de cierre se
añadieron el **2026-11-05** desde los documentos citados. **El catálogo ha cambiado desde el
2026-11-02** (entró la glucosa capilar, entre otras cosas): el 128 / 76 / 52 de entonces se volvió
a leer el **2026-11-05** sobre el commit `b079df9`, contando `CATALOG` y `DESCRIPTIVE_ONLY` de
`backend/app/ingest/codes.py` (lo mismo que sirve `GET /api/indicators`): 129 / 77 / 52, 46 solo
descriptivos, nueve dominios. Las cifras de `guion-video.md`,
`pagina-proyecto.md` y `uso-de-ia.md` son estas mismas. **Se vuelven a leer antes de grabar y antes
de entregar**: el catálogo y las métricas cambian con el código.

| Cifra | Valor el 2026-11-02 | Fuente de verdad |
|---|---|---|
| Indicadores del catálogo | 128: 76 LOINC, 52 del sistema propio `https://emma.mission/codes`; 45 solo descriptivos; nueve dominios. **Releído el 2026-11-05 (`b079df9`): 129: 77 LOINC, 52 propios; 46 solo descriptivos; nueve dominios** | `GET /api/indicators` (`count`, `is_standard_code`, `descriptive_only`, `domain`), que lee `CATALOG` de `backend/app/ingest/codes.py` |
| Sanos sin ninguna alerta (MMASH, 24 h, Tierra) | 21 de 22 | `compliance/external-validation.md`, cabecera y tabla «El resultado» |
| Falsa alarma por lectura (MMASH) | 17,07 % (primera medición) → 0,18 % (0,1842 %) | `compliance/external-validation.md`, tabla «El resultado» |
| Sensibilidad sobre deterioros inyectados en esa fisiología (detectado / dominio marcado) | taquicardia sostenida 95,5 % / 81,8 %; episodio agudo 90,9 % / 77,3 %; taquicardia progresiva 31,8 % / 13,6 %; colapso de HRV 13,6 % / 4,5 % | `compliance/external-validation.md`, tabla «El contrapeso»; pruebas `-m external` |
| Falsa alarma con varias semanas por persona (LifeSnaps) | 71 personas, en Tierra, sin cribado: 3,53 % de las lecturas (unas 19 veces el 0,18 % de MMASH), cota por arriba | `compliance/external-validation.md`, hallazgo 31 |
| Retardo Tierra-Marte el 2026-11-14 | 1,324 UA; 11,01 min de ida; 22,03 min de ida y vuelta | `backend/spikes/HALLAZGOS.md` (fila «2026-11-14 (día del hackathon)»), de JPL Horizons vía `backend/app/environment/ephemeris.py` |
| Franja común de la consola, alto a 1024×768 al tacto | 368 px → 216 px (2026-11-03) | `compliance/hmi-state-of-the-art.md` §5.40 |
| Asistente: comprensión de frases (`qwen3.5:9b`, local) | `baseline32` 15/32 → 31/32; `fresh` (nunca ajustadas) 24/32 → 27/32 (84 %); mediana 2,89 s por turno con modelo (2026-11-04) | `compliance/hmi-state-of-the-art.md` §5.43, tabla «Medido»; `backend/tests/data/assistant_nl_eval.json` |
| Glucosa capilar | LOINC 41653-7, mg/dL, descriptiva | `backend/app/data/instruments_read.json`; `docs/contexto/README.md` |
| Escenario de evento solar con vuelta a la normalidad | `spe-event-recovery`: pico 12 días antes del final | `compliance/hmi-state-of-the-art.md` §5.40.4 |
| Distancia de la frase de cierre | 225 millones de km (retórica, de la ideación; el día real: 1,324 UA ≈ 198 millones de km) | `docs/contexto/conversacion-ideacion-v1.md`; `backend/spikes/HALLAZGOS.md` |
| Commits con un asistente de código | 770 de 774 con la línea `Co-Authored-By: Claude …` | `git log` del repositorio local, contado el 2026-11-02 |

Los números de pruebas no se citan: cambian a diario. Si hacen falta, se cuentan ese día con
`pytest --collect-only -q` y `npm test`.

Aviso para el equipo: el `README.md` de la raíz aún dice «HALO» y lleva conteos de pruebas
antiguos. Estos textos usan el nombre vigente, **EMMA — Environment and Medical Monitoring
Assistant** (`NOTICE`), y no copian esos conteos.
