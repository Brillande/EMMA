# Guion del vídeo de impacto (ES / EN)

Borrador del 2026-11-02. Lo escribió un asistente de código a partir del repositorio; el equipo lo
revisa antes de grabar. Se graba una sola imagen y se le ponen dos locuciones (ver «Reglas del
guion»). Las cifras son las del
anexo de `presentacion.md` y **se vuelven a leer el día de la grabación**.

## Duración: 5 minutos

**Lo fija el equipo (Ellande, 2026-11-03): el vídeo dura 5 minutos.** Ninguna de las fuentes del
repositorio lo dice: ni el enunciado del reto (ficha `space-apps-2026-health-monitoring-challenge`),
ni las preguntas frecuentes (`space-apps-2026-participant-faqs`), ni el anuncio
(`nasa-space-apps-2026-announcement`) en `backend/app/data/evidence_refs.json`, ni
`compliance/challenge-coverage.md` §4.

El vídeo que se entrega es la **versión completa (5:00)**. La de **~30 s** sirve como avance para
los mentores o las redes. [EQUIPO: comprobar el formato el 13 de noviembre en la pestaña
«Resources» o en el formulario de entrega.]

A unas 140 palabras por minuto, en 5 minutos caben unas 700 palabras por idioma. Cada escena lleva
su tiempo y el total no debe pasar de 5:00. La locución actual se queda algo por debajo (unas 640
palabras en castellano y 605 en inglés) para dejar pausas a la imagen.

**Revisión del 2026-11-05.** Las escenas enseñan lo que EMMA hace hoy, según `git log` desde el
2026-11-03 y `compliance/hmi-state-of-the-art.md` §5.40-5.46: la consola de tableta (§5.40), el
evento solar sin red y la vuelta a la normalidad con el escenario `spe-event-recovery` (§5.40.4),
el lector de pantalla y el gesto de emergencia de la voz (§5.41, §5.40), el asistente de voz
«EMMA» con manos libres y su «confirmo» (§5.43, §5.44), la flecha del arriba real con giroscopio
o cara (esta, como demostración sin validar) y la vista «Qué se comparte y qué no» (§5.45). La
escena 9 cierra con la carta de Stuhlinger, con las palabras de la sección «Del espacio a la
Tierra» del `README.md`. Si una función no llega a `demo-v1`, su frase se quita y su tiempo pasa a
la escena 9.

## Reglas del guion

- Nada de «certificado»; nada que suene a orden médica; nada de «datos de astronautas».
- **Un solo vídeo, dos versiones (decisión de Ellande, 2026-11-04):** «un vídeo en inglés con
  subtítulos en inglés y otro en castellano con subtítulos en castellano, pero los dos vídeos sean
  el mismo». Se graba y se monta **una sola imagen**; encima van dos pistas de audio y subtítulos:
  locución ES + subtítulos ES, y locución EN + subtítulos EN. La consola que sale en pantalla sigue
  en castellano en las dos; lo que importe de sus rótulos lo explican la locución y los subtítulos
  ingleses. Los subtítulos salen de este guion: `subtitulos/` (mismos cortes y tiempos en los dos
  idiomas).
- Se graba sobre la versión etiquetada `demo-v1`, con la red desactivada.
- [EQUIPO: grabar las dos locuciones sobre el mismo montaje final, ajustadas a los tiempos de cada
  escena; después, reajustar los tiempos de `subtitulos/`.]
- [EQUIPO: subtítulos incrustados en la imagen o como pista aparte según lo que admita el
  formulario de entrega; comprobarlo el 13 de noviembre.]

---

## Versión corta (~30 s)

