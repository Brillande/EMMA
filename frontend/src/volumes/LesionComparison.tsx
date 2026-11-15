import { useState } from "react";

import { Command } from "../components/Command";
import { Mark, MarkOf } from "../components/Mark";
import { Th } from "../components/Th";
import { type LesionComparison as Comparison, api } from "../lib/api";
import { displayUnit, formatNumber } from "../lib/format";
import {
  type DensitySides,
  type HuDensity,
  densityCell,
  densityNotes,
  densityOf,
  densitySides,
  densityUnit,
} from "./comparison";
import { MISSING_MARK, type RequestOutcome, requestOutcome } from "../lib/marks";
import { type PhaseComparisonShown, type PhaseSide, comparisonPhase } from "./contrastPhase";
import { ATTENTION_MARK, PHASE_TONE_MARK, UNAVAILABLE_MARK, phaseMark } from "./marks";

/**
 * Lesiones candidatas de dos estudios, emparejadas, con lo que cambio cada una.
 *
 * Por que existe: el backend ya emparejaba las lesiones de dos segmentaciones, pero nadie lo
 * pedia, y dos tablas sueltas obligan a quien mira a buscar a ojo cual es cual y a restar.
 *
 * Lo que este componente NO hace: redactar. El estado de cada lesion, el criterio con sus
 * umbrales, el rotulo de "sin validar" y el aviso de pacientes distintos llegan escritos del
 * backend (los de estado son los de `visor3d.evolucion` de Polaris) y se muestran tal cual. Aqui
 * solo hay nombres de columna, cifras por `lib/format` y colores con su significado de F.5-1,
 * cada uno con su pictograma (`marks.ts`): amarillo para lo que pide atencion (sin validar,
 * aviso) y cian para el dato que falta (la medida previa de una lesion no vista antes). El
 * estado va sin color: una segmentacion no es una alerta.
 *
 * Densidad (HU): las dos cifras de cada lesion, una junto a otra, y NINGUNA columna de cambio. No
 * es un olvido: la fase de contraste de cada estudio puede no ser la misma, y una resta invitaria
 * a leer como evolucion lo que puede ser solo el contraste. Tampoco se colorea por valor ni se le
 * pone nombre a la lesion: el backend la da como descripcion y aqui se ensena como tal. Gris para
 * la lesion con pocos voxeles ("no disponible", con la palabra del backend), cian si no hay dato.
 *
 * Fase de contraste: la que una persona declaro de cada estudio, con el dibujo de esa fase junto
 * a su nombre, y lo que el backend dice de las dos (la misma, distintas o falta alguna), con su
 * texto. Sigue sin haber columna de cambio aunque las dos fases coincidan, y el estado de cada
 * lesion no la lee.
 *
 * Segunda pasada (§5.33.9): cada cabecera lleva el signo de lo que cuenta. Del vocabulario
 * (`lib/uiMarks.ts`): la lesion previa, «lo anterior»; diametro y volumen, «medida»; los cambios
 * en %, «cambio»; la region, «zona»; el estado, «estado». Lo que no tiene concepto lleva su dibujo
 * de `icons/sets/volumes.ts`: la lesion, la mancha; la densidad, el cuadrado rayado; la distancia
 * del emparejado, los dos puntos unidos a trazos.
 */
