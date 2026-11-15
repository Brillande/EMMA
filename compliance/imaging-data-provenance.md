# Procedencia de los datos ecográficos

Qué imágenes usa EMMA para desarrollar y validar la ecografía a bordo, de dónde salen, bajo qué
licencia y **qué pueden demostrar y qué no**. Se actualiza en el mismo cambio que añada, quite o
cambie el uso de un dataset.

Búsqueda reproducible: `backend/spikes/spike_ultrasound_data.py`. Resultados:
`backend/spikes/HALLAZGOS.md` §5.

---

## 1. Reglas

1. **La licencia se lee en el registro de origen**, no en un artículo que lo cite ni en un
   agregador. Si el origen no declara la licencia de los datos, el dataset no se usa.
2. **Se admite una licencia de datos sin restricción de uso** (CC0, CC BY 4.0). Se excluyen las
   cláusulas no comerciales (NC), sin derivadas (ND) o de "solo investigación". Base: los términos
   de Space Apps 2026 exigen que el material de terceros sea libre y público sin restricción o,
   como mínimo, tenga licencia OSI; y además obligan a citar toda fuente usada.
   CC BY no es una licencia OSI (la OSI no revisa licencias de contenido), pero es libre y pública,
   y solo exige atribución, que las reglas del concurso piden de todos modos.
3. **Los datos no se versionan en el repositorio.** Un script los descarga del origen y verifica
   su huella; las pruebas `-m external` se saltan si no están. **Única excepción: los ejemplos de
   demostración** (§2.1), una selección fija de pocas imágenes que la licencia permite
   redistribuir. Viajan en el paquete para que la demo funcione sin red, con un manifiesto que da
   el origen, la licencia y la huella SHA-256 de cada una; una imagen cambiada no se carga.
4. **Cada dataset declara qué valida.** Ningún dataset de este documento son datos de
   tripulación. Presentarlos como validación de fisiología espacial sería falso; es la misma regla
   que MMASH (`external-validation.md`).

---

## 2. Datasets en uso

| Dataset | Origen y licencia | Qué valida | Qué NO valida |
|---|---|---|---|
| **HC18**: ecografía fetal en modo B con perímetro cefálico de referencia | Zenodo, doi:10.5281/zenodo.1327317, **CC BY 4.0**. Trae el tamaño de píxel en mm de cada imagen (`training_set_pixel_size_and_HC.csv`) | Que el motor convierte calibres en píxeles a milímetros sin error de escala: el perímetro reconstruido con su distancia calibrada casa con la referencia en 999 imágenes, y un control con la escala desviada un 1 % lo detecta | La precisión de un operador (los puntos salen de la anotación experta), ninguna anatomía de interés para vuelo, ningún umbral clínico |
| **Hígado graso en modo B** (Byra et al., 2018) | Zenodo, doi:10.5281/zenodo.1009146, **CC BY 4.0** | Demo del protocolo hepático: visor, checklist, hallazgos anotados | Medidas en mm: el registro no declara calibración |
| **Ecografía pulmonar** (Katumba et al., 2025) | Mendeley Data, doi:10.17632/hb3p34ytvx.2, **CC BY 4.0** (licencia leída en el registro de datos, no en el artículo) | Demo del protocolo pulmonar: visor, signos por vista, hallazgos anotados | Medidas en mm (sin calibración); ninguna precisión diagnóstica: EMMA no clasifica imágenes |

### 2.0 TAC del visor 3D (2026-09-26)

| Dataset | Origen y licencia | Qué valida | Qué NO valida |
|---|---|---|---|
| **TotalSegmentator dataset v2.0.1** (Wasserthal et al., Radiol Artif Intell 2023) | Zenodo, doi:10.5281/zenodo.10047292, **CC BY 4.0** (leída en el registro). 1228 TAC con 117 estructuras segmentadas por expertos | Demo del visor 3D con TAC reales, y (`-m external`) cuánto coincide la segmentación local con la de referencia | Nada de vuelo: son pacientes hospitalarios; hoy no vuela ningún TAC (en la ISS solo hay ecografía) |

