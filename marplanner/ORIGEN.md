# Marplanner en EMMA

Copia literal de [Marplanner](https://github.com/diegomarino/marplanner) (planificador doméstico
autoalojado: calendario e ICS, rutinas y tareas, comidas y recetas, recordatorios, mensajes diarios,
hoja diaria impresa, avisos de hora hablados, copias de seguridad). Licencia **MIT**
(`LICENSE`, © 2026 Diego Mariño), compatible con la AGPL-3.0-or-later de EMMA.

- **Commit copiado:** el de `ADOPTADO.txt`. Lo copia `backend/scripts/marplanner_sync.py` desde los
  objetos de git; lo vigila `backend/tests/test_marplanner_copy.py`. **No se edita a mano.**
- **Arquitectura (decisión del usuario, 2026-11-12):** servicio Node aparte, solo en loopback,
  arrancado junto a EMMA; la consola de EMMA lo usa por su API HTTP con pantallas propias en el
  estilo de EMMA. Node 26 (el commit pide `>=24.21 <25`; se usa 26, decisión del usuario).
- **Fuera de la copia** (`fuera` en `ADOPTADO.txt`): despliegue en la nube y CI de GitHub.

## Salidas a internet (decisión del usuario, 2026-11-12)

Toda salida de Marplanner pasa por la puerta de EMMA (`core/egress.py`, invariante 3 bis) o no
sale: `planner-bridge/egress.mjs` envuelve su `fetch` global y su `undici`. A esta máquina
(loopback) va tal cual; a un host con propósito, por `POST /api/planner/fetch` de EMMA (lista
blanca, modo sin red, modo seguro, traza); a cualquier otro, error. Solo GET y sin cuerpo.

| Salida | Qué envía | Estado |
| --- | --- | --- |
| Open-Meteo (tiempo) | coordenadas del hogar | **no sale**: sin propósito; además `WEATHER_ENABLED=0` |
| UniFi Cloud (`api.ui.com`) | clave de API, control de la red | **no sale**: sin propósito; `undici` solo loopback; sin claves |
| ZenQuotes (cita del día) | nada nuestro | propósito `planner-quotes`; solo con red |
| Wikipedia «tal día» (en/es) | mes, día e idioma | propósito `planner-onthisday`; solo con red |
| Feeds ICS | GET a la URL que pone el usuario | **no sale** (decisión del usuario, 2026-11-12: ninguno); `undici` solo loopback |
| Sumidero externo de telemetría | — | no viene ninguno en el commit |

El código de Open-Meteo y UniFi sigue en la copia (está entrelazado); no puede salir por las tres
razones de la tabla. Quitarlo de la interfaz es trabajo de las pantallas de EMMA.

## Base de datos: el ledger firmado de EMMA (decisión del usuario, 2026-11-12)

«Migrar sus base de datos al registro firmado que tenemos». Marplanner no guarda nada en un
fichero SQLite: `planner-bridge/` (código de EMMA, fuera de la copia) sustituye su `better-sqlite3`
por SQLite **en memoria** (`node:sqlite`, Node 26) y anota cada transacción confirmada en el ledger
de EMMA (`POST /api/planner/changesets`, `compliance/record-integrity.md` §3.31) **antes** del
COMMIT; si el ledger la rechaza, se deshace. Al arrancar reproduce el ledger. En disco quedan solo
el fichero vacío que marca el sitio, su cerrojo de instancia y las copias de seguridad que pida el
usuario. Una restauración entra al ledger como una transacción más.

- Se arranca con `node --import <repo>/planner-bridge/register.mjs` y
  `EMMA_PLANNER_LEDGER=http://127.0.0.1:<puerto>/api/planner` (solo loopback). `memory:` es solo
  para correr la suite de Marplanner sin EMMA.
- El ledger de EMMA vive en memoria del proceso: **los datos de Marplanner duran lo que dura el
  backend de EMMA**, como los demás (decisión del usuario, 2026-11-12: «dejarlo en memoria»).
