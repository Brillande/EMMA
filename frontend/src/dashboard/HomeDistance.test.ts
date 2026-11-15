import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { CrewOverview, CrewStatus, LinkSync, Sharing } from "../lib/api";
import type { Distances } from "../lib/distanceApi";
import { epochOf } from "../lib/distanceApi";
import { formatNumber } from "../lib/format";
import { LINK_DOWN_MARK } from "../lib/linkSync";
import { LOADING_MARK, MISSING_MARK, UNAVAILABLE_MARK } from "../lib/marks";
import type { Fetched } from "./HomeBoard";
import { HomeDistance, commsNodes, formatKm, formatLightTime, isCrewPlace, linkFigure, workMode } from "./HomeDistance";

/**
 * «Distancia y comunicaciones» y «Sincronización y datos» (lote «reservas», unidad 4): se adaptan al
 * perfil enseñado, no inventan cifras (ni distancias de la maqueta ni nodos de relé) y dicen «no
 * aplica» en gris lo que el perfil no calcula. Se pinta con `renderToStaticMarkup`, sin red: los
 * efectos no corren y las peticiones no salen.
 */

function status(over: {
  profile?: string | null;
  comms?: CrewStatus["comms"];
  state?: "available" | "not_applicable" | "missing";
  freshness?: "fresh" | "stale" | "missing";
  integrity?: boolean;
} = {}): CrewStatus {
  const state = over.state ?? "available";
  const partial = {
    subject: "crew-01",
    data: { reference_time: "2026-12-10T23:00:00Z", integrity_ok: over.integrity ?? true, observations: 1234 },
    mission: { profile: over.profile === null ? null : { id: over.profile ?? "mars-transit" } },
    freshness: { comms: { state: over.freshness ?? "fresh" }, solar: { state: "fresh" }, basis: "" },
    comms: over.comms === undefined ? { one_way_minutes: 9.14, round_trip_minutes: 18.28 } : over.comms,
    comms_status: {
      state,
      source: state === "available" ? "spice" : null,
      source_text: state === "available" ? "calculado en local (SPICE)" : null,
      word: state === "available" ? "Retardo calculado en local (SPICE)" : state === "not_applicable" ? "No aplica" : "Sin efemérides",
      text: "T",
      discrepancy: null,
    },
  };
  return partial as unknown as CrewStatus;
}

function distances(over: Partial<Distances> = {}): Fetched<Distances> {
  return {
    state: "ready",
    value: {
      profile: "lunar-surface",
      declared_profile: "mars-transit",
      epoch: "2026-12-10",
      scope: "Descriptivo",
      observer: "desde el geocentro (centro de la Tierra), centro a centro",
      spice: { available: true, reason: null, source: "SPICE local, núcleo de432s.bsp" },
      known: true,
      display: "superficie lunar",
      unknown_text: null,
      crew_place: { body: "moon", text: "En la superficie de la Luna." },
      earth_link: { state: "not_applicable", target: null, distance_km: null, one_way_seconds: null, source: null, text: "NO" },
      bodies: [
        { id: "moon", label: "Luna", note: "n", state: "available", distance_km: 405_837.3, one_way_seconds: 1.3537, source: "S", text: null },
        { id: "mars", label: "Marte", note: "n", state: "missing", distance_km: null, one_way_seconds: null, source: null, text: "sin núcleos" },
      ],
      ...over,
    },
  };
}

const SYNC = {
  label: "Enlace con Tierra simulado (declarado por una persona)",
  state: "up",
  state_display: "restablecido",
  to_send: { count: 0 },
  cut: null,
  held: false,
  crew_sentence: "C",
  ground_sentence: "G",
  not_measured: "EMMA no mide el enlace",
} as unknown as LinkSync;

describe("las cifras se escriben con `lib/format`", () => {
  it("kilómetros enteros hasta un millón; después, millones", () => {
    expect(formatKm(405_837.3)).toBe(`${formatNumber(405_837.3)} km`);
    expect(formatKm(164_386_135)).toBe(`${formatNumber(164.386135, 1)} M km`);
  });

  it("segundos por debajo del minuto; minutos por encima", () => {
    expect(formatLightTime(1.3537)).toBe("1,35 s");
    expect(formatLightTime(12.34)).toBe("12,3 s");
    expect(formatLightTime(548.3)).toBe("9,1 min");
  });
});

