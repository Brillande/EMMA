import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, CONSOLE_HEADER, CONSOLE_HEADER_VALUE } from "../lib/api";
import { formatNumber } from "../lib/format";
import { FAILURE_MARK, REFUSED_MARK, UNAVAILABLE_MARK } from "../lib/marks";
import { uiPictogram } from "../lib/uiMarks";
import {
  APP_UPDATE_POLL_MS,
  AppUpdate,
  type AppUpdateState,
  AppUpdateView,
  type AppUpdateViewProps,
  callAppUpdate,
  isWorking,
} from "./AppUpdate";

/**
 * «Actualizar EMMA» (`components/AppUpdate.tsx`) con el contrato de `/api/app-update` ya leído.
 * Sin jsdom: el contenido se pinta a HTML estático, y las peticiones se miran con `fetch` simulado.
 * Lo que fija: lo que dice el backend sale tal cual, los mandos aparecen según el estado, y al
 * montar no se consulta lo publicado (decisión del usuario: comprobar es una orden).
 */

const idle: AppUpdateState = {
  state: "idle",
  phase: null,
  current_version: "0.1.4",
  available: null,
  comparable: true,
  done_bytes: 0,
  total_bytes: 0,
  ready: null,
  install_requested: false,
  error: null,
  network: true,
  network_note: null,
  restart_note: null,
};

function view(state: Partial<AppUpdateState>, extra: Partial<AppUpdateViewProps> = {}): string {
  return renderToStaticMarkup(
    createElement(AppUpdateView, {
      state: { ...idle, ...state },
      busy: false,
      problem: null,
      upToDate: false,
      onAction: () => undefined,
      ...extra,
    }),
  );
}

const CHECK = "Comprobar si hay una versión nueva";
const INSTALL = "Instalar y reiniciar";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("lo que se muestra", () => {
  it("la versión instalada; «desconocida», con la marca de no disponible, si el backend no la sabe", () => {
    expect(view({})).toContain("0.1.4");
    const unknown = view({ current_version: null });
    expect(unknown).toContain("desconocida");
    expect(unknown).toContain(UNAVAILABLE_MARK.className);
  });

  it("la versión publicada, su tamaño por `formatNumber` y sus notas tal cual", () => {
    const html = view({ available: { version: "0.2.0", size: 123_456_789, notes: "NOTAS-DEL-BACKEND" } });
    expect(html).toContain("0.2.0");
    expect(html).toContain(`${formatNumber(123.456789, 1)} MB`);
    expect(html).toContain("NOTAS-DEL-BACKEND");
    expect(html).toContain("Descargar");
  });

  it("los avisos de red y de reinicio y el mensaje de error son los del backend", () => {
    const html = view({
      network: false,
      network_note: "NOTA-DE-RED",
      ready: { version: "0.2.0" },
      restart_note: "NOTA-DE-REINICIO",
      error: { code: "bad-hash", message: "MENSAJE-DE-ERROR" },
    });
    expect(html).toContain("NOTA-DE-RED");
    expect(html).toContain("NOTA-DE-REINICIO");
    expect(html).toContain("MENSAJE-DE-ERROR");
    expect(html).toContain(FAILURE_MARK.className);
  });

  it("sin red o bloqueado no es un fallo sino «no disponible»", () => {
    for (const code of ["offline", "blocked"]) {
      const html = view({ error: { code, message: "SIN-RED" } });
      expect(html, code).toContain(UNAVAILABLE_MARK.className);
      expect(html, code).not.toContain(FAILURE_MARK.className);
    }
  });

  it("un rechazo de una orden lleva su marca", () => {
    const html = view({}, { problem: { mark: REFUSED_MARK, text: "NO-HAY-INSTALADOR" } });
    expect(html).toContain("NO-HAY-INSTALADOR");
    expect(html).toContain(REFUSED_MARK.className);
  });
});

