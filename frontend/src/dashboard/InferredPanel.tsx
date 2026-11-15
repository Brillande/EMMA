import { BoardDetail } from "../components/BoardDetail";
import { useLook } from "../components/BoardOnly";
import { Mark } from "../components/Mark";
import { ObservationTypeBadge } from "../components/ObservationTypeBadge";
import { PanelTitle } from "../components/PanelTitle";
import type { CrewStatus, ExerciseMeasured, InferredState } from "../lib/api";
import { formatNumber } from "../lib/format";
import { DensitometryBeside } from "./DensitometryBeside";
import { RangeBar } from "./HomeCharts";
import { bandPictogram, indicatorNotes, indicatorStyle, recordStyle, singleContext } from "./inferredExercise";

/**
 * Lo MEDIDO que acompaña a la banda (especificacion §9): minutos de ejercicio e impactos de carga
 * de la ultima semana de datos. Cada frase es del backend (`analysis/exercise_summary.py`),
 * tambien la que dice que esto no mueve la banda y la que explica por que no hay un porcentaje.
 * Aqui solo se pone el rotulo de tipo, el dibujo de la familia de cada indicador y la señal en
 * cian de lo que falta (`inferredExercise.ts`).
 */
function ExerciseBeside({ exercise }: { exercise: ExerciseMeasured }) {
  const record = recordStyle(exercise.record.state);
  if (useLook() === "reference") return <ExerciseBoard exercise={exercise} />;
  return (
    <>
      <p>
        <ObservationTypeBadge type={exercise.observation_type} context={singleContext(exercise)} /> {exercise.relation}
      </p>
      <ul className="drivers">
        {exercise.indicators.map((item) => {
          const style = indicatorStyle(item);
          return (
            <li key={item.key}>
              <Mark pictogram={style.pictogram} color={style.color}>
                {item.statement}
              </Mark>
              {indicatorNotes(item).map((note) => (
                <span key={note} className="secondary">
                  {" "}
                  {note}
                </span>
              ))}
            </li>
          );
        })}
      </ul>
      <p className="secondary">
        <Mark pictogram={record.pictogram} color={record.color}>
          {exercise.record.note}
        </Mark>{" "}
        {exercise.adherence_note} {exercise.window_basis}
      </p>
    </>
  );
}

/**
 * Lo medido en la concha de la maqueta (muestra, 2026-11-08: la banda ósea ocupaba media pantalla de
 * prosa). A la vista, el rótulo MEDIDO, la frase de cada indicador con su dibujo —o el anillo cian si
 * no tiene lecturas— y la del registro cuando falta o es de cero, con su marca: son el dato y lo que
 * falta de él. Tras «Ver detalle», las frases que lo explican (la del registro cuando lo hay, la relación con la banda, la base y la tendencia de cada
 * indicador, con su nombre delante —sin el dibujo de su familia: en uno sin lecturas, el
 * anillo cian ocupa ese sitio— para que no se separen de él, y la nota sobre el porcentaje y la
 * ventana). Las frases son las mismas, del backend; solo cambian de sitio.
 */
function ExerciseBoard({ exercise }: { exercise: ExerciseMeasured }) {
  const record = recordStyle(exercise.record.state);
  // Con registro, la frase del registro explica; sin él, o con un registro de cero, es el dato.
  const recorded = exercise.record.state === "recorded";
  const recordNote = (
    <p className="secondary">
      <Mark pictogram={record.pictogram} color={record.color}>
        {exercise.record.note}
      </Mark>
    </p>
  );
  return (
    <>
      <p>
        <ObservationTypeBadge type={exercise.observation_type} context={singleContext(exercise)} />
      </p>
      <ul className="drivers">
        {exercise.indicators.map((item) => {
          const style = indicatorStyle(item);
          return (
            <li key={item.key}>
              <Mark pictogram={style.pictogram} color={style.color}>
                {item.statement}
              </Mark>
            </li>
          );
        })}
      </ul>
      {!recorded && recordNote}
      <BoardDetail label="cómo se lee lo medido">
        {recorded && recordNote}
        <p className="secondary">{exercise.relation}</p>
        <ul className="drivers">
          {exercise.indicators.map((item) => (
            <li key={item.key}>
              <strong>{item.display_es}</strong>:
              {indicatorNotes(item).map((note) => (
                <span key={note} className="secondary">
                  {" "}
                  {note}
                </span>
              ))}
            </li>
          ))}
        </ul>
        <p className="secondary">
          {exercise.adherence_note} {exercise.window_basis}
        </p>
      </BoardDetail>
    </>
  );
}