| Tiempo | Imagen | Locución ES | Locución EN |
|---|---|---|---|
| 0–7 s | Tierra y Marte; el contador de retardo | «14 de noviembre de 2026. Una pregunta al médico de vuelo, desde Marte, tarda 22 minutos en ir y volver.» | "November 14, 2026. A question from Mars to the flight surgeon takes 22 minutes to go and come back." |
| 7–17 s | Consola de tripulación: figura humana, una alerta, su explicación | «EMMA vigila la salud de la tripulación a bordo, sin red. Compara cada medida con la propia persona y explica cada aviso con sus datos y su evidencia.» | "EMMA watches over crew health on board, offline. It compares every reading with that same person and explains each alert with its data and its evidence." |
| 17–25 s | La decisión se firma; panel de auditoría en verde | «La decisión es de la tripulación, y cada dato queda firmado en un registro que no se puede alterar sin que se note.» | "The crew decides, and every data point is signed into a record that can't be altered without it showing." |
| 25–30 s | Logo y nombre | «EMMA. Apoyo a la decisión cuando la Tierra está lejos.» | "EMMA. Decision support when Earth is far away." |

---

## Versión completa (5:00)

| Escena | Tiempo | Contenido |
|---|---|---|
| 1 | 0:00–0:20 | El problema |
| 2 | 0:20–0:45 | Qué hace |
| 3 | 0:45–1:20 | La tableta, para cualquiera que la mire |
| 4 | 1:20–1:50 | La voz «EMMA» |
| 5 | 1:50–2:35 | Evento solar sin red, y la vuelta a la normalidad |
| 6 | 2:35–3:00 | Cuando faltan recursos: modos de misión |
| 7 | 3:00–3:25 | Qué se comparte y qué no |
| 8 | 3:25–3:55 | Por qué fiarse |
| 9 | 3:55–5:00 | Del espacio a la Tierra, y cierre |

### Escena 1 — El problema (0:00–0:20)

*Imagen:* la distancia Tierra-Marte; el contador de retardo; una tripulante tomándose el pulso.

**ES** — «El 14 de noviembre de 2026, Marte está a 1,324 unidades astronómicas. Una pregunta al médico de
vuelo tarda once minutos en llegar y otros once en volver. No hay consulta en directo. Lo que la
tripulación necesita saber, lo tiene que saber a bordo.»

**EN** — "On November 14, 2026, Mars is 1.324 astronomical units away. A question to the flight surgeon takes
eleven minutes to arrive and eleven more to come back. There's no live consultation. Whatever the
crew needs to know, they have to know on board."

### Escena 2 — Qué hace (0:20–0:45)

*Imagen:* consola de tripulación; llegan medidas de varias fuentes; se toca el corazón en la figura y se abre
para qué sirve, qué lo mide y su fuente.

**ES** — «EMMA recoge medidas de un wearable, de un test de vigilancia, de un diario, de una ecografía o de
un informe escaneado. Cada medida entra en un formato clínico estándar y se firma. Se compara con
la línea base de esa misma persona, no solo con un rango de población. Cada parte del cuerpo se
toca: dice qué la mide, cómo está y qué evidencia hay detrás.»

**EN** — "EMMA gathers readings from a wearable, a vigilance test, a diary, an ultrasound or a scanned
report. Each reading goes into a standard clinical format and gets signed. It's compared with that
person's own baseline, not just with a population range. Every part of the body can be tapped: what
measures it, how it's doing and what evidence lies behind it."

### Escena 3 — La tableta, para cualquiera que la mire (0:45–1:20)

*Imagen:* la consola en una tableta; el carril de pestañas; la portada con los cinco peligros; «Entorno de la
misión» de órbita baja a Marte; se gira la tableta y la flecha del arriba real sigue el giroscopio
(y, rotulado como demostración, «Seguir la cara»); «Pantalla» con letra grande, «Alto contraste» y
privacidad; el lector de pantalla anuncia una alerta; Escape tres veces y la voz lee el estado.

**ES** — «La consola es una tableta con pestañas. Lo primero, los cinco peligros del vuelo espacial que
define la NASA. El entorno cambia lo que importa: no es lo mismo la órbita baja que la Luna o
Marte. En microgravedad no hay arriba ni abajo. Siguiendo el giroscopio, o la cara de quien mira
como demostración, una flecha señala el arriba real. Hay letra grande, alto contraste y un modo
privacidad. La consola se deja leer con lector de pantalla. Y si alguien no puede mirar, Escape
tres veces o tres dedos encienden la voz y le leen el estado.»

