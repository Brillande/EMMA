# Inventario para el apagado progresivo: funcionalidades, coste energético y familias

_Borrador de trabajo, 2026-11-11. Preparación de la idea «desconexión progresiva» (prioridades del
evento, `docs/contexto/prioridades-evento.md`)._

## Qué hay ya y qué falta

EMMA ya tiene tres niveles de misión (`backend/app/data/mission_modes.json`, cargados por
`core/mission_modes.py`): **nominal → reducido → mínimo**. Deciden **qué medidas se siguen
esperando**, por clase de medida (continua, periódica sin muestra, con muestra, laboratorio) y por
si gasta consumibles. El propio fichero lo dice: «EMMA no tiene la potencia eléctrica de los
equipos, y el nivel no la estima».

Este inventario prepara esa pieza que falta, en dos ejes que hoy no existen:

1. **El coste eléctrico de los instrumentos** que dan las medidas (hardware).
2. **El coste de las funciones del propio EMMA** en el ordenador de a bordo (software): modelo de
   lenguaje, voz, cámara, 3D, OCR… Los niveles actuales no apagan nada de esto.

## Cómo leer las cifras

**Las clases 0-4 de las tablas A y B no están medidas ni tienen fuente leída**: son un orden
relativo, no datos para el modelo. Lo medido (en el portátil de desarrollo, no en hardware de
vuelo) está en §F, y lo leído en fuentes, con su cita, en §G; donde una medida corrigió una clase,
la celda lo dice. Antes de que un nivel use una cifra, tiene que venir de §F, de §G o de una medida
nueva, como el resto del proyecto.

| Clase | Significado (orden de magnitud típico de la categoría, sin fuente) |
|---|---|
| 0 | No consume a bordo, o lo paga otro sistema de la nave y no depende de EMMA |
| 1 | Muy bajo: sensor de batería con radio de baja energía (mW) |
| 2 | Bajo: ráfaga corta de CPU, o equipo pequeño encendido unos minutos |
| 3 | Medio: CPU sostenida, pantalla encendida, equipo de sobremesa encendido |
| 4 | Alto: GPU sostenida, o CPU/GPU al máximo durante minutos |

- **Arranque**: coste puntual de ponerlo en marcha (cargar un modelo, calentar un equipo).
- **En uso**: mientras trabaja.
- **Standby**: encendido y listo, sin trabajo. Es la columna que más importa para apagar: lo que
  cuesta en standby es lo que ahorra apagarlo.

---

## A. Instrumentos (hardware): de dónde salen las medidas

Familias por el campo `equipment` de `measurement_cost.json` (129 indicadores; la cuenta vigente
la da `/api/indicators`).