Se bajan sujetos sueltos por rangos HTTP (`backend/scripts/fetch_ct_samples.py`), sin los 23,6 GB
del zip. Los ejemplos que viajan en el paquete (`app/data/volume_samples/`) llevan el TAC recortado
a la región a 2 mm y su segmentación precalculada por TotalSegmentator, con huella SHA-256 por
fichero; entran firmados como simulados (`simulator:dataset`). Cita obligatoria: Wasserthal J. et
al. *TotalSegmentator: Robust Segmentation of 104 Anatomic Structures in CT Images.* Radiol Artif
Intell 2023;5(5):e230024. Datos: doi:10.5281/zenodo.10047292.

Los ejemplos son cuatro: dos de hígado (s0816, s0048), uno de órbitas (s0289) y, desde el
2026-10-06, uno de esqueleto (`esqueleto-4`, s1152: politrauma, reparto `test`). Es el único TAC
de los bajados que va de cuello a cadera (42 × 30 × 67 cm tras el recorte); con los otros, el
preset de esqueleto saca trozos de costilla o nada. Su segmentación se hizo en local con
TotalSegmentator, pico de 13,7 GB, y trae los 60 huesos del preset. Al añadirlo, las tres muestras
anteriores se dejaron byte a byte como estaban: regeneradas hoy salen con los mismos vóxeles pero
otra cabecera NIfTI, y cambiar su huella no aportaba nada.

**Volúmenes que sube el operador (2026-10-07).** Un NIfTI subido por `POST /api/volumes` no entra
si su cabecera lleva texto libre, extensiones o la identidad declarada del tripulante, ni si su
envoltorio gzip guarda el nombre que tenía el fichero (`app/volumes/privacy.py`, con
`verifica_sin_pii` de Polaris y tres reglas de EMMA encima). No se limpia en silencio: se rechaza y
se dice qué campo. Los cuatro ejemplos de arriba pasan esa misma comprobación, y también los 15
TAC del dataset bajados en local, tal como los publica el dataset (`-m external`). Qué no cubre
(los vóxeles, lo que no sea la identidad declarada): `risk-management-file.md`, H18.

**Volúmenes que EMMA limpia al entrar (2026-10-07).** Esa puerta rechaza también el texto técnico
inocuo que deja un conversor de DICOM en `descrip`. Por decisión del usuario se ofrece la limpieza
dentro de EMMA, sin ablandar la puerta. Qué cambia en la procedencia de un volumen así:

- **Solo a petición.** El rechazo (422) dice si limpiar serviría (`cleanable`) y trae el texto de
  la oferta; el operador reenvía el mismo fichero con `clean=true`. Sin `clean` nada cambia, y un
  fichero que ya pasa la puerta se guarda como llegó aunque se pida limpiar.
- **Lo guardado no es el fichero recibido, y el asiento lo dice.** Se guarda y se firma el volumen
  limpio. Su asiento `volume-study` lleva un bloque `cleaned`: los nombres de los campos vaciados
  (`descrip`, `extensiones`, `envoltorio gzip`…; nunca su contenido), el SHA-256 y el tamaño del
  fichero recibido, y una nota. El `sha256` del asiento es el del guardado. El fichero recibido no
  se conserva en ningún sitio.
- **Es el mismo estudio.** Los vóxeles son, bit a bit, los recibidos (se comprueba contra los
  bytes del fichero antes de guardar); `sform` y `qform` con sus códigos, `dim`, `pixdim`, tipo,
  `scl_slope`/`scl_inter` y unidades se reponen del fichero recibido (`privacy.CONSERVED`). La
  cabecera vacía la da `nifti_limpio` de Polaris; lo demás es regla de EMMA, declarada en
  `app/volumes/privacy.py`. El resto de campos queda de fábrica y se declara por su nombre.
- **Vuelve a pasar la misma puerta.** Lo limpio se comprueba otra vez con la identidad declarada
  del tripulante; si no pasa, 422 y no se guarda nada.
- **Qué no hace.** No mira ni limpia los vóxeles: texto quemado en la imagen, o una cara
  reconstruible, siguen ahí. La oferta y la nota firmada lo dicen.

Pruebas: `tests/test_volumes.py` («La puerta ofrece limpiar»); campañas `volumes_privacy` y
`volumes_upload_privacy`.

### 2.1 Ejemplos que viajan en el paquete

`backend/app/data/ultrasound_samples/`, generados con `backend/scripts/extract_ultrasound_samples.py`
desde las descargas de origen. Dos de pulmón (una imagen cada uno, del conjunto de prueba del
dataset, elegidas por nombre de fichero) y dos de hígado (los 10 fotogramas del primer paciente de
cada clase). Qué se decidió y por qué:

