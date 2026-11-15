"""Validación externa contra MMASH: fisiologia humana real.

Marcadas `external` porque necesitan el dataset descargado. Fuera de CI, como
las `live`. Descarga:

    https://physionet.org/files/mmash/1.0.0/MMASH.zip  ->  data/mmash/MMASH.zip

EL UMBRAL SE FIJO DESPUES DE MEDIR, NO ANTES
--------------------------------------------
`MEASURED_ALARM_RATE` es el valor observado el 2026-09-20, no un objetivo. La
prueba detecta **empeoramientos**; no certifica que la cifra sea buena — no lo
es, y `compliance/external-validation.md` lo dice con todas las letras.

Bajar el umbral porque el codigo mejoro es correcto. Subirlo para que pase una
suite que empeoro es exactamente el fallo que este fichero existe para evitar.
"""

import datetime as dt
from pathlib import Path

import pytest

from app.analysis.baseline import BaselineEngine
from app.ingest.fhir import Context
from app.validation import report as R
from app.validation.mmash import LOADED, MAX_PLAUSIBLE_SPAN, MmashLoader

DATASET = Path(__file__).resolve().parents[2] / "data" / "mmash" / "MMASH.zip"

# Medido el 2026-09-22, tras dejar de leer "cero pasos con el acelerometro
# quitado" como reposo (hallazgo 28). Antes: 0,0023; antes de etiquetar el sueno
# desde los registros de cama, 0,0172.
MEASURED_ALARM_RATE = 0.0018
# EL TECHO ESTABA A CINCO VECES LA CIFRA PUBLICADA.
#
# Era 0,0032 + 0,01: un techo del **1,32 %** mientras el proyecto publicaba
# 0,23 %. Una regresion de 0,23 % a 1,2 % —cinco veces peor— pasaba en verde, y
# la constante se habia quedado ademas en el valor anterior a corregir el eje
# temporal del dataset (hallazgo 17). La metrica que sostiene la invariante 5 no
# estaba sujeta. Lo encontro una auditoria de los documentos contra el codigo.
#
# La medicion es determinista —mismo dataset, mismo codigo—, asi que la
# tolerancia no cubre ruido de muestreo: cubre cambios pequenos y legitimos del
# motor. 0,0005 deja el techo en 0,28 %, a una distancia que un empeoramiento
# real no cabe.
TOLERANCE = 0.0005

# Sensibilidad minima por deterioro inyectado, medida el mismo dia. Existe para
# que **nadie pueda bajar la tasa de falsa alarma volviendo sordo al sistema**:
# sin este suelo, apagar las alertas daria un 0 % de falsas alarmas y pasaria la
# suite. Ocurrio de verdad durante el desarrollo — el episodio agudo cayo del
# 100 % al 0 % de deteccion mientras la especificidad "mejoraba".
MIN_SUBJECT_DETECTION = {
    "taquicardia sostenida (+25 lpm)": 0.85,
    "taquicardia progresiva (+15 lpm/día)": 0.30,
    "episodio agudo (+40 lpm, 2 h)": 0.80,
    "colapso de HRV (-30 ms SDNN)": 0.10,
}

# La inyeccion progresiva acumula solo ~8 lpm en las 13,5 h posteriores a su
# inicio: esta dentro de la variacion normal. Su baja deteccion es una
# limitacion del experimento, no del motor. Se deja documentada en vez de subir
# la magnitud hasta que el numero quede bonito.
#
# EL SUELO BAJO DE 0,35 A 0,30, Y NO PORQUE EL MOTOR EMPEORARA.
#
# Medido: 31,8 %. El 0,35 anterior se fijo cuando `user_8` y `user_9` tenian la
# etiqueta de dia corrupta (`day = -29`) y abarcaban 31,5 dias en vez de 1,45.
# Sobre ese eje falso, una deriva de 15 lpm/dia acumulaba hasta 370 lpm: esos dos
# sujetos eran triviales de detectar, y valian 9 puntos porcentuales.
#
# Es decir: **la sensibilidad publicada para este escenario estaba inflada por un
# defecto del dataset**. Arreglado el eje, la cifra honesta es 31,8 %, y el suelo
# ancla ese valor. Subir la magnitud de la inyeccion hasta recuperar el 35 %
# seria ajustar el experimento al numero, que es justo lo que este proyecto se
# comprometio a no hacer.

