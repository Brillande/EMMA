# Cronograma día a día hasta el evento (3–15 de noviembre de 2026)

Borrador del 2026-11-02, hecho con la priorización del equipo
(`docs/contexto/prioridades-evento.md`). El evento es el **sábado 14 y el domingo 15 de noviembre**
(`compliance/challenge-coverage.md` §4); la pestaña «Resources» del reto se publica el **viernes 13**
(§1). [EQUIPO: asignar responsables y confirmar la hora límite de entrega del día 15.]

Criterios de orden:

- Primero lo que el jurado busca en el enunciado y hoy falta o está a medias (la función de cada
  órgano, las instrucciones y el glosario, la gamificación): se ve en la demo y en el vídeo.
- Los textos se escriben pronto y se graban tarde: la grabación va sobre la versión congelada.
- Lo que gasta más trabajo (y más tokens del asistente de código) va al principio de la semana, con
  margen; los últimos días solo se ensaya y se corrige.
- Toda tarea de código cumple `CLAUDE.md`: invariantes, pruebas en verde, `docs/contexto/README.md`
  y `compliance/challenge-coverage.md` actualizados en el mismo cambio que cierre un hueco.
- Si se tocan umbrales, línea base o riesgo, se reportan las dos métricas juntas (invariante 5).

---

## Semana 1: construir lo que falta

### Martes 3

- Revisar y corregir estos textos (`docs/entrega/`); rellenar los huecos de equipo de
  `uso-de-ia.md` (lista completa en `huecos-equipo.md`).
- **Función de cada órgano en la figura humana:** decidir las fuentes y empezar el texto. Cada
  frase con su fuente; ninguna inventada. Se apoya en `backend/app/anatomy.py` y
  `frontend/src/anatomy/`.

### Miércoles 4

- **Función de cada órgano:** terminar e integrar en la cadena de la región
  (`frontend/src/anatomy/RegionChain.tsx`). El texto viene del backend: la interfaz no redacta texto
  clínico.
- **Instrucciones paso a paso y glosario:** empezar por las medidas que pide el reto (tensión,
  pulso, temperatura, glucosa, sueño, ánimo).

### Jueves 5

- **Instrucciones y glosario:** terminar.
- **Gamificación** (la única fila «no» del enunciado): por una vía que no use el color ni la
  animación como premio, porque llevan los significados de la tabla F.5-1 (por ejemplo, rachas de
  medidas hechas al día). Diseño y primera versión.

### Viernes 6

- **Gamificación:** terminar.
- **Monitorización intensificada ante un evento:** subir la frecuencia y priorizar parámetros cuando
  se dispara un evento, sobre lo que ya hay (`backend/app/analysis/radiation.py`,
  `backend/app/routines.py`). Luce en la demo con DONKI.
- **Hecho (2026-11-04): que el evento solar se vea en la demo sin red y la vuelta a la normalidad.**
  Sin red, la monitorización la intensifica la dosis de a bordo por encima de su límite; escenario
  `spe-event-recovery` (comienzo, periodo intensificado y vuelta a nominal en la línea temporal);
  instantánea fechada de DONKI para el instalador, declarada «no en vivo». **Pendiente antes de
  `demo-v1`:** ejecutar `backend/scripts/fetch_donki_snapshot.py` con red (mejor con clave propia en
  `EMMA_NASA_API_KEY`) y fusionar el `backend/app/data/donki_snapshot.json` que escribe
  (`compliance/hmi-state-of-the-art.md` §5.40.4).

### Sábado 7

- **Desconexión progresiva:** qué es lo mínimo con poca energía o poca tripulación, sobre el modo
  seguro y el fallo cerrado que ya existen (`backend/app/api/safe_mode.py`). Con la monitorización
  intensificada forma los «modos de misión».

### Domingo 8

- Margen para lo que se haya retrasado.
- Si sobra tiempo: **perfil de róver o de base** y **perfil cislunar**
  (`backend/app/data/mission_profiles.json`).