- **Se revisaron a ojo, una a una.** Ninguna lleva datos identificativos. Sí llevan marcas
  quemadas en los píxeles —calibres de una medida ajena en un ejemplo de pulmón; escala de
  profundidad, hora y FC en los de hígado— y el DICOM lo declara (`BurnedInAnnotation = YES`), en
  vez de callarlo.
- **Firmados como simulados** (`simulator:dataset`): son pacientes de un dataset, no esta
  tripulación. El modo de misión lo declara, y cambiar de escenario los puede descartar.
- **Sin calibración.** Los datasets no publican la escala; inventarla daría milímetros falsos. Se
  pueden ver y anotar, no medir.
- **Claves neutras y etiqueta fuera del estudio.** La clase del dataset ("con esteatosis",
  "healthy"...) y el nombre del fichero original, que la delata, quedan solo en el manifiesto. En
  la interfaz se rotulan "Pulmón 1", "Hígado 2"...: quien anota los signos no debe saber de
  antemano qué "tiene" la imagen.
- **La cita viaja en el asiento del ledger** (`dataset`: nombre, cita, DOI, licencia, URL), no solo
  en la interfaz: acompaña al estudio allá donde se exporte.

Citas obligatorias en la entrega:

- van den Heuvel T. L. A., de Bruijn D., de Korte C. L., van Ginneken B. *Automated measurement of
  fetal head circumference using 2D ultrasound images.* PLoS ONE 13(8): e0200412, 2018.
  Datos: doi:10.5281/zenodo.1327317.
- Byra M. et al. *Transfer learning with deep convolutional neural network for liver steatosis
  assessment in ultrasound images.* Int J CARS, 2018. doi:10.1007/s11548-018-1843-2.
  Datos: doi:10.5281/zenodo.1009146.
- Katumba A. et al. *A dataset of lung ultrasound images for automated AI-based lung disease
  classification.* Data in Brief 62:112034, 2025. Datos: Mendeley Data, doi:10.17632/hb3p34ytvx.2.

---

## 3. Buscados y descartados

| Fuente | Por qué no se usa |
|---|---|
| NASA OSDR/ALSDA **OSD-435** (ecocardiografía de ratón) | Solo tablas de medidas derivadas (CSV), sin imágenes; ratón irradiado en tierra |
| NASA OSDR, ecografía de tripulación en la ISS | No publicada como imagen. Los datos de astronautas son procesados o de acceso controlado |
| Dataset multicéntrico de nervio óptico transorbital (Marzola et al., *Ultrasound Med Biol*, 2023) | La licencia CC BY es del **artículo**; no hay repositorio ni licencia de los **datos** |
| POCUS de pulmón (github.com/jannisborn/covid19_ultrasound) | Etiquetas CC BY-NC 4.0; muchos vídeos no se pueden redistribuir |
| COVID-BLUES (ecografía pulmonar) | Licencia de los datos CC BY-NC-ND, aunque algún catálogo lo destaque como abierto: no comercial y sin derivadas |
| Ecografías de Inspiration4 (vejiga, yugular, ojo) en TRISH EXPAND | Existen, pero con acceso controlado y revisión de solicitud: no se pueden redistribuir en una entrega pública |
| Vejiga, yugular interna, FAST | No se encontró ningún dataset abierto con licencia declarada |

---

## 4. Consecuencia para la validación

- Para **nervio óptico, yugular y vejiga** no hay imágenes abiertas: su medida se valida como
  geometría (calibres a mm, con HC18) y su respaldo clínico se toma de la literatura, con la misma
  clasificación que los parámetros del simulador: magnitud documentada, sentido documentado o
  contestado.
- Para los protocolos sin dataset, la demo usa **fantomas sintéticos deterministas** generados por
  EMMA (`app/imaging/phantom.py`), con la medida real conocida. Entran firmados como simulados
  (`simulator:phantom`) y se rotulan así en la interfaz y en la API.
- HC18 se descarga con `backend/scripts/fetch_hc18.py`, que comprueba la huella MD5 publicada por
  Zenodo, en `data/hc18/` (fuera del repositorio). Resultado en `external-validation.md`.
- Si aparece un dataset de tripulación publicado (p. ej. en OSDR), entra aquí primero, con su
  licencia y su nivel de acceso.
