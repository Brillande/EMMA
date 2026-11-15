# SPDX-License-Identifier: AGPL-3.0-or-later
"""Único punto de entrada de EMMA al código de Polaris copiado tal cual en `polaris/tools/`.

Por qué existe: la regla del proyecto es copiar Polaris literal y decidir los cambios después
(`polaris/ORIGEN.md`). Entonces lo que haga falta para que ese código viva dentro de EMMA tiene que
estar fuera de él, y en un solo sitio:

* **Dónde escribe.** Las herramientas de Polaris resuelven su casa y su estado con `BTP_REPO` y
  `BTP_STATE_DIR` (`_casa.py`). Aquí se apuntan a un directorio de EMMA, para que nunca escriban en
  `~/claudecode` ni en ningún otro sitio de la máquina.
* **A qué modelo habla.** `ia.py` elige cerebro de un registro (`BTP_PERIPHERIES`). EMMA le da uno
  con un solo cerebro, el `local-ollama` del propio registro de Polaris con la URL y el modelo de
  EMMA: la "nube" de Polaris se queda en Ollama local (decisión del usuario, 2026-09-29).
* **Qué lo para.** Polaris tiene un freno por fichero (`HALT_FILES`): si existe `~/.btp.HALT` o
  el `.HALT` de su repositorio —que `borde` saca de `__file__` y no de `BTP_REPO`, así que cae
  dentro de la copia—, `borde.egress_check` lo niega todo. Tal cual, un fichero en la carpeta
  personal cortaba toda la salida de EMMA sin que EMMA lo supiera, y `cost_guard._panic` habría
  escrito uno allí. Aquí ese freno se confina a un único fichero del estado de EMMA
  (`halt_file`), y no solo en `load`: un gancho de importación lo hace en cuanto se ejecuta
  cualquier módulo de `polaris/tools`, también el que una herramienta importa tarde, dentro de
  una función.
* **Windows.** Lo que a la copia le falta en Windows se pone desde `compat/`, sin tocarla: la
  carpeta va al final de `sys.path` para que `borde.py` encuentre un `fcntl` (de Unix), y a cada
  herramienta que se carga se le instala la sonda de `compat/winlock.py` sobre el candado de
  Polaris. La lista entera de esos módulos, con lo que hace cada uno, la escribe
  `polaris/ESTADO.md`.
* **Qué no carga.** Lo que aun así no importe, `load` lo devuelve con su motivo en vez de romper,
  e `inventory` lo lista entero para `polaris/ESTADO.md`.
* **Qué no se importa para contarlo.** `inventory` importa cada herramienta para decir si carga,
  y hay herramientas que hacen algo solo con importarse (`NOT_IMPORTED`). Esas se listan con su
  motivo y sin importarlas: preguntar qué hay en la copia no puede lanzar nada.

Licencia y origen (AGPL §5a): este fichero no contiene código de Polaris. Carga el de la copia
literal `polaris/tools/` (commit en `polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de
Polaris, «Beyond the Protocol») sin modificarlo: todo lo de aquí es pegamento de EMMA.
"""

from __future__ import annotations

import importlib
import importlib.abc
import json
import os
import sys
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType
from typing import Any

from app.core.config import get_settings
from app.polaris.compat import winlock

_HERE = Path(__file__).resolve()
# En desarrollo `polaris/` está en la raíz del repo; en el backend congelado, junto a `app/`.
_CANDIDATES = (_HERE.parents[3] / "polaris", _HERE.parents[2] / "polaris")
LOCAL_BRAIN = "local-ollama"


class PolarisUnavailable(RuntimeError):
    """Una herramienta de Polaris no se puede cargar aquí; el mensaje dice por qué."""


