# Prueba de micrófono y voz en vivo

Lista para la primera prueba con persona y micrófono real (ideograma P1). Hasta ahora todo lo
comprobado es con voz sintética y micrófono falso de Chromium (`compliance/hmi-state-of-the-art.md`
§5.43 y §5.44): esta prueba es la que falta. Apunta lo que pase, también lo que salga bien.

## Antes de empezar

1. Aplicación instalada, o `http://localhost:5173` con el backend en `:8000`.
2. Ollama en marcha con `qwen3.5:9b` (sin modelo, EMMA contesta solo lo que tiene en tabla).
3. Sala sin mucho ruido para la primera pasada; luego, si quieres, una segunda con ruido.
4. Consola de tripulación, con un tripulante elegido y tu nombre en «quién está en consola» (sin
   él no se firma nada).

## 1. Manos libres: «Escuchar «EMMA»»

1. Abre el plegable **«Pantalla»** (al pie del carril de pestañas) y pulsa **«Escuchar «EMMA»»**.
2. El navegador o Windows pide permiso para el micrófono: **permitir**.
3. Debe salir arriba, en azul, **«Micrófono escuchando»**. Si sale «Escucha no disponible: …» en
   gris, copia el motivo tal cual y salta al apartado 4.
4. La primera vez tarda unos segundos (carga el modelo de la palabra).

## 2. Tres frases

Di la palabra, una pausa corta y la frase. Al oír «EMMA», el aviso pasa a
**«Micrófono escuchando · te escucho»**. Calla ~1 s al acabar: así se cierra la frase.

| Di | Debe pasar |
|---|---|
| «EMMA, ¿cómo estoy?» | El panel «EMMA (asistente)» se abre, sale tu frase transcrita y una respuesta, y EMMA la dice en voz alta. Si la redactó el modelo, lleva «respuesta del modelo local, sin validar». |
| «EMMA, abre la biblioteca» | Se abre la pestaña de la biblioteca. |
| «EMMA, apunta en el diario que mi ánimo es un 6» | **No se escribe nada todavía.** Sale una propuesta campo a campo, con quien firma, y EMMA pide «confirmo» o «cancela». |
| «EMMA, confirmo» | Se firma la entrada del diario (o di «cancela» para descartarla). Comprueba que aparece en el diario. |

Para apagar la escucha: «EMMA, deja de escuchar» (el aviso azul desaparece), o vuelve a pulsar el
mando. También se apaga sola al ocultar la ventana o al poner la privacidad.

## 3. Otras formas de hablar

- **Pulsar y hablar:** mantén **Ctrl+Espacio** (o el botón «Hablar con EMMA») mientras hablas y
  suelta al acabar. Mientras, sale «Micrófono abierto» en azul.
- **Voz de emergencia:** **Esc tres veces** seguidas (o tres dedos un segundo en la pantalla; en la
  aplicación de escritorio, **Ctrl+Alt+V**): activa la voz y lee el estado sin mirar la pantalla.
- **Voces:** solo voces locales del equipo. En Windows en español deberían estar Helena, Laura y
  Pablo; prueba que la que suena se entiende bien.

## 4. Si algo falla, apunta

- **El texto exacto de la pantalla** (por ejemplo «Hablar no disponible: …», «Escucha no
  disponible: …», «Asistente no disponible», «No conozco esa orden; no hago nada»).
- **Lo que transcribió** (la línea «Tú …» del panel) frente a lo que dijiste.
- **Dónde se quedó:** no oyó «EMMA» (el aviso no pasó a «te escucho») → palabra de activación
  (Vosk); oyó pero la transcripción sale mal o vacía → Whisper; transcripción bien pero respuesta
  rara, lenta o ninguna → modelo (Ollama).
- Cuánto tardó la respuesta, aproximado, y si había ruido.
- Si EMMA se disparó sola (con «Emma» en una conversación o con su propia voz).

## Comprobación previa (2026-11-05)

Con el micrófono falso de Chromium (`emma_fc.wav`, «EMMA, ¿cuál es mi frecuencia cardíaca?» en voz
sintética) contra el servidor de desarrollo y el backend reales, `qwen3.5:9b` en la GPU: la
palabra se oyó, Whisper transcribió «¿Cuál es mi frecuencia cardíaca?» (una vez «frecuencia cadía
acá»), y EMMA respondió y dijo «Tu frecuencia cardíaca es de 49 por minuto», rotulado como
respuesta del modelo sin validar. Ninguna petición fuera del origen. No sustituye a esta prueba:
voz sintética limpia, sin ruido ni acento.