| Familia (instrumento) | Funcionalidades / indicadores | Arranque | Uso | Standby | Notas para el apagado |
|---|---|---|---|---|---|
| **A1. Wearable de pecho/muñeca (BLE)** | FC, HRV SDNN, HRV RMSSD, frecuencia respiratoria. Ingesta BLE en vivo (trama 0x2A37 con R-R) e importación Apple Health / Google Fit (`ingest/wearable.py`) | 1 | 1 | 1 | Una sola radio da 4 indicadores. Lo más barato que hay y lo único que vigila sin que nadie haga nada: último en apagarse |
| **A2. Pulsioxímetro** | SpO₂ | 1 | 1 | 0–1 | Puede ir integrado en A1; si es aparte, se puede pasar a puntual |
| **A3. Sensor de temperatura** | Temperatura corporal | 1 | 1 | 1 | Igual que A2 |
| **A4. Actígrafo / acelerómetro** | Duración y eficiencia de sueño, desfase circadiano, impactos de carga | 1 | 1 | 1 | Si es el mismo reloj que A1, es la misma familia: un dispositivo, 7-8 indicadores |
| **A5. Sensores inerciales + vídeo** | Marcha en tándem, levantarse tras estar tumbado | 2 | 2 | 0 | Prueba puntual; la cámara de vídeo pesa más que las IMU |
| **A6. Tensiómetro** | PAS, PAD, caída ortostática | 2 | 2 | 0 | Solo consume al medir; standby 0 si se apaga |
| **A7. Medidor de masa en microgravedad** | Masa corporal | 2 | 2 | 0–2 | Equipo de la nave; standby según el equipo |
| **A8. Ecógrafo** | ONSD izq./der., yugular izq./der., volumen vesical; estudios DICOM, cine, medida guiada (`imaging/`) | 3 | 3 | 2 | De los equipos más caros por sesión; 5 indicadores. Candidato a «solo bajo petición» en reducido |
| **A9. Analizador de gases (esfuerzo)** | VO₂ pico | 3 | 3 | 2 | Más cicloergómetro (A10) |
| **A10. Equipo de ejercicio (ARED, cinta, ciclo)** | Minutos de ejercicio, fuerza IMTP (en vuelo, el ARED) | 0 | 0 | 0 | Lo paga la nave; EMMA solo lee su registro. Apagar EMMA no ahorra nada aquí |
| **A11. Dosímetro de la nave** | Tasa de dosis absorbida → dosis acumulada (derivada) | 0 | 0 | 0 | Equipo de la nave; la dosis es seguridad, no se apaga |
| **A12. Anclas de ubicación (BLE/UWB)** | Módulo donde está cada tripulante (`analysis/location.py`, `scripts/anchor_gateway.py`) | 0 | 0 | 0 para la nave / 1 la pasarela | Las balizas son de la nave (decisión 2026-11-10); EMMA solo escucha. La pasarela es lo único propio |
| **A13. Sistemas del hábitat** | CO₂ y demás del módulo (`environment/habitat.py`, `systems.py`) | 0 | 0 | 0 | Lo paga la nave |
| **A14. Analizador de sangre** | ~45 analitos: hemograma, bioquímica, hormonas, marcadores tumorales, vit. D | 3 | 3 | 2–3 | Gasta consumibles (ya suspendido en «reducido»). Los analizadores clínicos suelen tener calentamiento: el arranque puede ser lo caro |
| **A15. Orina de 24 h / tira / refractómetro** | Volumen, densidad, 8 analitos de cálculos renales, NTx | 0–2 | 0–2 | 0 | Casi todo se mide en Tierra (`orina-24h-en-tierra`); a bordo, coste eléctrico casi nulo |
| **A16. Saliva + análisis** | Cortisol salival, excreción de virus latentes | 0 | 0 | 0 | Se analiza en Tierra; a bordo solo recoger |
| **A17. Glucómetro** | Glucosa capilar | 1 | 1 | 0 | Pila; gasta tiras (consumible) |
| **A18. Dinamómetro de mano** | Fuerza de prensión der./izq. | 0 | 0–1 | 0 | Mecánico o con pila |
| **A19. DXA (solo en Tierra)** | DMO lumbar, cadera, masa magra | 0 | 0 | 0 | No vuela: coste a bordo 0 |
| **A20. Consola / portátil de la tripulación** | PVT (2), batería Cognition (17), autoinformes (ánimo, síntomas, dolor, estrés, TLX, cohesión ×3, visión, apetito, aceptabilidad), registro de ingesta (8), diario | ver S2 | ver S2 | ver S2 | **No es un instrumento aparte: es la pantalla.** ~35 indicadores dependen de ella, incluidos síntomas y dolor, que el nivel «mínimo» sigue esperando. O se deja un camino de bajo consumo para declararlos, o el «mínimo» exige pantalla |

---

## B. Funciones de EMMA (software) en el ordenador de a bordo

