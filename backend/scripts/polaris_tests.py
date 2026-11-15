# SPDX-License-Identifier: AGPL-3.0-or-later
"""Corre las pruebas de Polaris copiadas tal cual y escribe `polaris/PRUEBAS.md`.

Por qué existe: que una herramienta copiada *cargue* (`polaris/ESTADO.md`) no dice que *haga lo
que Polaris espera* aquí, en Windows y con el adaptador de EMMA. Sus propias pruebas lo dicen. Se
corren como las corre Polaris (`tests/test_all.sh`): fichero a fichero, con rc 77 como "saltada
porque falta su entorno", y nunca dentro de la suite de EMMA.

Aislamiento (invariante 3): el estado va a un directorio temporal, `BTP_IA_FAKE` contesta por el
modelo, y `HTTP(S)_PROXY` apunta a un puerto muerto, así que un intento de salir a internet falla
y se ve en rojo. Lo que salga en rojo no se arregla tocando la copia: se declara, y la causa de
cada roja va en `CAUSES`, de donde sale al informe.

Dos errores que ya costaron una pasada cada uno, y cómo se cierran aquí:

* **Las pruebas corrían sobre la copia versionada.** Varias herramientas de Polaris calculan su
  casa desde `__file__` y no miran `BTP_REPO`: `biomarcadores` creó dos veces
  `polaris/00_FUENTE-DE-VERDAD/00 · Bandeja de entrada/`, y la huella de la copia dejó de casar.
  Ahora corren sobre una copia temporal de `polaris/` (`sandbox`), así que nada de lo que hagan
  puede tocar la versionada; lo único que este guion escribe en ella es `PRUEBAS.md`.
* **`python3` era otro Python.** Polaris lanza `python3` por nombre (sus ganchos, `mutantes.py`).
  En Windows un venv no trae `python3.exe`, y el `PATH` encontraba un Python 3.14 del sistema sin
  las dependencias de EMMA. `interpreter_dir` pone delante del `PATH` un `python`/`python3` que es
  el intérprete que corre este guion.

Y uno que no rompía nada pero ensuciaba: **las pruebas dejaban sus `mkdtemp` en el temporal del
sistema** (cientos de carpetas por pasada, que nadie borraba). Ahora `TMP`, `TEMP` y `TMPDIR`
apuntan a `tmp/`, dentro de la carpeta de la pasada, y esa carpeta entera se borra al terminar
(`pass_folder`). No va dentro de `polaris/`: ahí no se genera nada. Si algo se resiste al borrado
(un fichero que retiene un proceso que una prueba dejó vivo), se dice dónde queda.

Uso:
    .venv/Scripts/python.exe scripts/polaris_tests.py              # pruebas
    .venv/Scripts/python.exe scripts/polaris_tests.py --mutantes   # y sus campañas de mutantes
    .venv/Scripts/python.exe scripts/polaris_tests.py --solo test_fichas   # una, con su salida

Licencia y origen (AGPL §5a): este fichero no contiene código de Polaris. Corre las pruebas de la
copia literal `polaris/tests/` (commit en `polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la
autora de Polaris, «Beyond the Protocol») sin modificarlas.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app import polaris  # noqa: E402

SKIPPED = 77  # convención de Polaris (tests/_entorno.py)
TIMEOUT_S = 180
DEAD_PROXY = "http://127.0.0.1:9"


# Clases de causa. Ninguna es "se arregla tocando la copia"; la última sí sería trabajo de EMMA.
WINDOWS = "Windows"
NOT_COPIED = "no copiado"
EMMA_DECISION = "decisión de EMMA"
HER_HOME = "fuera de su casa"
EMMA_GLUE = "pegamento de EMMA"
KINDS = {
    WINDOWS: "la prueba o la herramienta piden algo de macOS o de Unix que Windows no tiene",
    NOT_COPIED: "falta un fichero del entorno de la autora que la copia no trae",
    EMMA_DECISION: "consecuencia de una decisión declarada en `docs/polaris-divergencias.md`",
    HER_HOME: "la prueba da por hecho que corre dentro del lazo de Polaris, en casa de su autora",
    EMMA_GLUE: "fallo real del adaptador de EMMA: se arregla en `backend/app/polaris/`",
}

_PS = (
    "no hay `/bin/ps` ni `lsof`: `ramas` no puede leer dónde están las sesiones de Claude vivas, "
    "las cuenta como ilegibles y se niega a proponer podas (falla cerrado)"
)
_SYMLINK = "crear un enlace simbólico pide un privilegio que el usuario no tiene (WinError 1314)"
_HOOKS = "los ganchos de Claude Code de la autora (`.claude/hooks/`)"

# Por qué sale en rojo cada prueba roja, leída la aserción que falla (clase, causa). Sale al
# informe; una roja sin entrada aparece como «sin explicar», y una entrada cuya prueba ya no está
# en rojo, como causa caducada. `tests/test_polaris_tests_runner.py` exige que cada clave sea una
# prueba que existe en la copia.
CAUSES: dict[str, tuple[str, str]] = {
    "test_aprobaciones_atascos": (NOT_COPIED, "`tools/config/politica_aprobacion.json`"),
    "test_autopoda_residuo": (WINDOWS, _PS),
    "test_avisos_origen": (
        EMMA_DECISION,
        "EMMA registra solo Ollama (§1): con ese registro cambia qué fallo de cerebro se clasifica "
        "como ambiental y qué se avisa",
    ),
    "test_backup_latido": (NOT_COPIED, "`tools/backup.sh`"),
    "test_bucles_colgados": (WINDOWS, "lanza un guion de shell (`zsh`) que no existe (WinError 2)"),
    "test_capacidades": (NOT_COPIED, "el catálogo de agentes de la autora (`.claude/agents/`)"),
    "test_casa_estilo": (
        HER_HOME,
        "fuera de launchd (`XPC_SERVICE_NAME`/`BTP_LAZO` = `com.btp.*`) `salida` antepone el sello "
        "«origen: sesión local» a la alerta, que ya no es idéntica al texto crudo, y el aviso de "
        "«hay un borrador esperando» cuenta como entrega; 78 de 80 bien",
    ),
    "test_caso_publico": (
        NOT_COPIED,
        "la marca `.espejo-publico`: la copia sale del espejo público, donde el léxico vetado "
        "llega reescrito, y sin la marca la prueba no se salta el caso que ya no tiene qué cazar",
    ),
    "test_cerebro_enlace": (WINDOWS, _SYMLINK),
    "test_clinico_guard": (NOT_COPIED, _HOOKS + ": sin `clinico_guard.py` todo sale denegado"),
    "test_codigo_rojo_excepciones": (NOT_COPIED, "`tools/config/` (excepciones de código rojo)"),
    "test_cola_turnos": (NOT_COPIED, "`tools/btp_dispatcher.sh`"),
    "test_cost_guard": (
        WINDOWS,
        "`os.getuid` no existe (la sonda de `cost_guard` revienta al calcular su carpeta temporal) "
        "y los permisos `0600` no se pueden fijar; 84 de 86 bien",
    ),
    "test_decision_alto_riesgo": (
        NOT_COPIED,
        "el catálogo de agentes de la autora (`.claude/agents/`): sin él `evaluar` da «panel "
        "INCOMPLETO» (3 aserciones). Las otras dos son de Windows: los permisos `0600` del acta "
        "y el informe de la propia prueba, escrito en modo texto (su huella no es la del "
        "texto); 83 de 88 bien",
    ),
    "test_deid_eval": (
        NOT_COPIED,
        "`.claude/hooks/zonas_clinicas.py`: sin él la «ventanilla clínica» no reconoce ninguna "
        "zona. Lo que EMMA usa de `deid_eval` (`cargar_brat`, `fugas`, la detección) pasa",
    ),
    "test_deuda_cerrar_ejecuta": (NOT_COPIED, "`tests/test_all.sh`"),
    "test_deuda_disponibilidad": (NOT_COPIED, "`tests/test_all.sh`, donde busca el enganche"),
    "test_dominios_con_dueno": (NOT_COPIED, "`.claude/agents/`"),
    "test_escalado_inteligencia": (
        NOT_COPIED,
        "`.claude/rules/normas-que-se-me-olvidan.md`: la prueba lee una norma de las reglas de "
        "Claude Code de la autora, no una herramienta",
    ),
    "test_f1_opus_supervision": (NOT_COPIED, _HOOKS),
    "test_fichas": (
        NOT_COPIED,
        "el catálogo cuenta las piezas del repositorio entero de Polaris (más de 200, con "
        "`hooks/` y guiones); la copia trae solo las herramientas adoptadas y sus pruebas",
    ),
    "test_fuente_clinica": (WINDOWS, _SYMLINK),
    "test_git_mutex_merge_fallido": (NOT_COPIED, "`tools/githooks/reference-transaction`"),
    "test_git_mutex_poda": (NOT_COPIED, "`tools/btp_dispatcher.sh`"),
    "test_healthcheck_cpu": (
        WINDOWS, "`os.getloadavg` no existe: `_cpu_ahora` no puede tomar la medida real",
    ),
    "test_healthcheck_halt_inactividad": (
        WINDOWS,
        "`launchctl` es de macOS: `_check_roster_daemons` sale con «launchctl ilegible» antes de "
        "calcular la inactividad; 10 de 13 bien",
    ),
    "test_healthcheck_syspath": (NOT_COPIED, "`tools/correo_smtp.py` y `tools/postdicom.py`"),
    "test_identidad_paciente": (
        NOT_COPIED, "`.claude/hooks/zonas_clinicas.py` (la ventanilla clínica); 24 de 25 bien",
    ),
    "test_inventario_uso": (
        NOT_COPIED,
        "`tools/onco.py`, cuyo uso mide uno de sus casos (quedó fuera: abre una URL), y "
        "`tools/launchd/com.btp.inventario-uso.plist`; 11 de 13 bien",
    ),
    "test_inventario_viejas_modelos": (
        WINDOWS,
        "`inventario` busca la fecha de cada pieza con la clave `tools\\vieja.py` "
        "(`os.path.join`) y `git log --name-only` la da como `tools/vieja.py`: toda fecha sale "
        "«?» y `--viejas` no lista ninguna; 9 de 10 bien",
    ),
    "test_kickstart_bootstrap": (WINDOWS, "`os.getuid` no existe"),
    "test_laminillas_jaulas_secretos": (WINDOWS, "el módulo `pwd` es de Unix"),
    "test_lector_clinico_binario": (WINDOWS, _SYMLINK),
    "test_lentes": (NOT_COPIED, "los comités de la autora (`.claude/agents/`)"),
    "test_llavero_mudo": (NOT_COPIED, "`tools/hoy_compose.sh`"),
    "test_muro_fase0": (WINDOWS, _SYMLINK),
    "test_muro_secreto_stdout": (NOT_COPIED, _HOOKS),
    "test_nonce_a4_blindado": (
        NOT_COPIED, "`.claude/hooks/salida_guard.py`: sin el gancho fallan los cuatro «deja pasar»",
    ),
    "test_presencia_cc": (
        NOT_COPIED, "`.claude/settings.json` y " + _HOOKS + "; además, un enlace simbólico",
    ),
    "test_prueba_entregable": (NOT_COPIED, "`.claude/hooks/muro_guard.py`"),
    "test_ramas_borrador": (WINDOWS, _PS),
    "test_ramas_detached": (WINDOWS, _PS),
    "test_rc_turnos_agotados": (NOT_COPIED, "`tools/btp_dispatcher.sh`"),
    "test_rebuild_agents": (
        NOT_COPIED,
        "`tools/templates/agente_boilerplate.md`: la plantilla que `rebuild_agents` lee nada más "
        "importarlo la prueba",
    ),
    "test_regla_en_accion": (NOT_COPIED, _HOOKS),
    "test_replay_gate": (NOT_COPIED, "`.claude/hooks/gate_salida.py`"),
    "test_replay_guard_json": (NOT_COPIED, "`.claude/hooks/salida_guard.py`"),
    "test_replay_hook_roto": (
        NOT_COPIED,
        "`.claude/hooks/clinico_guard.py`: sin el gancho real `comprueba` lo rechaza e `iniciar` "
        "sale con rc 2 sin escribir `rodaje.json`, que la prueba abre después; 3 de 5 bien antes "
        "de caer",
    ),
    "test_rodaje_hook_fijo": (
        WINDOWS,
        "`rodaje_muro` pide el gancho al commit con `git show <sha>:.claude\\hooks\\g.py` "
        "(`os.path.relpath`) y git solo entiende `/`: da rc 128, la comparación se salta y el "
        "árbol reciclado pasa por bueno; 12 de 13 bien",
    ),
    "test_rodaje_utc": (
        NOT_COPIED,
        "`.claude/hooks/clinico_guard.py`: `iniciar` sale con rc 2 sin escribir `rodaje.json`",
    ),
    "test_saldo_aprende": (NOT_COPIED, "`tools/run_agent.sh`"),
    "test_seguimiento_objetivo_ned": (NOT_COPIED, "`.claude/agents/asistente.md`"),
    "test_tools_no_sombrea_stdlib": (NOT_COPIED, "`tools/correo_smtp.py`"),
    "test_visor3d": (NOT_COPIED, "`.claude/hooks/zonas_clinicas.py`"),
    "test_visor3d_cateter": (NOT_COPIED, "`.claude/hooks/zonas_clinicas.py`"),
    "test_visor3d_colab": (
        WINDOWS, "una ruta de Windows con `\\U` dentro de una cadena de código generado",
    ),
    "test_web_lint": (
        NOT_COPIED,
        "la marca `.espejo-publico` (como `test_caso_publico`): «ingeniera» es el léxico de marca "
        "ya reescrito y no hay qué cazar",
    ),
}

# Campañas de mutantes que no pueden correr: su prueba ya está en rojo sin mutar.
CAMPAIGN_CAUSES: dict[str, str] = {
    "caso_publico.json": (
        "no corre: `test_caso_publico` ya está en rojo sin mutar, por la marca `.espejo-publico` "
        "que la copia no trae"
    ),
    "lector_clinico.json": (
        "no corre: su prueba (`test_lector_clinico_binario`) ya está en rojo sin mutar, por los "
        "enlaces simbólicos de Windows"
    ),
}


def unknown_causes(tests_dir: Path) -> list[str]:
    """Claves de `CAUSES` que no son una prueba de la copia: una causa escrita para nadie."""
    return sorted(name for name in CAUSES if not (tests_dir / f"{name}.py").is_file())


@dataclass(frozen=True)
class Result:
    name: str
    outcome: str  # verde | rojo | saltada
    detail: str


def sandbox(root: Path, scratch: Path) -> Path:
    """Copia temporal de `polaris/`: lo que una prueba escriba "en su casa" cae aquí.

    Sin `node_modules` ni cachés: la copia ya no lleva ninguno (el visor web se compila fuera
    desde el 2026-10-08), pero un resto no debe viajar a la copia temporal.
    """
    copy = scratch / "polaris"
    shutil.copytree(root, copy, ignore=shutil.ignore_patterns("node_modules", "__pycache__"))
    return copy


def interpreter_dir(scratch: Path) -> Path:
    """Directorio para el `PATH` donde `python` y `python3` son el intérprete de este guion.

    En POSIX basta el `bin/` del venv, que ya trae los dos nombres. En Windows un venv solo trae
    `python.exe`, y su lanzador no se puede copiar suelto: busca `pyvenv.cfg` a su lado o un
    nivel arriba. Se monta por eso un venv mínimo —el lanzador con los dos nombres, el
    `pyvenv.cfg` del real y un `.pth` que añade sus `site-packages`—, que acaba en el mismo
    Python base con las mismas dependencias.
    """
    scripts = Path(sys.executable).parent
    config = Path(sys.prefix) / "pyvenv.cfg"
    if sys.platform != "win32" or not config.is_file():
        return scripts
    shim = scratch / "python"
    (shim / "Scripts").mkdir(parents=True)
    for name in ("python.exe", "python3.exe"):
        shutil.copy(Path(sys.executable), shim / "Scripts" / name)
    shutil.copy(config, shim / "pyvenv.cfg")
    site_packages = shim / "Lib" / "site-packages"
    site_packages.mkdir(parents=True)
    (site_packages / "emma.pth").write_text(
        f"import site; site.addsitedir({sysconfig.get_paths()['purelib']!r})\n", encoding="utf-8"
    )
    return shim / "Scripts"


@contextmanager
def pass_folder() -> Iterator[Path]:
    """La carpeta de la pasada, en el temporal del sistema, borrada entera al salir.

    Con `ignore_cleanup_errors`, lo que se resista no corta el borrado del resto ni oculta el
    resultado de la pasada; pero tampoco se calla: se dice qué ruta queda.
    """
    holder = tempfile.TemporaryDirectory(prefix="polaris_pruebas_", ignore_cleanup_errors=True)
    scratch = Path(holder.name).resolve()
    try:
        yield scratch
    finally:
        holder.cleanup()
        if scratch.exists():
            print(f"la carpeta de la pasada no se pudo borrar entera; queda en {scratch}",
                  file=sys.stderr)


def pass_temp(scratch: Path) -> Path:
    """El temporal de las pruebas (`TMP`): dentro de la pasada, para que su borrado lo lleve."""
    temporary = scratch / "tmp"
    temporary.mkdir()
    return temporary


def environment(
    state: Path, interpreter: Path | None = None, temporary: Path | None = None
) -> dict[str, str]:
    """El entorno del adaptador, apuntado a `state`, sin red y con `fcntl` en Windows.

    Con `temporary`, `TMP`/`TEMP`/`TMPDIR` van ahí: `tempfile` los mira en ese orden (`TMPDIR`
    primero) en cualquier sistema, y git y los programas de Windows, `TMP` y `TEMP`.
    """
    env = dict(os.environ)
    env.update({
        # `~` también al directorio temporal: alguna prueba de Polaris escribe en
        # `~/claudecode` sin mirar `BTP_REPO` (test_muro_fase0 lo intentó en la primera pasada).
        "HOME": str(state / "home"),
        "USERPROFILE": str(state / "home"),
        "BTP_REPO": str(state),
        "BTP_STATE_DIR": str(state / "tools" / "state"),
        "BTP_PERIPHERIES": str(state / "peripheries.json"),
        "BTP_PORTABLE": "1",
        "BTP_IA_FAKE": "respuesta de prueba",
        "HTTP_PROXY": DEAD_PROXY, "HTTPS_PROXY": DEAD_PROXY,
        "http_proxy": DEAD_PROXY, "https_proxy": DEAD_PROXY,
        "NO_PROXY": "", "no_proxy": "",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    })
    if sys.platform == "win32":
        compat = str(BACKEND / "app" / "polaris" / "compat")
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [compat, env.get("PYTHONPATH", "")]))
    if interpreter is not None:
        env["PATH"] = os.pathsep.join(filter(None, [str(interpreter), env.get("PATH", "")]))
    if temporary is not None:
        env.update({"TMP": str(temporary), "TEMP": str(temporary), "TMPDIR": str(temporary)})
    return env


Places = list[tuple[Path, str]]


def _spellings(path: Path) -> list[str]:
    """Las formas en que una ruta aparece en una traza: tal cual, con `/` y escapada en un repr."""
    plain = str(path)
    return [plain.replace("\\", "\\\\"), path.as_posix(), plain]


def _last_line(text: str, places: Places) -> str:
    """La última línea con texto, con las rutas temporales por su nombre.

    Las pruebas corren sobre una copia de nombre aleatorio: sin esto el informe cambiaría entero en
    cada pasada y diría `…\\Temp\\polaris_copia_x1\\polaris\\tools\\…` donde el lector busca
    `polaris/tools/…`.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    line = lines[-1]
    for path, name in places:
        for spelling in _spellings(path):
            line = line.replace(spelling, name)
    return line[:200]


