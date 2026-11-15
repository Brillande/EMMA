# Registro de mediciones y fuentes del apagado progresivo

_2026-11-11. Para comprobar cada cifra de consumo de `docs/apagado-progresivo-inventario.md`:
de dónde sale, con qué se midió y cómo repetirla._

Hay dos clases de cifra y ninguna tercera:

1. **Medidas en este equipo** (software de EMMA): con los scripts de `scripts/`, todas las muestras
   en `datos/`. Se rehacen con los comandos de abajo.
2. **Leídas en una fuente** (instrumentos): cada una con su enlace, su página o sección y la frase
   copiada tal cual.

Las clases 0-4 de las tablas A y B del inventario no son ninguna de las dos: son un orden relativo,
sin medir ni fuente, y así lo dice el inventario.

---

## 1. Medidas en este equipo

### El equipo y su estado

| | |
|---|---|
| Equipo | Portátil de desarrollo, enchufado. **No es hardware de vuelo**: sirve para comparar funciones entre sí, no como consumo de la nave |
| GPU | NVIDIA GeForce RTX 4070 Laptop GPU, 8 GB, controlador 617.42 (`nvidia-smi --query-gpu=name,driver_version`) |
| CPU | 32 hilos (`os.cpu_count()`) |
| Límite de potencia de la GPU | **140 W**; el valor por defecto que declara la tarjeta es 55 W (`nvidia-smi -q -d POWER`) |
| Estado | Dos tandas. **Con *overclock*** (T18xx, T19xx): MSI Center aplicaba +200 MHz al núcleo y +200 MHz a la memoria en P0 (leído con `scripts/nvapi_desplazamientos.py`; en carga, núcleo 2 760 MHz y memoria 8 201 MHz, sobre un máximo nominal de 8 001). **De serie** (T2124-T2216): desplazamientos puestos a 0 con `nvapi_desplazamientos.py --poner-a-cero` (como administrador); en carga, núcleo 2 565 MHz y memoria 8 001 MHz. Cada JSON de `medir.py` de serie guarda los desplazamientos leídos (`desplazamientos_reloj_gpu`); el de la interfaz no, pero se leyeron a 0 justo antes y justo después de la tanda |

### Instrumentos de medida

| Magnitud | Herramienta | Qué es exactamente | Qué no es |
|---|---|---|---|
| Potencia de la GPU (W) | `nvidia-smi --query-gpu=power.draw` cada 0,5 s | La potencia de la placa que informa el controlador de NVIDIA | No es un vatímetro externo; no incluye la GPU integrada ni la pantalla |
| Uso de GPU (%) y VRAM (MB) | `nvidia-smi --query-gpu=utilization.gpu,memory.used` | Lectura del controlador | |
| CPU del sistema (%) | `GetSystemTimes` (kernel32 de Windows), diferencia entre muestras | Fracción de tiempo no ociosa de los 32 hilos. 1 % ≈ 0,32 núcleos | **No da vatios**: Windows no expone la potencia de la CPU sin herramientas aparte |
| CPU en vatios | Contadores RAPL del «Energy Meter» de Windows con PDH (`scripts/cpu_rapl.py`), sin administrador: paquete (PKG) y núcleos (PP0) | Lo que estima el propio procesador | En este portátil, la gráfica integrada (PP1) y la memoria (DRAM) dan 0 |
| Portátil entero, pantalla incluida (W) | Descarga de la batería, `root\wmi` `BatteryStatus.DischargeRate` (`scripts/bateria.ps1`), cruzada por fase con `scripts/cruzar_bateria.py` | Todo el equipo | **Solo desenchufado**, y con batería el portátil limita la GPU (ver abajo). El firmware la actualiza cada pocos segundos |
| CPU de un proceso (s) | `GetProcessTimes` del proceso y sus hijos | Segundos de CPU consumidos en la fase | Puede incluir hilos que se quedan girando tras el trabajo (ONNX) |
| CPU de Chrome (% de un núcleo) | `Win32_Process.KernelModeTime + UserModeTime` de todos los procesos de ese perfil | Incluye *workers* (Vosk, MediaPipe) | |
| Tareas de la página (%) | `Performance.getMetrics` → `TaskDuration` (protocolo de depuración de Chrome) | Tiempo del hilo principal | No incluye *workers* |