| Familia (recurso) | Funcionalidades | Arranque | Uso | Standby | Notas para el apagado |
|---|---|---|---|---|---|
| **S1. Núcleo (CPU, siempre)** | Backend FastAPI, ledger encadenado y firmado, almacén, línea base, tendencia, riesgo, alertas, recomendaciones, evidencia (`core/`, `analysis/`, `advisor/`, `evidence/`) | 2 | 1–2 | 1 | Es lo que da sentido al sistema; nunca se apaga. Petición a petición es barato |
| **S2. Consola / pantalla** | Las dos consolas (tripulación y Tierra), refresco cada 30 s (`useConsoleData.ts`, `REFRESH_MS`) | 2 | 3 | 1–3 | **La pantalla suele ser el mayor consumo del portátil.** Bajar brillo, alargar el refresco o apagarla tras inactividad es el primer ahorro sin perder ninguna medida |
| **S3. 3D en la interfaz (GPU)** | Cuerpo 3D de Dolor e Inicio (~160 000 triángulos), visor 3D de Polaris (TAC/RM), cine de ecografía, bucles `requestAnimationFrame` | 2 | 1–2 (cuerpo 3D medido, §F) | 0 (cuerpo 3D medido) | El cuerpo de Dolor dibuja solo cuando cambia algo: quieto no gasta. El visor de Polaris y el cine de ecografía, sin medir |
| **S4. Modelo de lenguaje local (Ollama, GPU)** | Borrador de interpretación (`interpret/`, Clase C), asistente (`assistant/`), modelos verificadores; calentamiento al arrancar (`api/assistant.py`, `warm_up`) | 2 (medido, §F) | 4 (medido: ~74 W) | 1 en energía, alto en VRAM (§F) | **El más caro con diferencia al generar.** Cargado y quieto apenas gasta energía, pero retiene la VRAM. No entra nunca en el análisis ni en las alertas (invariante 6): apagarlo no quita vigilancia. Primero en apagarse |
| **S5. Palabra de activación «EMMA» (micrófono)** | Vosk en WebAssembly escuchando de continuo (`assistant/wake/`) | 2 | 3 (medido, §F) | 3 (medido: ~13 % de un núcleo) | Standby = uso: escucha todo el rato. La función de interfaz que más gasta de forma continua |
| **S6. Transcripción de voz (Whisper)** | Dictado al asistente (`voice.py`, `.venv-voice`) | 3 | 3–4 | 0 | Ráfaga cara por frase; standby 0 si el proceso no queda residente |
| **S7. Lectura en voz alta** | `ReadAloud.tsx` (síntesis del sistema) | 1 | 2 | 0 | Barato |
| **S8. Seguimiento de cara (cámara)** | MediaPipe para girar la vista (`lib/faceCamera.ts`, demo sin validar) | 2 | 3 | 0 | Cámara + detector continuo. Es una demo: fuera en cuanto haya que ahorrar |
| **S9. Búsqueda semántica** | Modelo e5-small cuantizado, ONNX en CPU (`data/kb-model`, ~130 MB) | 2 | 2 | 1 | Arranque = cargar el modelo en memoria; cada consulta es una ráfaga corta |
| **S10. Documentos escaneados** | OCR local (tesseract), des-identificación (`.venv-deid`), extracción de analíticas, identidad del paciente, incongruencias (`reports/`) | 2–3 | 3 | 0 | Bajo demanda; se puede diferir sin perder nada (los informes esperan) |
| **S11. Segmentación de TAC** | TotalSegmentator (`volumes/segment.py`, `.venv-seg`, PyTorch) | 4 | 4 | 0 | Minutos de GPU/CPU al máximo. Siempre diferible: es imagen de referencia previa, no diagnóstico a bordo |
| **S12. Ecografía (software)** | Lectura DICOM, render a PNG, medida guiada, fantomas (`imaging/`) | 1 | 2 | 0 | Va con A8: si el ecógrafo está apagado, esto no trabaja |
| **S13. Datos externos (red)** | Efemérides Horizons/SPICE, DONKI, iSWA, SSCweb, OSDR, NTRS (`environment/`, `core/egress.py`) | 1–2 | 2 (+ radio) | 0 | `EMMA_OFFLINE=true` ya es el modo nominal: con la precarga (`/comms/preload`) este coste puede ser 0. El coste real es el del enlace de la nave |
| **S14. Enlace con Tierra (sincronización)** | Cola de lo pendiente y corte de Tierra (`core/link_sync.py`) | 1 | 2 (+ radio) | 1 | Agrupar envíos en ventanas ahorra radio |
| **S15. Simulador** | Constantes simuladas, fantomas, muestras | 1 | 1 | 0 | Solo demo; en vuelo real no corre |
| **S16. Escritorio (Electron)** | Envoltorio que arranca el backend congelado y abre la interfaz (`desktop/`) | 2 | ver S2 | ver S2 | Un Chromium entero; en un terminal mínimo se podría servir la interfaz sin él |

---

## C. Familias que comparten recurso (lo que se apaga junto)

Apagar un recurso apaga todas sus funciones a la vez. Agrupadas así:

| Recurso compartido | Funciones que caen juntas |
|---|---|
| **GPU** | S4 modelo de lenguaje, S11 segmentación, S3 3D (y S6 Whisper si corre en GPU) |
| **Micrófono** | S5 palabra de activación, S6 dictado |
| **Cámara** | S8 seguimiento de cara, A5 vídeo de la marcha |
| **Pantalla** | S2, S3 y los ~35 indicadores de A20 (PVT, Cognition, autoinformes, ingesta, síntomas, dolor) |
| **Radio BLE del wearable** | A1-A4 (si es un solo dispositivo, 7-12 indicadores) |
| **Radio de la nave / enlace** | S13, S14 |
| **Ecógrafo** | A8 + S12 |
| **Analizador de sangre** | A14 (~45 indicadores; ya suspendido en «reducido» por consumibles) |
| **Lo paga la nave** | A10, A11, A12, A13: apagar EMMA no ahorra nada; son las fuentes que quedan cuando todo lo demás está apagado |