def run_test(path: Path, env: dict[str, str], places: Places) -> Result:
    try:
        done = subprocess.run(
            [sys.executable, str(path)], cwd=path.parents[1], env=env,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return Result(path.name, "rojo", f"más de {TIMEOUT_S} s")
    if done.returncode == SKIPPED:
        return Result(path.name, "saltada", _last_line(done.stdout + done.stderr, places))
    if done.returncode == 0:
        return Result(path.name, "verde", _last_line(done.stderr or done.stdout, places))
    # unittest escribe el fallo en stderr; la línea con el error suele ser la última con texto.
    detail = _last_line(done.stderr, places) or _last_line(done.stdout, places)
    return Result(path.name, "rojo", detail)


def run_mutants(copy: Path, env: dict[str, str], places: Places) -> list[Result]:
    """Las campañas de Polaris con su propio `mutantes.py`, sobre la copia temporal `copy`."""
    results = []
    for campaign in sorted((copy / "tests" / "mutantes").glob("*.json")):
        try:
            done = subprocess.run(
                [sys.executable, "tools/mutantes.py", str(campaign)], cwd=copy, env=env,
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=TIMEOUT_S * 10,
            )
        except subprocess.TimeoutExpired:
            results.append(Result(campaign.name, "rojo", f"más de {TIMEOUT_S * 10} s"))
            continue
        outcome = "verde" if done.returncode == 0 else "rojo"
        detail = _last_line(done.stdout + done.stderr, places)
        results.append(Result(campaign.name, outcome, detail))
    return results


def run_suite(
    root: Path, *, mutants: bool = False, registry: dict[str, object] | None = None
) -> tuple[list[Result], list[Result] | None]:
    """Las pruebas de `root/tests` sobre copias temporales de `root`; `root` no se toca.

    Los mutantes van sobre una segunda copia, limpia: las pruebas dejan rastro en la primera
    (carpetas de la autora, cachés) y una campaña tiene que partir de lo que Polaris trae.
    """
    with pass_folder() as scratch:
        state = scratch / "estado"
        (state / "home").mkdir(parents=True)
        (state / "peripheries.json").write_text(
            json.dumps(registry or {}, ensure_ascii=False), encoding="utf-8"
        )
        temporary = pass_temp(scratch)
        env = environment(state, interpreter_dir(scratch), temporary)
        copy = sandbox(root, scratch / "pruebas")
        places: Places = [
            (copy, "polaris"), (scratch / "mutantes" / "polaris", "polaris"),
            (state, "<estado>"), (temporary, "<tmp>"), (scratch, "<pasada>"),
            (Path(tempfile.gettempdir()).resolve(), "<tmp del sistema>"),
        ]
        tests = [
            run_test(path, env, places) for path in sorted((copy / "tests").glob("test_*.py"))
        ]
        campaigns = None
        if mutants:
            campaigns = run_mutants(sandbox(root, scratch / "mutantes"), env, places)
    return tests, campaigns


def run_alone(root: Path, name: str, registry: dict[str, object]) -> int:
    """Una sola prueba, con su salida entera a la consola: para leer la aserción que falla."""
    with pass_folder() as scratch:
        state = scratch / "estado"
        (state / "home").mkdir(parents=True)
        (state / "peripheries.json").write_text(
            json.dumps(registry, ensure_ascii=False), encoding="utf-8"
        )
        copy = sandbox(root, scratch / "pruebas")
        path = copy / "tests" / f"{name.removesuffix('.py')}.py"
        if not path.is_file():
            print(f"no existe polaris/tests/{path.name}")
            return 2
        try:
            return subprocess.run(
                [sys.executable, str(path)], cwd=copy,
                env=environment(state, interpreter_dir(scratch), pass_temp(scratch)),
                timeout=TIMEOUT_S, check=False,
            ).returncode
        except subprocess.TimeoutExpired:
            print(f"más de {TIMEOUT_S} s")
            return 1


def _stem(name: str) -> str:
    return name.removesuffix(".py")


def _cell(text: str) -> str:
    return text.replace("|", "/")


def _cause(result: Result) -> str:
    if result.outcome != "rojo":
        return ""
    kind, why = CAUSES.get(_stem(result.name), ("**sin explicar**", ""))
    return _cell(f"{kind}: {why}" if why else kind)


def report(tests: list[Result], mutants: list[Result] | None) -> str:
    def count(results: list[Result], outcome: str) -> int:
        return sum(1 for result in results if result.outcome == outcome)

    lines = [
        "# Pruebas de Polaris en esta máquina",
        "",
        f"Generado por `backend/scripts/polaris_tests.py` en {platform.system()} "
        f"{platform.release()}, Python {platform.python_version()}. No se edita a mano.",
        "",
        "Son las pruebas del propio Polaris sobre lo copiado, sin tocar, con el adaptador de",
        "EMMA, sin red y con el estado en un directorio temporal. Corren sobre una copia temporal",
        "de `polaris/` (aquí `polaris\\…` es esa copia, `<estado>` su estado, `<pasada>` la",
        "carpeta de la pasada, `<tmp>` el temporal de las pruebas, `TMP`, dentro de ella y",
        "borrado con ella, y `<tmp del sistema>` lo que, aun así, cayó en el del sistema), con",
        "`python` y `python3` en el `PATH` apuntando al intérprete de",
        "arriba. Un rojo no se arregla tocando la copia: se explica en la columna «Causa».",
        "",
        f"**{count(tests, 'verde')} verdes, {count(tests, 'rojo')} rojas y "
        f"{count(tests, 'saltada')} saltadas** de {len(tests)}.",
        "",
    ]
    reds = [r for r in tests if r.outcome == "rojo"]
    if reds:
        lines += ["## Por qué sale en rojo cada una", "", "| Clase | Rojas | Qué significa |",
                  "|---|---|---|"]
        for kind, meaning in KINDS.items():
            n = sum(1 for r in reds if CAUSES.get(_stem(r.name), ("",))[0] == kind)
            if n or kind == EMMA_GLUE:
                lines.append(f"| {kind} | {n} | {meaning} |")
        unexplained = [r.name for r in reds if _stem(r.name) not in CAUSES]
        lines.append(
            f"| **sin explicar** | {len(unexplained)} | "
            "roja sin causa en `CAUSES` (`backend/scripts/polaris_tests.py`): hay que leerla |"
        )
        lines.append("")
    stale = sorted(
        r.name for r in tests if r.outcome != "rojo" and _stem(r.name) in CAUSES
    )
    if stale:
        lines += [
            "Causas caducadas (la prueba ya no está en rojo; quítalas de `CAUSES`): "
            + ", ".join(f"`{name}`" for name in stale) + ".",
            "",
        ]
    lines += [
        "## Una a una",
        "",
        "| Prueba | Resultado | Causa | Última línea |",
        "|---|---|---|---|",
        *[
            f"| `{r.name}` | {r.outcome} | {_cause(r)} | {_cell(r.detail)} |"
            for r in sorted(tests, key=lambda r: ("rojo", "saltada", "verde").index(r.outcome))
        ],
        "",
    ]
    if mutants is not None:
        lines += [
            "## Campañas de mutantes de Polaris",
            "",
            "Con el `mutantes.py` de Polaris, sobre otra copia temporal. Una campaña en rojo es un",
            "mutante que sobrevive o una campaña que no puede correr; la causa conocida, al lado.",
            "",
            "| Campaña | Resultado | Causa | Última línea |",
            "|---|---|---|---|",
            *[
                f"| `{r.name}` | {r.outcome} | "
                f"{_cell(CAMPAIGN_CAUSES.get(r.name, '')) if r.outcome == 'rojo' else ''} | "
                f"{_cell(r.detail)} |"
                for r in mutants
            ],
            "",
        ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--mutantes", action="store_true", help="corre también las campañas")
    parser.add_argument("--solo", metavar="PRUEBA", help="una prueba, con su salida; sin informe")
    args = parser.parse_args()
    root = polaris.root()
    if args.solo:
        return run_alone(root, args.solo, polaris.registry())
    tests, mutants = run_suite(root, mutants=args.mutantes, registry=polaris.registry())
    (root / "PRUEBAS.md").write_text(report(tests, mutants), encoding="utf-8", newline="\n")
    reds = [r for r in tests + (mutants or []) if r.outcome == "rojo"]
    unexplained = [r.name for r in tests if r.outcome == "rojo" and _stem(r.name) not in CAUSES]
    print(f"{len(tests)} pruebas; rojas: {len(reds)}. Detalle en polaris/PRUEBAS.md")
    if unexplained:
        print("rojas sin explicar (léelas con --solo y añade su causa): " + ", ".join(unexplained))
    return 0


if __name__ == "__main__":
    sys.exit(main())
