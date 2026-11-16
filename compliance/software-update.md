# Actualización de la aplicación de escritorio

**Estado:** especificación del actualizador, escrita el mismo día que su implementación (backend,
API, aplicación de escritorio, interfaz y guion de publicación, en piezas paralelas del mismo lote).
Lo que aquí se fija es el contrato que esas piezas cumplen; una divergencia entre este documento y
el código es un fallo de cumplimiento, no un desajuste de documentación, igual que con
[`record-integrity.md`](record-integrity.md) y `core/ledger.py`.
**Última revisión:** 2026-11-16

Documento de respaldo para una decisión de entrega: cómo una instalación de EMMA pasa a la versión
nueva publicada en `github.com/Brillande/EMMA` (cada versión `vX.Y.Z`, con `EMMA.Setup.X.Y.Z.exe`)
sin abrir una segunda salida a internet, sin instalar nada que no se haya comprobado y sin que
ocurra sin que una persona lo pida.

> **Nota de alcance.** IEC 62304 es una norma de pago. El §9 **parafrasea** su estructura y no
> cita su texto. Los números de subcláusula de ese apartado no se han cotejado con la norma en esta
> revisión y hay que comprobarlos antes de citarlos fuera. EMMA se desarrolla **conforme a**
> IEC 62304 Clase B ([`software-safety-classification.md`](software-safety-classification.md));
> nada de lo que se describe aquí la certifica ni la acerca a una certificación.

---

## 1. La decisión: el patrón de «Modelos de IA», no `electron-updater`

**Por qué no `electron-updater`.** Es la biblioteca habitual de las aplicaciones Electron, y
saldría a internet desde el proceso de Node de la aplicación de escritorio. Eso se salta
`backend/app/core/egress.py`, que es la única salida a internet de EMMA (invariante 3 bis de
`CLAUDE.md`): la lista blanca por propósito, el modo sin red, el modo seguro, el control de borde
de Polaris y la traza de cada salida viven allí, y una segunda puerta tendría que reproducirlos
todos o callarlos. Además sería una dependencia nueva, con su ficha de SOUP.

**Lo que se hace.** Se copia el patrón que ya baja el paquete de modelos desde el propio programa
(`backend/app/models_download.py`, `backend/app/api/models_pack.py`,
`frontend/src/components/ModelsPack.tsx`):

1. **El backend** consulta y descarga por `egress.client`, comprueba tamaño y huella, y deja el
   instalador verificado en una carpeta propia.
2. **La aplicación de escritorio** (`desktop/main.cjs`) no sale a la red: cuando una persona pide
   instalar, vuelve a comprobar el fichero, lanza el instalador y se cierra.

**No se añade ninguna dependencia**: ni en el backend, ni en la interfaz, ni en la aplicación de
escritorio (§4.1 de `software-safety-classification.md`).

**Nunca es automático** (decisión del usuario, 2026-11-16). No hay comprobación periódica ni al
arrancar: la consulta sale solo cuando alguien pulsa «Comprobar», la descarga solo cuando pulsa
«Descargar», y la instalación solo cuando pulsa «Instalar y reiniciar». Una nave en misión no
cambia el software que vigila a la tripulación porque haya salido una versión.

---

## 2. Contrato

### 2.1 El manifiesto: `emma-update.json`

Cada versión de la aplicación publicada lleva, junto al instalador, un fichero
`emma-update.json`:

```json
{"schema": 1, "version": "0.1.5", "installer": "EMMA.Setup.0.1.5.exe",
 "size": 123456789, "sha256": "<64 cifras hexadecimales>", "notes": "<texto corto>"}
```

| Campo | Regla |
|---|---|
| `schema` | `1`. Otro valor es `bad-manifest`: un formato que esta versión no entiende no se interpreta a medias |
| `version` | `X.Y.Z` numérico. Se compara como semver numérico (`0.1.10` es mayor que `0.1.9`) |
| `installer` | Nombre del fichero del instalador publicado en la misma versión |
| `size` | Bytes del instalador. La descarga que no los alcanza o los pasa no es válida |
| `sha256` | Huella SHA-256 del instalador, en hexadecimal |
| `notes` | Texto corto que la interfaz muestra tal cual |

Un manifiesto mal formado, sin alguno de esos campos o con tipos que no casan es `bad-manifest`, y
no se ofrece ninguna actualización.

### 2.2 De dónde se lee y por qué puerta sale

