import { useCallback, useEffect, useState } from "react";

import { ApiError, withConsoleHeader } from "../lib/api";
import { formatNumber } from "../lib/format";
import { tr } from "../lib/i18n";
import { FAILURE_MARK, OK_MARK, type RequestOutcome, type StateMark, UNAVAILABLE_MARK, requestOutcome } from "../lib/marks";
import { Fold } from "./Fold";
import { MarkOf } from "./Mark";

/**
 * «Actualizar EMMA»: la versión instalada, la publicada y los mandos para bajarla e instalarla
 * (petición del usuario, 2026-11-16: que el programa instalado pueda pasar a las versiones nuevas
 * que se publican, sin reinstalar a mano).
 *
 * Texto de producto, no clínico. Las notas de la versión, los fallos y los avisos de red y de
 * reinicio los compone el backend (`/api/app-update`) y aquí se muestran tal cual; aquí solo los
 * rótulos de los mandos.
 *
 * Dos decisiones del usuario mandan en este panel:
 * - **Consultar lo publicado es una orden**, nunca algo que pase al montar ni al abrir el
 *   plegable: lo único que se pide al montar es el estado local (`GET`, que no sale a la red).
 *   Lo vigila `AppUpdate.test.ts`.
 * - **Instalar lo decide una persona**: solo «Instalar y reiniciar» lo pide. Después, la
 *   aplicación de escritorio cierra EMMA y lanza el instalador; el panel dice que se está
 *   cerrando para que nadie crea que se ha colgado.
 *
 * Mientras se consulta o se baja, se pregunta el estado cada dos segundos; parado, nada.
 */

export interface AppUpdateState {
  state: string;
  phase: string | null;
  current_version: string | null;
  available: { version: string; size: number | null; notes: string | null } | null;
  comparable: boolean;
  done_bytes: number;
  total_bytes: number;
  ready: { version: string } | null;
  install_requested: boolean;
  error: { code: string; message: string } | null;
  network: boolean;
  network_note: string | null;
  restart_note: string | null;
}

export type AppUpdateAction = "/check" | "/download" | "/cancel" | "/install";

export const APP_UPDATE_URL = "/api/app-update";
export const APP_UPDATE_POLL_MS = 2000;

/** El texto de un rechazo: `detail` como cadena, o el `message` de `{code, message}`. */
function detailText(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (typeof detail === "object" && detail !== null && "message" in detail) {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }
  return fallback;
}

/** Una petición al backend: sin `action`, el estado local (`GET`); con ella, la orden (`POST`). */
export async function callAppUpdate(action?: AppUpdateAction): Promise<AppUpdateState> {
  const init: RequestInit = action === undefined ? {} : { method: "POST" };
  const response = await fetch(`${APP_UPDATE_URL}${action ?? ""}`, withConsoleHeader(init));
  let data: unknown = null;
  try {
    data = await response.json();
  } catch {
    // cuerpo no JSON: se queda el texto de estado
  }
  if (!response.ok) {
    const detail = typeof data === "object" && data !== null && "detail" in data ? data.detail : undefined;
    throw new ApiError(response.status, detailText(detail, response.statusText));
  }
  return data as AppUpdateState;
}

/** ¿Hay que seguir preguntando? Solo mientras se consulta o se baja. */
export function isWorking(state: AppUpdateState | null): boolean {
  return state?.state === "checking" || state?.state === "downloading";
}

/** Bytes en MB con un decimal (por la pieza común de cifras, `lib/format.ts`). */
function megabytes(bytes: number): string {
  return `${formatNumber(bytes / 1e6, 1)} MB`;
}

/** La marca de un fallo del estado: sin red o bloqueado es «no disponible», no un fallo. */
function errorMark(code: string): StateMark | null {
  if (code === "offline" || code === "blocked") return UNAVAILABLE_MARK;
  if (code === "same-version") return null;
  return FAILURE_MARK;
}

export interface AppUpdateViewProps {
  state: AppUpdateState;
  busy: boolean;
  /** Lo que salió mal en la última orden, ya con su marca. */
  problem: RequestOutcome | null;
  /** Se consultó desde este panel y no hay nada más nuevo. */
  upToDate: boolean;
  onAction: (action: AppUpdateAction) => void;
}