---

## D. Primer orden de apagado que sale de las tablas (para discutir)

Ordenado **solo por energía y por lo que se pierde de vigilancia**, no por importancia clínica,
que EMMA no puede afirmar (lo mismo que dice `mission_modes.json`). Es una propuesta para hablar con
el equipo, no una decisión.

1. **Lo que no vigila nada y gasta mucho**: S8 cámara (demo), S4 modelo de lenguaje (y su
   calentamiento al arrancar), S11 segmentación, S3 animación 3D (pasar a silueta 2D).
2. **Lo que se puede diferir sin perder datos**: S10 OCR y documentos, S6 dictado, S13 red
   (ya cubierta por la precarga), S14 agrupar envíos.
3. **Ahorros de pantalla**: alargar el refresco de 30 s, brillo, apagado por inactividad; S5
   palabra de activación fuera (queda el botón).
4. **Instrumentos caros por sesión**: A14 analizador y A9 VO₂ (ya fuera en «reducido» por
   consumibles), A8 ecógrafo solo bajo petición.
5. **Lo último**: S1 núcleo + A1-A4 wearable + lo que paga la nave (A10-A13), más un camino
   barato para declarar síntomas y dolor.

Los niveles actuales cubren el paso 4 y parte del 5 desde los consumibles; los pasos 1-3 (software)
son nuevos.

## F. Medido en el portátil de desarrollo (2026-11-11)

> **Para comprobar estas cifras**: `docs/apagado-progresivo/README.md` dice con qué se mide cada
> magnitud y cómo repetirlo, y trae la tanda reproducible del 2026-11-11 con todas sus muestras en
> `docs/apagado-progresivo/datos/` (scripts en `docs/apagado-progresivo/scripts/`). Las tablas de
> esta sección son de las primeras pruebas del mismo día; donde difieren de la tanda reproducible,
> mandan los datos. Estas tablas se hicieron con la GPU con *overclock* de MSI Center (+200 MHz
> núcleo y memoria); el registro tiene también la tanda **de serie** y la comparación. **Causa de los
> fallos de la segmentación en GPU: ese *overclock*.** De serie, con cuDNN encendido, 8 de 8 bien.

**Equipo**: portátil con RTX 4070 Laptop (8 GB), CPU de 32 hilos, enchufado. **No es hardware de
vuelo**: sirve para comparar funciones entre sí, no como cifra de la nave. GPU en vatios con
`nvidia-smi` (potencia de la placa); CPU como % de uso del sistema (Windows no da vatios de CPU
sin herramientas aparte). Muestreo cada 0,5 s. Script: `medir.py` en el scratchpad de la sesión.

**S4, modelo de lenguaje** (`qwen3.5:9b`, el que usa hoy el asistente; el de `config.py`,
`qwen3.6:35b-a3b`, no está instalado y no cabe en 8 GB):

| Fase | Duración | GPU media | GPU máx. | Uso GPU | VRAM | CPU |
|---|---|---|---|---|---|---|
| Reposo, sin modelo | 20 s | 9,8 W | 10,7 W | 3 % | 1,8 GB | 4,9 % |
| Cargar el modelo | 7,8 s | 12,5 W | 21,9 W | 10 % | → 5,0 GB | 9,9 % |
| Modelo cargado, sin trabajo | 20 s | 11,0 W | 15,4 W | 2 % | 7,6 GB | 4,9 % |
| Generar 300 tokens | 7,5 s | **74,2 W** | 90,3 W | 93 % | 7,6 GB | 7,7 % |

Lo que cambia respecto a las clases de arriba:
- **Arrancar el modelo es barato** aquí (~8 s a ~12 W, ~100 J). La clase 4 de arranque era
  exagerada para un modelo de 9 B; habría que volver a medir con uno de 35 B.
- **El standby con el modelo cargado cuesta ~1 W más que sin él**, pero retiene 5,8 GB de VRAM: el
  coste del standby es memoria, no energía. Apagarlo libera la GPU para la segmentación o el 3D.
- **Lo caro es generar**: ~74 W mientras escribe, ~1,9 J por token (557 J por 300 tokens). Siete
  veces el reposo de la GPU. Ahorrar aquí es limitar respuestas, no descargar el modelo.

**S1 núcleo y S9 búsqueda** (backend con `EMMA_OFFLINE=true`, sin calentamiento del asistente,
almacén en memoria; CPU en segundos de CPU del proceso y sus hijos):