- **URL:** `settings.update_url` (`EMMA_UPDATE_URL`), por defecto
  `https://github.com/Brillande/EMMA/releases/latest/download`. El manifiesto es
  `<update_url>/emma-update.json` y el instalador `<update_url>/<installer>`.
- **«latest»:** GitHub resuelve `latest` a la versión marcada como la última. La versión del
  paquete de modelos (`modelos-1`, `backend/packaging/publish_models.py`) se publica **sin**
  marcarla como `latest` y no interfiere; por la misma razón `settings.models_url` apunta a una
  etiqueta fija y no a `latest`.
- **Puerta:** propósito `app-update` de `core/egress.py`, con `github.com`,
  `objects.githubusercontent.com` y `release-assets.githubusercontent.com` (adonde GitHub redirige
  cada fichero). Solo sale la URL de cada fichero: ningún dato de salud, de la tripulación ni del
  equipo.

### 2.3 La versión instalada

`settings.app_version` (`EMMA_APP_VERSION`). La fija la aplicación de escritorio con
`app.getVersion()` al arrancar el backend. Si falta —el backend arrancado a mano, en desarrollo—
vale `None` y la comprobación dice **«versión desconocida»** sin comparar: no se ofrece una versión
como «nueva» frente a algo que no se sabe.

Una prueba exige la misma versión en `backend/pyproject.toml`, `frontend/package.json`,
`desktop/package.json` y `backend/app/main.py`, porque cada una la lee un sitio distinto (el
instalador, la API, la interfaz) y una que se quede atrás haría comparar contra un número falso.

### 2.4 La carpeta de actualización

`settings.update_dir` (`EMMA_UPDATE_DIR`). La aplicación de escritorio la fija en
`userData/actualizacion`; por defecto es `cache_dir/actualizacion`.

| Fichero | Quién lo escribe | Qué significa |
|---|---|---|
| `<installer>.partial` | Backend, al descargar | Descarga en curso o cortada. Se reanuda con `Range` desde donde quedó. **Nunca se ejecuta** |
| `<installer>` (`EMMA.Setup.X.Y.Z.exe`) | Backend, al terminar | El instalador, ya con tamaño y SHA-256 comprobados contra el manifiesto |
| `listo.json` | Backend | `{version, file, sha256, size}`. Se escribe **de forma atómica y solo después** de comprobar tamaño y SHA-256. Sin él no hay nada que instalar |
| `instalar.json` | Backend, al pedir instalar | `{version, file, sha256, requested_at}`. Es la petición que lee la aplicación de escritorio |

El orden es el que sostiene la seguridad: un fichero que no ha pasado la comprobación nunca tiene
`listo.json`, y sin `listo.json` el backend no escribe `instalar.json`.

### 2.5 API

| Ruta | Qué hace |
|---|---|
| `GET /api/app-update` | Estado sin salir a la red: estado del trabajo, versión instalada, versión disponible (la de la última comprobación), progreso de la descarga, `network` y `network_note` (como en `GET /api/models-pack`: sin red se dice por qué) |
| `POST /api/app-update/check` | Lee el manifiesto y compara versiones |
| `POST /api/app-update/download` | Empieza o reanuda la descarga; responde `202` y sigue en segundo plano |
| `POST /api/app-update/cancel` | Para la descarga. El `.partial` se queda para reanudar |
| `POST /api/app-update/install` | Escribe `instalar.json`. Solo vale si hay `listo.json`; si no, `not-ready` |

Los cuatro `POST` pasan por `console_post()` (`backend/app/api/console_header.py`): ninguno lleva
cuerpo, así que sin la cabecera propia una página ajena abierta en el mismo navegador podría
dispararlos con una petición simple. Es una barrera, no autenticación (§7.5 de
`record-integrity.md`).

| Código de error | Cuándo |
|---|---|
| `offline` | Modo sin red (`EMMA_OFFLINE`) o no se llega al servidor. No es un fallo (§6) |
| `blocked` | La puerta lo niega: modo seguro, host fuera de la lista del propósito o freno de borde de Polaris |
| `bad-manifest` | El manifiesto no se puede leer, no es `schema` 1 o le falta o le sobra forma |
| `bad-hash` | El fichero descargado no tiene el tamaño o la huella del manifiesto. Se descarta y no se escribe `listo.json` |
| `no-space` | No cabe en el disco |
| `not-ready` | Se pide instalar sin un `listo.json` |
| `safe-mode` | Se pide instalar con el modo seguro activo (`423`, §7). El instalador sigue listo |
| `same-version` | La versión publicada no es mayor que la instalada |

### 2.6 La aplicación de escritorio

