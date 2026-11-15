# Prueba con lector de pantalla: Narrador de Windows y NVDA

Nota del 2026-11-05. La escribió un asistente de código después de una pasada automática (axe-core
y el árbol de accesibilidad de Chromium, `compliance/hmi-state-of-the-art.md` §5.41). Esa pasada
mira el marcado; **no dice qué oye una persona**. Esta lista es para comprobarlo con un lector de
verdad, en unos 20 minutos por lector.

## Antes de empezar

- EMMA abierta: la aplicación de escritorio, o `npm run dev` en `frontend/` con el backend en
  :8000, en Edge o Chrome. Un escenario cargado con alguna alerta (el de partida las tiene).
- Auriculares: el lector habla por los altavoces.
- **Narrador**: se enciende y se apaga con **Ctrl + Win + Intro**. Su tecla («Narrador») es Bloq
  Mayús o Insert. **Bloq Mayús + Espacio** cambia entre modo examinar (leer con flechas, saltar
  con letras) y modo foco (las teclas van a la página).
- **NVDA** (gratuito, nvaccess.org): **Ctrl + Alt + N** lo arranca; **Insert + Q** lo cierra. Su
  tecla es Insert. En una página empieza en modo exploración; **Insert + Espacio** pasa a modo foco.
- En los dos: **H** salta de encabezado en encabezado, **D** de punto de referencia en punto de
  referencia (en NVDA; en el Narrador también, en modo examinar), **Tab** recorre los mandos.

## Qué pulsar y qué debería decir

Lo que va entre comillas es aproximado: cada lector y cada versión lo dice a su manera. Lo que
importa es que aparezcan el **nombre**, el **papel** (botón, pestaña…) y el **estado** (seleccionada,
presionado, contraído).

| # | Qué hacer | Qué debería decir |
|---|---|---|
| 1 | Abrir EMMA con el lector ya encendido | El título «EMMA» y, al poco, las alertas que hay, una a una y sin cortarse entre ellas («Precaución: Radiación. …»). Al entrar se dicen corteses, sin interrumpir |
| 2 | Pulsar **Tab** una vez desde arriba | «Saltar al contenido, enlace». Con **Intro**, el foco pasa al contenido sin recorrer la franja ni las pestañas |
| 3 | Pulsar **H** varias veces (modo examinar) | Primero el encabezado de nivel 1 «EMMA · Consola de tripulación · crew-01»; después los paneles en nivel 2 y cada alerta en nivel 3 con su nivel y su dominio |
| 4 | Pulsar **D** varias veces | «Banner»; «navegación, Consola, tripulante y escenario»; «principal»; «navegación, Secciones de la consola de tripulación»; «complementario, EMMA (asistente)»; «información de contenido» (Acerca de) |
| 5 | Ir con Tab a «Consola de tripulación» y pulsar **flecha derecha** | «Consolas, lista de pestañas», «Consola de tripulación, pestaña, seleccionada, 1 de 2»; con la flecha, «Consola de Tierra, pestaña, seleccionada, 2 de 2». Al cambiar de consola se dicen sus alertas, corteses |
| 6 | En el carril de secciones, flechas arriba y abajo | Cada sección como pestaña, «x de y»; la de alertas con su recuento («Peligros y alertas, 2 activas, sin reconocer 2») |
| 7 | Tab hasta «Pantalla» e **Intro** | «Pantalla, contraído» y, abierto, «expandido». Dentro: «Baja visión, botón de alternancia, no presionado» y los demás modos igual. **Un solo «Pantalla»**, no dos |
| 8 | Dentro de Pantalla, pulsar **Privacidad** | «Presionado». Después: la franja dice «tripulante tapado»; el selector de tripulante ya no se alcanza con Tab; los paneles personales dicen «Tapado por privacidad». Las alertas se siguen diciendo con nivel y dominio, sin motivos |
| 9 | Pulsar **Quitar privacidad** | Vuelve el selector «Tripulante, cuadro combinado, crew-01» |
| 10 | Sección **Cuerpo**: recorrer las regiones con Tab | «Regiones del cuerpo, lista»; «Corazón y circulación, Nominal, botón de alternancia, no presionado»; con Intro, «presionado» y debajo su cadena. (Antes eran «opciones» sueltas; se cambió en esta pasada) |
| 11 | Barra superior, junto a «Escenario:» | «Escenario al que cambiar, cuadro combinado, Cambiar a…». **No cambiarlo** si no se quiere perder la sesión simulada |
| 12 | Tab hasta «EMMA (asistente) Mostrar» e Intro | «EMMA (asistente) Ocultar, botón, expandido»; la respuesta del asistente se dice sola al llegar (región cortés). El asistente puede tardar o no estar disponible: anotarlo, no es un fallo del lector |
| 13 | Con el lector encendido, pulsar **Escape tres veces** seguidas | Enciende la voz de EMMA y lee el estado; o, sin voz, el aviso del Narrador. Puede que el lector se quede las pulsaciones: anotarlo |

## Qué apuntar

Para cada paso: **lector y versión**, **navegador o aplicación de escritorio**, el número del paso
y una de estas tres cosas:

- **Bien**: dijo nombre, papel y estado.
- **Raro**: lo dijo, pero confunde (dos cosas con el mismo nombre, un símbolo leído en voz alta como
  «punto medio», un orden que no se entiende, algo dicho dos veces).
- **Mal**: no lo dijo, lo dijo mal, o el foco se perdió (se quedó en ningún sitio o volvió arriba).

Copiar la frase tal cual la dijo el lector, aunque sea larga: es lo que sirve para arreglarlo.
Apuntar también si una alerta **interrumpió** cuando no debía, o **no se dijo** cuando apareció.

## Lo que ya se sabe y no hace falta apuntar

- La voz propia de EMMA y el lector son dos salidas: con las dos encendidas, una alerta se oye dos
  veces (§5.40).
- Las gráficas no tienen alternativa textual completa; sí sus tablas y frases.
- Las alertas se dicen en el sondeo (cada 30 s), no en el instante en que el backend las detecta.