| Fase | Duración | CPU del proceso | Nota |
|---|---|---|---|
| Arrancar hasta responder | 1,1 s | 0,8 s | |
| Reposo, sin datos | 20 s | 0,02 s | Prácticamente cero |
| Simular la misión (`POST /api/simulate`) | 3,9 s | 3,9 s | Solo demo |
| `/api/status` ×5 | 6,9 s | 6,8 s | La primera 4,2 s; después ~0,7 s y ~1 s de CPU cada una |
| Reposo, con datos | 20 s | 0,0 s | |
| Búsqueda semántica, consulta | 0,1–0,9 s | 11–23 s | Ver nota |
| Búsqueda, primera vez (construye el índice) | 64 s | — | ~80 % de CPU del sistema entero |

- **El backend en reposo no gasta**: el coste de S1 es por petición, no por estar encendido.
- **El coste continuo real lo pone la consola**: refresca cada 30 s y `/api/status` cuesta ~1 s de
  CPU. Es ~3 % de un núcleo para siempre, solo por tener la pantalla abierta. Alargar el refresco en
  los niveles bajos ahorra en proporción directa.
- **La búsqueda semántica cuesta muchos segundos de CPU por consulta** aunque responda en menos de
  un segundo: el modelo ONNX reparte cada consulta entre todos los núcleos, y la cuenta incluye
  probablemente el tiempo en que sus hilos se quedan girando después (sin verificar). Construir el
  índice es una ráfaga de un minuto: que no ocurra en un nivel bajo (hacerlo antes, en nominal).
- `nvidia-smi` no se mueve con el backend: todo es CPU. Sin vatios de CPU, falta convertir a energía.

**S2 consola y S3 3D** (interfaz compilada servida por el backend, misión simulada, Chrome aparte
con perfil limpio y ventana de 1672×941; ventanas de 30 s; CPU en % de un núcleo):

| Situación | Chrome | Tareas de la página | Backend | GPU dedicada |
|---|---|---|---|---|
| Chrome en blanco | 1,9 % | 0 % | 0 % | ~10 W |
| Inicio abierta, quieta | 2,9 % | 0,4 % | 4,5 % | ~8 W |
| Dolor: cuerpo 3D quieto | 0,8 % | 0,1 % | 4,9 % | ~10 W |
| Dolor: cuerpo 3D girando sin parar (arrastre a 30 Hz) | 4,4 % | 1,4 % | 5,2 % | ~11 W |
| Inicio con la ventana minimizada | 0,6 % | 0,4 % | 4,9 % | ~7 W |

- **El 3D no es el gasto que yo suponía.** El cuerpo de Dolor (`pain/BodyMap.tsx`) solo dibuja
  cuando algo cambia, sin bucle de animación; quieto no cuesta nada, y girándolo sin parar sube a
  unos pocos % de un núcleo. Baja de la clase 3 a la 1-2.
- **Con la consola abierta, el que más gasta es el backend** (~5 % de un núcleo, por el refresco de
  datos), y lo sigue haciendo con la ventana minimizada: el refresco no se para cuando nadie mira.
  Pararlo o espaciarlo con la ventana oculta es un ahorro sin perder nada.
- **Lo que falta medir aquí: la pantalla y la GPU integrada.** La GPU dedicada no cambia con la
  interfaz; lo más probable es que Chrome dibuje con la integrada, que `nvidia-smi` no ve. Y el
  panel, que en un portátil suele ser de lo que más consume, no tiene contador. Ninguna de las dos
  cosas está medida.
- El visor 3D de Polaris (TAC) y la ecografía en cine no están medidos.

**S10 OCR, S6 Whisper y S11 segmentación**, llamados como los llama el backend. Durante esta tanda
el equipo tenía ~16 % de CPU de fondo (otras sesiones), así que la CPU va como **exceso sobre el
reposo** (32 hilos: 1 % del sistema ≈ 0,32 núcleos):

| Función | Duración | CPU del sistema (exceso) | GPU | Nota |
|---|---|---|---|---|
| OCR de una página A4 (tesseract) | 1,3–1,7 s | ~+2 % | sin cambio | Ráfaga mínima |
| Whisper `base`, dictado de 8 s | 4–6 s | ~+16–19 % (≈5-6 núcleos) | sin cambio | Corre en CPU; carga el modelo en cada frase, así que no queda nada residente: standby 0 |
| TotalSegmentator, hígado (15 máscaras), CPU | **238 s** | ~+22 % (≈7 núcleos) | sin cambio | ≈ 1 700 s de CPU. Lo más caro de todo EMMA en una sola tarea |