### Cómo se repite

Desde la raíz del repositorio (Windows, GPU NVIDIA, los entornos opcionales instalados):

```bash
powershell -File docs/apagado-progresivo/scripts/generar-dictado.ps1        # audio sintético de 8 s
backend/.venv/Scripts/python.exe docs/apagado-progresivo/scripts/medir.py llm
backend/.venv/Scripts/python.exe docs/apagado-progresivo/scripts/medir.py backend
backend/.venv/Scripts/python.exe docs/apagado-progresivo/scripts/medir.py herramientas
backend/.venv/Scripts/python.exe docs/apagado-progresivo/scripts/medir.py segmentacion
cd frontend && npx vite build --outDir ../docs/apagado-progresivo/datos/dist --emptyOutDir && cd ..
node docs/apagado-progresivo/scripts/medir-ui.mjs
```

Cada plan escribe `datos/<plan>-<fecha>.csv` (una fila por muestra de 0,5 s, con la fase en la que
cayó) y `datos/<plan>-<fecha>.json` (el equipo y la media por fase). La interfaz escribe
`datos/ui-<fecha>.json` y `datos/ui-<fecha>-gpu.csv`. Las medias de abajo se recalculan de los CSV. Solo el visor de Polaris:
`SOLO=polaris node docs/apagado-progresivo/scripts/medir-ui.mjs` (gira el render 3D con eventos de
ratón en su propio documento, porque el arrastre del protocolo de depuración no entra en su `<iframe>`).

### De serie frente a *overclock* (2026-11-11)

**Fiabilidad de la segmentación en GPU** (preset de hígado, 4 tareas; GPU libre 30 s antes de cada
ronda; `scripts/fiabilidad_segmentacion.py`; salidas en `datos/fiabilidad-*.txt`):

| | *Overclock*, torch 2.11 | *Overclock*, torch 2.7.1 | **De serie, torch 2.11** |
|---|---|---|---|
| Con cuDNN (ejecutable tal cual) | 1 de 2 (solo `total`) | 1 de 8 | **8 de 8** |
| Sin cuDNN (`scripts/totalseg_sin_cudnn.py`) | 7 de 8 | 8 de 8 | 8 de 8 |
| Preset completo con cuDNN, de serie | — | — | 144-177 s |
| Preset completo sin cuDNN, de serie | — | — | 182-190 s |

**Los fallos CUDA de la segmentación los causaba el *overclock* de MSI Center**: de serie, cuDNN no
falla ni una vez, y con *overclock* falla con dos versiones distintas de torch y de cuDNN.

**Energía, de serie frente a *overclock*** (mismos scripts; ficheros `T2205-T2216` y `ui-…T2124`
frente a `T1850-T1900` y `ui-…T1817`):

| Fase | *Overclock* | De serie |
|---|---|---|
| LLM: generar 300 tokens | 72,7 W media, 90,3 W máx., 525 J | 72,6 W media, 86,9 W máx., 534 J |
| LLM: cargado, sin trabajo | 5,0 W | 5,1 W |
| Segmentación del hígado vía `segment.run` (sin cuDNN), GPU | 213 s, 12,3 W, 2 619 J | 188 s, 19,5 W, 3 672 J |
| Segmentación del hígado, CPU | 198 s, 20 % de CPU | 192 s, 19 % de CPU |
| Whisper, dictado de 8 s | 4,0-4,2 s | 4,0-6,5 s |
| Interfaz: escuchar «EMMA» / seguir la cara / cuerpo 3D girando / cine | 10,7 / 8,1 / 8,2 / 5,4 % de un núcleo | 10,7 / 10,8 / 9,7 / 6,4 % |
| Visor 3D de Polaris quieto / girando (de serie, `ui-polaris-…T2146`) | — | 0,6 / **8,1 %** de un núcleo; GPU dedicada 2 → **26 %** de uso, 3,4 → 4,2 W |

En energía, el *overclock* apenas cambia las cifras: el modelo de lenguaje gasta lo mismo en media.
En la segmentación por GPU, la tanda con *overclock* gastó menos julios de GPU porque parte de sus
tareas fallaron y acabaron en CPU (más lento, menos GPU); de serie todas van por GPU.

### Enchufado, con la CPU en vatios (de serie, 2026-11-12)