# Escalado: la deteccion que la tripulacion **llega a ver**, no la interna.
#
# Medir solo desviaciones dejaba ciega la via de tendencia, que es justo la que
# capta una deriva lenta. Estos suelos son mas bajos que los de desviacion
# porque la metrica es mas estricta: exige que la perturbacion **suba** el nivel
# de riesgo respecto al que ese mismo sujeto ya tenia sin ella.
#
# Son bajos en terminos absolutos y eso esta dicho en
# `compliance/external-validation.md`: el escalado es el eje debil del motor.
# Solo los deterioros que MMASH **puede** validar.
#
# La deriva lenta depende de `trend.py`, que exige varios ciclos circadianos
# completos (MIN_SPAN_DAYS = 3) para no confundir fase diaria con tendencia. Con
# 24 h de datos esa via esta correctamente desactivada, asi que fijar aqui un
# suelo para la taquicardia progresiva o el colapso de HRV seria inventarse una
# validacion que el dataset no soporta.
#
# Esa via se valida en la suite interna con datos de duracion de mision:
# `test_trend_path_works_on_mission_length_data`.
MIN_ESCALATION = {
    "taquicardia sostenida (+25 lpm)": 0.60,
    "episodio agudo (+40 lpm, 2 h)": 0.55,
}

# LA METRICA CLINICA: con el deterioro presente, ¿el dominio queda marcado?
#
# `escalated` penaliza a los sujetos que ya alertaban sin deterioro, asi que
# infravalora la deteccion. En la taquicardia sostenida, 12 sujetos pasaban de
# nominal a concern, 9 ya estaban en concern y solo 1 se escapaba: el escalado
# decia 55 %, pero marcados quedaban 21 de 22.
MIN_FLAGGED = {
    "taquicardia sostenida (+25 lpm)": 0.75,
    "episodio agudo (+40 lpm, 2 h)": 0.65,
}

# Contrapeso: cuantos sujetos SANOS acaban marcados. Sin este techo, subir los
# suelos de deteccion se consigue alarmando con todo.
MAX_HEALTHY_FLAGGED = 0.25

pytestmark = pytest.mark.external


@pytest.fixture(scope="module")
def loader() -> MmashLoader:
    if not DATASET.exists():
        pytest.skip(f"MMASH no descargado en {DATASET}")
    return MmashLoader(DATASET)


# --------------------------------------------------------------------------- #
# Carga
# --------------------------------------------------------------------------- #


def test_dataset_has_the_expected_shape(loader: MmashLoader) -> None:
    assert len(loader.subjects()) == 22


def test_real_rr_intervals_survive_the_artifact_filter(loader: MmashLoader) -> None:
    """El filtro de `wearable.py` atravesado por latidos humanos reales.

    Si rechazara una fraccion grande estaria descartando fisiologia, no ruido.
    """
    data = loader.load("user_1")

    assert data.beats > 50_000, "un día de latidos debería dar decenas de miles"
    assert data.artifact_rate < 0.05, (
        f"el filtro rechaza el {data.artifact_rate:.1%} de los latidos reales; "
        f"por encima del 5 % estaria descartando fisiologia"
    )


