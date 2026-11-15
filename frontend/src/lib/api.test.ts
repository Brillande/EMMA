import { afterEach, describe, expect, it, vi } from "vitest";

import { api, CONSOLE_HEADER, CONSOLE_HEADER_VALUE, postVolume, withConsoleHeader } from "./api";

/*
 * La cabecera propia de la consola en cada POST (`backend/app/api/console_header.py`, §5.39.23):
 * el backend la exige en los POST que una petición simple podría disparar desde otra página del
 * navegador (`/simulate`, `/comms/preload`, las importaciones). Si `request` dejara de ponerla,
 * la consola no podría cargar un escenario (403). No es autenticación: el valor es fijo y público.
 */

function headerOf(init: RequestInit | undefined): string | null {
  return new Headers(init?.headers).get(CONSOLE_HEADER);
}

describe("withConsoleHeader", () => {
  it("pone X-EMMA-Console: 1 en un POST sin cabeceras", () => {
    const init = withConsoleHeader({ method: "POST" });
    expect(headerOf(init)).toBe(CONSOLE_HEADER_VALUE);
    expect(init.method).toBe("POST");
  });

  it("la añade a las que ya hubiera, vengan como objeto, lista o Headers", () => {
    const given: HeadersInit[] = [
      { "Content-Type": "application/json" },
      [["Content-Type", "application/json"]],
      new Headers({ "Content-Type": "application/json" }),
    ];
    for (const headers of given) {
      const merged = new Headers(withConsoleHeader({ method: "post", headers }).headers);
      expect(merged.get(CONSOLE_HEADER)).toBe(CONSOLE_HEADER_VALUE);
      expect(merged.get("Content-Type")).toBe("application/json");
    }
  });

  it("no toca un GET", () => {
    expect(headerOf(withConsoleHeader(undefined))).toBeNull();
    expect(headerOf(withConsoleHeader({ method: "GET" }))).toBeNull();
  });
});

describe("la consola la manda", () => {
  afterEach(() => vi.unstubAllGlobals());

  function stubFetch(body: unknown) {
    const fetched = vi.fn<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>(
      async () =>
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetched);
    return fetched;
  }

  it("en POST /api/simulate, el que la ronda 16 dejó escrito", async () => {
    const fetched = stubFetch({ recorded: 1, replaced: true });
    await api.simulate("nominal", true);
    const [url, init] = fetched.mock.calls[0] ?? [];
    expect(url).toBe("/api/simulate?scenario=nominal&replace=true");
    expect(headerOf(init)).toBe(CONSOLE_HEADER_VALUE);
  });

  it("en un POST con cuerpo JSON, sin perder el Content-Type", async () => {
    const fetched = stubFetch({ ledger_index: 0 });
    await api.acknowledge({
      subject: "crew-01",
      domain: "cardiovascular",
      level: "warning",
      reference_time: "2026-11-14T00:00:00Z",
      acknowledged_by: "CMO",
    });
    const [, init] = fetched.mock.calls[0] ?? [];
    expect(headerOf(init)).toBe(CONSOLE_HEADER_VALUE);
    expect(new Headers(init?.headers).get("Content-Type")).toBe("application/json");
  });

  it("en la subida de un volumen, que no pasa por request", async () => {
    const fetched = stubFetch({ ledger_index: 0 });
    await postVolume(new Blob([new Uint8Array(4)]), "CT", "crew-01", "CMO", false);
    const [, init] = fetched.mock.calls[0] ?? [];
    expect(headerOf(init)).toBe(CONSOLE_HEADER_VALUE);
    expect(new Headers(init?.headers).get("Content-Type")).toBe("application/octet-stream");
  });

  it("no en un GET", async () => {
    const fetched = stubFetch({ reasons: [] });
    await api.dismissalReasons();
    const [, init] = fetched.mock.calls[0] ?? [];
    expect(headerOf(init)).toBeNull();
  });
});