- Actualizar `compliance/challenge-coverage.md` §2 con las filas que hayan cambiado de «no» o «en
  parte».

---

## Semana 2: congelar, grabar, ensayar

### Lunes 9

- ~~Interfaz en inglés, como mínimo la demo.~~ Sustituido (Ellande, 2026-11-04): el vídeo es uno
  solo, con la consola en castellano, y lleva dos versiones de locución y subtítulos, ES y EN
  (`guion-video.md`, «Reglas del guion»; subtítulos en `subtitulos/`).
- Si sobra tiempo: modo deslumbramiento o alto contraste (dentro de `frontend/src/lib/palette.ts`) y
  la vista de qué se comparte y qué no (sobre `backend/app/core/egress.py`).
- Primer ensayo de la demo (`presentacion.md`, diapositiva 9), cronometrado.

### Martes 10

- **Congelar la versión de demo:** suite, `ruff`, `mypy --strict`, `tsc` y `npm test` en verde;
  instalador con `npm run dist` (`desktop/`); etiqueta git **local** `demo-v1`. Desde aquí, los
  mentores solo ven esa versión, y los cambios van a otra rama.
- Volver a leer las cifras del anexo de `presentacion.md` sobre `demo-v1` y corregir los textos si
  han cambiado.

### Miércoles 11

- **Grabar el vídeo (una sola imagen) con la locución en castellano** (versión completa de 5 min y avance de ~30 s, `guion-video.md`) sobre
  `demo-v1`, sin red.
- Montar la presentación en castellano.

### Jueves 12

- **Grabar la locución inglesa sobre el mismo montaje** y reajustar los tiempos de los subtítulos ES
  y EN (`subtitulos/`).
- Montar la presentación en inglés.
- Cerrar la página del proyecto (`pagina-proyecto.md`) y la declaración de uso de IA
  (`uso-de-ia.md`), en inglés y castellano.
- Ensayo completo: presentación + demo, en los dos idiomas.

### Viernes 13

- **Leer la pestaña «Resources» del reto** y **ver su vídeo**; rellenar la tabla de
  `compliance/challenge-coverage.md` §3 (un recurso por fila, su clase y si EMMA ya lo usa) y
  actualizar la ficha del enunciado si la página ha cambiado.
- Comprobar en «Resources» o en el formulario de entrega la duración del vídeo, el número de
  diapositivas y los campos de la página, y recortar lo que haga falta.
- Si los recursos cambian algo de lo que se cuenta, retocar textos (no el código de `demo-v1`).
- Ensayo final; instalador `demo-v1` probado en el portátil de la demo, sin red.

---

## El evento

### Sábado 14 — primer día

- [EQUIPO: horario del evento local.]
- Presentar a los mentores sobre `demo-v1`.
- Lo que digan los mentores se anota; solo se toca el código si es un fallo, y en otra rama.
- Si hace falta, regrabar la versión corta del vídeo.

### Domingo 15 — entrega

- Subir la entrega: vídeo, presentación, página del proyecto y descripción del uso de IA.
  [EQUIPO: hora límite.]
- Última lectura de los textos contra `CLAUDE.md`: nada de «certificado», nada que suene a orden
  médica, cifras con su fuente.
- Nada del repositorio se sube a ningún sitio: es solo local (`CLAUDE.md`, «Convenciones»). Lo que
  se entrega son los textos y el vídeo. [EQUIPO: si el formulario pide un enlace al código, la
  decisión de publicarlo es solo del usuario.]

---

## Lo que no entra antes del evento

De `docs/contexto/prioridades-evento.md` §5: ecografía de ligamentos, sincronización diferida con
el enlace roto, pestañas laterales tipo tableta, DSM-5 y análisis lingüístico (chocan con la
invariante 7 o serían Clase C sin validar), y lo que necesita hardware. Las ideas del §4 (uso en
emergencias en Tierra, divulgación con colegios, ruta según el estado médico, datos para
investigación, protocolo de muestras) van solo en la presentación, diapositivas 10 y 11.