/** El contenido del plegable con un estado ya leído: sin efectos, para poder pintarlo en pruebas. */
export function AppUpdateView({ state, busy, problem, upToDate, onAction }: AppUpdateViewProps) {
  const working = isWorking(state);
  const closing = state.install_requested;
  const downloading = state.state === "downloading";
  const readyMatches = state.ready !== null && state.available !== null && state.ready.version === state.available.version;
  const canDownload = state.available !== null && !readyMatches && !working && !closing && state.network;
  const errorShown = state.error === null ? null : errorMark(state.error.code);
  return (
    <div className="app-update" style={{ overflowWrap: "anywhere" }}>
      <p>
        {tr("Versión instalada:", "Installed version:")}{" "}
        {state.current_version === null ? (
          <MarkOf mark={UNAVAILABLE_MARK}>{tr("desconocida", "unknown")}</MarkOf>
        ) : (
          <code>{state.current_version}</code>
        )}
      </p>
      {state.available !== null && (
        <>
          <p>
            {tr("Versión publicada:", "Published version:")} <code>{state.available.version}</code>
            {state.available.size !== null && <span className="secondary"> · {megabytes(state.available.size)}</span>}
          </p>
          {!state.comparable && (
            <p className="secondary">
              {tr(
                "No se puede comparar con la versión instalada: decide quien la instala.",
                "It cannot be compared with the installed version: whoever installs it decides.",
              )}
            </p>
          )}
          {state.available.notes !== null && state.available.notes !== "" && (
            <p className="secondary" style={{ whiteSpace: "pre-line" }}>
              {state.available.notes}
            </p>
          )}
        </>
      )}
      {state.network_note !== null && (
        <p>
          <MarkOf mark={UNAVAILABLE_MARK}>{state.network_note}</MarkOf>
        </p>
      )}
      {!working && !closing && state.network && (
        <p>
          <button type="button" className="command" disabled={busy} onClick={() => onAction("/check")}>
            {tr("Comprobar si hay una versión nueva", "Check for a new version")}
          </button>{" "}
          {canDownload && (
            <button type="button" className="command" disabled={busy} onClick={() => onAction("/download")}>
              {tr("Descargar", "Download")} {state.available?.version}
            </button>
          )}
        </p>
      )}
      {upToDate && !working && state.available === null && state.error === null && (
        <p className="secondary">
          {tr("No hay una versión publicada más nueva que la instalada.", "There is no published version newer than the installed one.")}
        </p>
      )}
      {working && (
        <p>
          {downloading ? (
            <>
              {/* Sin el total todavía, la barra sin valor (indeterminada) y solo lo recibido. */}
              {state.total_bytes > 0 ? <progress max={state.total_bytes} value={state.done_bytes} /> : <progress />}{" "}
              <span className="secondary">
                {megabytes(state.done_bytes)}
                {state.total_bytes > 0 && ` / ${megabytes(state.total_bytes)}`}
              </span>
            </>
          ) : (
            <span className="secondary">{tr("Consultando lo publicado…", "Checking what is published…")}</span>
          )}{" "}
          <button type="button" className="command" disabled={busy} onClick={() => onAction("/cancel")}>
            {tr("Cancelar", "Cancel")}
          </button>
        </p>
      )}
      {state.ready !== null && !closing && (
        <p>
          <MarkOf mark={OK_MARK}>
            {tr("Instalador verificado:", "Verified installer:")} <code>{state.ready.version}</code>
          </MarkOf>{" "}
          <button type="button" className="command" disabled={busy || working} onClick={() => onAction("/install")}>
            {tr("Instalar y reiniciar", "Install and restart")}
          </button>
        </p>
      )}
      {state.ready !== null && state.restart_note !== null && !closing && (
        <p className="secondary">{state.restart_note}</p>
      )}
      {closing && (
        <p>
          <strong>{tr("Cerrando EMMA para instalar la versión nueva…", "Closing EMMA to install the new version…")}</strong>
        </p>
      )}
      {state.error !== null &&
        (errorShown === null ? (
          <p className="secondary">{state.error.message}</p>
        ) : (
          <p>
            <MarkOf mark={errorShown}>{state.error.message}</MarkOf>
          </p>
        ))}
      {problem !== null && (
        <p>
          <MarkOf mark={problem.mark}>{problem.text}</MarkOf>
        </p>
      )}
    </div>
  );
}


export function AppUpdate() {
  const [state, setState] = useState<AppUpdateState | null>(null);
  const [problem, setProblem] = useState<RequestOutcome | null>(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [asked, setAsked] = useState(false);

  const run = useCallback(async (action?: AppUpdateAction) => {
    if (action !== undefined) setBusy(true);
    if (action === "/check") setAsked(true);
    try {
      setState(await callAppUpdate(action));
      setProblem(null);
    } catch (error) {
      setProblem(requestOutcome(error));
    } finally {
      if (action !== undefined) setBusy(false);
    }
  }, []);

  // Al montar, solo el estado local: nunca `/check` (decisión del usuario). Si ya se está bajando
  // o hay un instalador listo, el plegable se abre solo para que se vea.
  useEffect(() => {
    let alive = true;
    void callAppUpdate()
      .then((first) => {
        if (!alive) return;
        setState(first);
        if (isWorking(first) || first.ready !== null || first.install_requested) setOpen(true);
      })
      .catch((error: unknown) => {
        if (alive) setProblem(requestOutcome(error));
      });
    return () => {
      alive = false;
    };
  }, []);

  const working = isWorking(state);
  useEffect(() => {
    if (!working) return undefined;
    const timer = window.setInterval(() => void run(), APP_UPDATE_POLL_MS);
    return () => window.clearInterval(timer);
  }, [working, run]);

  return (
    <Fold
      concept="appUpdate"
      label={tr("Actualizar EMMA", "Update EMMA")}
      open={open}
      onToggle={(event) => {
        const now = event.currentTarget.open;
        if (now !== open) setOpen(now);
        if (now && state === null) void run();
      }}
    >
      {state === null ? (
        problem !== null && (
          <p>
            <MarkOf mark={problem.mark}>{problem.text}</MarkOf>
          </p>
        )
      ) : (
        <AppUpdateView state={state} busy={busy} problem={problem} upToDate={asked} onAction={(action) => void run(action)} />
      )}
    </Fold>
  );
}