# Las herramientas de la copia que el inventario NO importa, cada una con su motivo (el texto sale
# tal cual por `GET /api/polaris/estado` y en `polaris/ESTADO.md`).
#
# Por qué existe: `inventory` importa todo `polaris/tools` para decir qué carga, y lo llama una
# ruta de solo lectura. Una herramienta que hace algo al importarse lo haría entonces cada vez que
# alguien mira el inventario, sin que EMMA lo haya decidido. La copia es literal y no se toca, así
# que se dejan fuera del inventario desde aquí (decisión del usuario, 2026-10-09). Solo afecta al
# inventario: `load("…")` por su nombre sigue cargándolas, con lo que hagan.
#
# `tests/test_polaris_bridge.py` falla si un nombre de aquí no está en la copia (para que la lista
# no caduque en silencio), y `tests/test_soup_polaris.py` mide que pedir el inventario no lanza
# procesos, ni escribe, ni abre conexiones, y que `rodaje_muro`, importada a propósito, sí lanza
# el suyo: la exclusión no se quita sin saber por qué está.
NOT_IMPORTED: dict[str, str] = {
    "rodaje_muro": (
        "al importarse lanza git para preguntar por la rama de la carpeta que contiene la copia"
    ),
    "transcribe_audios": (
        "es un guion sin función de entrada: importarlo es ejecutarlo entero; "
        "EMMA lo lanza como programa aparte"
    ),
}


@dataclass(frozen=True)
class ToolStatus:
    """El estado de una herramienta en el inventario.

    Tres casos, no dos: carga (`loads`), no carga (`reason` es el error de importación) y no se
    importa (`imported` falso; `reason` es su motivo de `NOT_IMPORTED`). De la tercera no se sabe
    si cargaría, así que `loads` es falso sin que eso signifique «no carga»: quien cuente tiene
    que mirar `imported` antes.
    """

    name: str
    loads: bool
    reason: str | None
    imported: bool = True


def root() -> Path:
    for candidate in _CANDIDATES:
        if (candidate / "tools").is_dir():
            return candidate
    raise PolarisUnavailable("no está la copia de Polaris (polaris/tools)")


def tools_dir() -> Path:
    return root() / "tools"


def state_dir() -> Path:
    return get_settings().cache_dir / "polaris"


def registry() -> dict[str, object]:
    """El registro de cerebros que ve `ia.py`: solo Ollama local, con la URL y el modelo de EMMA.

    El modelo es el del asistente (`Settings.assistant_model`), no el del borrador de
    interpretación: decisión del usuario del 2026-11-03, tras medir los candidatos en este equipo
    (`core/config.py`, `docs/polaris-divergencias.md` §19).
    """
    source = json.loads((tools_dir() / "peripheries.json").read_text(encoding="utf-8"))
    brains = [brain for brain in source["cerebros"] if brain.get("name") == LOCAL_BRAIN]
    if len(brains) != 1:
        raise PolarisUnavailable(f"el registro de Polaris no trae un único {LOCAL_BRAIN!r}")
    settings = get_settings()
    brain = {
        **brains[0],
        "url": settings.llm_url.rstrip("/") + "/v1/chat/completions",
        "model": settings.assistant_model,
        "enabled": True,
    }
    return {
        "_nota": "Generado por EMMA (app/polaris): solo el cerebro local. Los de nube de Polaris "
        "están en la copia (su registro y sus módulos), pero no se registran aquí y por eso no "
        "se pueden alcanzar: quedan fuera para siempre (decisión del usuario, 2026-09-29).",
        "cerebros": [brain],
    }


_configured = False
# Reentrante: `seed_decoy` llama a `load`, que llama a `configure`. Dos cerrojos y no uno para que
# sembrar (que importa herramientas) no retenga a quien solo necesita el entorno.
_configure_lock = threading.RLock()
_seed_lock = threading.Lock()


