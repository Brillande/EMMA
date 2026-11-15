import { useEffect, useState } from "react";

import { BoardOnly } from "../components/BoardOnly";
import { Mark, MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { StatTile } from "../components/StatTile";
import { type MissionHistory, api } from "../lib/api";
import { useArrivalCheck } from "../lib/arrival";
import { formatMinutes } from "../lib/format";
import { MISSING_MARK, type RequestOutcome, requestOutcome } from "../lib/marks";
import { uiPictogram } from "../lib/uiMarks";
import { MissionHistoryContent } from "../radiation/MissionHistory";
import { tr } from "../lib/i18n";

/**
 * El historial misión a misión del tripulante en la consola de Tierra (especificación §3
 * `mission_history`; §5.36.4 del estado del arte), de solo lectura: lo que la tripulación
 * declaró y ya ha llegado, con los cotejos del backend contra el perfil.
 *
 * Por qué existe: hasta aquí solo se veía en la consola de tripulación, junto a donde se declara
 * el perfil, y el cirujano de vuelo no tenía la carrera previa del tripulante que mira. Aquí no
 * se declara nada (no hay formulario): declarar es de a bordo. Lo firmado hace menos de un tiempo
 * de luz está en tránsito y no se pinta; si es una corrección, Tierra sigue viendo la anterior,
 * que es la que tiene.
 */
export function MissionHistoryPanel({
  subject,
  oneWayMinutes,
}: {
  subject: string;
  oneWayMinutes: number | null;
}) {
  // Lo cargado va con el tripulante del que es: al cambiar de tripulante no se pinta ni un
  // instante la carrera del anterior bajo el nuevo (revisión de código, 2026-10-23).
  const [loaded, setLoaded] = useState<{ subject: string; body: MissionHistory } | null>(null);
  const [failed, setFailed] = useState<{ subject: string; outcome: RequestOutcome } | null>(null);
  // El corte del reloj (`arrivalCut`): una declaración viaja cuando se firma, haya o no
  // telemetría nueva, y el backend la cuenta para Tierra si se firmó antes del corte
  // (`api/mission.latest_mission_history`, la misma regla que el perfil). Se mira cada 30 s, con
  // el último tiempo de luz, y no cada vez que cambia unas centésimas (`useArrivalCheck`).
  const { checkKey, cutNow } = useArrivalCheck(oneWayMinutes);

  useEffect(() => {
    let alive = true;
    api
      .missionHistory(subject, cutNow())
      .then((body) => {
        if (!alive) return;
        setLoaded({ subject, body });
        setFailed(null);
      })
      .catch((reason: unknown) => {
        if (alive) setFailed({ subject, outcome: requestOutcome(reason) });
      });
    return () => {
      alive = false;
    };
  }, [subject, checkKey, cutNow]);

  const data = loaded?.subject === subject ? loaded.body : null;
  const unavailable = failed?.subject === subject ? failed.outcome : null;
  return <MissionHistoryGround data={data} unavailable={unavailable} oneWayMinutes={oneWayMinutes} />;
}

/**
 * Solo pinta. Separado de la carga para poder probar lo que se lee en pantalla.
 *
 * Un refresco que falla no borra lo que Tierra ya tenía: se sigue viendo, con la marca de lo que
 * falló encima, como en «Dolor referido». Sin nada cargado, la marca de lo que fue en su lugar.
 *
 * Tablero (decisión del usuario, 2026-11-07): bajo la concha de la maqueta (`BoardOnly`), con
 * misiones declaradas, las fichas de cuántas, la dosis sumada y cuántas van sin dosis
 * (`HistoryBoard`); en cursiva si el último refresco falló.
 */
export function MissionHistoryGround({
  data,
  unavailable,
  oneWayMinutes,
}: {
  data: MissionHistory | null;
  unavailable: RequestOutcome | null;
  oneWayMinutes: number | null;
}) {
  return (
    <section data-ui="ground-mission-history" className="panel" aria-label={tr("Historial misión a misión", "Mission-by-mission history")}>
      <PanelTitle concept="previous">{tr("Historial misión a misión", "Mission-by-mission history")}</PanelTitle>
      {oneWayMinutes !== null && (
        <p className="secondary">
          {/* El signo del retardo con Tierra, el de la cabecera y del tránsito de la ecografía. */}
          <Mark pictogram={uiPictogram("lightTime")}>
            {tr("Lo declarado a bordo hace menos de", "What was declared on board less than")}{" "}
            <span className="num">{formatMinutes(oneWayMinutes)}</span>{" "}
            {tr("está en tránsito y todavía no se ve aquí.", "ago is in transit and not yet visible here.")}
          </Mark>
        </p>
      )}
      {data !== null && unavailable !== null && (
        <p>
          <MarkOf mark={unavailable.mark}>
            {tr("No se pudo actualizar:", "Could not refresh:")} {unavailable.text}
          </MarkOf>
        </p>
      )}
      {data !== null && data.declared && data.missions.length > 0 && (
        <BoardOnly>
          <HistoryBoard
            missions={data.missions.length}
            doseSum={data.dose_sum_msv}
            withoutDose={data.missions_without_dose}
            stale={unavailable !== null}
          />
        </BoardOnly>
      )}
      <MissionHistoryContent data={data} unavailable={data === null ? unavailable : null} />
    </section>
  );
}

/**
 * Las cifras del historial que ya da el backend: misiones declaradas, la suma de las dosis
 * conocidas (`dose_sum_msv`) y, si hay alguna conocida, cuántas van sin dosis (`missions_without_dose`). Sin ninguna dosis
 * conocida la suma es `null` y la ficha lo dice con el cian del dato ausente, con las mismas palabras
 * que la fila de la tabla; con alguna dosis que falta, la suma es parcial y la ficha lo dice: no es
 * la dosis de toda la carrera.
 */
function HistoryBoard({
  missions,
  doseSum,
  withoutDose,
  stale,
}: {
  missions: number;
  doseSum: number | null;
  withoutDose: number;
  stale: boolean;
}) {
  return (
    <div className="board-stats history-board" role="group" aria-label={tr("Historial declarado, en cifras", "Declared history, in figures")}>
      <StatTile concept="previous" label={tr("Misiones previas", "Previous missions")} value={missions} stale={stale} />
      {doseSum === null ? (
        <StatTile concept="radiation" label={tr("Dosis sumada", "Summed dose")} value={null} status={{ mark: MISSING_MARK, word: tr("sin dosis declarada", "no declared dose") }} stale={stale} />
      ) : (
        <StatTile
          concept="radiation"
          label={tr("Dosis sumada", "Summed dose")}
          value={doseSum}
          decimals={2}
          unit="mSv"
          stale={stale}
          {...(withoutDose > 0 ? { status: { mark: MISSING_MARK, word: tr("parcial: faltan dosis", "partial: doses missing") } } : {})}
        />
      )}
      {/* Sin ninguna dosis conocida, la ficha de la dosis ya lo dice: no se repite. */}
      {doseSum !== null && <StatTile concept="previous" label={tr("Misiones sin dosis", "Missions without dose")} value={withoutDose} stale={stale} />}
    </div>
  );
}