export function LesionComparison({ before, after }: { before: number; after: number }) {
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<RequestOutcome | null>(null);

  const compare = async () => {
    setBusy(true);
    setError(null);
    try {
      setComparison(await api.volumes.compare(before, after));
    } catch (reason) {
      setError(requestOutcome(reason));
    } finally {
      setBusy(false);
    }
  };

  const density = comparison === null ? null : densitySides(comparison);
  const unit = density === null ? null : densityUnit(density);
  const hu = unit === null ? "" : ` (${displayUnit(unit)})`;
  const notAssessable = (density?.despues ?? density?.antes)?.no_valorable ?? "";
  const phase = comparison === null ? null : comparisonPhase(comparison);

  return (
    <div className="lesion-comparison">
      <div className="measure-actions">
        <Command concept="compare" disabled={busy} onClick={() => void compare()}>
          {busy ? "Comparando…" : "Comparar con el estudio anterior"}
        </Command>
      </div>
      {error !== null && (
        <p>
          <MarkOf mark={error.mark}>{error.text}</MarkOf>
        </p>
      )}
      {comparison !== null && (
        <>
          <p>
            <MarkOf mark={ATTENTION_MARK}>
              {comparison.estado}
              {comparison.segmentador === null ? "" : ` (${comparison.segmentador})`}
            </MarkOf>
          </p>
          {comparison.aviso !== null && (
            <p>
              <MarkOf mark={ATTENTION_MARK}>{comparison.aviso}</MarkOf>
            </p>
          )}
          <p className="secondary">{comparison.criterio}</p>
          {phase !== null && <PhaseComparison phase={phase} />}
          <div className="quality-table">
          <table className="ledger" aria-label="Lesiones candidatas: estudio anterior y posterior">
            <thead>
              <tr>
                <Th pictogram="blob">Lesión</Th>
                <Th concept="previous">Lesión previa</Th>
                <Th concept="measure">Diámetro antes (mm)</Th>
                <Th concept="measure">Diámetro después (mm)</Th>
                <Th concept="change">Cambio de diámetro (%)</Th>
                <Th concept="measure">Volumen antes (ml)</Th>
                <Th concept="measure">Volumen después (ml)</Th>
                <Th concept="change">Cambio de volumen (%)</Th>
                <Th pictogram="dots-dashed-line">Distancia del emparejado (mm)</Th>
                {density !== null && <Th pictogram="square-hatched">Densidad antes{hu}: mediana (p10 a p90)</Th>}
                {density !== null && <Th pictogram="square-hatched">Densidad después{hu}: mediana (p10 a p90)</Th>}
                <Th concept="state">Estado</Th>
              </tr>
            </thead>
            <tbody>
              {comparison.lesiones.map((lesion) => (
                <tr key={lesion.id}>
                  <th scope="row">L{lesion.id}</th>
                  <td>{lesion.previa === null ? <Missing /> : `L${lesion.previa.id}`}</td>
                  <td><Figure value={lesion.previa?.diametro_mm} decimals={1} /></td>
                  <td className="num">{formatNumber(lesion.diametro_mm, 1)}</td>
                  <td><Figure value={lesion.evolucion.delta_diametro_pct} decimals={1} /></td>
                  <td><Figure value={lesion.previa?.volumen_ml} decimals={2} /></td>
                  <td className="num">{formatNumber(lesion.volumen_ml, 2)}</td>
                  <td><Figure value={lesion.evolucion.delta_volumen_pct} decimals={1} /></td>
                  <td><Figure value={lesion.evolucion.distancia_emparejado_mm} decimals={1} /></td>
                  {density !== null && (
                    <td><Density density={densityOf(lesion.previa)} word={notAssessable} /></td>
                  )}
                  {density !== null && (
                    <td><Density density={densityOf(lesion)} word={notAssessable} /></td>
                  )}
                  <td>{lesion.evolucion.estado}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
          {comparison.no_reencontradas.length > 0 && (
            <div className="quality-table">
            <table className="ledger" aria-label="Lesiones del estudio anterior sin pareja en el posterior">
              <thead>
                <tr>
                  <Th concept="previous">Lesión previa sin pareja en el estudio posterior</Th>
                  <Th concept="zone">Región</Th>
                  <Th concept="measure">Diámetro antes (mm)</Th>
                  <Th concept="measure">Volumen antes (ml)</Th>
                  {density !== null && <Th pictogram="square-hatched">Densidad antes{hu}: mediana (p10 a p90)</Th>}
                </tr>
              </thead>
              <tbody>
                {comparison.no_reencontradas.map((lesion) => (
                  <tr key={lesion.id_previo}>
                    <th scope="row">L{lesion.id_previo}</th>
                    <td className="num">{lesion.region === null ? <Missing /> : lesion.region}</td>
                    <td className="num">{formatNumber(lesion.diametro_mm, 1)}</td>
                    <td className="num">{formatNumber(lesion.volumen_ml, 2)}</td>
                    {density !== null && (
                      <td><Density density={densityOf(lesion)} word={notAssessable} /></td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          )}
          {density !== null && <DensityFootnotes sides={density} hu={hu} word={notAssessable} />}
        </>
      )}
    </div>
  );
}

/**
 * La densidad de una lesion: mediana y percentiles 10 y 90 por `lib/format`. Con menos voxeles que
 * el minimo no hay cifra: la palabra del backend, en gris con el circulo tachado de «no
 * disponible», y cuantos voxeles eran (el motivo entero, tambien suyo, queda al pasar el cursor).
 */
function Density({ density, word }: { density: HuDensity | null; word: string }) {
  const cell = densityCell(density);
  if (cell.kind === "ausente") return <Missing />;
  if (cell.kind === "no-valorable") {
    return (
      <MarkOf mark={UNAVAILABLE_MARK} title={cell.motivo ?? undefined}>
        {word} · {formatNumber(cell.voxeles)} vóxeles
      </MarkOf>
    );
  }
  return (
    <span className="num">
      {formatNumber(cell.mediana, 1)} ({formatNumber(cell.p10, 1)} a {formatNumber(cell.p90, 1)})
    </span>
  );
}

/**
 * Lo que acompana a las cifras: la referencia de cada estudio (el organo fuera de las lesiones
 * candidatas; su nombre lo da el backend), el minimo de voxeles y las notas del backend tal cual.
 */
function DensityFootnotes({ sides, hu, word }: { sides: DensitySides; hu: string; word: string }) {
  const references = [
    { label: "Referencia antes", block: sides.antes },
    { label: "Referencia después", block: sides.despues },
  ];
  const minimum = (sides.despues ?? sides.antes)?.minimo_voxeles;
  return (
    <div className="density-notes">
      {references.map(({ label, block }) =>
        block === null || block.referencia === null ? null : (
          <p className="secondary" key={label}>
            {label}{hu}: {block.referencia.nombre} · <Density density={block.referencia} word={word} />
            {" · "}{formatNumber(block.referencia.voxeles)} vóxeles
          </p>
        ),
      )}
      {minimum !== undefined && (
        <p className="secondary">Mínimo de vóxeles para dar cifra: {formatNumber(minimum)}</p>
      )}
      {densityNotes(sides).map((note) => (
        <p key={note}>
          <MarkOf mark={ATTENTION_MARK}>{note}</MarkOf>
        </p>
      ))}
    </div>
  );
}

/**
 * Las fases de contraste de los dos estudios y lo que el backend dice de ellas (`PHASE_TONE_MARK`):
 * amarillo si pide atencion (distintas, o falta alguna), gris si no aplica, sin color y con el
 * signo igual si constan y coinciden: que coincidan no es un visto bueno. La que falta va en cian,
 * con la palabra del backend; la declarada, con el dibujo de su fase.
 */
function PhaseComparison({ phase }: { phase: PhaseComparisonShown }) {
  const tone = PHASE_TONE_MARK[phase.tone];
  return (
    <div role="note" aria-label="Fase de contraste de los dos estudios">
      {phase.tone !== "no-aplica" && (
        <p className="secondary">
          Fase de contraste antes: <Phase side={phase.antes} /> · después: <Phase side={phase.despues} />
        </p>
      )}
      <p className={tone.color === null ? "secondary" : undefined}>
        <MarkOf mark={tone}>{phase.texto}</MarkOf>
      </p>
    </div>
  );
}

function Phase({ side }: { side: PhaseSide }) {
  return side.kind === "sin-declarar" ? (
    <MarkOf mark={MISSING_MARK}>{side.display}</MarkOf>
  ) : (
    <span>
      <Mark pictogram={phaseMark(side.code).pictogram}>{side.display}</Mark> (declarada por {side.declaredBy})
    </span>
  );
}

/** Una cifra por `lib/format`, o la marca de dato ausente si el backend no la da. */
function Figure({ value, decimals }: { value: number | null | undefined; decimals: number }) {
  return value === null || value === undefined ? <Missing /> : <span className="num">{formatNumber(value, decimals)}</span>;
}

/**
 * F.5-1: el cian es "dato ausente". Una lesion no vista antes no tiene medida previa. El
 * pictograma no va solo (§5.32 a): lo acompana la raya que estas tablas ya usan para la celda
 * sin dato.
 */
function Missing() {
  return <MarkOf mark={MISSING_MARK}>—</MarkOf>;
}