def configure() -> Path:
    """Prepara el entorno de Polaris (estado, casa y registro de cerebros). Idempotente.

    Bajo cerrojo: la primera llamada llega a la vez desde varios hilos (las rutas síncronas de
    FastAPI corren en un grupo de hilos). Sin él, dos escribían `peripheries.json` a la par —y una
    herramienta podía leerlo a medio escribir— y el gancho del freno o la ruta de `tools` podían
    quedar dos veces en `sys.meta_path` y `sys.path`.
    """
    global _configured
    state = state_dir()
    with _configure_lock:
        if not _configured:
            state.mkdir(parents=True, exist_ok=True)
            peripheries = state / "peripheries.json"
            peripheries.write_text(
                json.dumps(registry(), ensure_ascii=False, indent=1), encoding="utf-8"
            )
            os.environ["BTP_REPO"] = str(state)
            os.environ["BTP_STATE_DIR"] = str(state / "tools" / "state")
            os.environ["BTP_PERIPHERIES"] = str(peripheries)
            _configured = True
        # En cada llamada, no solo la primera: alguna herramienta de Polaris toca `sys.path` al
        # importarse, y la siguiente dejaba de encontrarse (pasó con visor3d_superpone_focos).
        tools = str(tools_dir())
        if tools not in sys.path:
            sys.path.insert(0, tools)
        # Los módulos de Unix que la copia importa y Windows no tiene, fuera de la copia: cada
        # uno de `compat/` dice por qué en su docstring, y `polaris/ESTADO.md` los lista.
        compat = str(_HERE.parent / "compat")
        if sys.platform == "win32" and compat not in sys.path:
            sys.path.append(compat)
        # También en cada llamada: quien vacíe o rehaga `sys.meta_path` no deja el freno sin
        # confinar.
        if _BRAKE_HOOK not in sys.meta_path:
            sys.meta_path.insert(0, _BRAKE_HOOK)
    return state


def seed_decoy() -> str:
    """Siembra el señuelo de Polaris (`canarios.sembrar_estado`) donde lo lee su `borde`.

    Un señuelo es un fichero que ningún flujo de EMMA lee: si su token aparece en algo que sale a
    internet, no tiene explicación inocente y `borde.egress_check` lo bloquea (`core/egress.py`).
    `canarios` y `borde` fijan sus rutas al importarse; se siembra en las del `borde` cargado, que
    son las que mira. Si ya hay uno vigente, no se rota: rotarlo en cada arranque no aporta nada.
    Devuelve dónde está.

    Mirar si hay señuelo y sembrarlo va bajo cerrojo: dos hilos que no lo encuentran a la vez
    sembraban los dos, cada uno con su token, y `canarios._escribir` escribe por un `.tmp` de
    nombre fijo, así que en Windows el segundo `os.replace` daba `PermissionError`. Con el cerrojo
    siembra uno y el otro ya lo encuentra. Vale dentro del proceso: dos procesos de EMMA sobre el
    mismo estado no están cubiertos.
    """
    with _seed_lock:
        border: Any = load("borde")
        decoys: Any = load("canarios")
        folder = Path(border.CANARIO_FILE).parent
        decoys.BORDE_DIR = str(folder)
        decoys.CANARIOS = str(border.CANARIO_FILE)
        decoys.REGISTRO = str(folder / "canarios_registro.json")
        decoys.SENUELO_ESTADO = str(folder / "senuelo_no_leer.json")
        try:
            token = json.loads(Path(decoys.SENUELO_ESTADO).read_text(encoding="utf-8"))["token"]
            seeded = json.loads(Path(decoys.CANARIOS).read_text(encoding="utf-8"))
        except (OSError, ValueError, KeyError):
            token, seeded = None, []
        if token is None or token not in seeded:
            decoys.sembrar_estado()
        return str(decoys.SENUELO_ESTADO)