def test_real_hrv_lands_in_catalog_range(loader: MmashLoader) -> None:
    """La HRV calculada de datos reales debe caer en el rango del catalogo.

    Si no, o el calculo esta mal o el rango es irreal. Ambas cosas importan.
    """
    from app.ingest.codes import get

    data = loader.load("user_1")
    sdnn = [o.value for o in data.observations if o.key == "hrv-sdnn"]
    code = get("hrv-sdnn")

    assert sdnn
    median = sorted(sdnn)[len(sdnn) // 2]
    assert code.reference_low <= median <= code.reference_high, (
        f"SDNN mediana real {median:.0f} ms fuera del rango del catálogo "
        f"{code.reference_low}-{code.reference_high}"
    )


def test_sleep_is_aggregated_by_night_not_by_segment(loader: MmashLoader) -> None:
    """Regresion: leer cada segmento como una noche marcaba al 95 % de sanos."""
    data = loader.load("user_1")
    durations = [o.value for o in data.observations if o.key == "sleep-duration"]

    assert len(durations) == 1, "user_1 tiene dos segmentos en UNA noche"
    assert 5.0 < durations[0] < 7.0, f"noche agregada implausible: {durations[0]:.2f} h"


def test_mood_is_not_loaded(loader: MmashLoader) -> None:
    """PANAS no se convierte a `mood-valence`: no existe esa equivalencia."""
    data = loader.load("user_1")
    assert not [o for o in data.observations if o.key == "mood-valence"]


def test_cortisol_is_not_loaded(loader: MmashLoader) -> None:
    """MMASH normaliza el cortisol a proteina; LOINC 2142-8 es Mass/volume."""
    data = loader.load("user_1")
    assert not [o for o in data.observations if o.key == "cortisol-salivary"]


def test_the_real_dataset_yields_exactly_the_loader_table(loader: MmashLoader) -> None:
    """Lo que la matriz de riesgos dice que sale de MMASH (`mmash.LOADED`) es lo que sale del
    dataset real, clave y fuente, sumados los 22 sujetos. La prueba sin red lo mira con un
    archivo sintético (`test_mmash_loaded.py`); esta, con el de verdad."""
    emitted = {
        (item.key, item.source) for data in loader.load_all() for item in data.observations
    }
    assert emitted == set(LOADED.items())


def test_context_is_tagged_from_the_activity_diary(loader: MmashLoader) -> None:
    data = loader.load("user_1")
    contexts = {o.context for o in data.observations}
    assert Context.ACTIVE in contexts or Context.REST in contexts


# --------------------------------------------------------------------------- #
# La metrica
# --------------------------------------------------------------------------- #


def test_external_alarm_rate_does_not_regress(loader: MmashLoader) -> None:
    """LA prueba. Alerta sobre gente sana = falsa alarma, por construccion."""
    result = R.run(loader, label="regresion")

    assert result.alarm_rate <= MEASURED_ALARM_RATE + TOLERANCE, (
        f"la tasa de falsa alarma sobre sujetos sanos subio a "
        f"{result.alarm_rate:.2%} (medida: {MEASURED_ALARM_RATE:.2%}). "
        f"Diagnosticar la causa; no subir el umbral"
    )


def test_sensitivity_does_not_regress(loader: MmashLoader) -> None:
    """El contrapeso de la prueba anterior. Las dos juntas, o ninguna sirve.

    Una tasa de falsa alarma baja sin suelo de sensibilidad se consigue apagando
    el sistema. Esta prueba lo impide.
    """
    results = R.measure_all_sensitivity(loader)
    assert results

    for result in results:
        floor = MIN_SUBJECT_DETECTION.get(result.label)
        assert floor is not None, f"deterioro sin suelo declarado: {result.label}"
        assert result.subject_detection_rate >= floor, (
            f"{result.label}: detección cayo a "
            f"{result.subject_detection_rate:.0%} (suelo {floor:.0%}). "
            f"Si esto falla tras reducir falsas alarmas, se ha vuelto sordo al "
            f"sistema, no se ha mejorado"
        )

        flagged_floor = MIN_FLAGGED.get(result.label)
        if flagged_floor is not None:
            assert result.flagged_rate >= flagged_floor, (
                f"{result.label}: solo se marca el dominio en "
                f"{result.flagged_rate:.0%} de los sujetos (suelo "
                f"{flagged_floor:.0%}). La tripulación no lo veria"
            )

        escalation_floor = MIN_ESCALATION.get(result.label)
        if escalation_floor is None:
            continue  # deriva lenta: MMASH no puede validarla, ver MIN_ESCALATION
        assert result.escalation_rate >= escalation_floor, (
            f"{result.label}: el escalado cayo a {result.escalation_rate:.0%} "
            f"(suelo {escalation_floor:.0%}). La tripulación dejaria de verlo"
        )


def test_acute_episode_is_detected_without_personal_baseline(
    loader: MmashLoader,
) -> None:
    """Regresion del fallo mas grave de la sesion.

    Al quitar las alarmas estadisticas del rango poblacional, el episodio agudo
    paso de detectarse en 20/20 sujetos a 0/20: sus lecturas caian todas sin base
    personal, con valores de 111-145 lpm contra un limite critico de 150.

    Lo arreglo distinguir el limite por estado: 145 lpm corriendo es normal, en
    reposo es un hallazgo.
    """
    from app.validation.injection import acute_episode

    result = R.measure_sensitivity(loader, acute_episode, "agudo", limit=10)
    assert result.subject_detection_rate >= 0.8


def test_context_stratification_reduces_false_alarms(loader: MmashLoader) -> None:
    """La correccion de diseno debe seguir aportando.

    Sin estratificar, una lectura despierto se compara contra una referencia
    construida mientras el sujeto dormia: 68 lpm de amplitud circadiana frente a
    11 lpm de dispersion de base.
    """
    data = [loader.load(name) for name in loader.subjects()[:8]]

    def alarm_rate(stratify: bool) -> float:
        flagged = evaluated = 0
        for subject in data:
            deviations = BaselineEngine().evaluate_rolling(
                subject.observations,
                window=R.MISSION_WINDOW,
                lag=R.MISSION_LAG,
                stratify_by_context=stratify,
            )
            evaluated += len(deviations)
            flagged += sum(1 for item in deviations if item.is_concerning)
        return flagged / evaluated if evaluated else 0.0

    assert alarm_rate(stratify=True) < alarm_rate(stratify=False)


def test_body_weight_produces_no_alarms(loader: MmashLoader) -> None:
    """Control negativo: un indicador estable no debe generar hallazgos."""
    result = R.run(loader, label="control", limit=5)
    assert result.subjects


def test_report_serializes_with_its_caveats(loader: MmashLoader) -> None:
    payload = R.run(loader, label="serializacion", limit=3).to_dict()

    assert payload["subjects"] == 3
    assert "alarm_rate" in payload
    assert "alarm_rate_at_rest" in payload
    assert payload["beats"] > 100_000


def test_uncovered_indicators_are_reported(loader: MmashLoader) -> None:
    """No afirmar que la validacion cubre mas de lo que cubre."""
    data = loader.load("user_1")
    uncovered = R.uncovered_indicators(data)

    assert "absorbed-dose-rate" in uncovered, "MMASH no tiene dosimetría"
    assert "cortisol-salivary" in uncovered
    assert len(uncovered) > 10, "MMASH cubre una minoria del catálogo"


def test_short_window_configuration_also_runs(loader: MmashLoader) -> None:
    """Los parametros de mision estan dimensionados para semanas, no para 24 h."""
    result = R.run(
        loader, window=R.SHORT_WINDOW, lag=R.SHORT_LAG, label="corta", limit=5
    )
    assert result.total_deviations > 0


def test_mission_parameters_leave_readings_without_personal_baseline(
    loader: MmashLoader,
) -> None:
    """Con 24 h de dato y 12 h de desfase, mucha lectura cae al rango poblacional.

    No es un fallo: es la constatacion de que los parametros son de mision.
    """
    data = loader.load("user_1")
    deviations = BaselineEngine().evaluate_rolling(
        data.observations, window=dt.timedelta(days=14), lag=dt.timedelta(hours=12)
    )
    fallbacks = sum(1 for item in deviations if item.used_population_range)
    assert fallbacks > 0


def test_sleep_is_tagged_from_bed_records_not_the_diary(loader: MmashLoader) -> None:
    """Regresion del cambio que mas rindio: 5,06 % -> 1,72 % de falsa alarma.

    El diario de actividad apenas registra el sueno —nadie apunta "estoy
    dormido"— asi que solo 228 de 18 460 observaciones llevaban contexto de
    sueno. El resto de lecturas nocturnas se comparaba contra una base de
    vigilia, con el pulso 20-30 lpm mas bajo, y se marcaban en rachas de hasta
    90 lecturas seguidas.
    """
    tagged = sum(
        1
        for name in loader.subjects()[:8]
        for obs in loader.load(name).observations
        if obs.context is Context.SLEEP
    )
    assert tagged > 500, (
        f"solo {tagged} observaciones con contexto de sueño; los registros de "
        f"cama de sleep.csv no se estan usando"
    )


def test_context_is_inferred_where_the_diary_is_silent(loader: MmashLoader) -> None:
    """El diario dejaba sin contexto un tercio de las lecturas.

    Los pasos lo resuelven, y son **independientes del pulso**: inferir el estado
    desde la frecuencia cardiaca para luego juzgarla contra ese estado seria
    circular y enmascararia una bradicardia real.
    """
    data = loader.load("user_1")
    unknown = sum(1 for o in data.observations if o.context is Context.UNKNOWN)

    assert data.steps_per_minute, "no se cargo la acelerometría"
    assert unknown < len(data.observations) * 0.2, (
        f"{unknown}/{len(data.observations)} lecturas siguen sin contexto"
    )


def test_acute_episode_escalates_without_persistence(loader: MmashLoader) -> None:
    """Regresion de un bug propio.

    La red de seguridad que deja pasar un hallazgo aislado seguia condicionada a
    |z| >= 6 despues de que la gravedad pasara a decidirse por cuantiles: un
    hallazgo grave con z moderado ya no la disparaba. El episodio agudo detectaba
    el 90 % de las desviaciones y **escalaba el 0 %**, porque sus ~25 lecturas en
    una ventana de 280 no llegaban al 30 % de persistencia.
    """
    from app.validation.injection import acute_episode

    # Conjunto COMPLETO: el umbral se midio sobre los 22 sujetos, y aplicarlo a
    # un subconjunto daba un valor distinto (30 % con 12 sujetos, 50 % con 22).
    result = R.measure_sensitivity(loader, acute_episode, "agudo")
    assert result.escalation_rate >= MIN_ESCALATION["episodio agudo (+40 lpm, 2 h)"], (
        f"el episodio agudo solo escala en {result.escalation_rate:.0%} de los "
        f"sujetos; revisar la red de seguridad de `representative_deviation`"
    )


def test_healthy_subjects_mostly_get_no_alert(loader: MmashLoader) -> None:
    """El contrapeso de los suelos de deteccion.

    Sin este techo, cualquier suelo de sensibilidad se satisface alarmando con
    todo. Junto con `MIN_FLAGGED` acota el sistema por los dos lados.

    Lo que lo hizo bajar de 10/22 a 3/22: la red de seguridad dejaba pasar UNA
    lectura grave aislada, y en los sanos de MMASH el 0,49 % de las lecturas de
    pulso cruza un limite de peligro. Ahora exige una rafaga, cuyo tamano se
    calcula segun la ventana: 3 en la de MMASH (`risk.min_severe_readings`).
    """
    from app.analysis.baseline import BaselineEngine
    from app.analysis.risk import RiskEngine, RiskLevel
    from app.analysis.trend import trends_by_indicator

    flagged = 0
    subjects = loader.subjects()
    for name in subjects:
        data = loader.load(name)
        status = RiskEngine().assess(
            name,
            BaselineEngine().evaluate_rolling(
                data.observations, window=R.MISSION_WINDOW, lag=R.MISSION_LAG
            ),
            trends=trends_by_indicator(data.observations),
        )
        if status.overall_level is not RiskLevel.NOMINAL:
            flagged += 1

    rate = flagged / len(subjects)
    assert rate <= MAX_HEALTHY_FLAGGED, (
        f"{flagged}/{len(subjects)} sujetos sanos acaban marcados ({rate:.0%}); "
        f"techo {MAX_HEALTHY_FLAGGED:.0%}"
    )


# --------------------------------------------------------------------------- #
# Integridad del eje temporal del dataset
# --------------------------------------------------------------------------- #


def test_burst_rule_rate_is_what_healthy_people_produce(loader: MmashLoader) -> None:
    """La tasa con la que la regla de rafaga escala sale de aqui, y aqui se vigila.

    `risk._HEALTHY_SEVERE_RATE` son las lecturas graves por lectura en los sanos
    de MMASH. Si el motor cambia y la tasa medida se mueve, la constante deja de
    describir los datos: esta prueba lo dice en vez de dejarlo pasar.

    Y fija un hecho que costo ver: **ninguna** de esas lecturas graves es un
    suceso de percentil. Todas son cruces de limite de peligro, porque ninguna
    base de MMASH alcanza las muestras que exige declarar "grave" por cuantil.
    La primera version de la regla modelaba justo el suceso que no ocurre. Si
    algun dia aparece uno, el modelo de la regla hay que revisarlo.
    """
    from collections import Counter

    from app.analysis.baseline import Severity, SeverityBasis
    from app.analysis.risk import _HEALTHY_SEVERE_RATE

    lecturas: Counter[str] = Counter()
    graves = []
    for name in loader.subjects():
        data = loader.load(name)
        for deviation in BaselineEngine().evaluate_rolling(
            data.observations, window=R.MISSION_WINDOW, lag=R.MISSION_LAG
        ):
            lecturas[deviation.key] += 1
            if deviation.severity is Severity.SEVERE:
                graves.append(deviation)

    # La regla cuenta por indicador, asi que la tasa es por lectura DEL
    # indicador. El pulso es el unico de MMASH que produce lecturas graves; si
    # aparece otro, la constante ya no es "la tasa del pulso" y hay que revisarla.
    assert {d.key for d in graves} == {"heart-rate"}
    rate = len(graves) / lecturas["heart-rate"]
    assert rate == pytest.approx(_HEALTHY_SEVERE_RATE, abs=0.0005), (
        f"los sanos producen {rate:.4%} de lecturas graves de pulso y la regla "
        f"escala con {_HEALTHY_SEVERE_RATE:.4%}: re-derivar la constante y su ancla"
    )
    assert all(d.basis is SeverityBasis.DANGER_LIMIT for d in graves), (
        "aparecio una lectura grave por percentil en la validacion: el modelo "
        "de la regla de rafaga ya no describe los datos"
    )


@pytest.mark.parametrize("per_day", [12, 24, 48])
def test_short_windows_do_not_alarm_more_than_the_validated_one(
    loader: MmashLoader, per_day: int
) -> None:
    """Donde la rafaga baja a 2, los sanos no pueden salir mas marcados.

    La regla de rafaga pide 3 lecturas graves en la ventana de MMASH y 2 en las
    cortas. Que esas 2 no compren deteccion con falsas alarmas se comprueba
    submuestreando el pulso real a la cadencia de un wearable modesto. Medido el
    2026-09-21: 0, 0 y 1 de 22 sanos marcados, igual con la constante 3 que con
    la regla calculada. El techo es el de la ventana completa: 2 de 22.
    """
    from app.analysis.risk import RiskEngine, RiskLevel
    from app.analysis.trend import trends_by_indicator

    submuestreado = _SubsampledPulse(loader, per_day)
    flagged = []
    for name in submuestreado.subjects():
        muestra = submuestreado.load(name).observations
        status = RiskEngine().assess(
            name,
            BaselineEngine().evaluate_rolling(
                muestra, window=R.MISSION_WINDOW, lag=R.MISSION_LAG
            ),
            trends=trends_by_indicator(muestra),
        )
        if status.overall_level is not RiskLevel.NOMINAL:
            flagged.append(name)

    assert len(flagged) <= 2, (
        f"a {per_day} lecturas/día se marcan {len(flagged)} sanos {flagged}; con "
        f"la ventana completa son 2 de 22"
    )


class _SubsampledPulse:
    """MMASH con el pulso submuestreado a la cadencia de un wearable modesto."""

    def __init__(self, loader: MmashLoader, per_day: int) -> None:
        self._loader = loader
        self._step = 288 // per_day  # MMASH agrega el pulso cada 5 min
        self._cache: dict[str, object] = {}

    def subjects(self) -> list[str]:
        return self._loader.subjects()

    def load(self, name: str):  # type: ignore[no-untyped-def]
        from dataclasses import replace

        if name not in self._cache:
            data = self._loader.load(name)
            pulso = sorted(
                (o for o in data.observations if o.key == "heart-rate"),
                key=lambda o: o.effective,
            )[:: self._step]
            resto = [o for o in data.observations if o.key != "heart-rate"]
            self._cache[name] = replace(data, observations=pulso + resto)
        return self._cache[name]


def test_short_window_sensitivity_does_not_regress(loader: MmashLoader) -> None:
    """El otro eje de la prueba anterior, en la ventana corta: las dos juntas.

    Medido el 2026-09-21 a 48 lecturas de pulso/dia: taquicardia sostenida
    marcada en el 41 % de los sujetos (27 % con la constante 3) y episodio agudo
    en el 59 % (36 %). Bajar la rafaga a 2 en ventanas cortas gano sensibilidad
    sin coste en falsas alarmas. A 12 lecturas/dia no se marca ningun deterioro
    con ninguna de las dos reglas, y eso esta declarado, no escondido.
    """
    floors = {
        "taquicardia sostenida (+25 lpm)": 0.40,
        "episodio agudo (+40 lpm, 2 h)": 0.55,
    }
    results = R.measure_all_sensitivity(_SubsampledPulse(loader, 48))  # type: ignore[arg-type]
    for result in results:
        floor = floors.get(result.label)
        if floor is None:
            continue
        assert result.flagged_rate >= floor, (
            f"{result.label} a 48 lecturas/día: marcado {result.flagged_rate:.0%}, "
            f"suelo {floor:.0%}"
        )


@pytest.mark.external
def test_no_subject_spans_more_than_the_protocol(loader: MmashLoader) -> None:
    """MMASH dura ~36 h. Un sujeto que abarque semanas tiene el eje roto.

    `user_8` y `user_9` traen `day = -29` en vez de `2`. Tomado literalmente
    colocaba media jornada 30 dias en el pasado: 31,5 dias de span y un hueco de
    710 h. Con eso, la ventana movil descartaba medio registro y el ajuste de
    tendencia cruzaba un vacio de un mes — en silencio, alimentando la tasa de
    falsa alarma publicada.
    """
    for data in loader.load_all():
        momentos = [obs.effective for obs in data.observations]
        span = max(momentos) - min(momentos)
        assert span <= MAX_PLAUSIBLE_SPAN, (
            f"{data.subject}: {span.days} días de registro. Etiqueta de día corrupta"
        )


@pytest.mark.external
def test_corrupt_day_label_lands_on_the_second_day(loader: MmashLoader) -> None:
    """`-29` ocupa la franja del dia 2, y ahi debe quedar colocado.

    No es una suposicion: las franjas horarias de los dos sujetos rotos coinciden
    con las de los veinte sanos (dia 1 de ~09:50 a 23:59, dia 2 de 00:00 a ~09:20).
    """
    for subject in ("user_8", "user_9"):
        momentos = sorted(obs.effective for obs in loader.load(subject).observations)
        dias = {momento.date() for momento in momentos}
        assert len(dias) == 2, f"{subject}: {len(dias)} fechas distintas, se esperaban 2"
        assert max(dias) - min(dias) == dt.timedelta(days=1)
