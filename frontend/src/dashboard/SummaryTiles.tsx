import { BoardOnly } from "../components/BoardOnly";
import { Meter } from "../components/Meter";
import { StatTile, StatTiles } from "../components/StatTile";
import type { CrewStatus } from "../lib/api";
import { DISCREPANCY_MARK, commsMark, commsStatusOf } from "../lib/commsStatus";
import { formatMinutes, formatNumber } from "../lib/format";
import { tr } from "../lib/i18n";
import { MISSING_MARK, NO_MARK } from "../lib/marks";
import { freshnessOf } from "../lib/staleness";

/**
 * Las cifras del resumen de la consola de tripulación, de un vistazo (segunda pasada, §5.33.2).
 *
 * Por qué existe: el día de misión, el retardo con Tierra, las alertas, la dosis y las lecturas
 * que sostienen el veredicto ya estaban en la consola, pero repartidos en frases de la franja, de
 * la línea temporal, del dosímetro y de «En qué se apoya»; para saber «cuánto» había que leer cada
 * frase. Aquí van como fichas con cifra, debajo del resumen, y ninguna dice nada que la consola no
 * dijera ya: la cifra es la misma, del mismo campo de `/api/status`, y el rótulo es una palabra
 * que la interfaz ya escribía (el «Día … de …» de la línea temporal, el «Retardo con Tierra» y las
 * «Alertas activas» de la franja, la «Dosis de carrera» del dosímetro, las «Lecturas analizadas»
 * de la base del veredicto). Sin color propio: lo que falta o caduca lo dice la marca de dato
 * ausente, y lo que preocupa, el nivel del backend en su panel, no una ficha.
 *
 * Lo que falta no se pinta como cero (`StatTile` lanza si se intenta): sin efemérides no hay
 * retardo, y sin dosis facilitada no hay dosis.
 *
 * Tablero (decisión del usuario, 2026-11-07): bajo la concha de la maqueta, dos fichas llevan
 * además su medidor neutro, con la escala que da el backend y ninguna otra: el día de misión sobre
 * la duración prevista (`duration_days`) y la dosis sobre el límite de carrera (`limit_msv`, solo
 * si el backend dio `fraction`: sin dosis ya está la marca cian). Fuera de la escala el medidor no
 * se recorta (patrón de Open MCT, `components/Meter.tsx`): el día lo dice con la fase que nombra el
 * backend (antes del inicio, en prevuelo; pasada la duración, en posvuelo) y la dosis con su tanto
 * por ciento, como el dosímetro.
 */
export function SummaryTiles({ status, alerts }: { status: CrewStatus; alerts: number }) {
  const mission = status.mission;
  const dose = status.dose.cumulative_msv;
  return (
    <StatTiles label={tr("Resumen", "Summary")}>
      <StatTile
        concept="missionDay"
        label={tr("Día", "Day")}
        value={mission.mission_day}
        decimals={1}
        unit={tr(`de ${formatNumber(mission.duration_days)}`, `of ${formatNumber(mission.duration_days)}`)}
      >
        {mission.duration_days > 0 && (
          <BoardOnly>
            <Meter
              value={mission.mission_day}
              max={mission.duration_days}
              label={tr("Día de misión sobre la duración prevista", "Mission day against the planned duration")}
              outOfRange={{ word: mission.phase_display }}
            />
          </BoardOnly>
        )}
      </StatTile>
      <LightTime status={status} />
      <StatTile concept="alerts" label={tr("Alertas activas", "Active alerts")} value={alerts} />
      {dose === null ? (
        <StatTile
          concept="radiation"
          label={tr("Dosis de carrera", "Career dose")}
          value={null}
          status={{ mark: MISSING_MARK, word: tr("sin datos", "no data") }}
        />
      ) : (
        <StatTile concept="radiation" label={tr("Dosis de carrera", "Career dose")} value={dose} decimals={1} unit="mSv">
          {status.dose.fraction !== null && status.dose.limit_msv > 0 && (
            <BoardOnly>
              <Meter
                value={dose}
                max={status.dose.limit_msv}
                label={tr("Dosis acumulada sobre el límite de carrera", "Cumulative dose against the career limit")}
                outOfRange={{ word: `${formatNumber(status.dose.fraction * 100, 1)} %` }}
              />
            </BoardOnly>
          )}
        </StatTile>
      )}
      <StatTile concept="value" label={tr("Lecturas analizadas", "Readings analysed")} value={status.data.observations} />
    </StatTiles>
  );
}

/**
 * El retardo de ida, como en la franja: sin efemérides no se inventa (cian, «Sin efemérides»; con un
 * perfil sin objetivo, «No aplica» en gris: lo dice `comms_status`), y
 * con efemérides caducadas la cifra se conserva en cursiva y con la marca de dato caducado al
 * lado de la edad de las efemerides, la misma frase que da la franja.
 */
function LightTime({ status }: { status: CrewStatus }) {
  // El estado lo da el backend (`comms_status`, 2026-11-11): sin retardo, «Sin efemérides» en cian
  // solo si de verdad falta, y «No aplica» en gris con un perfil sin objetivo de efemérides.
  const comms = commsStatusOf(status);
  if (status.comms === null) {
    return (
      <StatTile
        concept="lightTime"
        label={tr("Retardo con Tierra", "Delay to Earth")}
        value={null}
        status={{ mark: commsMark(comms.state), word: comms.word }}
      />
    );
  }
  const delay = formatMinutes(status.comms.one_way_minutes);
  // Si el cálculo local discrepa de JPL Horizons, eso es lo que hay que mirar (triángulo en ámbar);
  // si no, la fuente del retardo, sin señal.
  const said =
    comms.discrepancy !== null
      ? { mark: DISCREPANCY_MARK, word: comms.discrepancy.word }
      : comms.source_text !== null
        ? { mark: NO_MARK, word: comms.source_text }
        : null;
  if (freshnessOf(status.freshness?.comms) === "fresh") {
    return (
      <StatTile
        concept="lightTime"
        label={tr("Retardo con Tierra", "Delay to Earth")}
        value={delay}
        unit={tr("ida", "one way")}
        {...(said === null ? {} : { status: said })}
      />
    );
  }
  return (
    <StatTile
      concept="lightTime"
      label={tr("Retardo con Tierra", "Delay to Earth")}
      value={delay}
      unit={tr("ida", "one way")}
      stale
      status={
        comms.discrepancy !== null
          ? { mark: DISCREPANCY_MARK, word: comms.discrepancy.word }
          : { mark: MISSING_MARK, word: <>{tr("efemérides ", "ephemeris ")}{status.comms_data_age ?? tr("sin fecha", "undated")}</> }
      }
    />
  );
}
