import { BoardDetail } from "../components/BoardDetail";
import { BoardOnly, useLook } from "../components/BoardOnly";
import { IndicatorName } from "../components/IndicatorName";
import { Fold } from "../components/Fold";
import { Mark } from "../components/Mark";
import { Meter } from "../components/Meter";
import { ObservationTypeBadge } from "../components/ObservationTypeBadge";
import { PanelTitle } from "../components/PanelTitle";
import { QualityBadge } from "../components/QualityBadge";
import { StatTile } from "../components/StatTile";
import { Th } from "../components/Th";
import type { DataQuality, IndicatorQuality } from "../lib/api";
import { displayUnit, formatNumber } from "../lib/format";
import { hasDoubtfulReadings, qualityStyle } from "../lib/provenance";
import { deviceBindingsView } from "./deviceBindings";
import { readingSourcePictogram } from "./readingSources";

/**
 * Cuanto se puede confiar en cada lectura (especificacion del equipo §2 y §10).
 *
 * El analisis ya descontaba las lecturas de baja confianza; lo que faltaba era
 * decirlo. F.6.2: el operador tiene que poder comprobar la informacion que usa la
 * automatizacion, y eso incluye saber que una lectura no cuenta como referencia.
 *
 * Consola de tripulacion, "poco y relevante": a la vista, solo los indicadores con
 * lecturas dudosas; el resto, plegado. Cada fila junta lo que se sabe del ultimo
 * dato: valor, tipo y entorno, confianza y fuente. Resumen, etiquetas y frases son
 * del backend (`data.quality`); aqui no se redacta. El indicador lleva el pictograma de su
 * familia (`IndicatorName`) y la fuente el de su canal (`readingSources.ts`), sin color.
 *
 * Tablero (decisión del usuario, 2026-11-07): bajo la concha de la maqueta (`BoardOnly`), las tres
 * cifras de lo reciente (`quality.recent`) van como fichas encima del resumen: las lecturas, las de
 * baja confianza y las que no declaran confianza, con las etiquetas del backend (`labels`) tal
 * cual. La señal de baja confianza (triángulo, amarillo) la lleva la frase del resumen, justo debajo:
 * en el rótulo de la ficha se sumaría al signo de la ficha (dos dibujos). Bajo la cifra, el medidor
 * de cuántas son sobre las lecturas recientes: la escala es la propia cuenta, no un umbral. Nada se pide de nuevo: la tabla de abajo ya sumaba
 * estas cifras por indicador.
 *
 * Una pantalla por sección (lote «muestra», 2026-11-08): en la concha de la maqueta, el aviso de
 * vínculos cuando no avisa de nada y el plegable con el resto de indicadores van juntos detrás de
 * «Ver detalle», al final. A la vista quedan las fichas, el resumen, la frase de las lecturas sin
 * confianza declarada (dice que se analizan como plenas: es una salvedad del dato), el aviso de
 * vínculos cuando lleva la señal de baja confianza y la tabla de los indicadores con lecturas
 * dudosas: eso no se pliega nunca. En la clásica, todo en su sitio de antes.
 */