def halt_file() -> Path:
    """El único fichero de freno (`HALT`) que las herramientas de Polaris miran dentro de EMMA.

    Qué significa en EMMA: es el freno por fichero de Polaris, confinado, y no el modo seguro.

    * El **modo seguro** (`api/safe_mode.py`) es el interruptor de EMMA: un asiento firmado en el
      ledger, con su motivo y con la persona que lo levanta.
    * Este **fichero** no lo crea EMMA nunca. Solo existe si lo pone una persona a mano o si lo
      escribe el propio Polaris (`cost_guard._panic`, `codigo_rojo.trigger`), y se levanta
      borrándolo. Mientras existe, `borde` niega todo lo que pasa por él —en EMMA, la salida a
      internet de `core/egress.py`— y las herramientas de Polaris que lo consultan se paran.

    Los dos cortan lo mismo, la red: el modelo local (`interpret/llm.py`) no pasa por el borde y
    sigue con cualquiera de ellos. No pueden contradecirse porque solo suman cortes: algo sale si
    ninguno está activo. La diferencia es que este no se firma ni deja asiento; por eso
    `core/egress.py` lo nombra en su error y en su traza, y `GET /api/safe-mode` lo enseña.

    Es `<BTP_REPO>/.HALT`, donde ya lo buscan `cost_guard` y `soporte_cita`, que sí resuelven la
    casa con `BTP_REPO`.
    """
    return state_dir() / ".HALT"


def _confine_module(module: ModuleType, tools: Path, target: str) -> None:
    """Deja en `target` el freno de `module`, si es una herramienta de la copia que lo define.

    En la copia el freno tiene dos formas: la constante `HALT_FILES` (`borde`, `cost_guard`,
    `salida`, `codigo_rojo`…) y la función `_halt_files()` (`soporte_cita`). Se sustituyen las dos.
    No sirve su variable `BTP_HALT_FILES`: la parten por `:` y una ruta de Windows (unidad, dos
    puntos, ruta) queda en dos trozos.
    """
    namespace = vars(module)
    files, reader = namespace.get("HALT_FILES"), namespace.get("_halt_files")
    if files is None and reader is None:
        return
    origin = getattr(module, "__file__", None)
    if not origin or Path(origin).resolve().parent != tools:
        return  # un módulo ajeno que use los mismos nombres no se toca
    if files is not None:
        # Lista donde el original es lista: quien lo lee solo lo recorre.
        namespace["HALT_FILES"] = [target] if isinstance(files, list) else (target,)
    if reader is not None:
        namespace["_halt_files"] = lambda: (target,)


def _confine_halt() -> None:
    """Deja el freno de toda herramienta de Polaris ya importada en `halt_file()`, y solo ahí.

    Se recorre `sys.modules` entero, y no solo el módulo pedido, porque `borde` y `cost_guard`
    llegan también arrastrados por otros (`deid`, `ia`). Lo que se importe después lo confina el
    gancho (`_BrakeHook`); este barrido queda para lo que ya estaba importado antes de instalarlo
    y para volver a apuntar a `halt_file()` si alguien pisó la constante.
    """
    tools = tools_dir().resolve()
    target = str(halt_file())
    for name, module in list(sys.modules.items()):
        if "." not in name and isinstance(module, ModuleType):
            _confine_module(module, tools, target)


class _ConfiningLoader(importlib.abc.Loader):
    """El cargador de siempre de una herramienta de Polaris, que confina su freno al ejecutarla.

    Todo lo que no sea ejecutar el módulo (`get_source`, `get_code`, `get_filename`…) lo sigue
    respondiendo el cargador original: trazas, `inspect` y `linecache` no notan la diferencia.
    """

    def __init__(self, inner: Any, tools: Path) -> None:
        self._inner = inner
        self._tools = tools

    def __getattr__(self, name: str) -> Any:
        if name == "_inner":  # una copia a medio construir no tiene a quién preguntar
            raise AttributeError(name)
        return getattr(self._inner, name)

    def create_module(self, spec: ModuleSpec) -> ModuleType | None:
        created: ModuleType | None = self._inner.create_module(spec)
        return created

    def exec_module(self, module: ModuleType) -> None:
        try:
            self._inner.exec_module(module)
        finally:
            # También si falla a medias: otro módulo puede haberse quedado ya con una referencia.
            _confine_module(module, self._tools, str(halt_file()))
        # El candado de Polaris, con su sonda de Windows (compat/winlock.py): solo actúa sobre
        # `_lock`, y solo en Windows. EMMA no toma ese candado; es para que, si una herramienta
        # cargada lo toma por su cuenta, no espere a un dueño muerto.
        winlock.install(module)