Tanda `T0156-T0207` (+ `ui-…T0055`), enchufado. CPU del paquete con RAPL y GPU con nvidia-smi; **el
portátil entero no se puede medir enchufado** (ningún sensor mide lo que entra por el cargador: haría
falta un vatímetro de enchufe). Enchufado, el reposo es más alto y más inestable que con batería:
CPU 17-37 W y GPU 10-12 W con nada de EMMA en marcha (otras aplicaciones del equipo y el modo de
energía del cargador).

| Fase | Duración | CPU paquete | GPU dedicada | Energía CPU + GPU |
|---|---|---|---|---|
| Reposo (varía) | — | 17-37 W | 10-12 W | — |
| LLM: cargar el modelo | 7,8 s | 54 W | 19 W | 0,57 kJ |
| LLM: generar 300 tokens | 12,5 s | 43 W | **63 W** | 1,32 kJ |
| Backend: arrancar | 1,1 s | 52 W | 11 W | 0,07 kJ |
| Backend: `/api/status` ×5 | 7,1 s | 51 W | 12 W | 0,44 kJ |
| Búsqueda semántica, reindexando | 70 s | **86 W** | 11 W | 6,7 kJ |
| OCR de una página | 1,2 s | 48-58 W | 12 W | ~0,08 kJ |
| Whisper, dictado de 8 s | 4-6 s | 50-52 W | 11-12 W | 0,26-0,37 kJ |
| Segmentación del hígado en GPU | 168 s | 48 W | 18 W | **11,2 kJ** |
| Segmentación del hígado en CPU | 227 s | 70 W | 12 W | **18,6 kJ** |

Enchufado, segmentar en GPU gasta ~40 % menos energía de CPU + GPU que en CPU (con batería, 30 %
menos del equipo entero). **La interfaz enchufada (`ui-…T0055`) no sirve para separar sus funciones**:
suman 1-3 W de CPU y el reposo oscilaba ±5 W; sus cifras quedan en el fichero, sin atribuir. La
medida limpia de la interfaz es con batería.

### Con batería: el portátil entero y la CPU en vatios (de serie, 2026-11-11/12)

Tanda `T2333-T2346` (+ `ui-…T2334`), con el portátil desenchufado; cada plan tiene su
`*-bateria.json` (media de la descarga por fase) y el CSV `bateria-2026-11-11T2331.csv` /
`bateria-ui-2026-11-12T0026.csv`. **Con batería el portátil limita la GPU**: generar 300 tokens tardó
14 s (7 s enchufado) con la GPU a 27 W (73 W enchufado); y la CPU va más lenta (segmentación en CPU,
306 s frente a 192).

| Fase | Portátil entero | CPU paquete (RAPL) | GPU dedicada |
|---|---|---|---|
| Reposo (pantalla encendida) | **41-55 W** | 6-9 W | 5-6 W |
| LLM: cargar el modelo | 70 W | 21 W | 13 W |
| LLM: cargado, sin trabajo | 57 W | 11 W | 8 W |
| LLM: generar 300 tokens (14 s) | **86 W** | 16 W | 27 W |
| Backend: `/api/status` ×5 | 71 W | 22 W | 7 W |
| Búsqueda semántica, reindexando (116 s) | 68 W | 22 W | 7 W |
| OCR de una página | 36-62 W | 20-22 W | 5 W |
| Whisper, dictado de 8 s | 63-65 W | 18-21 W | 5 W |
| Segmentación del hígado en GPU (194 s) | 74 W → **14,3 kJ** | 21 W | 11 W |
| Segmentación del hígado en CPU (306 s) | 67 W → **20,5 kJ** | 21 W | 7 W |
| Interfaz: Chrome en blanco / Inicio | 47 / 48 W | 8,8 / 9,7 W | 5,0 / 5,4 W |
| Interfaz: escuchar «EMMA» | **53 W** (+5 W) | 11,0 W | 5,8 W |

**Segmentar en GPU gasta un 30 % menos de energía que en CPU**, aunque tire de más vatios, porque
acaba antes. Las fases de la interfaz después de «escuchar "EMMA"» se hicieron ya enchufado (sin
dato del equipo entero) y con la CPU de fondo subiendo (33 W con la ventana minimizada y Chrome
quieto): sus vatios de CPU no se atribuyen a la interfaz.