/** «Si nada cambia»: cada paso de la trayectoria con su margen, en cifras. */
function Trajectory({ item }: { item: InferredState }) {
  if (item.trajectory.length === 0) return null;
  return (
    <p className="secondary">
      Si nada cambia:{" "}
      {item.trajectory.map((step, index) => (
        <span key={step.mission_day}>
          {index > 0 ? " · " : ""}día <span className="num">{formatNumber(step.mission_day)}</span>,{" "}
          <span className="num">{formatNumber(step.loss_pct_low, 1)}</span>–
          <span className="num">{formatNumber(step.loss_pct_high, 1)}</span> %
        </span>
      ))}
    </p>
  );
}

/**
 * La banda de ahora y cada paso de la trayectoria como tramos sobre una misma escala (tablero,
 * 2026-11-07): de cero al techo de la propia trayectoria (la mayor `loss_pct_high`, la de ahora
 * incluida), que es la única escala que el dato trae. Tramos y no barras de proporción: la banda es
 * una estimación con margen, nunca un valor, y una barra llena hasta su techo se leería como una
 * medida. Las cifras siguen escritas en las frases de arriba; cada tramo dice las suyas en su
 * rótulo, y el día va escrito al lado. Con una trayectoria sin techo (todo cero), con un tramo al
 * revés o con uno que se salga de la escala (una pérdida negativa: `RangeBar` lo recortaría a cero
 * en silencio, lo señaló la revisión) no se dibuja nada: las frases ya lo dicen.
 */
function BandLadder({ ladder }: { ladder: Ladder }) {
  const { rungs, ceiling } = ladder;
  return (
    <ul className="inferred-ladder">
      {rungs.map((rung) => (
        <li key={rung.day}>
          <span className="secondary">
            día <span className="num">{formatNumber(rung.day)}</span>
          </span>
          <RangeBar
            low={rung.low}
            high={rung.high}
            min={0}
            max={ceiling}
            label={`día ${formatNumber(rung.day)}: entre ${formatNumber(rung.low, 1)} y ${formatNumber(rung.high, 1)} %`}
          />
        </li>
      ))}
    </ul>
  );
}

interface Ladder {
  readonly rungs: readonly { day: number; low: number; high: number }[];
  readonly ceiling: number;
}

/** Los tramos de la escalera y su techo, o `null` si no se puede dibujar (ver `BandLadder`). */
function ladderOf(item: InferredState): Ladder | null {
  const rungs = [item.now, ...item.trajectory].map((step) => ({
    day: step.mission_day,
    low: step.loss_pct_low,
    high: step.loss_pct_high,
  }));
  const ceiling = Math.max(...rungs.map((rung) => rung.high));
  const drawable =
    Number.isFinite(ceiling) &&
    ceiling > 0 &&
    rungs.every((rung) => Number.isFinite(rung.low) && rung.low >= 0 && rung.low <= rung.high);
  return drawable ? { rungs, ceiling } : null;
}

/**
 * Estados inferidos (especificacion §9, escenario musculoesqueletico): una banda estimada, nunca
 * una medida. Se muestra como rango y con su base, que redacta el backend; el nombre de la banda
 * lleva el dibujo de lo que estima (`bandPictogram`), sin color. En posvuelo la banda llega
 * cortada en el día de regreso (`cut`): el rótulo del corte y la frase de la recuperación, con su
 * fuente, son del backend; aquí solo se pinta la cifra del día con su formato. Si el tripulante
 * tiene densitometría (DXA), va al lado, MEDIDA, con su comparación con la banda
 * (`DensitometryBeside`). En la concha de la maqueta, bajo las frases de la banda va la escalera de
 * tramos (`BandLadder`).
 */