export function QualityPanel({ quality }: { quality: DataQuality }) {
  const doubtful = quality.indicators.filter(hasDoubtfulReadings);
  const rest = quality.indicators.filter((item) => !hasDoubtfulReadings(item));
  const low = qualityStyle("low");
  const recent = quality.recent;
  const flagged = recent.low_confidence > 0;
  // Lecturas de un dispositivo que constaba vinculado a otro tripulante: un aviso sobre el
  // dato, con la senal de «baja confianza» y la frase del backend (`deviceBindings.ts`).
  const bound = deviceBindingsView(quality.device_bindings);
  const board = useLook() === "reference";
  const undeclared = quality.undeclared_note !== null && <p className="secondary">{quality.undeclared_note}</p>;
  const boundLine = bound !== null && (
    <p className={bound.style === null ? "secondary" : undefined}>
      {bound.style === null ? (
        bound.text
      ) : (
        <Mark pictogram={bound.style.pictogram} color={bound.style.color}>
          {bound.text}
        </Mark>
      )}
      {bound.note !== null && <span className="secondary"> {bound.note}</span>}
    </p>
  );
  // En el tablero, el aviso de vínculos solo se pliega si no avisa (sin señal).
  const boundFolds = board && bound !== null && bound.style === null;
  const restFold = rest.length > 0 && (
    <Fold data-ui="data-quality-by-indicator"
      concept="byIndicator"
      label={
        <>
          {doubtful.length > 0 ? "Resto de indicadores" : "Por indicador"} (
          <span className="num">{formatNumber(rest.length)}</span>)
        </>
      }
    >
      <QualityTable rows={rest} quality={quality} />
    </Fold>
  );
  return (
    <section data-ui="data-quality" className="panel" aria-label="Calidad del dato">
      <PanelTitle concept="dataQuality">Calidad del dato</PanelTitle>
      <BoardOnly>
        <div className="board-stats" role="group" aria-label={`Lecturas recientes (${quality.recent_label})`}>
          <StatTile concept="value" label={<>Lecturas ({quality.recent_label})</>} value={recent.readings} />
          <StatTile concept="confidence" label={quality.labels.low} value={recent.low_confidence}>
            {/* Sin lecturas recientes no hay escala; una cuenta mayor que el total no es una
                proporción y el medidor lanzaría: la cifra de arriba ya lo dice. */}
            {recent.readings > 0 && recent.low_confidence <= recent.readings && (
              <Meter value={recent.low_confidence} max={recent.readings} label={`${quality.labels.low} sobre las lecturas recientes`} />
            )}
          </StatTile>
          <StatTile concept="confidence" label={quality.labels.undeclared} value={recent.undeclared} />
        </div>
      </BoardOnly>
      <p>
        {flagged ? (
          <Mark pictogram={low.pictogram} color={low.color}>
            {quality.summary}
          </Mark>
        ) : (
          quality.summary
        )}
      </p>
      {undeclared}
      {!boundFolds && boundLine}
      {doubtful.length > 0 && <QualityTable rows={doubtful} quality={quality} />}
      {!board && restFold}
      {board && (boundFolds || restFold !== false) && (
        <BoardDetail label="calidad por indicador">
          {boundFolds && boundLine}
          {restFold}
        </BoardDetail>
      )}
    </section>
  );
}

function QualityTable({ rows, quality }: { rows: IndicatorQuality[]; quality: DataQuality }) {
  return (
    <div className="quality-table">
      <table className="ledger">
        <thead>
          <tr>
            <Th concept="indicator">Indicador</Th>
            <Th concept="time">Última lectura</Th>
            <Th concept="confidence">Confianza</Th>
            <Th concept="source">Fuente</Th>
            {/* Sin dibujo: es la confianza otra vez (baja), y el suyo ya va en «Confianza». Sin
                pictograma delante, `::first-letter` sigue poniendo la mayúscula a la etiqueta
                del backend, que viene en minúscula. */}
            <th scope="col">
              {quality.labels.low} ({quality.recent_label})
            </th>
            <Th concept="baseline">Línea base</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map((item) => (
            <QualityRow key={item.key} item={item} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function QualityRow({ item }: { item: IndicatorQuality }) {
  // De que fuentes salen las lecturas dudosas: es lo que dice que sensor mirar.
  const doubtfulSources = item.recent.sources.filter((source) => source.low_confidence > 0);
  return (
    <tr>
      <td>
        <IndicatorName indicatorKey={item.key} displayEs={item.display_es} />
      </td>
      <td>
        <span className="num">{formatNumber(item.latest.value, item.decimals)}</span>{" "}
        {displayUnit(item.unit)}{" "}
        <ObservationTypeBadge
          type={item.latest.observation_type}
          context={item.latest.evidence_context}
        />
      </td>
      <td>
        <QualityBadge
          state={item.latest.state}
          label={item.latest.label}
          confidence={item.latest.confidence}
        />
      </td>
      <td>
        <Mark pictogram={readingSourcePictogram(item.latest.source)}>{item.latest.source_label}</Mark>
      </td>
      <td>
        <span className="num">
          {formatNumber(item.recent.low_confidence)} de {formatNumber(item.recent.readings)}
        </span>
        {doubtfulSources.map((source) => (
          <span className="secondary" key={source.source}>
            {" "}
            · <Mark pictogram={readingSourcePictogram(source.source)}>{source.label}</Mark>{" "}
            <span className="num">{formatNumber(source.low_confidence)}</span>
          </span>
        ))}
      </td>
      <td className={item.baseline.discounted ? undefined : "secondary"}>{item.baseline.text}</td>
    </tr>
  );
}