`desktop/main.cjs` sondea `instalar.json` cada 2 s. Cuando aparece:

1. Recalcula el SHA-256 del fichero y lo compara con el de la petición.
2. Comprueba que la versión pedida es **mayor** que `app.getVersion()`.
3. Comprueba que el fichero está **dentro** de la carpeta de actualización (una ruta con `..` o
   absoluta a otro sitio no se lanza).
4. Cierra el backend, el planificador y Ollama, como en `before-quit`.
5. Lanza el instalador con `/S` y `--updated` como argumentos separados, y hace `app.quit()`.

Si algo falla, borra `instalar.json` y lo anota en el registro de la aplicación
(`userData/logs`). No reintenta: la persona vuelve a pedirlo.

### 2.7 La interfaz

Un panel «Actualizaciones» en el pie «Acerca de», junto a «Modelos de IA». Muestra la versión
instalada, la disponible con sus notas, el progreso y el estado de la red con su nota. Solo hay
comprobación con botón. **Nunca se instala sin que una persona pulse «Instalar y reiniciar».** El
texto de error lo da el backend con su código; la interfaz no lo redacta.

### 2.8 Publicación

`backend/packaging/publish_app.py`, con `gh` y en el estilo de `publish_models.py`: calcula el
SHA-256 del instalador construido, escribe `emma-update.json`, crea el borrador `vX.Y.Z`, sube el
exe y el manifiesto y lo marca `--latest`. **Lo ejecuta solo el usuario**: publicar en el
repositorio público es decisión suya (`CLAUDE.md`, Convenciones), y nada de EMMA ni de sus pruebas
lo lanza.

---

## 3. Flujo

```
Comprobar ──► manifiesto ──► ¿mayor que la instalada? ──no──► same-version
                                    │ sí
                                    ▼
Descargar ──► <installer>.partial ──► tamaño y SHA-256 ──mal──► bad-hash (se descarta)
   ▲   (Range)                               │ bien
   └── corte / cancelar                      ▼
                          <installer> + listo.json (atómico)
                                             │
Instalar y reiniciar ──► instalar.json ──► Electron: SHA-256, versión, carpeta ──mal──► se borra y se anota
                                             │ bien
                                             ▼
                     cierra backend, planificador y Ollama ──► EMMA.Setup.X.Y.Z.exe /S --updated ──► app.quit()
```

**Después de instalar, EMMA no se vuelve a abrir sola.** En el instalador asistido de
electron-builder 26.15.3 (`oneClick: false` en `desktop/package.json`), la aplicación solo se
relanza tras una instalación silenciosa si se pasa además `--force-run`
(`app-builder-lib/templates/nsis/installSection.nsh`), y el contrato pasa `/S --updated`. La
persona la abre desde su acceso directo cuando el instalador termina. Leído en la plantilla, no
comprobado con un instalador construido (§10).

---

## 4. Modelo de amenazas

| Amenaza | Control | Lo que queda |
|---|---|---|
| **Descarga cortada o corrupta** (enlace que cae, proxy que trunca, bit cambiado) | Tamaño y SHA-256 del manifiesto antes de `listo.json`; el `.partial` nunca se ejecuta | Nada que dependa del canal: un fichero que no casa se descarta |
| **Instalador sin firmar** | Ninguno de Windows: el instalador **no va firmado** con certificado de código y SmartScreen puede avisar. La huella del manifiesto es lo que sustituye, en parte, a la firma | Ver la fila siguiente |
| **Cuenta de GitHub comprometida o versión publicada maliciosa** | **Ninguno.** El manifiesto viaja por el mismo canal y lo publica la misma cuenta que el exe: quien pueda subir un instalador alterado puede subir su huella. La huella protege de la corrupción y de las descargas cortadas, **no de quien controla la publicación** | **Límite declarado.** Cerrarlo pide una firma que no viaje con el fichero: firma de código Authenticode comprobada por la aplicación de escritorio antes de lanzar, o un manifiesto firmado con una clave que no esté en GitHub. **Pendiente**; no hay fecha |
| **Bajada de versión forzada** (una versión antigua con un fallo conocido, publicada como `latest`) | El backend no ofrece una versión que no sea mayor (`same-version`) y la aplicación de escritorio vuelve a exigir versión mayor que `app.getVersion()` | Un atacante con la cuenta publica una versión mayor; es la fila anterior |
| **Fichero sustituido en disco entre la comprobación del backend y el lanzamiento** | La aplicación de escritorio recalcula el SHA-256 justo antes de lanzar y exige que el fichero esté dentro de la carpeta | Queda una ventana entre su comprobación y la ejecución. La carpeta es del usuario: quien puede escribir en ella ya ejecuta código como él, y la instalación es por usuario (`perMachine: false`), sin elevación, así que no gana privilegios |
| **`instalar.json` escrito por otro proceso local** | Solo lo escribe el backend; Electron compara la huella real del fichero con la de la petición, la versión y la carpeta | Un proceso con permiso de escritura en la carpeta puede escribir un exe y una petición coherentes. Mismo razonamiento que la fila anterior: no es una escalada |
| **Una página ajena dispara descarga o instalación** | `console_post()` en los cuatro `POST` | Es una barrera contra peticiones simples entre orígenes, no autenticación: la API sigue sin identificar operadores (H3, H12) |
| **Datos de salud en la petición** | Por `egress.client` con propósito `app-update`: la traza guarda metadatos y el control de borde de Polaris mira la URL. Solo sale la URL de un fichero público | Lo de cualquier salida (H15): la puerta vigila el código de EMMA |