**EN** — "The console is a tablet with tabs. First come the five spaceflight hazards NASA defines. The
setting changes what matters: low orbit is not the Moon or Mars. In microgravity there is no up or
down. Following the gyroscope, or the viewer's face as a demo, an arrow points to the real up.
There's large text, high contrast and a privacy mode. The console works with a screen reader. And
if someone can't look, Escape three times or three fingers turn on the voice and read out the
status."

### Escena 4 — La voz «EMMA» (1:20–1:50)

*Imagen:* manos ocupadas, sin tocar la tableta; se dice «EMMA, ¿cómo estoy?»; el rótulo «Micrófono abierto»;
la respuesta en el hilo; se le pide apuntar en el diario, la propuesta se enseña campo a campo y
solo se firma al decir «confirmo».

**ES** — «Y se le puede hablar. Basta decir «EMMA», sin tocar la pantalla: «EMMA, ¿cómo estoy?». La palabra,
la transcripción y el modelo de lenguaje corren en el equipo, sin red. Lo que redacta el modelo va
rotulado como sin validar. Puede apuntar en el diario o reconocer una alerta, pero no firma nada
hasta que la persona dice «confirmo».»

**EN** — "And you can talk to it. Just say "EMMA", without touching the screen: "EMMA, how am I doing?" The
wake word, the transcription and the language model run on the device, offline. Whatever the model
writes is labelled as unvalidated. It can log a diary entry or acknowledge an alert, but it signs
nothing until the person says "confirmo", I confirm."

### Escena 5 — Evento solar sin red, y la vuelta a la normalidad (1:50–2:35)

*Imagen:* escenario `spe-event-recovery` con la red apagada; la tasa de dosis cruza su límite; las rutinas
pasan a periodo acortado y dicen qué las acorta; la alerta y su explicación, con la recomendación y
su fuente; se avanza en el tiempo: la dosis baja, las rutinas vuelven a su periodo y al final no
queda ninguna alerta; la consola de Tierra con el retardo.

**ES** — «Llega un evento de partículas solares, y la nave está sin red. Basta el dosímetro de a bordo:
mientras la dosis cruza su límite, EMMA acorta las medidas que más importan, y dice por qué. Cuando
algo cambia, explica qué ha cambiado, desde cuándo y frente a qué, qué conviene comprobar y qué
evidencia lo respalda. Recomienda; no diagnostica ni prescribe. La decisión es de la tripulación.
La demo enseña también la vuelta: baja la dosis, las rutinas recuperan su ritmo y, días después, ya
no queda ninguna alerta. En Tierra lo ven después, con el retardo, y la pantalla lo dice.»

**EN** — "A solar particle event arrives, and the spacecraft is offline. The onboard dosimeter is enough:
while the dose is over its limit, EMMA shortens the measurements that matter most, and says why.
When something changes, it explains what changed, since when and against what, what is worth
checking and what evidence supports it. It recommends; it doesn't diagnose or prescribe. The crew
decides. The demo also shows the way back: the dose falls, the routines return to their pace and,
days later, no alert remains. On the ground they see it later, with the delay, and the screen says
so."

### Escena 6 — Cuando faltan recursos: modos de misión (2:35–3:00)

*Imagen:* se declara el modo «mínimo» con un motivo; la lista de medidas suspendidas; las alertas siguen.

**ES** — «En una nave falta de todo: energía, tiempo, manos. La tripulación puede declarar un modo reducido o
mínimo, firmado, y EMMA deja de pedir lo que más cuesta medir. Lo que nunca se apaga es el análisis
ni las alertas.»

**EN** — "On a spacecraft everything is scarce: power, time, hands. The crew can declare a reduced or minimal
mode, signed, and EMMA stops asking for what is costliest to measure. What never switches off is
the analysis and the alerts."

### Escena 7 — Qué se comparte y qué no (3:00–3:25)

*Imagen:* la vista «Qué se comparte y qué no» en «Calidad y sensores»: un bloque por destino (internet,
Tierra con el retardo, a bordo, solo en esta consola); una fila marcada «No lo impone el código»;
el panel de auditoría verificando la cadena.