**La pantalla** (`brillo-…T0226` y su `-bateria.json`, desenchufado; `medir.py brillo`): el brillo se
puso con `WmiSetBrightness` y se leyó de Windows en cada fase (100 %, 0 %, 100 %; al final, el de
antes). Portátil entero: 46,4 W y 42,4 W al 100 %, **35,4 W al 0 %** → **la retroiluminación gasta
~7-11 W al 100 %**, la cuarta parte del reposo. Un intento anterior de apagar la pantalla con
`SC_MONITORPOWER` (`pantalla-…T0213`) dio solo 1-2 W de diferencia: casi seguro no llegó a apagarla
(no se puede leer si lo hizo), y no se usa.

**La interfaz con batería, completa** (`ui-…T0122` y su `-bateria.json`): el portátil entero oscila
±5 W por sí solo (41-57 W entre fases sin relación con lo que hacían), y las funciones de la interfaz
suman 1-3 W: **quedan por debajo del ruido**, con batería igual que enchufado. Lo que sí las separa es
el % de un núcleo de Chrome (escuchar «EMMA» 15 %, seguir la cara 12 %, cuerpo 3D girando 10 %, cine
10 %, frente a 0,2-3,5 % quietas). Es un resultado: en este equipo, su coste es menor que lo que
cambia el reposo por sí solo.

**Seguir la cara con una persona delante** (cámara real, `ui-cara-…T2230`, desenchufado): Chrome
17,7 % de un núcleo (2,4 % sin el modo), CPU de 8,8 a 11,8 W (+3 W), GPU de 5,6 a 7,6 W (+2 W).

### Resultados de la tanda con *overclock* del 2026-11-11 (T1850-T1900, `ui-…T1817`)

**Modelo de lenguaje** (`qwen3.5:9b` en Ollama) — `datos/llm-2026-11-11T1850.*`

| Fase | Duración | GPU media | GPU máx. | VRAM | Energía GPU |
|---|---|---|---|---|---|
| Reposo, sin modelo | 20 s | 3,2 W | 3,5 W | 1,5 GB | 64 J |
| Cargar el modelo | 6,8 s | 9,9 W | 16,1 W | → 4,3 GB | 67 J |
| Modelo cargado, sin trabajo | 20 s | 5,0 W | 13,6 W | 7,5 GB | 100 J |
| Generar 300 tokens | 7,2 s | **72,7 W** | 90,3 W | 7,5 GB | **525 J** (≈1,75 J/token) |

**Backend** (`EMMA_OFFLINE=true`, sin calentamiento del asistente) — `datos/backend-2026-11-11T1852.*`

| Fase | Duración | CPU del proceso |
|---|---|---|
| Arrancar hasta responder | 1,6 s | 0,7 s |
| Reposo sin datos / con datos | 20 s / 20 s | 0,0 s / 0,0 s |
| Simular la misión | 3,8 s | 3,7 s |
| `/api/status` ×5 | 6,7 s (4,1 + 4 × ~0,66) | 6,6 s |
| Búsqueda semántica, primera tras cambiar la documentación (reindexa) | **64 s** | **1 498 s** (CPU del sistema 78 %) |
| Búsqueda semántica, siguiente | 0,13 s | 11,4 s |

La primera búsqueda reconstruye el índice cada vez que cambia la documentación indexada (como pasó
aquí, al escribir este registro). Es una ráfaga de un minuto con casi toda la CPU.

**OCR y Whisper** — `datos/herramientas-2026-11-11T1853.*`

| Fase | Duración | CPU del sistema | GPU |
|---|---|---|---|
| Reposo | 15 s | 1,2 % | 4,6 W |
| OCR de una página A4 (tesseract) | 1,1–1,4 s | 4–6 % | sin cambio |
| Whisper `base`, dictado de 8 s | 4,0–4,2 s | 19–24 % (≈6-8 núcleos) | sin cambio |

El texto que devolvió Whisper con este dictado salió peor que en la primera prueba (el audio se
regeneró); no afecta al coste.

**Segmentación** (preset de hígado, 4 tareas, 15 máscaras; con el arreglo de `segment.py`) —
`datos/segmentacion-2026-11-11T1900.*`

