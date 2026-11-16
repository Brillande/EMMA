"""Configuracion del sistema.

`offline` no es un modo degradado: es el modo de operacion nominal de una mision
de larga duracion. La conectividad es la excepcion.
"""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.ingest.fhir import EvidenceContext

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EMMA_", env_file=".env", extra="ignore")

    # api.nasa.gov. DEMO_KEY funciona para desarrollo pero tiene cuota muy baja.
    nasa_api_key: str = "DEMO_KEY"

    cache_dir: Path = REPO_ROOT / "data" / "cache"
    request_timeout: float = 30.0

    # Fuerza a no tocar la red. Con esto activado, un dato no cacheado es un fallo
    # explicito, nunca una espera indefinida.
    offline: bool = False

    # Idioma del texto servido a quien no pide ninguno (`core/i18n.py`): ingles en esta version
    # (decision del usuario, 2026-11-15). La consola dice el suyo en cada peticion; lo que EMMA
    # firma en el registro se escribe siempre en castellano y no depende de esto.
    lang: Literal["es", "en"] = "en"

    # Sin red y sin cache, usar la instantanea fechada de NASA DONKI que viaja en el paquete
    # (`app/data/donki_snapshot.json`, `environment/donki.py`). Apagado por defecto: lo enciende
    # la aplicacion de escritorio (`desktop/main.cjs`), que arranca con la cache vacia. Nunca tapa
    # un dato en vivo ni una cache, y se declara como instantanea con su fecha, no en vivo.
    donki_snapshot: bool = False

    # Cuerpo objetivo por defecto para las efemerides (Marte).
    target_body: str = "499"
    observer_body: str = "500@399"  # geocentro terrestre

    # Limite de dosis efectiva de carrera, en mSv.
    career_dose_limit_msv: float = 600.0

    # Origen del tiempo de mision (MET). NASA-STD-3001 Vol 2, F.6.1, exige mostrar
    # siempre la hora etiquetada con su sistema, y sin este origen la interfaz no
    # puede calcular el MET. Es el mismo que usa el simulador por defecto.
    mission_start: dt.date = dt.date(2026, 11, 1)

    # En que entorno se toman las lecturas reales (wearable, PVT, manuales, dolor).
    # `ground` por defecto porque hoy es la verdad: los wearables de este equipo estan
    # en Tierra. Desplegado en un analogo o en vuelo, se declara aqui
    # (`EMMA_DEPLOYMENT_CONTEXT=iss`). Lo simulado se etiqueta solo.
    deployment_context: EvidenceContext = EvidenceContext.GROUND

    # Duracion prevista de la mision y regimen de gravedad, para la fase de mision
    # (`core/mission.py`). 180 dias: una expedicion tipica de la ISS dura unos seis meses.
    # Solo se muestran; el analisis no los usa.
    mission_days: int = 180
    gravity_regime: str = "microgravedad"

    # Perfil de mision declarado (`evidence/mission_profiles.py`): `leo`, `cislunar`,
    # `lunar-surface`, `mars-transit` o `mars-surface`. DESCRIPTIVO: se muestra con lo que una
    # fuente leida dice de el y no cambia el escalado del riesgo, que sale del tiempo de luz
    # real. Por defecto, transito a Marte: es el que casa con lo que ya esta configurado
    # (efemerides hacia Marte, `target_body` 499, y microgravedad), asi que nada de lo que hoy
    # se ve cambia ni aparece un aviso de desajuste. `gravity_regime` sigue siendo texto libre
    # y el perfil lo acompana.
    mission_profile: str = "mars-transit"

    # Interfaz compilada (`frontend/dist`). Si se indica, el backend la sirve desde
    # el mismo origen: es como corre la aplicacion de escritorio. Sin ella, solo API.
    frontend_dist: Path | None = None

    # Tesseract para el OCR de informes escaneados (`app/reports/`). Programa externo, local, no
    # se empaqueta: sin él, los informes se guardan y se ven, pero sin texto. None: se busca en
    # el PATH y en la ruta de instalación típica de Windows.
    tesseract_cmd: str | None = None

    # TotalSegmentator para la segmentación de volúmenes (`app/volumes/`, visor 3D de Polaris).
    # Programa externo con PyTorch y pesos preinstalados; no va en el instalador (sí en el paquete
    # de modelos, `packaging/models_pack.py`). Vale su lanzador o un `python.exe` que lleve el
    # paquete `totalsegmentator` (`volumes/segment.py: command_prefix`). None: se busca en PATH.
    totalseg_cmd: str | None = None

    # El paquete de modelos (`packaging/models_pack.py`). `models_dir` es donde se instala: la
    # misma carpeta que mira la aplicación de escritorio (`EMMA_MODELS_DIR`, o
    # `%LOCALAPPDATA%\EMMA-modelos` si no se da; `app/models_download.py: models_dir`).
    # `models_url` es de dónde lo baja «Descargar modelos»: la carpeta (sin la barra final) donde
    # están publicados `emma-modelos-partes.json`, `MANIFIESTO.json` y los trozos que deja
    # `packaging/models_parts.py`. Sale por `core/egress.py` (propósito `models-pack`), así que
    # en modo sin red o con el modo seguro no se descarga nada.
    models_dir: Path | None = None
    # Una etiqueta fija (`modelos-1`), no `latest`: una versión de la aplicación publicada después
    # pasaría a ser la `latest` y la descarga dejaría de encontrar los trozos.
    models_url: str = "https://github.com/Brillande/EMMA/releases/download/modelos-1"
    # Bajar el paquete entero al arrancar si no hay nada instalado. Lo enciende la aplicación de
    # escritorio cuando en el instalador se marcó «Descargar también los modelos de IA»
    # (`desktop/installer.nsh`, `desktop/main.cjs`). Sin red no sale igualmente (`egress.py`).
    models_autodownload: bool = False

    # «Actualizar EMMA» (`app/app_update.py`). `update_url` es la carpeta de la última versión
    # publicada en GitHub (aquí sí `latest`: lo que se busca es justo la más reciente), donde
    # están `emma-update.json` y el instalador. `app_version` es la versión que corre, la pasa la
    # aplicación de escritorio (`EMMA_APP_VERSION`); sin ella no se puede comparar y la
    # comprobación lo dice. `update_dir` es donde se deja el instalador descargado y comprobado
    # (None: `cache_dir/actualizacion`). Sale por `core/egress.py` (propósito `app-update`), solo
    # cuando la persona lo pide: no hay comprobación al arrancar (decisión del usuario).
    update_url: str = "https://github.com/Brillande/EMMA/releases/latest/download"
    app_version: str | None = None
    update_dir: Path | None = None

    # Modelo de lenguaje LOCAL para el borrador de interpretacion (app/interpret/). Solo
    # loopback: el cliente rechaza cualquier otra direccion. El modelo es configurable y no
    # esta validado clinicamente; sin servidor local, la funcion se declara no disponible.
    #
    # Elegido midiendo la tarea real el 2026-09-24 en el equipo de desarrollo (RTX 4070 de
    # 8 GB, 32 GB de RAM): qwen3.6:35b-a3b (mezcla de expertos, 3B activos) redacto un
    # borrador limpio en 8,5 s ya cargado; qwen3.5:9b iba entero en GPU pero su verificador
    # objetaba frases correctas. Un equipo con menos memoria necesita un modelo menor.
    #
    # CAMBIADO el 2026-11-14 (decisión del usuario): qwen3.6:35b-a3b y gemma4:latest ya no están
    # instalados en este portátil y la función salía «no disponible». Redactor gemma4:e4b: en dos
    # redacciones del borrador de la vaina del nervio óptico copió las cifras bien y no recetó;
    # seco pero fiel, ~30 s con cambio de modelo en la GPU.
    llm_url: str = "http://127.0.0.1:11434"
    llm_model: str = "gemma4:e4b"
    # Comité de verificadores (patrón de Polaris: voces de casas distintas). Todos locales y
    # todos obligatorios: si falta uno, la función se declara no disponible. Medido el
    # 2026-09-25 con dos borradores correctos y uno con una afirmación inventada: gemma4 (Google)
    # no objetó nada correcto y cazó la inventada; llama3.1:8b (Meta) objetó todas las frases,
    # correctas incluidas, y queda fuera; qwen3.5:9b objetó una frase correcta.
    #
    # Repetido el 2026-11-14 con la misma forma (dos correctos, uno con un síntoma inventado):
    # gemma4:12b-it-qat 3/3; gemma4:e4b DEJÓ PASAR el inventado —no sirve de verificador, aunque
    # redacte bien—; qwen3.5:9b bloqueó los dos correctos. Queda un solo verificador, de la misma
    # casa que el redactor: es una desviación del patrón de Polaris, aceptada porque no hay aquí
    # un modelo de otra casa que respete lo correcto. Muestra pequeña: orienta, no valida.
    llm_verifiers: list[str] = ["gemma4:12b-it-qat"]
    # Modelo LOCAL del asistente de voz (app/assistant/) y cerebro de la copia de Polaris
    # (app/polaris, decision del usuario del 2026-11-03). Mismo servidor que `llm_url`, solo
    # loopback. No toca el borrador de interpretacion ni su comite, que siguen arriba.
    #
    # Elegido midiendo el 2026-11-03 en este portatil (RTX 4070 de 8 GB, 32 GB de RAM) con un
    # banco de 17 casos: 12 ordenes que enrutar, 3 respuestas solo con lo dado y 2 de no recetar,
    # a temperatura 0 y sin razonamiento. qwen3.5:4b: 9/12, 2/3 (cambio 74 lpm por 64), 2/2,
    # 0,24 s de mediana. gemma4:12b-it-qat: 11/12, 3/3, 2/2, 0,70 s. gemma4:latest: 9/12, 2/3,
    # 2/2, 0,25 s. El unico que no cambio una cifra. Banco pequeno: orienta, no valida.
    #
    # Revisado el mismo dia con 24 ordenes reales por `POST /api/assistant/turn` (escenario
    # spe-event, prompt y catalogo de EMMA): qwen3.5:9b 19/24 intenciones, ~6 s por turno;
    # gemma4:12b-it-qat 18/24, ~7 s; ministral-3:8b 18/24, ~6 s, y se invento una definicion;
    # granite4.2:8b 18/24, ~6 s, con un espanol peor. Los cuatro dieron la cifra bien y no
    # recetaron; casi todo el tiempo es evaluar el estado, no el modelo. qwen3.5:9b (6,6 GB) cabe
    # entero en la GPU con holgura. Los seis fallos comunes a todos eran del catalogo, no del
    # modelo. Sigue siendo una muestra pequena.
    assistant_model: str = "qwen3.5:9b"
    # Quién pasa a texto lo dicho al asistente (`POST /api/assistant/audio`). `auto`: el propio
    # modelo si Ollama dice que oye (`capabilities` con `audio`) y el audio es WAV; si no, Whisper
    # (`app/voice.py`). `whisper`: siempre Whisper.
    #
    # Por qué (el usuario, 2026-11-06: «el qwen suele patinar con la voz»): con Whisper `base`, el
    # modelo recibe la frase ya mal transcrita. Probado el mismo día con gemma4:e4b (Ollama
    # 0.40.14) y cuatro frases de las voces es-ES de Windows: las cuatro bien, 0,3 s cada una ya
    # cargado. OJO: la copia `gemma4:latest` de 6 meses antes también declara `audio` y devolvía
    # sílabas sin sentido («el re o el re o…»); `auto` no puede notarlo, así que el modelo que
    # oiga hay que probarlo antes de ponerlo.
    assistant_hearing: Literal["auto", "whisper"] = "auto"
    # Precalentar el modelo del asistente con el primer `GET /api/assistant` (una petición mínima
    # en segundo plano, `api/assistant.py::warm_up`): en frío, el primer turno tardaba 4-5 s más.
    # Las pruebas lo apagan (`tests/conftest.py`): un hilo suelto no debe llamar a nada.
    assistant_warmup: bool = True

    def ensure_dirs(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