describe("los mandos según el estado", () => {
  it("parado y con red: solo «Comprobar»", () => {
    const html = view({});
    expect(html).toContain(CHECK);
    expect(html).not.toContain("Descargar");
    expect(html).not.toContain(INSTALL);
    expect(html).not.toContain("Cancelar");
  });

  it("sin red no se ofrece comprobar ni descargar", () => {
    const html = view({ network: false, available: { version: "0.2.0", size: null, notes: null } });
    expect(html).not.toContain(CHECK);
    expect(html).not.toContain("Descargar");
  });

  it("bajando: barra de progreso, bytes por `formatNumber` y «Cancelar»", () => {
    const html = view({
      state: "downloading",
      available: { version: "0.2.0", size: 200e6, notes: null },
      done_bytes: 50e6,
      total_bytes: 200e6,
    });
    expect(html).toContain("<progress");
    expect(html).toContain(`${formatNumber(50, 1)} MB / ${formatNumber(200, 1)} MB`);
    expect(html).toContain("Cancelar");
    expect(html).not.toContain(CHECK);
    expect(html).not.toContain("Descargar 0.2.0");
  });

  it("bajando sin el total todavía: barra indeterminada y solo lo recibido, nunca «0,0 MB / 0,0 MB»", () => {
    const html = view({ state: "downloading", done_bytes: 0, total_bytes: 0 });
    expect(html).toContain("<progress></progress>");
    expect(html).not.toContain(" / ");
  });

  it("con el instalador verificado: «Instalar y reiniciar», y no se vuelve a ofrecer bajarlo", () => {
    const html = view({ state: "ready", available: { version: "0.2.0", size: null, notes: null }, ready: { version: "0.2.0" } });
    expect(html).toContain(INSTALL);
    expect(html).not.toContain("Descargar");
  });

  it("pedida la instalación: dice que se cierra y ya no hay mandos", () => {
    const html = view({ ready: { version: "0.2.0" }, install_requested: true });
    expect(html).toContain("Cerrando EMMA para instalar");
    expect(html).not.toContain(INSTALL);
    expect(html).not.toContain(CHECK);
  });

  it("consultado sin nada más nuevo, lo dice", () => {
    expect(view({}, { upToDate: true })).toContain("No hay una versión publicada más nueva");
    expect(view({})).not.toContain("No hay una versión publicada más nueva");
  });

  it("solo se sigue preguntando mientras se consulta o se baja", () => {
    expect(isWorking({ ...idle, state: "checking" })).toBe(true);
    expect(isWorking({ ...idle, state: "downloading" })).toBe(true);
    for (const state of ["idle", "ready", "error"]) expect(isWorking({ ...idle, state })).toBe(false);
    expect(isWorking(null)).toBe(false);
    expect(APP_UPDATE_POLL_MS).toBe(2000);
  });
});

describe("las peticiones", () => {
  function stubFetch(status = 200, body: unknown = idle) {
    const fetchMock = vi.fn(() => Promise.resolve(new Response(JSON.stringify(body), { status })));
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  it("el estado es un GET sin cabecera de consola; las órdenes, POST con ella", async () => {
    const fetchMock = stubFetch();
    await callAppUpdate();
    await callAppUpdate("/check");
    const calls = fetchMock.mock.calls as unknown as [string, RequestInit][];
    expect(calls[0]?.[0]).toBe("/api/app-update");
    expect(calls[0]?.[1].method).toBeUndefined();
    expect(calls[1]?.[0]).toBe("/api/app-update/check");
    expect(calls[1]?.[1].method).toBe("POST");
    expect(new Headers(calls[1]?.[1].headers).get(CONSOLE_HEADER)).toBe(CONSOLE_HEADER_VALUE);
  });

  it("un 409 not-ready es un rechazo con el `message` del backend", async () => {
    stubFetch(409, { detail: { code: "not-ready", message: "NO-HAY-INSTALADOR-VERIFICADO" } });
    const error = await callAppUpdate("/install").catch((reason: unknown) => reason);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).detail).toBe("NO-HAY-INSTALADOR-VERIFICADO");
  });

  it("al montar no se consulta lo publicado: `/check` solo sale de su botón", () => {
    // Pintar el componente entero no pide nada (sin efectos en el servidor)…
    const fetchMock = stubFetch();
    expect(renderToStaticMarkup(createElement(AppUpdate))).toContain("Actualizar EMMA");
    expect(fetchMock).not.toHaveBeenCalled();
    // …y en la fuente, la única petición del montaje es el estado local, y `/check` aparece solo en
    // el mando: ni en un efecto ni en el plegable.
    const source = readFileSync(fileURLToPath(new URL("./AppUpdate.tsx", import.meta.url)), "utf8");
    const mount = source.slice(source.indexOf("useEffect(() => {"), source.lastIndexOf("const working = isWorking(state);"));
    expect(mount).toContain("callAppUpdate()");
    expect(mount).not.toContain("/check");
    expect(source.match(/"\/check"/g)).toHaveLength(3); // el tipo, el botón y la marca de «consultado»
    expect(source).toContain('onClick={() => onAction("/check")}');
    const toggle = source.slice(source.indexOf("onToggle="), source.indexOf("</Fold>"));
    expect(toggle.slice(0, toggle.indexOf("}}"))).not.toContain("/check");
  });

  it("el plegable lleva el signo de su concepto", () => {
    expect(uiPictogram("appUpdate")).toBe("tray-arrow-down");
  });
});
