import { BoardDetail } from "../components/BoardDetail";
import { FieldLabel } from "../components/FieldLabel";
import { Fold } from "../components/Fold";
import { BoardOnly } from "../components/BoardOnly";
import { Mark, MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import type { Credibility, CredibilityCriticality, CredibilityLayer } from "../lib/api";
import { formatNumber, formatSourceDate } from "../lib/format";
import { tr } from "../lib/i18n";
import { factorGroups, layerSign } from "./credibility";
import { extentStyle } from "./framework";

/**
 * La credibilidad de cada cifra que EMMA rotula INFERIDA o PREDICHA, por los factores de
 * NASA-STD-7009B (decimosexta ronda, E10).
 *
 * Va en el panel del marco de NASA, detrás del IMM: allí está la frase del IMM sobre ponderar sus
 * resultados por su credibilidad, y esto es lo mismo dicho de las capas de EMMA. Todo el texto es
 * del backend (`app/evidence/credibility.py`): la frase de la norma, la pregunta de cada factor y
 * lo que hay en cada uno para cada capa. Aquí no hay nivel, color de nivel ni puntuación —la norma
 * puntúa con tablas que EMMA no ha aplicado, y la ficha lo dice—; solo se agrupa y se pliega. Cada
 * capa se pliega con el pictograma de su tipo, el que lleva la cifra donde se enseña
 * (`ObservationTypeBadge`), y la palabra que da el backend.
 */
export function CredibilityView({ credibility }: { credibility: Credibility }) {
  return (
    <article className="section-gap" aria-label={credibility.title}>
      <PanelTitle as="h3" concept="provenance">
        {credibility.title}
      </PanelTitle>
      {/* Lote «muestra», segunda ronda (2026-11-08): la baldosa medía más de 1 000 px (lo leído de la
          norma, los factores, el Apéndice D y ocho capas, una fila cada una). En el tablero, cuántas
          capas hay de cada tipo, con el dibujo y la palabra de su tipo; todo lo demás, plegables con
          `data-ui` incluidos (el asistente abre el detalle para llegar a ellos), tras un solo «Ver
          detalle». Aquí no hay nivel ni estado que se esconda: la norma no se ha puntuado. */}
      <BoardOnly>
        <LayerTally layers={credibility.layers} />
      </BoardOnly>
      <BoardDetail label={tr(`lo leído de la norma y ${formatNumber(credibility.layers.length)} ${credibility.layers.length === 1 ? "capa" : "capas"}`, `what was read of the standard and ${formatNumber(credibility.layers.length)} ${credibility.layers.length === 1 ? "layer" : "layers"}`)}>
      <p>{credibility.about}</p>
      <p className="secondary">{credibility.note}</p>
      <ul className="evidence" aria-label={tr("Documentos leídos y cuánto de cada uno", "Documents read and how much of each")}>
        {credibility.sources.map((source) => (
          <li key={source.ref}>
            <span lang="en">{source.title}</span> —{" "}
            <MarkOf mark={extentStyle(source.extent)}>{source.extent_text}</MarkOf> ·{" "}
            <span className="num">{formatSourceDate(source.read_on)}</span>
            <div className="secondary">{source.what}</div>
            {source.url !== null && <div className="secondary num url">{source.url}</div>}
          </li>
        ))}
      </ul>
      <ul className="evidence" aria-label={tr("Lo que dice la norma", "What the standard says")}>
        {credibility.statements.map((item) => (
          <li key={item.id}>
            <strong>{item.label}</strong>
            <div>
              <q lang="en">{item.quote}</q>
            </div>
            <div className="secondary">
              <span lang="en">{item.source}</span> · {item.where}
            </div>
          </li>
        ))}
      </ul>
      <dl className="kv">
        <FieldLabel as="dt" concept="decline">
          {tr("Sin evaluar", "Not assessed")}
        </FieldLabel>
        <dd>{credibility.not_assessed}</dd>
        <FieldLabel as="dt" concept="systems">
          EMMA
        </FieldLabel>
        <dd>{credibility.emma}</dd>
      </dl>

      <Fold data-ui="credibility-factors" concept="sourceText" label={tr("Los once factores de la norma", "The eleven factors of the standard")}>
        {credibility.groups.map((group) => (
          <div key={group.id} className="mt-2">
            <p>
              <strong>{group.name_es}</strong> · <span lang="en">{group.name}</span> ·{" "}
              <span className="num">{group.requirement}</span>, {group.where}
            </p>
            <p className="secondary">
              <q lang="en">{group.quote}</q>
            </p>
            <ul className="evidence">
              {group.factors.map((factor) => (
                <li key={factor.id}>
                  <strong>{factor.name_es}</strong>
                  <div>
                    <q lang="en">{factor.question}</q>
                  </div>
                  <div className="secondary">{factor.where}</div>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </Fold>

      {credibility.criticality !== undefined && (
        <CriticalityRead criticality={credibility.criticality} />
      )}

      {credibility.layers.map((layer) => (
        <LayerCard key={layer.id} credibility={credibility} layer={layer} />
      ))}

      <dl className="kv">
        <FieldLabel as="dt" concept="decline">
          {tr("Fuera de estas fichas", "Outside these records")}
        </FieldLabel>
        <dd>
          <ul className="evidence mt-0">
            {/* Por posición: dos líneas iguales del backend no chocan como clave. */}
            {credibility.out_of_scope.map((line, index) => (
              <li key={index}>{line}</li>
            ))}
          </ul>
        </dd>
        <FieldLabel as="dt" concept="withoutReading">
          {tr("No leído o no encontrado", "Not read or not found")}
        </FieldLabel>
        <dd>
          <ul className="evidence mt-0">
            {credibility.not_read.map((line, index) => (
              <li key={index}>{line}</li>
            ))}
          </ul>
        </dd>
      </dl>
      </BoardDetail>
    </article>
  );
}

/** Cuántas capas hay de cada tipo (INFERIDA, PREDICHA…), con su dibujo y la palabra del backend. */
function LayerTally({ layers }: { layers: CredibilityLayer[] }) {
  const kinds = new Map<string, { sign: ReturnType<typeof layerSign>; count: number }>();
  for (const layer of layers) {
    const entry = kinds.get(layer.observation_type);
    if (entry === undefined) kinds.set(layer.observation_type, { sign: layerSign(layer), count: 1 });
    else entry.count += 1;
  }
  if (kinds.size === 0) return null;
  return (
    <ul className="board-tally" aria-label={tr("Capas por tipo", "Layers by type")}>
      {[...kinds].map(([kind, { sign, count }]) => (
        <li key={kind} className="ref-pill board-pill">
          <span>
            <Mark pictogram={sign.pictogram}>{sign.word}</Mark> <span className="num">{formatNumber(count)}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

/**
 * Lo leído del Apéndice D, la criticidad del uso (decimoctava ronda, U14): su día de lectura, las
 * frases de la norma y que la matriz no se ha aplicado, a la vista; los dos ejes, plegados. Sin
 * casilla ni color de la matriz: el texto es del backend, que ya rechaza una categoría escrita.
 */
function CriticalityRead({ criticality }: { criticality: CredibilityCriticality }) {
  return (
    <div className="section-gap">
      <PanelTitle as="h4" concept="provenance">
        {criticality.title}
      </PanelTitle>
      <p>{criticality.about}</p>
      <p className="secondary">
        {tr("Leído el", "Read on")} <span className="num">{formatSourceDate(criticality.read_on)}</span>.
      </p>
      <ul className="evidence" aria-label={tr("Lo que dice el Apéndice D", "What Appendix D says")}>
        {criticality.statements.map((item) => (
          <li key={item.id}>
            <strong>{item.label}</strong>
            <div>
              <q lang="en">{item.quote}</q>
            </div>
            <div className="secondary">
              <span lang="en">{item.source}</span> · {item.where}
            </div>
          </li>
        ))}
      </ul>
      <dl className="kv">
        <FieldLabel as="dt" concept="decline">
          {tr("Sin aplicar", "Not applied")}
        </FieldLabel>
        <dd>{criticality.not_applied}</dd>
      </dl>
      <Fold data-ui="criticality-axes" concept="sourceText" label={tr("Los dos ejes de la matriz", "The two axes of the matrix")}>
        <ul className="evidence">
          {criticality.axes.map((axis) => (
            <li key={axis.id}>
              <strong>{axis.name_es}</strong> · <span lang="en">{axis.name}</span>
              <div>
                <q lang="en">{axis.quote}</q>
              </div>
              <div className="secondary">{axis.where}</div>
            </li>
          ))}
        </ul>
      </Fold>
    </div>
  );
}

/** Una capa: su modelo, dónde se rotula, dónde se sirve, qué la prueba y cada factor en palabras. */
function LayerCard({ credibility, layer }: { credibility: Credibility; layer: CredibilityLayer }) {
  const sign = layerSign(layer);
  const axes = layer.criticality ?? [];
  return (
    <Fold data-ui="credibility-layer"
      pictogram={sign.pictogram}
      aria-label={layer.display}
      label={
        <>
          {layer.display} ·{" "}
          <span className="obs-type" title={sign.meaning ?? undefined}>
            {sign.word}
          </span>
        </>
      }
    >
      <dl className="kv">
        <FieldLabel as="dt" concept="type">
          {tr("Modelo", "Model")}
        </FieldLabel>
        <dd>
          {layer.model_version !== null ? (
            <span className="num">{layer.model_version}</span>
          ) : (
            layer.model_note
          )}
        </dd>
        <FieldLabel as="dt" concept="source">
          {tr("Dónde se rotula y se sirve", "Where it is labeled and served")}
        </FieldLabel>
        {/* Rutas y nombres de prueba largos, sin espacios: monoespaciados como una dirección
            web y, como ella (`.num.url`), se parten antes que ensanchar el panel. */}
        <dd>
          <div className="num url">{layer.sites.join(" · ")}</div>
          <div className="secondary num url">{layer.served_in.join(" · ")}</div>
        </dd>
        <FieldLabel as="dt" concept="evidence">
          {tr("Pruebas", "Tests")}
        </FieldLabel>
        <dd>
          <ul className="evidence mt-0">
            {layer.tests.map((test) => (
              <li key={test} className="secondary num url">
                {test}
              </li>
            ))}
          </ul>
        </dd>
      </dl>
      {factorGroups(credibility, layer).map((group) => (
        <div key={group.id}>
          <p>
            <strong>{group.name ?? group.id}</strong>
          </p>
          <dl className="kv">
            {group.rows.map((row) => (
              <FactorRow key={row.id} name={row.name_es} state={row.state} />
            ))}
          </dl>
        </div>
      ))}
      {/* Los dos ejes de criticidad, como un grupo más, con el título de lo leído del apéndice.
          Un backend anterior no los manda: entonces el grupo no se pinta y el panel sigue. */}
      {credibility.criticality !== undefined && axes.length > 0 && (
        <div>
          <p>
            <strong>{credibility.criticality.title}</strong>
          </p>
          <dl className="kv">
            {axes.map((row) => (
              <FactorRow key={row.axis} name={row.name_es} state={row.state} />
            ))}
          </dl>
        </div>
      )}
    </Fold>
  );
}

function FactorRow({ name, state }: { name: string; state: string }) {
  return (
    <>
      <dt>{name}</dt>
      <dd>{state}</dd>
    </>
  );
}
