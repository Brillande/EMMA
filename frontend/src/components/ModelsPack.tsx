import { useCallback, useEffect, useState } from "react";

import { withConsoleHeader } from "../lib/api";
import { formatNumber } from "../lib/format";
import { tr } from "../lib/i18n";
import { FAILURE_MARK, OK_MARK, UNAVAILABLE_MARK } from "../lib/marks";
import { Fold } from "./Fold";
import { MarkOf } from "./Mark";

/**
 * «Modelos de IA»: lo que hay instalado del paquete de modelos y el botón para bajarlo, todo
 * junto o pieza a pieza (decisión del usuario, 2026-11-15; backend en `app/models_download.py`).
 *
 * Texto de producto, no clínico. Los nombres de las piezas, los fallos y las notas los compone el
 * backend en el idioma de la petición; aquí solo los rótulos de los mandos. Mientras baja, se
 * pregunta el estado cada dos segundos; parado, no se pregunta nada. Consultar lo publicado es
 * una orden (sale a internet por la puerta del backend), nunca algo que pase al abrir el plegable.
 *
 * Al montar se lee el estado local una vez (no sale a la red): si la descarga ya va, porque se
 * marcó en el instalador (`desktop/build/installer.nsh`), el plegable se abre solo para que se vea.
 */

interface Piece {
  name: string;
  label: string;
  installed: boolean;
  current: boolean;
  published: boolean;
  download_bytes: number | null;
  installed_bytes: number | null;
}

interface Job {
  state: "idle" | "running" | "done" | "error" | "cancelled";
  phase?: "index" | "download" | "install" | null;
  component_label?: string;
  done_bytes?: number;
  total_bytes?: number;
  message?: string;
}

interface PackState {
  folder: string;
  network: boolean;
  network_note: string | null;
  checked: boolean;
  pieces: Piece[];
  job: Job;
  restart_note: string;
}

async function call(path: string, body?: unknown): Promise<PackState> {
  const init: RequestInit =
    body === undefined
      ? {}
      : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const response = await fetch(`/api/models-pack${path}`, withConsoleHeader(init));
  const data = (await response.json()) as PackState | { detail?: unknown };
  if (!response.ok) {
    const detail = "detail" in data ? data.detail : undefined;
    throw new Error(typeof detail === "string" ? detail : response.statusText);
  }
  return data as PackState;
}

/** Bytes en GB con un decimal (por la pieza común de cifras, `lib/format.ts`). */
function gigabytes(bytes: number): string {
  return `${formatNumber(bytes / 1e9, 1)} GB`;
}

export function ModelsPack() {
  const [state, setState] = useState<PackState | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);

  const run = useCallback(async (path: string, body?: unknown) => {
    setBusy(true);
    try {
      setState(await call(path, body));
      setProblem(null);
    } catch (error) {
      setProblem(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    let alive = true;
    void call("")
      .then((first) => {
        if (!alive) return;
        setState(first);
        if (first.job.state === "running") setOpen(true);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  const running = state?.job.state === "running";
  useEffect(() => {
    if (!running) return undefined;
    const timer = window.setInterval(() => void run(""), 2000);
    return () => window.clearInterval(timer);
  }, [running, run]);

  const missing = state?.pieces.filter((piece) => piece.published && !piece.current) ?? [];
  const missingBytes = missing.reduce((sum, piece) => sum + (piece.download_bytes ?? 0), 0);
  const job = state?.job;

  return (
    <Fold
      concept="modelsPack"
      label={tr("Modelos de IA", "AI models")}
      open={open}
      onToggle={(event) => {
        const now = event.currentTarget.open;
        if (now !== open) setOpen(now);
        if (now && state === null) void run("");
      }}
    >
      {state === null ? null : (
        <div className="models-pack">
          <p className="secondary">
            {tr("Carpeta:", "Folder:")} <code>{state.folder}</code>
          </p>
          {state.network_note !== null && (
            <p>
              <MarkOf mark={UNAVAILABLE_MARK}>{state.network_note}</MarkOf>
            </p>
          )}
          {state.pieces.length > 0 && (
            <ul className="models-pack-pieces">
              {state.pieces.map((piece) => (
                <li key={piece.name}>
                  {piece.installed ? <MarkOf mark={OK_MARK}>{piece.label}</MarkOf> : piece.label}
                  {piece.download_bytes !== null && (
                    <span className="secondary"> · {gigabytes(piece.download_bytes)}</span>
                  )}
                  {piece.installed && (
                    <span className="secondary">
                      {" · "}
                      {piece.current ? tr("instalada", "installed") : tr("instalada, hay otra versión", "installed, a newer one exists")}
                    </span>
                  )}
                  {piece.published && !piece.current && !running && state.network && (
                    <>
                      {" "}
                      <button type="button" className="command" disabled={busy} onClick={() => void run("/download", { components: [piece.name] })}>
                        {tr("Descargar", "Download")}
                      </button>
                    </>
                  )}
                </li>
              ))}
            </ul>
          )}
          {state.network && !running && (
            <p>
              <button type="button" className="command" disabled={busy} onClick={() => void run("/check")}>
                {state.checked ? tr("Volver a consultar", "Check again") : tr("Ver qué hay para descargar", "See what can be downloaded")}
              </button>{" "}
              {missing.length > 0 && (
                <button type="button" className="command" disabled={busy} onClick={() => void run("/download", {})}>
                  {tr("Descargar todo", "Download everything")} ({gigabytes(missingBytes)})
                </button>
              )}
            </p>
          )}
          {state.checked && missing.length === 0 && state.pieces.length > 0 && (
            <p className="secondary">{tr("Todo lo publicado está instalado.", "Everything published is installed.")}</p>
          )}
          {job !== undefined && running && (
            <p>
              <progress max={job.total_bytes || 1} value={job.done_bytes ?? 0} />{" "}
              {job.component_label ?? ""}{" "}
              <span className="secondary">
                {gigabytes(job.done_bytes ?? 0)} / {gigabytes(job.total_bytes ?? 0)}
              </span>{" "}
              <button type="button" className="command" onClick={() => void run("/cancel", {})}>
                {tr("Cancelar", "Cancel")}
              </button>
            </p>
          )}
          {job?.state === "error" && job.message !== undefined && (
            <p>
              <MarkOf mark={FAILURE_MARK}>{job.message}</MarkOf>
            </p>
          )}
          {job?.state === "cancelled" && (
            <p className="secondary">
              {tr("Descarga cancelada: lo ya bajado se sigue la próxima vez.", "Download cancelled: what was already fetched resumes next time.")}
            </p>
          )}
          {job?.state === "done" && <p className="secondary">{state.restart_note}</p>}
          {problem !== null && (
            <p>
              <MarkOf mark={FAILURE_MARK}>{problem}</MarkOf>
            </p>
          )}
        </div>
      )}
    </Fold>
  );
}