- **La segmentación en GPU falla en este portátil tal como la lanza EMMA** («misaligned address» /
  «illegal memory access» en una `Conv3d` del decodificador de nnU-Net; torch 2.11.0+cu128, cuDNN
  9.19, nnunetv2 2.8.1, TotalSegmentator 2.18.0, controlador 617.42). Una `Conv3d` suelta no falla.
  Probado el 2026-11-11 con la API de Python de TotalSegmentator, mismo TAC y misma tarea:

  Primero, **solo la tarea `total`** (una de las cuatro del preset de hígado):

  | Variante | Resultado | Tiempo | GPU media / máx. |
  |---|---|---|---|
  | Como antes (`cudnn.benchmark = True`, lo pone nnU-Net) | falla siempre (2 de 2) | — | — |
  | `cudnn.benchmark = False` | 4 de 5 bien; 1 fallo | ~21 s | ~8 W / 29 W (en la que falló) |
  | cuDNN desactivado | 5 de 5 bien | ~30–33 s | ~14 W / 37 W, 3,2 GB de VRAM |

  Después, **el preset entero** (`total`, `liver_vessels`, `liver_segments`, `liver_lesions`; 15
  máscaras), que es lo que hay que comparar con los 238 s de CPU de arriba:

  | Variante | Resultado | Tiempo |
  |---|---|---|
  | CPU (`-d cpu`) | bien | 238 s |
  | GPU sin cuDNN, todo bien | 4 tareas en GPU (48 + 42 + 45 + 66 s) | **201 s** |
  | GPU sin cuDNN, reintentando la GPU en cada tarea | `total` bien; las otras 3 fallan en GPU (~25 s perdidos cada una) y se repiten en CPU | 291 s |
  | Tres pasadas reales más, con la máquina ocupada | las 3 terminaron | 216–325 s |

  **Con la GPU libre** (esperando 30 s seguidos con menos del 10 % de uso y 15 W antes de cada
  ronda, sin nada más lanzado; idea de Ellande, por si la GPU estaba ocupada):

  | Variante | Resultado |
  |---|---|
  | Ejecutable original (cuDNN encendido), tarea `total` | 1 de 2 bien; la otra, «illegal memory access» |
  | Sin cuDNN, las 4 tareas, sin paso a CPU, 2 rondas | **7 de 8 bien**; falló `liver_lesions` en la segunda |

  Con la GPU libre falla menos, pero sigue fallando a veces, también con cuDNN encendido: la GPU
  ocupada no es la causa, o no la única. El paso a CPU sigue haciendo falta.

  **Otra versión de torch** (entorno de prueba aparte, sin tocar `.venv-seg`: torch 2.7.1+cu126,
  cuDNN 9.7, mismo TotalSegmentator 2.18.0 y nnunetv2 2.8.1; GPU libre, 2 rondas de las 4 tareas):

  | Variante | torch 2.11 + cuDNN 9.19 | torch 2.7.1 + cuDNN 9.7 |
  |---|---|---|
  | cuDNN encendido | 1 de 2 (solo `total`) | **1 de 8** |
  | Sin cuDNN | 7 de 8 | 8 de 8 |

  Cambiar torch no lo arregla: con cuDNN encendido falla con las dos versiones, y sin cuDNN las dos
  van casi siempre bien. Que falle con dos cuDNN distintos, y alguna vez sin cuDNN, apunta al
  controlador (617.42) o al propio equipo (reloj o memoria de la GPU), no a una versión de
  biblioteca. No se ha comprobado. `.venv-seg` se queda como estaba, con el arreglo de `segment.py`.

  **Corrección**: una versión anterior de este párrafo decía «8 veces más rápido»; comparaba una
  tarea en GPU (30 s) con el preset entero en CPU (238 s). Comparando lo mismo, la GPU sin cuDNN
  gana ~16 % cuando funciona, y aun sin cuDNN falla a veces («illegal memory access»), así que la
  causa no es solo cuDNN: probablemente la combinación de torch 2.11 + cu128 + este controlador. No
  se ha probado otra versión de torch.

  **Arreglo final (2026-11-11, decisiones de Ellande)**: la causa era el overclock de MSI Center
  (ver el párrafo de serie más abajo y `docs/apagado-progresivo/README.md`). Quitado el overclock,
  `volumes/segment.py` vuelve a lanzar el ejecutable con cuDNN (8 de 8 bien, 144-177 s el preset) y
  conserva solo el paso a CPU si una tarea falla en GPU. El lanzador sin cuDNN que hubo unas horas
  (`totalseg_launch.py`) se retiró; queda en `docs/apagado-progresivo/scripts/` para repetir la prueba.