---

## 5. Un corte a mitad de misión

**Durante la descarga.** Se queda el `.partial`. La siguiente descarga lo reanuda con `Range` desde
donde quedó; si el servidor no admite `Range`, empieza de cero. Ningún fichero sin comprobar se
instala: el corte puede retrasar una actualización, no instalar una a medias.

**Entre la descarga y la instalación.** El instalador comprobado y `listo.json` se quedan en la
carpeta, que no está dentro de la instalación. Instalar no necesita red: se puede pedir más tarde,
en otra ventana de trabajo, también sin conexión con Tierra.

**Durante la instalación.** Mientras el instalador corre, **EMMA está cerrada y no vigila**: no hay
análisis ni alertas hasta que la persona vuelve a abrirla (§3). Si la instalación se corta (corte
de corriente, el equipo se apaga), la aplicación puede quedar a medias. **No hay instalación A/B
ni vuelta atrás automática.** La recuperación es manual: volver a ejecutar el instalador, que sigue
en la carpeta de actualización (no la borra la desinstalación, §8), o el de la versión anterior
(§8).

Por eso la decisión de instalar es de una persona y no del programa: elegir el momento —fuera de
una EVA, de una alerta abierta o de una tarea en la que se esté leyendo EMMA— es la medida de
control, y la interfaz no lo hace por ella (H26 de
[`risk-management-file.md`](risk-management-file.md)).

---

## 6. Sin red: el modo nominal

`EMMA_OFFLINE=true` es el modo nominal de misión, no uno degradado (`CLAUDE.md`). Sin red:

- `GET /api/app-update` responde igual (no sale a la red) y `network_note` dice por qué no se
  puede comprobar;
- comprobar y descargar terminan en `offline`, sin esperar;
- un instalador ya comprobado se puede instalar, porque instalar no sale a la red.

**Que no haya actualización sin red no es un fallo.** La versión instalada es la que se probó; la
nave sigue con ella. La interfaz lo presenta como estado, no como error.

---

## 7. El modo seguro

Con el modo seguro activo (asiento `safe-mode`, §3.20 de `record-integrity.md`), `core/egress.py`
corta toda salida: comprobar y descargar terminan en `blocked`, y nada sale.

**Tampoco se instala** (decisión del usuario, 2026-11-16), aunque el instalador ya esté bajado y
comprobado y no haga falta red: instalar cierra EMMA y cambia de versión, que es justo lo que no se
quiere en una contingencia. `POST /api/app-update/install` responde `423` con el código
`safe-mode` y el motivo declarado, no escribe `instalar.json` y deja el instalador listo para
cuando se desactive (`Updater.request_install`, que pregunta a `egress.safe_mode_reason()`).
Pruebas: `test_safe_mode_blocks_installing_even_a_ready_installer` y
`test_the_api_refuses_to_install_in_safe_mode` (`tests/test_app_update.py`).

**Límite:** el bloqueo está en la petición. Una petición escrita justo antes de declarar el modo
seguro la recoge la aplicación de escritorio en su siguiente sondeo (≤ 2 s); no se revoca.

---

## 8. Vuelta atrás y conservación de datos

**El actualizador nunca baja de versión.** Volver a una anterior es manual: descargar el
`EMMA.Setup.X.Y.Z.exe` de esa versión desde la página de Releases de `github.com/Brillande/EMMA` y
ejecutarlo. Que el instalador asistido de electron-builder acepte instalar una versión menor sobre
una mayor no se ha comprobado con un instalador construido.

