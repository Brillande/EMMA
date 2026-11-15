// SPDX-License-Identifier: AGPL-3.0-or-later
import { useEffect, useState } from "react";

import { Chosen } from "../components/Chosen";
import { FieldLabel } from "../components/FieldLabel";
import { Mark, MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { Th } from "../components/Th";
import { type PolarisStatus, polarisApi } from "../lib/api";
import { formatNumber } from "../lib/format";
import { LOADING_MARK, MISSING_MARK, OK_MARK, type RequestOutcome, requestOutcome } from "../lib/marks";
import { uiPictogram } from "../lib/uiMarks";
import {
  POLARIS_FILTERS,
  type PolarisFilter,
  changeDate,
  countByFilter,
  filterTools,
  loadStyle,
  shortCommit,
  useStyle,
} from "./polarisInventory";
import { tr } from "../lib/i18n";

/**
 * La copia de Polaris de esta instalacion, a la vista (AGPL §5a).
 *
 * EMMA lleva codigo de terceros copiado tal cual: Tierra tiene que poder ver de que commit, que
 * piezas importan en esta maquina, cuales llama EMMA y cuales solo viajan con la copia, y que se
 * cambio respecto del original. Todo viene de `GET /api/polaris/estado`, que lo lee de
 * `polaris/` (commit en `polaris/ADOPTADO.txt`): el estado, el motivo, la ficha y el porque de
 * cada cambio se muestran literales. Las que el backend no importa para hacer el inventario
 * salen con ese estado y su motivo, no como fallos de carga. Este fichero no contiene codigo de
 * Polaris.
 *
 * Es un inventario de software, no un estado clinico: que una herramienta cargue no dice que
 * EMMA la use, ni que nada de Polaris decida sobre la tripulacion. Lo que falta (commit, ficha,
 * prueba, ruta, motivo) lleva el anillo punteado en cian, dato ausente, junto a la palabra que ya
 * decia que falta; la celda de la prueba, que no tenia palabra, toma el «sin dato» del commit.
 *
 * El título lleva el enchufe (`plug`, el de «en uso por EMMA»): la copia es lo que EMMA enchufa.
 * Los filtros, como las ventanas de las tendencias, solo llevan el anillo con punto cuando están
 * elegidos (§5.33.6).
 */
export function PolarisPanel() {
  const [status, setStatus] = useState<PolarisStatus | null>(null);
  const [error, setError] = useState<RequestOutcome | null>(null);
  const [filter, setFilter] = useState<PolarisFilter>("all");
  const [text, setText] = useState("");

  useEffect(() => {
    let current = true;
    polarisApi
      .status()
      .then((body) => {
        if (current) setStatus(body);
      })
      .catch((reason: unknown) => {
        if (current) setError(requestOutcome(reason));
      });
    return () => {
      current = false;
    };
  }, []);

  if (status === null) {
    return (
      <section data-ui="polaris" className="panel" aria-label={tr("Copia de Polaris", "Polaris copy")}>
        <PanelTitle pictogram="plug">
          {tr("Código de terceros: copia de Polaris", "Third-party code: Polaris copy")}
        </PanelTitle>
        {error === null ? (
          <p className="secondary">
            <MarkOf mark={LOADING_MARK}>{tr("Consultando la copia…", "Querying the copy…")}</MarkOf>
          </p>
        ) : (
          <p>
            <MarkOf mark={error.mark}>
              {tr("Inventario no disponible:", "Inventory unavailable:")} {error.text}
            </MarkOf>
          </p>
        )}
      </section>
    );
  }

  const counts = countByFilter(status.herramientas);
  const shown = filterTools(status.herramientas, filter, text);
  const commit = shortCommit(status.commit);

  return (
    <section data-ui="polaris" className="panel" aria-label={tr("Copia de Polaris", "Polaris copy")}>
      <PanelTitle pictogram="plug">
          {tr("Código de terceros: copia de Polaris", "Third-party code: Polaris copy")}
        </PanelTitle>
      <p className="secondary mb-2">
        {tr(
          "Herramientas de Polaris (AGPL-3.0-or-later) copiadas tal cual. «Carga» dice que importa en esta máquina; solo las marcadas «en uso» las llama el código de EMMA.",
          "Polaris tools (AGPL-3.0-or-later) copied as is. “Loads” means it imports on this machine; only those marked “in use” are called by EMMA code.",
        )}
      </p>
      <dl className="kv">
        <FieldLabel as="dt" concept="state">
          {tr("Cargan", "Load")}
        </FieldLabel>
        <dd className="num">
          {formatNumber(status.cargan)} {tr("de", "of")} {formatNumber(status.total)}
        </dd>
        {/* Las que el inventario no importa a proposito: ni cargan ni fallan, y su motivo va en su fila. */}
        <FieldLabel as="dt" concept="state">
          {tr("No se importan", "Not imported")}
        </FieldLabel>
        <dd className="num">
          {formatNumber(status.no_se_importan.length)} {tr("de", "of")} {formatNumber(status.total)}
        </dd>
        <FieldLabel as="dt" pictogram="plug">
          {tr("En uso por EMMA", "In use by EMMA")}
        </FieldLabel>
        <dd className="num">
          {formatNumber(status.en_uso)} {tr("de", "of")} {formatNumber(status.total)}
        </dd>
        <FieldLabel as="dt" concept="value">
          {tr("Commit copiado", "Copied commit")}
        </FieldLabel>
        {commit === null ? (
          <dd>
            <Missing />
          </dd>
        ) : (
          <dd className="num" title={status.commit ?? undefined}>
            {commit}
          </dd>
        )}
        <FieldLabel as="dt" concept="provenance">
          {tr("Procedencia", "Provenance")}
        </FieldLabel>
        <dd>{status.origen}</dd>
      </dl>
      {status.faltan.length > 0 && (
        <p className="mt-2">
          <MarkOf mark={MISSING_MARK}>
            {tr("Falta o no se puede leer en esta instalación:", "Missing or unreadable in this installation:")}{" "}
            {status.faltan.join(", ")}
          </MarkOf>
        </p>
      )}

      <div className="measure-actions mt-3" role="group" aria-label={tr("Filtrar herramientas", "Filter tools")} data-ui-view="">
        {POLARIS_FILTERS.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            className="command"
            aria-pressed={filter === id}
            onClick={() => setFilter(id)}
          >
            {/* Como las ventanas de las tendencias: el filtro elegido lleva el anillo con punto
                de «elegido» (`ring-dot`), no solo el color del botón pulsado (F.5.10 e). */}
            <Chosen chosen={filter === id}>
              {label} <span className="num">({formatNumber(counts[id])})</span>
            </Chosen>
          </button>
        ))}
      </div>
      <div className="inline-form mt-2">
        <input
          aria-label={tr("Buscar herramienta por nombre", "Search tool by name")}
          placeholder={tr("nombre de la herramienta", "tool name")}
          value={text}
          maxLength={60}
          onChange={(event) => setText(event.target.value)}
        />
        <span className="secondary num" aria-live="polite">
          {formatNumber(shown.length)} {tr("de", "of")} {formatNumber(status.total)}
        </span>
      </div>

      <div className="quality-table polaris-table table-scroll" tabIndex={0} role="region" aria-label={tr("Herramientas copiadas", "Copied tools")}>
        <table className="ledger">
          <thead>
            <tr>
              <Th concept="systems">{tr("Herramienta", "Tool")}</Th>
              <Th concept="state">{tr("En esta máquina", "On this machine")}</Th>
              <Th pictogram="plug">EMMA</Th>
              <Th concept="about">{tr("Para qué sirve (ficha de su autora)", "What it is for (its author's note)")}</Th>
              <Th concept="document">{tr("Su prueba", "Its test")}</Th>
            </tr>
          </thead>
          <tbody>
            {shown.map((tool) => {
              const load = loadStyle(tool);
              const use = useStyle(tool);
              return (
                <tr key={tool.herramienta}>
                  <th scope="row" className="num">
                    {tool.herramienta}
                  </th>
                  <td>
                    <MarkOf mark={load}>{load.word}</MarkOf>
                    {tool.motivo !== null && <div className="secondary">{tool.motivo}</div>}
                  </td>
                  <td>
                    <MarkOf mark={use}>{use.word}</MarkOf>
                  </td>
                  <td>
                    {tool.ficha?.para ? (
                      tool.ficha.para
                    ) : (
                      <MarkOf mark={MISSING_MARK}>
                        {tr("sin ficha", "no note")}
                      </MarkOf>
                    )}
                  </td>
                  <td className="num">{tool.ficha?.test ? tool.ficha.test : <Missing />}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {shown.length === 0 && (
          <p className="secondary">
            <Mark pictogram={uiPictogram("searchedNotFound")}>
              {tr("Ninguna herramienta con ese filtro.", "No tool matches that filter.")}
            </Mark>
          </p>
        )}
      </div>

      <PanelTitle as="h3" concept="divergences" className="section-gap">
        {tr("Cambios decididos sobre la copia (AGPL §5a)", "Changes decided on the copy (AGPL §5a)")}
      </PanelTitle>
      {status.cambios.length === 0 ? (
        <p className="secondary">
          {status.faltan.includes("polaris/CAMBIOS.json") ? (
            <MarkOf mark={MISSING_MARK}>
              {tr(
                "Sin dato: el fichero de cambios falta o no se puede leer.",
                "No data: the changes file is missing or unreadable.",
              )}
            </MarkOf>
          ) : (
            <MarkOf mark={OK_MARK}>{tr("Ninguno: la copia es literal.", "None: the copy is verbatim.")}</MarkOf>
          )}
        </p>
      ) : (
        <ul className="evidence">
          {status.cambios.map((change, index) => (
            <li key={`${change.ruta ?? ""}:${index}`}>
              <strong className="num">
                {change.ruta ?? (
                  <MarkOf mark={MISSING_MARK}>
                    {tr("sin ruta", "no path")}
                  </MarkOf>
                )}
              </strong>{" "}
              <span className="secondary num">
                — {changeDate(change) ?? <MarkOf mark={MISSING_MARK}>{tr("sin fecha", "no date")}</MarkOf>} ·{" "}
                {formatNumber(change.reemplazos)}{" "}
                {change.reemplazos === 1 ? tr("reemplazo", "replacement") : tr("reemplazos", "replacements")}
              </span>
              <div>
                {change.motivo ?? (
                  <MarkOf mark={MISSING_MARK}>
                    {tr("sin motivo anotado", "no reason noted")}
                  </MarkOf>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Un dato que la copia no trae: anillo punteado en cian con la palabra que ya lo decía. */
function Missing() {
  return (
    <MarkOf mark={MISSING_MARK}>
      {tr("sin dato", "no data")}
    </MarkOf>
  );
}