- Whisper se queda en clase 3 en uso y 0 en standby, como estaba. El OCR baja de 3 a 2.

**S5, S8, S12 y visor de Polaris en la interfaz** (mismo montaje que S2; micrófono y cámara falsos
de Chrome, `--use-fake-device-for-media-stream`: el micrófono da un pitido y la cámara no enseña
ninguna cara; % de un núcleo):

| Situación | Chrome | Tareas de la página | Nota |
|---|---|---|---|
| Inicio, base | 0,5 % | 0,1 % | |
| **Escuchar «EMMA» (Vosk) encendido** | **12,8 %** | 0,3 % | Continuo mientras esté encendido: standby = uso. El trabajo va en un *worker*, por eso no sale en las tareas de la página |
| Seguir la cara (cámara + MediaPipe), sin cara delante | 6,8 % | 4,4 % | Con una cara delante probablemente más; sin medir |
| Ecografía abierta, quieta | 0,9 % | 0,1 % | |
| Ecografía en cine (10 fotogramas/s) | 5,6 % | 2,1 % | Solo mientras se reproduce |
| Visor 3D de Polaris abierto, quieto | 0,1 % | 0 % | Girándolo: medida no válida (el arrastre no cayó en el lienzo) |

- **La palabra de activación es la función de la interfaz que más gasta de forma continua**: ~13 %
  de un núcleo, más que el refresco del backend, por estar encendida aunque nadie hable. Sube de la
  clase 2 a la 3 en standby. El botón del asistente hace lo mismo sin escuchar todo el rato.
- El arranque de Vosk (descomprimir ~40 MB de modelo la primera vez) no se midió aparte.
- El `<iframe>` del visor de Polaris midió 277 516 px de alto en esta tanda; en la segunda, 1 185 px.
  Era cosa del montaje de la medida.

**Des-identificación de informes**: `.venv-deid` existe pero sin la marca de pesos (`ner_ready()`
falso), así que solo corren las reglas: un informe de ~5 000 caracteres, en milisegundos. El NER no
está medido.

**Segunda tanda (2026-11-11)**:
- **Arranque de Vosk con perfil limpio**: ~66 s desde encender «Escuchar "EMMA"» hasta que la
  consola dice «Di "EMMA"», dos veces. En ese tiempo la CPU de Chrome casi no se mueve (0,4 s), así
  que la espera no parece cálculo; queda sin explicar. Con el modelo ya en IndexedDB, menos de 20 s.
- **Visor de Polaris girando: sin medida válida.** El `<iframe>` midió ahora 1 185 px de alto (lo
  de 277 516 px fue cosa del montaje anterior) y tiene dos lienzos (828×640 y 414×640), pero el
  arrastre sintético no movió ninguno: la CPU no subió en ninguno de los dos. Tres intentos; se deja.

**No medible aquí**: la pantalla y la GPU integrada, el NER de des-identificación (sin pesos
instalados) y el seguimiento de cara con una cara real.

## G. Lo leído de los instrumentos (2026-11-11)

Las frases copiadas de cada fuente, con su enlace y su página, están en
`docs/apagado-progresivo/README.md` §2. Fuentes leídas el 2026-11-11. Fuente principal: *ISS CHeCS Medical Hardware Catalog* v10.0
(NASA, 2011; ntrs 20110022379), que se declara a sí mismo «not an official NASA document». Lo
marcado **sin verificar** solo se vio en un extracto del buscador, no en la página. Si una cifra
pasa al código, antes necesita su ficha en `data/evidence_refs.json`.