| Fase | Duración | GPU media / máx. | VRAM | CPU del sistema | Energía GPU |
|---|---|---|---|---|---|
| GPU (sin cuDNN, paso a CPU si falla) | 213 s | 12,3 W / 38,8 W | 2,6 GB | 11 % | 2 619 J |
| CPU | 198 s | 4,5 W | — | 20 % (≈6 núcleos) | 898 J (reposo de la GPU) |

En esta tanda la GPU no ganó a la CPU. El registro no dice cuántas tareas pasaron a CPU por fallo;
las pruebas de fiabilidad con la GPU libre están en el inventario, §F.

**Interfaz** (Chrome aparte, perfil limpio, ventana 1672×941, sin ralentizar ventanas tapadas;
micrófono y cámara falsos de Chrome; 30 s por fase) — `datos/ui-2026-11-11T1817.*`

| Situación | Chrome (% de un núcleo) | Tareas de la página | Backend | GPU dedicada |
|---|---|---|---|---|
| Chrome en blanco | 1,4 | 0 | 0,1 | 3,5 W |
| Inicio, quieta | 0,8 | 0,1 | 4,2 | 4,1 W |
| **Escuchar «EMMA» encendido** (estado: «Di "EMMA"…») | **10,7** | 0,3 | 4,5 | 4,0 W |
| Seguir la cara, sin cara delante | 8,1 | 3,7 | 4,7 | 3,7 W |
| Dolor: cuerpo 3D quieto | 1,3 | 0,2 | 4,2 | 3,3 W |
| Dolor: cuerpo 3D girando (arrastre sintético a 30 Hz) | 8,2 | 1,4 | 4,2 | 3,6 W |
| Ecografía quieta | 0,5 | 0,1 | 4,3 | 3,1 W |
| Ecografía en cine (10 fps) | 5,4 | 2,0 | 4,4 | 3,6 W |
| Inicio, ventana minimizada | 0,6 | 0,2 | 4,3 | 3,4 W |

Primer arranque de Vosk con perfil limpio: **131 s** hasta que dice «Di "EMMA"», con 16 s de CPU de
Chrome (en una tanda anterior, 66 s). No se ha averiguado en qué se va el tiempo.

**Hallazgo de método**: la primera vez de esta tanda la ventana de Chrome quedó tapada por otras y
todos los modos de la interfaz salieron casi a cero (escuchar «EMMA» 0 %, cara 0,4 %, cine 0,1 %).
Chrome deja de dibujar las ventanas tapadas. Esa tanda se descartó y se repitió con
`--disable-backgrounding-occluded-windows`; para el apagado, quiere decir que **ocultar la consola
ya ahorra lo que cuesta dibujarla** (el refresco del backend, en cambio, sigue).

### Lo que no se ha medido, y qué hace falta para medirlo

| Falta | Por qué | Qué hace falta |
|---|---|---|
| Des-identificación con NER | El modelo `BSC-NLP4BIA/bsc-bio-ehr-es-contacto-anon` es de acceso restringido en Hugging Face | Una cuenta que acepte sus condiciones y un `HF_TOKEN`; después, `backend/scripts/install_deid_ner.py` |
| El portátil entero enchufado | Ningún sensor mide la entrada del cargador | Un vatímetro de enchufe |
| Instrumentos sin cifra (SLAMMD, VO₂, ecógrafos de vuelo, esperas y arranques) | Ninguna fuente leída la da | Fichas técnicas de vuelo o una medida real |
| Todo en hardware de vuelo | Esto es un portátil | — |

---

## 2. Leídas en fuentes (instrumentos)

Leídas el 2026-11-11. Fuente principal: **ISS CHeCS Medical Hardware Catalog**, versión 10.0,
marzo de 2011, NASA, NTRS 20110022379 —
<https://ntrs.nasa.gov/api/citations/20110022379/downloads/20110022379.pdf>. Su prefacio dice: «This
reference is not an official NASA document.»