describe("el retardo sigue al perfil enseñado", () => {
  it("con el perfil declarado, el del estado (el de la franja)", () => {
    const figure = linkFigure("mars-transit", status(), { state: "loading" });
    expect(figure).toMatchObject({ kind: "shown", stale: false });
    expect(figure.kind === "shown" && figure.seconds).toBeCloseTo(548.4);
  });

  it("caducado, se dice: cian, no una cifra limpia", () => {
    const figure = linkFigure("mars-transit", status({ freshness: "stale" }), { state: "loading" });
    expect(figure).toMatchObject({ kind: "shown", stale: true });
  });

  it("declarado sin objetivo de efemérides: «No aplica» en gris, no «sin efemérides»", () => {
    const figure = linkFigure("leo", status({ profile: "leo", comms: null, state: "not_applicable" }), { state: "loading" });
    expect(figure).toMatchObject({ kind: "absent", mark: UNAVAILABLE_MARK, word: "No aplica" });
  });

  it("declarado y sin efemérides: el cian del dato ausente", () => {
    const figure = linkFigure("mars-transit", status({ comms: null, state: "missing" }), { state: "loading" });
    expect(figure).toMatchObject({ kind: "absent", mark: MISSING_MARK });
  });

  it("otro perfil: el de `/api/distances`, no el del estado", () => {
    expect(linkFigure("lunar-surface", status(), distances())).toMatchObject({ kind: "absent", mark: UNAVAILABLE_MARK, word: "No aplica" });
    const mars = distances({
      earth_link: { state: "available", target: "499", distance_km: 1.6e8, one_way_seconds: 548.3, source: "SPICE", text: "Hacia Marte" },
    });
    expect(linkFigure("mars-surface", status(), mars)).toMatchObject({ kind: "shown", seconds: 548.3, source: "SPICE" });
    expect(linkFigure("mars-surface", status(), { state: "loading" })).toMatchObject({ kind: "absent", mark: LOADING_MARK });
  });

  it("un perfil que el backend no reconoce no se adivina", () => {
    const unknown = distances({ known: false, earth_link: null, bodies: [], unknown_text: "no está" });
    expect(linkFigure("venus", status(), unknown)).toMatchObject({ kind: "absent", mark: UNAVAILABLE_MARK, text: "no está" });
  });
});

describe("los nodos son solo los que existen en EMMA", () => {
  const crew = [
    { subject: "crew-01", location: null },
    { subject: "crew-02", location: { display: "Módulo laboratorio" } },
  ] as unknown as CrewOverview["crew"];

  it("los otros tripulantes a bordo y la consola de Tierra; ningún relé inventado", () => {
    const nodes = commsNodes("crew-01", crew, { kind: "absent", mark: UNAVAILABLE_MARK, word: "No aplica", text: null }, SYNC);
    expect(nodes.map((node) => node.name)).toEqual(["crew-02", "Consola de Tierra"]);
    expect(nodes[0]).toMatchObject({ where: "Módulo laboratorio", delay: { kind: "onboard" } });
    expect(nodes.map((node) => node.name).join(" ")).not.toMatch(/Gateway|Relay|Base/);
  });

  it("con el enlace caído, la marca del enlace fuera de servicio", () => {
    const down = { ...SYNC, state: "down", state_display: "caído" } as LinkSync;
    const ground = commsNodes("crew-01", null, { kind: "absent", mark: UNAVAILABLE_MARK, word: "x", text: null }, down).at(-1);
    expect(ground?.link).toMatchObject({ mark: LINK_DOWN_MARK, word: "enlace caído" });
  });
});

describe("sincronización", () => {
  it("sin red es el modo nominal de misión, no un fallo", () => {
    const sharing = { state: "ready", value: { internet: { offline: true, offline_text: "Ahora: modo sin red." } } } as unknown as Fetched<Sharing>;
    expect(workMode(sharing)).toEqual({ word: "Autónomo, sin red (modo de misión)", text: "Ahora: modo sin red.", mark: null });
  });

  it("la fila de la tripulación es la del perfil; en ruta, ninguna", () => {
    expect(isCrewPlace(distances(), "moon")).toBe(true);
    expect(isCrewPlace(distances({ crew_place: { body: null, text: "En ruta" } }), "moon")).toBe(false);
  });

  it("el día de las efemérides es el UTC de la última lectura", () => {
    expect(epochOf("2026-12-10T23:30:00-02:00")).toBe("2026-12-11");
    expect(epochOf("no")).toBeNull();
  });
});

describe("el tablero pintado", () => {
  const render = (profileId: string | null, sync: LinkSync | null = SYNC) =>
    renderToStaticMarkup(createElement(HomeDistance, { profileId, status: status(), sync }));

  it("adapta el título al perfil y no copia cifras de la maqueta", () => {
    const html = render("mars-transit");
    expect(html).toContain("Distancia y comunicaciones");
    expect(html).toContain("(Tránsito a Marte)");
    expect(html).toContain("Sincronización y datos");
    for (const invented of ["384.400", "400 km", "0,002 s", "Gateway", "Mars Relay", "v1.6.5", "Actualizar", "76 %"]) {
      expect(html).not.toContain(invented);
    }
    expect(html).toContain("Relés: sin nodos declarados en EMMA");
    expect(html).toContain("el backend no lo expone");
  });

  it("sin perfil, lo dice; sin enlace recibido, «no recibido» en gris", () => {
    const html = render(null, null);
    expect(html).toContain("Sin perfil de misión declarado ni ubicación elegida.");
    expect(html).toContain("no recibido");
  });
});