- Arranque: `node planner-bridge/start-marplanner.mjs [--port 8790] [--emma http://127.0.0.1:8000]`
  (loopback, ledger, tiempo apagado, sin claves de UniFi). Probado el 2026-11-12 contra el backend
  real: arranca, siembra, provisiona un dispositivo, escribe; al reiniciar Marplanner la clave del
  dispositivo y el tablero de tareas salen idénticos del ledger y `marplanner.db` sigue en 0 bytes.
- **Copias en disco:** Marplanner hace, como en el original, una copia previa a cada
  migración (`backups/pre-migration/`) y copias programadas (`backups/scheduled-*.db`). Son ficheros
  SQLite completos con los datos del hogar, fuera del ledger. **Se mantienen** (decisión del usuario,
  2026-11-12): restaurar una vuelve a pasar por el ledger, y con el ledger en memoria son lo único
  que sobrevive a un reinicio de EMMA.
- `better-sqlite3` no se compila (`npm ci --ignore-scripts`): no hay binario para Node 26 en
  Windows ni hace falta.

## Windows (`planner-bridge/compat-windows.mjs`)

Marplanner es de Linux/macOS. Su `fsync` sobre ficheros abiertos en solo lectura y sobre
directorios da EPERM en Windows; el puente lo resuelve sin tocar la copia (fichero: se fuerza con
un descriptor de escritura; directorio: NTFS ya lo garantiza).

Suite de servidor de Marplanner con el puente (`vitest run tests/boundary`, ledger `memory:`),
2026-11-12: **2077 de 2095**. Las 18 que fallan son de la plataforma o de lo excluido, no del
ledger: 10 crean enlaces simbólicos (Windows exige privilegio), 4 comprueban permisos POSIX 0600,
3 leen los ficheros de despliegue en la nube que se dejaron fuera, 1 (`ui-debt-ratchet`) por
revisar.

## Qué de Marplanner está en la consola de EMMA (2026-11-12)

Sección «Planificador» de la consola de tripulación (`frontend/src/planner/`), con el estilo de EMMA
(componentes, paleta F.5-1, `format.ts`, sin colores de miembro). Los datos pasan por
`/api/planner/app/*` (`backend/app/planner_link.py`), y lo escrito acaba en el ledger.

| Parte de Marplanner | En EMMA |
| --- | --- |
| Tablero de tareas del día | sí: marcar y deshacer |
| Rutinas y sus tareas | sí: añadir y quitar tareas (asignaciones: solo se ven) |
| Menú del día, de la semana, recetas, planes | sí: comida puntual, recetas con borrado informado, poner en el plan, planes |
| Calendario local | sí: 7 días, añadir y borrar eventos (asignar: solo se ve) |
| Recordatorios | sí: crear, pausar, borrar (los de calendario: solo se ven) |
| Mensajes del día | sí |
| Miembros | sí: alta, archivar, recuperar (sin fecha de nacimiento ni color) |
| Franjas del día | sí |
| Hoja diaria | sí: activar, componer, ver el papel, bloques por miembro |
| Avisos de hora | sí, con la voz local de la consola (no el motor de Marplanner) |
| Impresión térmica | no: Bluetooth del navegador del quiosco |
| Calendarios ICS remotos | no (decisión del usuario, 2026-11-12) |
| Tiempo (Open-Meteo), dispositivos de red (UniFi) | no: sacan datos nuestros |
| Complementos, copias de seguridad, telemetría, aprovisionamiento | no desde la consola: administración de Marplanner (el proxy no los deja pasar) |
| Consola de Tierra | sí: «Planificador de a bordo» en Historial, un resumen por persona y día para el apoyo a la salud mental (ocio, tareas y rachas, pasatiempos, mensajes y recordatorios), reconstruido del ledger hasta la hora real menos el retardo (`planner-bridge/ground-summary.mjs`, `GET /api/planner/ground-summary`) |

## Cambios §5a pendientes / hechos

Ninguno dentro de la copia. Pendiente: quitar Open-Meteo y UniFi.
