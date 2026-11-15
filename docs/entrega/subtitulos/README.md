# Subtítulos del vídeo (ES / EN)

Decisión de Ellande (2026-11-04): un solo montaje con dos versiones, locución y subtítulos en
castellano, y locución y subtítulos en inglés. La consola en pantalla sigue en castellano en las dos
(`../guion-video.md`, «Reglas del guion»).

| Fichero | Vídeo | Idioma |
|---|---|---|
| `emma-5min.es.srt` / `emma-5min.en.srt` | versión completa (5:00) | castellano / inglés |
| `emma-30s.es.srt` / `emma-30s.en.srt` | avance (~30 s) | castellano / inglés |

## De dónde salen

- El texto es la locución de `../guion-video.md`, tal cual. Las frases se han partido en varios
  subtítulos donde hacía falta, sin cambiar sentido ni cifras ni añadir nada. Si cambia el guion,
  cambian los subtítulos.
- Formato SRT, UTF-8. Cada subtítulo tiene como mucho 2 líneas de 42 caracteres y una velocidad de
  lectura de unos 17 caracteres por segundo.
- Cada subtítulo cae dentro de la ventana de tiempo de su escena y ninguno cruza de una escena a
  otra. Dentro de la escena, el tiempo se reparte según la longitud del texto más largo de los dos
  idiomas.

## Mismos cortes en los dos idiomas, a propósito

Los ficheros ES y EN de cada vídeo tienen **el mismo número de subtítulos y los mismos tiempos**,
porque la imagen es la misma. Si se parte o se une un subtítulo en un idioma, se hace también en el
otro.

## Los tiempos son provisionales

Salen de los tiempos de escena del guion, no del montaje. Cuando el montaje esté cerrado y estén
grabadas las locuciones (las graba el equipo: `../huecos-equipo.md`):

- **Desplazar todos los subtítulos** (si el montaje empieza antes o después): en Subtitle Edit,
  «Sincronización → Ajustar todos los tiempos»; con ffmpeg, `ffmpeg -itsoffset 2.5 -i emma-5min.es.srt
  salida.srt` adelanta o retrasa 2,5 s. Se aplica el mismo desplazamiento a ES y EN.
- **Reajustar una escena** si su duración cambia: se mueven sus subtítulos sin pasar del principio de
  la escena siguiente.
- Incrustarlos en la imagen o subirlos como pista aparte depende del formulario de entrega; se
  comprueba el 13 de noviembre.