| Familia | Lo leído | Fuente | Qué dice para el apagado |
|---|---|---|---|
| A1 wearable (proxy: banda Polar H10) | «Battery type: CR 2025», «Battery lifetime: 400 h»; 165 mAh | Manual de Polar H10, especificaciones técnicas; página de producto | Del orden de mW: confirma la clase 1 |
| A1 en la ISS (HRM2 de Polar, CHeCS §2.4) | «Average battery life for both the HRM Watch and HRM Transmitter is one year.» (pilas CR2430/CR2025) | Catálogo CHeCS, pp. 62-64 | No pide energía de la nave |
| A1/A4 camiseta Bio-Monitor (Astroskin) | «2x AA batteries – Autonomy: 48 h»; con envío en directo por Bluetooth, «less than 24-hour recordings» | Folleto de Astroskin (Hexoskin); NASA HERA, Toscano 2017 (ntrs 20190001996), diap. 14-15 | **Transmitir en directo reduce la autonomía a la mitad**: en niveles bajos, grabar a bordo y descargar después |
| A6 tensiómetro (CHeCS BP/ECG: Schiller AT-10 + SunTech Tango) | ECG «120VDC at 1 Amp or 28VDC at 3 Amps»; el tensiómetro, «10 VDC… Receives power from the ECG unit» | Catálogo CHeCS §2.2, pp. 44-46 | Energía de la nave, sin batería. Son valores nominales de alimentación, no consumo medido. El tensiómetro va colgado del ECG: se encienden juntos |
| A8 ecógrafo (Ultrasound-2 = GE Vivid q) | Comercial: «Input rating: 100-240 VAC/2.3 -1.1A»; «scanning with rechargeable battery power for more than one hour»; «Standby mode with battery allows fast boot-up»; cerrar la pantalla lo pone en standby | Ficha comercial de GE Vivid q (2008) | Tiene standby propio con arranque rápido; sin vatios de standby. En la ISS se enchufa al rack HRF-1 («up to 500W» por carga útil: es el límite, no el consumo). **Sin verificar**: «max. 130 VA» (Vivid iq) |
| A8 alternativa de mano (Butterfly iQ) | «P <15W (charging)» | NASA, Sargsyan, IWS 2021 (ntrs 20210000940), diap. 4 | Un ecógrafo de mano cargaría por debajo de 15 W |
| A9 VO₂ (PFS / PPFS) | Solo: el PPFS se usa «in any location that has power and data connections» | NASA/TM-2018-220243 | Energía de la nave; sin vatios |
| A11 dosímetros | Pasivos (RAM/CPD): «No operating power… required»; IV-CPDS: «Power Draw 12 W»; TEPC: 7,5 W (tabla mal extraída, lectura probable); EV-CPDS: ~32 W máx. por unidad | Catálogo CHeCS §3.3, pp. 204-219 | Los paga la nave y son seguridad: siguen fuera del apagado de EMMA |
| A14 analizador (Abbott i-STAT 1, el de la ISS **sin verificar**) | «Two 9-volt lithium batteries, or rechargeable battery»; ≥400 cartuchos termocontrolados por juego de pilas; «Cartridges that require thermal control consume more energy because of heating» | Manual del sistema i-STAT 1, sección 3 (Abbott, 2024) | A pilas y de mano: su coste es de pilas y cartuchos, no de la red de la nave. **Esto contradice mi clase 3 de la tabla A**, que suponía un analizador de sobremesa |
| A7 SLAMMD | No encontrado | — | Solo el límite del rack HRF |

**Corrige la tabla A**:
- **A14**: si el analizador es un i-STAT, el «calentamiento caro» que supuse no existe. Su coste es
  de pilas por cartucho y ya lo cubre el criterio de consumibles de los niveles actuales.
- **A1/A4**: transmitir en directo es lo que gasta. Un nivel bajo puede pasar del directo a
  «grabar y descargar» sin perder datos, solo retraso.
- **A6**: el tensiómetro depende del ECG. Apagar uno es apagar los dos.
- **No se encontró ninguna cifra de standby ni de arranque** de ningún instrumento, salvo que el
  Vivid q tiene un standby con arranque rápido.

## E. Huecos antes de convertir esto en código

- **Medir el software en este equipo**: CPU/GPU y potencia del backend en reposo, con el modelo de
  lenguaje cargado y sin él, con el 3D abierto y cerrado, con Vosk escuchando. Se puede hacer aquí
  con contadores del sistema (no da vatios exactos, sí el orden).
- **Leer las fichas de los instrumentos** (potencia en uso y en reposo, tiempo de calentamiento)
  para A6, A7, A8, A9, A14. Sin fuente, la columna se queda «sin fuente», como en
  `measurement_cost.json`.
- **Decidir si A1-A4 son un dispositivo o varios**: cambia cuántos indicadores caen al apagar una
  radio.
- **El «mínimo» y la pantalla**: hoy espera síntomas y dolor, que solo se declaran en la consola.
- Si sale un eje de energía en `mission_modes.json`, tendrá que clasificarse igual que el resto
  (fuente o «sin fuente») y actualizar `docs/contexto/README.md` en el mismo cambio.
