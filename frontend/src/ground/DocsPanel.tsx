import { useState } from "react";

import { BoardDetail } from "../components/BoardDetail";
import { Command } from "../components/Command";
import { Mark, MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { type KbResult, api, exportPdfUrl, painPdfUrl } from "../lib/api";
import { type StateMark, UNAVAILABLE_MARK, requestOutcome } from "../lib/marks";
import { uiPictogram } from "../lib/uiMarks";
import { tr } from "../lib/i18n";

/**
 * Exportar a PDF (Polaris `md_to_pdf_pro`) y buscar en la documentacion de EMMA (Polaris `kb`).
 * Los PDF del estado, de la cronica y del dolor son lo que Tierra tiene: hasta el corte del retardo. Los pasajes salen tal
 * cual, con su fichero y su seccion; aqui no se resume nada. Cada enlace a un PDF lleva la hoja
 * escrita junto a su rotulo, y el boton de buscar, la lupa.
 *
 * Desde la segunda pasada (§5.33.6) la nota de la búsqueda distingue sus dos causas: la búsqueda
 * no disponible (el backend lo dice con `available: false`) lleva la marca de «no disponible», y
 * la petición que falló, la de fallo; antes las dos salían con el anillo punteado en gris, que no
 * era ninguna de las dos. Sin pasajes, la lupa: buscado y no encontrado.
 */
export function DocsPanel({ subject, until }: { subject: string; until: Date | null }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<KbResult[] | null>(null);
  const [note, setNote] = useState<{ mark: StateMark; text: string } | null>(null);

  const search = () => {
    setNote(null);
    api
      .kb(query.trim())
      .then((body) => {
        setResults(body.results);
        if (!body.available) setNote({ mark: UNAVAILABLE_MARK, text: body.note ?? tr("búsqueda no disponible", "search unavailable") });
      })
      .catch((reason: unknown) =>
        setNote(requestOutcome(reason)),
      );
  };

  return (
    <section data-ui="docs" className="panel" aria-label={tr("Documentación y exportar", "Documentation and export")}>
      <PanelTitle concept="docs">{tr("Exportar y documentación", "Export and documentation")}</PanelTitle>
      <div className="measure-actions">
        <a className="command" href={exportPdfUrl("estado", subject, until)} download>
          <Mark pictogram="sheet-lines">{tr("Estado recibido (PDF)", "Received status (PDF)")}</Mark>
        </a>
        <a className="command" href={exportPdfUrl("cronica", subject, until)} download>
          <Mark pictogram="sheet-lines">{tr("Crónica (PDF)", "Chronicle (PDF)")}</Mark>
        </a>
        <a className="command" href={painPdfUrl(subject, until)} download>
          <Mark pictogram="sheet-lines">
            {tr("Anotaciones de dolor recibidas (PDF)", "Pain entries received (PDF)")}
          </Mark>
        </a>
        <a className="command" href={exportPdfUrl("dosier", subject, null)} download>
          <Mark pictogram="sheet-lines">{tr("Dosier de evidencia (PDF)", "Evidence dossier (PDF)")}</Mark>
        </a>
      </div>
      {/* Lote «muestra» (2026-11-08): los cuatro PDF, a la vista; el buscador y sus pasajes, tras
          «Ver detalle» en el tablero (la nota de una búsqueda no disponible va dentro, con ella). */}
      <BoardDetail label={tr("buscar en la documentación", "search the documentation")}>
      <form
        className="inline-form"
        onSubmit={(event) => {
          event.preventDefault();
          search();
        }}
      >
        <input
          aria-label={tr("Buscar en la documentación", "Search the documentation")}
          placeholder={tr(
            "¿por qué…? (p. ej. IEC 62304, modo seguro, falsa alarma)",
            "why…? (e.g. IEC 62304, safe mode, false alarm)",
          )}
          value={query}
          maxLength={200}
          size={48}
          onChange={(event) => setQuery(event.target.value)}
        />
        <Command concept="search" type="submit" disabled={query.trim().length < 2}>
          {tr("Buscar", "Search")}
        </Command>
      </form>
      {results !== null && results.length === 0 && note === null && (
        <p className="secondary">
          <Mark pictogram={uiPictogram("searchedNotFound")}>
            {tr("Sin pasajes para esa búsqueda.", "No passages for that search.")}
          </Mark>
        </p>
      )}
      {results !== null && results.length > 0 && (
        <ul className="evidence">
          {results.map((item) => (
            <li key={`${item.path}:${item.section}`}>
              <strong>{item.section}</strong> <span className="secondary">— {item.path}</span>
              <pre className="report-text">{item.text}</pre>
            </li>
          ))}
        </ul>
      )}
      </BoardDetail>
      {/* La marca de búsqueda no disponible o fallida, fuera del detalle: nunca se pliega. */}
      {note !== null && (
        <p>
          <MarkOf mark={note.mark}>{note.text}</MarkOf>
        </p>
      )}
    </section>
  );
}