**ES** — «¿Qué sale de la nave? Una vista lo dice, dato por dato: qué ve Tierra, qué se queda a bordo y qué
no sale nunca de la consola. Y donde el código no lo impone, también lo dice. Cada dato queda en un
registro que no se puede alterar sin que se note.»

**EN** — "What leaves the spacecraft? One view says it, item by item: what the ground sees, what stays on
board and what never leaves the console. And where the code doesn't enforce it, it says so too.
Every data point goes into a record that can't be altered without it showing."

### Escena 8 — Por qué fiarse (3:25–3:55)

*Imagen:* la tabla de las dos métricas.

**ES** — «La probamos con fisiología humana real: de 22 personas sanas, 21 no reciben ninguna alerta. Sobre
esa misma fisiología, inyectando deterioros, detecta el 95 % de las taquicardias sostenidas. Las
derivas lentas se le escapan, y con semanas de datos avisa demasiado. Es en Tierra, no en vuelo, y
lo decimos así.»

**EN** — "We tested it on real human physiology: of 22 healthy people, 21 get no alert at all. On that same
physiology, with injected deterioration, it detects 95% of sustained tachycardias. It misses slow
drifts, and with weeks of data it alerts too often. That's on Earth, not in flight, and we say so."

### Escena 9 — Del espacio a la Tierra, y cierre (3:55–5:00)

*Imagen:* la carta de Stuhlinger (nombre y año en pantalla); un refugio de montaña o un pueblo aislado por
una inundación, con un portátil sin cobertura; un aula; el portátil sin red; el logo.

**ES** — «En 1970, Ernst Stuhlinger respondió a una monja que preguntaba por qué gastar en ir a Marte con
niños pasando hambre: los retos extremos del espacio obligan a soluciones que después vuelven a la
Tierra. Lo que funciona a 22 minutos de la Tierra funciona donde no llega la ayuda: un refugio de
montaña, un pueblo aislado por una inundación. No es la misma medicina: es la misma arquitectura,
sin red y en local. Llevarla ahí, y a los colegios, es visión de producto: hoy no está hecho. EMMA
funciona sin internet y es código abierto. Desarrollada conforme a la norma IEC 62304, Clase B; no
reclama ninguna certificación. EMMA: apoyo a la decisión cuando la Tierra está lejos.»

**EN** — "In 1970, Ernst Stuhlinger answered a nun who asked why spend on going to Mars while children were
going hungry: the extreme challenges of space force solutions that later come back to Earth. What
works 22 minutes from Earth works wherever help can't reach: a mountain hut, a village cut off by a
flood. It isn't the same medicine: it's the same architecture, offline and local. Taking it there,
and into schools, is product vision: it isn't built today. EMMA works without internet and it's
open source. Developed in accordance with the IEC 62304 standard, Class B; it claims no
certification. EMMA: decision support when Earth is far away."

---

## Comprobaciones antes de grabar

- [ ] Las cifras siguen siendo las del anexo de `presentacion.md` (`compliance/external-validation.md`
      y `GET /api/indicators` del día).
- [ ] «95 %» redondea el 95,5 % de detección de la taquicardia sostenida; si la cifra cambia, cambia
      la locución.
- [ ] Se graba con `demo-v1` y la red apagada.
- [ ] El evento solar se graba con el escenario `spe-event-recovery`; la vuelta se enseña avanzando
      el tiempo hasta el final de la ventana. Sin instantánea de DONKI en el paquete (§5.40.4,
      «Límite»), la consola dice «sin datos de NASA DONKI»: lo que acorta las rutinas es la dosis de
      a bordo, y la locución no dice otra cosa.
- [ ] La voz «EMMA» necesita el modelo local y Whisper instalados en el equipo de grabación; si no
      están, la escena 4 no se graba con una respuesta inventada.
- [ ] Las dos versiones usan el mismo montaje; los subtítulos de `subtitulos/` están reajustados a él
      y la locución inglesa explica los rótulos en castellano que se ven.
- [ ] [EQUIPO: música y voces con licencia de uso; nada de imágenes de NASA que no se puedan usar.]
