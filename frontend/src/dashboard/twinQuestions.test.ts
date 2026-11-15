import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { markedHtml, taggedPictogram } from "../advisor/visibleText";
import { type TwinQuestion, type TwinQuestions, twinsApi } from "../lib/api";
import { levelStyle } from "../lib/levels";
import { FAILURE_MARK, OK_MARK, type RequestOutcome, UNAVAILABLE_MARK, UNKNOWN_MARK } from "../lib/marks";
import { uiPictogram } from "../lib/uiMarks";
import { TwinQuestionsView } from "./TwinQuestions";

/**
 * Las cinco preguntas de los gemelos (§5.35.1): se pinta lo que da el backend. Los textos de prueba
 * son marcadores: si la interfaz redactara algo propio en su sitio, el marcador no saldría.
 */
const question = (overrides: Partial<TwinQuestion> = {}): TwinQuestion => ({
  key: "human",
  twin: "CAPA-HUMANA",
  content: "CONTENIDO-LITERAL",
  question: "PREGUNTA-LITERAL",
  state: "answered",
  answer: "RESPUESTA-DEL-BACKEND",
  items: [{ text: "PARTE-CON-NIVEL", level: "watch" }, { text: "PARTE-SIN-NIVEL", level: null }],
  notes: ["RESERVA-DEL-BACKEND"],
  sources: ["ORIGEN-DEL-BACKEND"],
  ...overrides,
});

const body = (questions: TwinQuestion[]): TwinQuestions => ({
  subject: "crew-01",
  reference_time: "2026-12-10T00:00:00+00:00",
  until: null,
  rules_version: "reglas@prueba",
  source: "FUENTE-DE-LA-TABLA",
  note: "NOTA-DEL-BACKEND",
  questions,
});

const render = (data: TwinQuestions | null, unavailable: RequestOutcome | null = null): string =>
  renderToStaticMarkup(createElement(TwinQuestionsView, { data, unavailable }));

describe("las cinco preguntas de los gemelos", () => {
  it("pinta la pregunta, la respuesta, sus partes, sus reservas y su origen tal cual", () => {
    const html = render(body([question()]));
    for (const word of [
      "CAPA-HUMANA: PREGUNTA-LITERAL", "CONTENIDO-LITERAL", "RESPUESTA-DEL-BACKEND",
      "PARTE-CON-NIVEL", "PARTE-SIN-NIVEL", "RESERVA-DEL-BACKEND", "ORIGEN-DEL-BACKEND",
      "NOTA-DEL-BACKEND", "FUENTE-DE-LA-TABLA",
    ]) {
      expect(html).toContain(word);
    }
    expect(html).toMatch(taggedPictogram("h2", uiPictogram("twinQuestions"), "Las cinco preguntas de los gemelos"));
  });

  it("cada capa lleva el dibujo del panel que la responde, y una desconocida el de «desconocido»", () => {
    const keys = ["human", "habitat", "mission", "countermeasure", "decision"] as const;
    const concepts = ["domains", "habitat", "missionDay", "recommendations", "waiting"] as const;
    const html = render(body(keys.map((key) => question({ key, twin: `CAPA-${key}` }))));
    keys.forEach((key, index) => {
      expect(html).toMatch(
        taggedPictogram("h3", uiPictogram(concepts[index] ?? "domains"), `CAPA-${key}: PREGUNTA-LITERAL`, ' class="section-gap"'),
      );
    });
    const unknown = render(body([question({ key: "otra" as TwinQuestion["key"], twin: "CAPA-NUEVA" })]));
    expect(unknown).toContain("CAPA-NUEVA: PREGUNTA-LITERAL");
    if (UNKNOWN_MARK.pictogram !== null) expect(unknown).toContain(`data-pictogram="${UNKNOWN_MARK.pictogram}"`);
  });

  it("un nivel se pinta con su insignia, y la parte sin nivel va sin ella", () => {
    const style = levelStyle("watch");
    const html = render(body([question()]));
    expect(html).toMatch(
      new RegExp(`<li>${markedHtml(style.pictogram ?? "", style.label, style.color, "level").source}</span> PARTE-CON-NIVEL</li>`),
    );
    expect(html).toContain("<li>PARTE-SIN-NIVEL</li>");
  });

  it("«nada que contar» lleva la marca de hecho y «no disponible» la gris, con la frase del backend", () => {
    const html = render(body([
      question({ key: "human", state: "nothing", answer: "NADA-QUE-CONTAR", items: [] }),
      question({ key: "habitat", state: "unavailable", answer: "SIN-FUENTE", items: [] }),
    ]));
    expect(html).toMatch(markedHtml(OK_MARK.pictogram ?? "", "NADA-QUE-CONTAR", OK_MARK.color));
    expect(html).toMatch(markedHtml(UNAVAILABLE_MARK.pictogram ?? "", "SIN-FUENTE", UNAVAILABLE_MARK.color));
  });

  it("sin respuesta del backend, la marca de la petición; y si falla después, lo de antes queda caducado", () => {
    const failed: RequestOutcome = { mark: FAILURE_MARK, text: "MOTIVO" };
    expect(render(null, failed)).toMatch(markedHtml("cross", "Sin datos: MOTIVO", "red"));
    expect(render(null)).toMatch(markedHtml("refresh", "Cargando…"));
    const stale = render(body([question()]), failed);
    expect(stale).toMatch(markedHtml("cross", "Sin datos: MOTIVO", "red"));
    expect(stale).toContain('<div data-twin="human" class="stale">');
  });

  it("la nota que dice el corte de Tierra es la del backend, tal cual", () => {
    const html = render({ ...body([question()]), until: "2026-12-09T23:40:00+00:00", note: "NOTA-DE-TIERRA" });
    expect(html).toContain("NOTA-DE-TIERRA");
  });
});