**Lo que conserva una actualización.** `desktop/package.json` declara
`deleteAppDataOnUninstall: true`: desinstalar EMMA borra su carpeta de datos de usuario
(`%APPDATA%\EMMA`, el `userData` de Electron). Al instalar sobre una versión existente, el
instalador ejecuta antes el desinstalador de la anterior, y le pasa **siempre** `--updated`
(`app-builder-lib/templates/nsis/include/installUtil.nsh`, electron-builder 26.15.3, con el
comentario «to ensure that if DELETE_APP_DATA_ON_UNINSTALL is defined, user data will be not
removed»); con `--updated` el desinstalador no borra esos datos (`uninstaller.nsh`). Eso vale
también para la reinstalación manual de una versión anterior. Se conservan así la caché de datos
externos (`userData/cache`), los registros (`userData/logs`) y la propia carpeta de actualización.
El paquete de modelos vive aparte (`%LOCALAPPDATA%\EMMA-modelos`) y la desinstalación no lo toca.

**Lo que no se conserva, con o sin actualización.** El almacén de la API es **en memoria**
(`new_store` en `backend/app/api/routes.py`; §3.2 de `record-integrity.md`): el ledger de la sesión
—lecturas, firmas, modo seguro, la base de Marplanner (§3.31 de `record-integrity.md`)— vive lo
que vive el proceso. Cerrar EMMA para actualizar lo termina, igual que cerrarla por cualquier otra
razón. El actualizador no crea esta pérdida, pero la hace más probable, y por eso se declara (H27).

**Versión y almacén.** Hoy no hay almacén de salud en disco que migrar. Lo persistente son cachés
con su edad declarada y el paquete de modelos con su `instalado.json`. El día que el almacén pase a
fichero, una versión nueva tendrá que migrarlo o negarse a abrirlo, y una vuelta atrás manual
tendrá que poder leer lo que dejó la nueva: ese requisito queda escrito aquí y en H28, sin código
todavía.

---

## 9. Correspondencia con IEC 62304

*Paráfrasis de las cláusulas 5.8, 6 y 8.* Alcance: **conforme a**, en la medida en que se dice;
ninguna afirmación de esta tabla equivale a una certificación ni la reclama.

| Cláusula (paráfrasis) | Qué aporta el actualizador | Lo que no cubre |
|---|---|---|
| **5.8 Entrega del software:** identificar la versión que se entrega, documentar cómo se crea y las anomalías conocidas, archivarla, y asegurar que llega sin corrupción ni cambio no autorizado | Versión única en cuatro sitios con prueba (§2.3); cada versión publicada con su instalador y su huella (§2.1, §2.8); comprobación de tamaño y SHA-256 en el backend y de nuevo en la aplicación de escritorio | La huella no prueba el origen (§4): sin firma de código, «sin cambio no autorizado» depende de la cuenta que publica. Las anomalías conocidas de cada versión no tienen un registro formal (§5 de `software-safety-classification.md`, fila «9 Resolución de problemas») |
| **6 Mantenimiento:** analizar cada modificación y su efecto, implementarla con el mismo proceso y entregarla | Una versión nueva llega a una instalación existente por un camino definido y verificado, sin perder los datos de usuario (§8) y sin que se instale sola | No hay plan de mantenimiento formal ni análisis de impacto escrito por versión; el `notes` del manifiesto es un texto corto, no ese análisis |
| **8 Gestión de configuración:** identificar los elementos de configuración y sus versiones, controlar los cambios y llevar cuenta de su estado | El repositorio de trabajo usa git (local) y cada versión publicada es una foto en `github.com/Brillande/EMMA` con etiqueta `vX.Y.Z`; la versión instalada se lee en el programa y se compara | La foto publicada no lleva la historia (`CLAUDE.md`): la trazabilidad de cambio a cambio vive solo en el repositorio local. No hay control de cambios con aprobación formal |

---

## 10. Lo que no se ha comprobado

- **El instalador no se ha ejecutado con `/S --updated`** sobre una instalación existente en esta
  revisión. Lo dicho sobre `--updated`, la conservación de `userData` y el relanzamiento está leído
  en las plantillas NSIS de electron-builder 26.15.3, no observado.
- **Las versiones publicadas hasta la v0.1.4 no llevan `emma-update.json`.** La primera versión que
  trae el actualizador se instala a mano; desde ella, las siguientes se ofrecen en el panel.
- **El instalador no está firmado** (§4.1 de `software-safety-classification.md`), y Windows
  SmartScreen puede pedir confirmación también al lanzarlo desde EMMA.
