/**
 * «Distancia y comunicaciones» y «Sincronización y datos» en inglés (`lib/i18n.ts`): los rótulos y
 * las palabras de estado que pone la interfaz. Las cifras, las marcas y lo que viene del backend
 * son los de `HomeDistance.test.ts`; aquí solo el idioma.
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { CrewStatus, LinkSync, Sharing } from "../lib/api";
import type { Distances } from "../lib/distanceApi";
import type { Fetched } from "./HomeBoard";
import { HomeDistance, commsNodes, linkFigure, workMode } from "./HomeDistance";

function status(over: { profile?: string | null; integrity?: boolean } = {}): CrewStatus {
  const partial = {
    subject: "crew-01",
    data: { reference_time: "2026-12-10T23:00:00Z", integrity_ok: over.integrity ?? true, observations: 1234 },
    mission: { profile: over.profile === null ? null : { id: over.profile ?? "mars-transit" } },
    freshness: { comms: { state: "fresh" }, solar: { state: "fresh" }, basis: "" },
    comms: { one_way_minutes: 9.14, round_trip_minutes: 18.28 },
    comms_status: { state: "available", source: "spice", source_text: "computed locally (SPICE)", word: "W", text: "T", discrepancy: null },
  };
  return partial as unknown as CrewStatus;
}

const SYNC = {
  label: "Simulated link",
  state: "up",
  state_display: "restored",
  to_send: { count: 3 },
  cut: null,
  held: false,
  crew_sentence: "C",
  ground_sentence: "G",
  not_measured: "EMMA does not measure the link",
} as unknown as LinkSync;

const render = (profileId: string | null, sync: LinkSync | null = SYNC, crewStatus = status()) =>
  renderToStaticMarkup(createElement(HomeDistance, { profileId, status: crewStatus, sync }));

describe("«Distancia y comunicaciones» en inglés", () => {
  it("los títulos, el perfil corto y las tarjetas", () => {
    const html = render("mars-transit");
    for (const text of [
      'aria-label="Distance and communications"',
      "(Mars transit)",
      "Communication delay",
      "one way, to Earth · computed locally (SPICE)",
      "Communication nodes",
      "Ground console",
      "Relays: no nodes declared in EMMA",
      'aria-label="Distances from Earth"',
    ]) {
      expect(html).toContain(text);
    }
    expect(html).not.toMatch(/Distancia y comunicaciones|Tránsito a Marte|Retardo de comunicación|Consola de Tierra|Relés/);
  });

  it("sin perfil, lo dice en inglés", () => {
    const html = render(null);
    expect(html).toContain("No mission profile declared and no location chosen.");
    expect(html).toContain("No profile");
    expect(html).not.toMatch(/Sin perfil/);
  });

  it("«Sincronización y datos»: rótulos, enlace, pendientes y registro", () => {
    const html = render("mars-transit");
    for (const text of [
      'aria-label="Synchronization and data"',
      "Working mode",
      "Link to Earth",
      "(simulated, declared)",
      "Waiting to send",
      "3 entries",
      "Earth has up to",
      "everything on board",
      "Signed ledger",
      "Intact",
      "Readings analyzed",
      "Last reading",
      "Local storage",
      "not exposed by the backend",
    ]) {
      expect(html).toContain(text);
    }
    expect(html).not.toMatch(/Sincronización|Modo de trabajo|asientos|Registro firmado|Íntegro|Almacenamiento/);
    expect(render("mars-transit", null)).toContain("not received");
    expect(render("mars-transit", SYNC, status({ integrity: false }))).toContain("Integrity compromised");
  });
});

describe("las palabras de la lógica en inglés", () => {
  it("el retardo ausente: no aplica, sin efemérides, cargando y perfil no reconocido", () => {
    const base: Distances = {
      profile: "leo",
      declared_profile: "mars-transit",
      epoch: "2026-12-10",
      scope: "S",
      observer: "O",
      spice: { available: true, reason: null, source: null },
      known: true,
      display: "d",
      unknown_text: "U",
      crew_place: null,
      earth_link: { state: "not_applicable", target: null, distance_km: null, one_way_seconds: null, source: null, text: "NO" },
      bodies: [],
    };
    const ready = (value: Distances): Fetched<Distances> => ({ state: "ready", value });
    expect(linkFigure("leo", status(), ready(base))).toMatchObject({ kind: "absent", word: "Not applicable" });
    const missing = { ...base, earth_link: { ...base.earth_link!, state: "missing" as const } };
    expect(linkFigure("leo", status(), ready(missing))).toMatchObject({ word: "No ephemeris" });
    expect(linkFigure("leo", status(), ready({ ...base, earth_link: null }))).toMatchObject({ word: "Unrecognized profile" });
    expect(linkFigure("leo", status(), { state: "loading" })).toMatchObject({ word: "Loading…" });
  });

  it("los nodos y el modo de trabajo", () => {
    const nodes = commsNodes("crew-01", [{ subject: "crew-02" }] as never, { kind: "absent", mark: null as never, word: "x", text: null }, SYNC);
    expect(nodes.map((node) => node.where)).toEqual(["module not declared", "Earth"]);
    expect(nodes[1]?.name).toBe("Ground console");
    expect(nodes[1]?.link?.word).toBe("link restored");
    const sharing = (offline: boolean): Fetched<Sharing> =>
      ({ state: "ready", value: { internet: { offline, offline_text: "t" } } }) as unknown as Fetched<Sharing>;
    expect(workMode(sharing(true)).word).toBe("Autonomous, offline (mission mode)");
    expect(workMode(sharing(false)).word).toBe("Online");
    expect(workMode({ state: "loading" }).word).toBe("Loading…");
  });
});
