# Propuesta: versiones 1, 2 y 3 para los mentores (sábado 14)

**Propuesta para que el equipo la apruebe o la cambie**; borrador del 2026-11-05 escrito por un
asistente de código a partir del repositorio (commit `b079df9`). Responde a la pregunta «¿versiones
1, 2 y 3 para mentores?» del ideograma. Solo usa hechos del repositorio; lo que no existe todavía
lo dice.

La regla de partida ya está decidida: a los mentores se les enseña **solo la versión congelada**
`demo-v1`, y lo que digan se anota; el código solo se toca si es un fallo, y en otra rama
(`cronograma.md`, martes 10 y sábado 14; `docs/contexto/prioridades-evento.md`, idea 11). Las tres
«versiones» de abajo no son tres programas distintos: son tres capas de lo mismo, de lo que corre a
lo que es solo idea.

## v1 — lo que corre: `demo-v1`, congelada y sin red

- **Qué es:** la etiqueta git local `demo-v1` que se pone el martes 10 (`cronograma.md`), con la
  suite, `ruff`, `mypy --strict`, `tsc` y `npm test` en verde, y su instalador de Windows
  (`desktop/`, `npm run dist`). **Hoy todavía no existe**: las etiquetas actuales son `hito-01` a
  `hito-08`; la última, `hito-08-tableta-y-entornos` (`a41c64c`), es la interfaz para tableta y el
  entorno de la misión declarable.
- **Qué se enseña:** el guion de demo de `presentacion.md` (un tripulante, un evento solar sin red,
  una decisión firmada y la vuelta a la normalidad), con la red desactivada: `EMMA_OFFLINE=true` es
  el modo nominal de misión.
- **Antes:** la instantánea de DONKI (`backend/scripts/fetch_donki_snapshot.py`) tiene que estar en
  el paquete; hoy no está (`huecos-equipo.md`).
- **Qué se pide a los mentores:** si el problema y la demo se entienden en 3 minutos, y qué sobra.

## v2 — lo mismo, con el asistente de voz

- **Qué es:** `demo-v1` con el asistente local (palabra «EMMA» con Vosk en el navegador, modelo
  `qwen3.5:9b` en Ollama; `hito-07-asistente-jarvis`, `compliance/hmi-state-of-the-art.md` §5.43).
  Su borrador nunca entra en el análisis ni en una alerta (invariante 6).
- **El modelo ajustado no entra:** el ajuste fino LoRA se probó y acertó 191 de 198 frente a 192 de
  198 del modelo sin ajustar, así que no se adoptó (`uso-de-ia.md`, punto 5). Esta versión solo
  cambiaría si un ajuste nuevo **supera** al modelo base en la misma batería, antes del martes 10.
- **Condición:** que el portátil de la demo tenga Ollama con su modelo; si no, se enseña en el
  vídeo (`presentacion.md`, notas de la demo).
- **Qué se pide a los mentores:** si el asistente aporta o distrae en una demo corta.

## v3 — la visión: lo que no está construido

- **Qué es:** las diapositivas de visión de `presentacion.md` (13 a 15), rotuladas como ideas y no
  como funciones: uso en Tierra (emergencias, montaña), divulgación con colegios, y datos para
  investigación con consentimiento y protocolo de muestras (`docs/contexto/prioridades-evento.md`
  §4). OSD-288 son ratones: no se presenta como dato de astronautas.
- **Qué se pide a los mentores:** cuál de las tres ideas les parece más defendible ante el jurado.

## Lo que el equipo tiene que decidir

- [ ] Aprobar las tres capas, o quedarse solo con v1 (y v2 en vídeo).
- [ ] En qué orden y cuánto tiempo cada una (depende del horario del evento local, aún sin fijar).
- [ ] Quién presenta y quién anota lo que dicen los mentores.