class _BrakeHook(importlib.abc.MetaPathFinder):
    """Gancho de importación: toda herramienta de `polaris/tools` nace con el freno confinado.

    Por qué existe: confinar solo en `load` dejaba un hueco. Varias herramientas importan a otras
    tarde, dentro de una función (`borde.egress_check` con `escalar=True` trae `codigo_rojo`;
    `seguimiento` y `cronica`, `salida`; `atascos`, `cost_guard`), y esas llegaban con las rutas
    de fábrica —`~/.btp.HALT` y el `.HALT` de la copia— hasta la siguiente `load`: bastaba un
    fichero en la carpeta personal para que se pararan, y `cost_guard._panic` y
    `codigo_rojo.trigger` habrían escrito uno allí.

    No busca nada por su cuenta: pregunta a los demás buscadores, en su orden, y solo si el módulo
    resuelto es un fichero de `polaris/tools` envuelve su cargador. Lo demás (biblioteca estándar,
    dependencias, `app`, y una copia de Polaris en otra carpeta, como las temporales de
    `scripts/mutants.py` y `scripts/polaris_tests.py`) pasa sin tocarse.
    """

    def find_spec(
        self, fullname: str, path: Sequence[str] | None, target: ModuleType | None = None
    ) -> ModuleSpec | None:
        if "." in fullname:  # las herramientas de la copia son módulos sueltos, sin paquete
            return None
        try:
            tools = tools_dir().resolve()
        except PolarisUnavailable:
            return None
        if not (tools / f"{fullname}.py").is_file():
            return None  # lo habitual: una consulta al disco y a otra cosa
        for finder in list(sys.meta_path):
            find = getattr(finder, "find_spec", None)
            if finder is self or find is None:
                continue
            spec: ModuleSpec | None = find(fullname, path, target)
            if spec is None:
                continue
            origin, loader = spec.origin, spec.loader
            wrapped = loader is None or isinstance(loader, _ConfiningLoader)
            if origin and not wrapped and Path(origin).resolve().parent == tools:
                spec.loader = _ConfiningLoader(loader, tools)
            return spec
        return None


_BRAKE_HOOK = _BrakeHook()


def load(name: str) -> ModuleType:
    """Importa la herramienta `name` de Polaris tal cual, o `PolarisUnavailable` con el motivo."""
    configure()
    if not (tools_dir() / f"{name}.py").is_file():
        raise PolarisUnavailable(f"{name}: no está en la copia (polaris/ADOPTADO.txt)")
    try:
        module = importlib.import_module(name)
    except Exception as exc:  # noqa: BLE001 — cualquier fallo de import es "no disponible aquí"
        raise PolarisUnavailable(f"{name}: {type(exc).__name__}: {exc}") from exc
    finally:
        # También si falla: una importación a medias ya puede haber traído a `borde`. El gancho
        # ya confinó lo recién importado; esto repasa lo que hubiera de antes.
        _confine_halt()
    return module


def inventory() -> list[ToolStatus]:
    """Cada herramienta copiada: si importa en esta máquina y, si no, por qué.

    Las de `NOT_IMPORTED` no se importan: salen con `imported` falso y su motivo.
    """
    statuses = []
    for path in sorted(tools_dir().glob("*.py")):
        skipped = NOT_IMPORTED.get(path.stem)
        if skipped is not None:
            statuses.append(ToolStatus(path.stem, False, skipped, imported=False))
            continue
        try:
            load(path.stem)
        except PolarisUnavailable as exc:
            statuses.append(ToolStatus(path.stem, False, str(exc).split(": ", 1)[-1]))
        else:
            statuses.append(ToolStatus(path.stem, True, None))
    return statuses