| Instrumento | Frase copiada | Fuente y lugar |
|---|---|---|
| Tensiómetro + ECG (CHeCS) | «The ECG unit was modified for the capability to run at either 120VDC at 1 Amp or 28VDC at 3 Amps. In addition, the ECG unit and the Blood Pressure device were both modified, allowing the ECG unit to power the Blood Pressure device.» | Catálogo CHeCS §2.2.1, p. 44 |
| Tensiómetro | «Power Requirements 10 VDC… Receives power from the ECG unit» | Catálogo CHeCS, tabla 2.2.2.2-1, p. 46 |
| Pulsómetro de la ISS (HRM2, Polar) | «Average battery life for both the HRM Watch and HRM Transmitter is one year.» | Catálogo CHeCS §2.4, pp. 62-64 |
| Dosímetros pasivos (RAM/CPD) | «No operating power, electrical, acoustic, heat or ignition sources are required.» | Catálogo CHeCS §3.3.2.2.1, p. 208 |
| IV-CPDS | «Power Draw 12 W / Power Source CHeCS PCR» | Catálogo CHeCS, tabla 3.3.4.1.2-2, p. 219 |
| TEPC | «7.5 W» junto a «Power Draw» (la tabla salió descolocada al extraer el PDF: lectura probable) | Catálogo CHeCS, tabla 3.3.3.2-2, p. 214 |
| EV-CPDS (exterior) | «Max Power Draw ~32 [por unidad] ~96 [3 unidades]» | Catálogo CHeCS, tabla 3.3.1.2-2, p. 204 |
| Ecógrafo GE Vivid q (comercial; en la ISS, «Ultrasound 2») | «Input rating: 100-240 VAC/2.3 -1.1A»; «scanning with rechargeable battery power for more than one hour. Standby mode with battery allows fast boot-up anywhere.» | Ficha de GE Vivid q (2008), «Electrical Power» — <https://www.davismedical.com/content/pdf/vivid-q-datasheet.pdf> |
| Rack HRF de la ISS (límite, no consumo) | «Each payload can use up to 500W of power and the sum of all payloads can use up to 2000 W» | NASA, *ISSMP On-Orbit Hardware* (2016), diap. 7 — <https://www.nasa.gov/sites/default/files/atoms/files/issmp_on-orbit_hardware.pdf> |
| Ecógrafo de mano Butterfly iQ | «P <15W (charging)» | NASA, Sargsyan, IWS 2021, diap. 4 — <https://ntrs.nasa.gov/api/citations/20210000940/downloads/Butterfly_iQ_IWS2021_SargsyanA.pdf> |
| PPFS (VO₂) | «The PPFS is a smaller version of the PFS that can be used on board the ISS in any location that has power and data connections.» | NASA/TM-2018-220243, Introducción — <https://ntrs.nasa.gov/api/citations/20180005625/downloads/20180005625.pdf> |
| Analizador i-STAT 1 | «POWER: Two 9-volt lithium batteries, or rechargeable battery.»; «Cartridges that require thermal control consume more energy because of heating.» | Abbott, *i-STAT 1 System Manual*, sección 3, pp. 3-2/3-3 — <https://www.globalpointofcare.abbott/content/dam/ardx/globalpointofcare/apoc/support/hs-tni-resource-center/product-information/i-STAT_1_System_Manual_US_English_014331-00_66_A.pdf> |
| Camiseta Astroskin (Bio-Monitor) | «Battery – 2x AA batteries – Autonomy: 48 h» | Folleto de Astroskin, especificaciones — <https://cdn.shopify.com/s/files/1/0284/7802/files/Astroskin.pdf> |
| Astroskin con envío en directo | «real-time data streaming via Bluetooth… significantly reduces battery life resulting in less than 24-hour recordings» | NASA HERA, Toscano 2017, diap. 14-15 — <https://ntrs.nasa.gov/api/citations/20190001996/downloads/20190001996.pdf> |
| Banda Polar H10 (referencia comercial) | «Battery type: CR 2025», «Battery lifetime: 400 h» | Manual de Polar H10, especificaciones técnicas — <https://support.polar.com/e_manuals/h10-heart-rate-sensor/polar-h10-user-manual-english/technical-specifications.htm> |

**Sin verificar** (solo visto en extractos del buscador, no en la página): que la ISS use el i-STAT;
«max. 130 VA» del Vivid iq; ~3 W de los DOSTEL de DOSIS 3D.

**No encontrado**: vatios de SLAMMD, del PFS/PPFS, de ISS-RAD y de los ecógrafos de vuelo; ninguna
cifra de espera ni de arranque de ningún instrumento, salvo el modo de espera del Vivid q.