describe("en la consola de Tierra (§5.36.3)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("la petición lleva el corte, y sin corte no lleva ninguno", async () => {
    const urls: string[] = [];
    vi.stubGlobal("fetch", (url: string) => {
      urls.push(url);
      return Promise.resolve(new Response(JSON.stringify(body([])), { status: 200 }));
    });
    const cut = new Date("2026-12-09T23:40:00Z");
    await twinsApi.questions("crew-02", cut);
    await twinsApi.questions("crew-02");
    expect(urls).toEqual([
      `/api/twins?subject=crew-02&until=${encodeURIComponent(cut.toISOString())}`,
      "/api/twins?subject=crew-02",
    ]);
  });

  it("se monta con el corte del estado recibido y solo cuando a Tierra ha llegado algo", () => {
    const source = readFileSync(fileURLToPath(new URL("../ground/GroundConsole.tsx", import.meta.url)), "utf8");
    // El corte de toda la consola, una sola cuenta (§5.37.17).
    // Desde §5.47, con el enlace simulado: el corte por tiempo de luz pasado por `linkedCut`.
    expect(source).toMatch(/const cut = linkedCut\(groundCut\(status\.data\.reference_time, oneWay\), sync\);/);
    // Se vuelve a pedir también cuando el corte cambia de día (UTC): es el «hoy» del registro; la
    // clave es la compartida con la consola de tripulación (`twinsRefreshKey`, probada aparte).
    const mount = /\{received !== null && \(\s*<TwinQuestionsPanel\s+subject=\{status\.subject\}\s+until=\{cut\}\s+refreshKey=\{twinsRefreshKey\(received, cut\)\}/;
    expect(source).toMatch(mount);
  });

  it("la consola de tripulación pide con la misma clave, sin corte", () => {
    const crew = readFileSync(fileURLToPath(new URL("./CrewConsole.tsx", import.meta.url)), "utf8");
    expect(crew).toContain("<TwinQuestionsPanel subject={status.subject} refreshKey={twinsRefreshKey(status)} />");
  });
});