export function InferredPanel({ inferred }: { inferred: CrewStatus["inferred"] }) {
  const board = useLook() === "reference";
  if (inferred.length === 0) return null;
  return (
    <section data-ui="inferred" className="panel" aria-label="Estados inferidos">
      <PanelTitle concept="inferred">
        Estados inferidos <ObservationTypeBadge type="inferred" />
      </PanelTitle>
      {inferred.map((item) => {
        // La escalera solo se ve en la concha de la maqueta y si se puede dibujar; la frase de la
        // trayectoria solo se pliega cuando la escalera dice lo mismo a la vista.
        const ladder = board ? ladderOf(item) : null;
        const band = (
          <>
            <p>
              <strong>
                <Mark pictogram={bandPictogram(item.key)}>{item.display}</Mark>
              </strong>
              : entre <span className="num">{formatNumber(item.now.loss_pct_low, 1)}</span> y{" "}
              <span className="num">{formatNumber(item.now.loss_pct_high, 1)}</span> %{" "}
              {item.cut === undefined ? (
                <>
                  a día <span className="num">{formatNumber(item.now.mission_day)}</span>
                </>
              ) : (
                <>
                  {item.cut.label}, <span className="num">{formatNumber(item.now.mission_day)}</span>
                </>
              )}
            </p>
            {ladder === null && <Trajectory item={item} />}
            {ladder !== null && <BandLadder ladder={ladder} />}
            {/* La trayectoria escrita (si la escalera ya la dice a la vista), la base de la banda, su
              fuente y, en posvuelo, la de la recuperación: lectura, tras «Ver detalle» en la concha de
              la maqueta (muestra, 2026-11-08). El rótulo del corte sigue arriba, junto a la cifra. En
              la clásica salen en el orden de siempre: allí no hay escalera y `BoardDetail` pinta lo
              suyo tal cual. */}
            <BoardDetail label={ladder !== null ? "trayectoria, base y fuentes" : "base y fuentes"}>
              {ladder !== null && <Trajectory item={item} />}
              <p className="secondary">
                {item.basis}.{" "}
                <a href={item.source.url} target="_blank" rel="noreferrer">
                  {item.source.source}: {item.source.title}
                </a>
              </p>
              {item.cut !== undefined && (
                <p className="secondary">
                  {item.cut.basis}. {item.cut.recovery}{" "}
                  <a href={item.cut.recovery_source.url} target="_blank" rel="noreferrer">
                    {item.cut.recovery_source.source}: {item.cut.recovery_source.title}
                  </a>
                </p>
              )}
            </BoardDetail>
          </>
        );
        const beside = (
          <>
            {/* Sin bloque medido, la frase que dice que falta el ejercicio sigue a la vista: es la
              marca de un dato ausente (lo señaló la revisión). */}
            {item.exercise === undefined ? (
              <p className="secondary">{item.exercise_note}</p>
            ) : (
              <ExerciseBeside exercise={item.exercise} />
            )}
            {item.densitometry !== undefined && <DensitometryBeside check={item.densitometry} />}
          </>
        );
        // En la concha de la maqueta, la banda (con su escalera) y lo medido a su lado van en dos
        // bloques, que la hoja de «Cuerpo» pone en dos columnas cuando el panel da (R5-7): uno
        // debajo del otro dejaban la banda en más de media pantalla.
        return board ? (
          <div key={item.key} className="inferred-item">
            <div className="inferred-band">{band}</div>
            <div className="inferred-beside">{beside}</div>
          </div>
        ) : (
          <div key={item.key}>
            {band}
            {beside}
          </div>
        );
      })}
    </section>
  );
}
