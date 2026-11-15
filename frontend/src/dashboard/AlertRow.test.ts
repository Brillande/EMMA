import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { spanWithPictogram, taggedPictogram, textLines } from "../advisor/visibleText";
import type { Alert } from "../lib/alerts";
import type { AlertState, CrewStatus } from "../lib/api";
import { type AlertActions, AlertRow } from "./AlertRow";

/*
 * Una alerta pintada (segunda pasada, §5.33.1): cada mando con el signo de su concepto
 * (`lib/uiMarks.ts`), el mismo dibujo que el estado que deja; el retardo con Tierra con el del
 * tiempo de luz, y sin efemérides la marca de dato ausente. El texto visible es el de antes.
 */

const alert: Alert = { id: "behavioral:watch", domain: "behavioral", level: "watch", drivers: ["frase del motor"] };

const status = (comms: CrewStatus["comms"]) =>
  ({
    data: { reference_time: "2026-11-13T04:00:00+00:00" },
    mission: { start: "2026-11-01" },
    comms,
  }) as unknown as CrewStatus;

const COMMS = { one_way_minutes: 14 } as unknown as NonNullable<CrewStatus["comms"]>;

const state = (over: Partial<AlertState>): AlertState =>
  ({
    annunciation: "normal",
    acknowledged: false,
    acknowledged_by: null,
    silenced_until: null,
    silenced_by: null,
    silenced_reason: null,
    ...over,
  }) as unknown as AlertState;

const actions = {} as AlertActions;

const render = (shown: AlertState | undefined, comms: CrewStatus["comms"] = COMMS, operator = "CDR") =>
  renderToStaticMarkup(createElement(AlertRow, { alert, state: shown, status: status(comms), operator, actions }));

const button = (pictogram: string, word: string) => taggedPictogram("button", pictogram, word, ' class="command"');

describe("los mandos de una alerta llevan el signo de su concepto", () => {
  it("sin reconocer: Reconocer con la pluma, Suprimir con la campana tachada, Inhibir con la campana en su marco", () => {
    const html = render(state({}));
    expect(html).toMatch(button("pen", "Reconocer"));
    expect(html).toMatch(button("bell-slash", "Suprimir…"));
    expect(html).toMatch(button("bell-box", "Inhibir…"));
  });

  it("reconocida: el estado con la pluma, y En arreglo con la llave del estado que dejará", () => {
    const html = render(state({ acknowledged: true, acknowledged_by: "CDR" }));
    expect(html).toMatch(spanWithPictogram("mark", "pen", "Reconocida por CDR"));
    expect(html).toMatch(spanWithPictogram("mark", "dot-ringed", "Detectada"));
    expect(html).toMatch(button("wrench", "En arreglo"));
    const repairing = render(
      state({ acknowledged: true, acknowledged_by: "CDR", resolution: { state: "en_arreglo" } }),
    );
    expect(repairing).toMatch(spanWithPictogram("mark", "wrench", "En arreglo"));
    expect(repairing).toMatch(button("check", "Resuelta"));
  });

  it("descartar (§5.37.6): el «no» de no adoptar, después de reconocer, y la alerta sigue con su nivel", () => {
    expect(render(state({}))).not.toContain("Descartar");
    const seen = render(state({ acknowledged: true, acknowledged_by: "CDR" }));
    expect(seen).toMatch(button("slash-circle", "Descartar…"));
    const dismissal = {
      reason: "sensor_artifact",
      reason_display: "artefacto del sensor",
      note: "electrodo suelto",
      declared_by: "CMO",
      ledger_index: 7,
      reference_time: "2026-11-13T04:00:00+00:00",
    };
    const dismissed = render(state({ acknowledged: true, acknowledged_by: "CDR", dismissal }));
    expect(dismissed).toMatch(spanWithPictogram("mark", "slash-circle", "Descartada"));
    expect(textLines(dismissed).join(" ")).toContain("Descartada por CMO: artefacto del sensor (electrodo suelto)");
    // Una ya descartada no vuelve a ofrecer descartar; la insignia sigue siendo la de su nivel.
    expect(dismissed).not.toContain("Descartar…");
    expect(dismissed).toContain("En arreglo");
    // Un «en arreglo» anterior al descarte no se enseña como vigente: lo último es el descarte.
    const afterRepair = render(
      state({ acknowledged: true, acknowledged_by: "CDR", resolution: { state: "en_arreglo", declared_by: "FE" }, dismissal }),
    );
    expect(afterRepair).not.toContain("(FE)");
    expect(afterRepair).toMatch(button("wrench", "En arreglo"));
    // Descartada sin reconocer: se dice igual, y sigue parpadeando hasta que alguien la reconozca.
    const unseen = render(state({ dismissal }));
    expect(unseen).toMatch(spanWithPictogram("mark", "slash-circle", "Descartada"));
    expect(unseen).toMatch(button("pen", "Reconocer"));
  });

  it("silenciada: Habilitar con la campana de las alertas", () => {
    const html = render(state({ annunciation: "suppressed", silenced_by: "CDR", silenced_reason: "sensor" }));
    expect(html).toMatch(spanWithPictogram("mark", "bell-slash", "Suprimida"));
    expect(html).toMatch(button("bell", "Habilitar…"));
  });

  it("sin tripulante en consola, los mandos siguen con su signo, deshabilitados", () => {
    expect(render(state({}), COMMS, "")).toMatch(
      taggedPictogram("button", "pen", "Reconocer", ' class="command" disabled=""'),
    );
  });
});

describe("con qué reglas se firmó cada decisión (§5.39.9)", () => {
  const same = { rules_version: "reglas@abc", same_as_today: true, text: "decidido con reglas@abc; misma versión que hoy" };
  const differs = {
    rules_version: "reglas@old",
    same_as_today: false,
    text: "decidido con reglas@old; distinta de la de hoy: reglas@abc hoy",
  };
  const none = { rules_version: null, same_as_today: null, text: "sin versión registrada: el asiento no la lleva" };

  it("la frase del backend va junto al reconocimiento, al estado declarado y al descarte, tal cual", () => {
    const html = render(
      state({
        acknowledged: true,
        acknowledged_by: "CDR",
        acknowledgement_rules: same,
        resolution: { state: "en_arreglo", declared_by: "FE", rules: differs },
      }),
    );
    const text = textLines(html).join(" ");
    expect(text).toContain(`Reconocida por CDR · ${same.text}`);
    expect(text).toContain(`En arreglo (FE) · ${differs.text}`);
    const dismissed = render(
      state({
        acknowledged: true,
        acknowledged_by: "CDR",
        acknowledgement_rules: none,
        dismissal: {
          reason: "sensor_artifact",
          reason_display: "artefacto del sensor",
          note: "",
          declared_by: "CMO",
          ledger_index: 7,
          reference_time: "2026-11-13T04:00:00+00:00",
          rules: none,
        },
      }),
    );
    expect(textLines(dismissed).join(" ")).toContain(`Descartada por CMO: artefacto del sensor · ${none.text}`);
    expect(textLines(dismissed).join(" ")).toContain(`Reconocida por CDR · ${none.text}`);
  });

  it("sin color: una versión distinta es información, no una señal", () => {
    const html = render(
      state({ acknowledged: true, acknowledged_by: "CDR", acknowledgement_rules: differs }),
    );
    expect(html).toMatch(new RegExp(`Reconocida por CDR</span> · ${differs.text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}</span>`));
    expect(html).not.toMatch(/c-(red|yellow|cyan)[^>]*>[^<]*decidido con/);
  });

  it("un estado sin la frase (una versión anterior del backend) se pinta como antes", () => {
    const html = render(state({ acknowledged: true, acknowledged_by: "CDR" }));
    expect(textLines(html).join(" ")).not.toContain("·  ·");
    expect(html).not.toContain("decidido con");
  });
});

describe("el retardo con Tierra", () => {
  it("con efemérides, el signo del tiempo de luz junto a la frase de siempre", () => {
    const html = render(undefined);
    expect(html).toMatch(/<p class="earth secondary"><span class="mark"><svg [^>]*data-pictogram="signal-arcs">/);
    expect(textLines(html)).toContain(
      "Tierra lo sabrá a MET 12/04:14:00 · su respuesta no puede llegar antes de MET 12/04:28:00",
    );
  });

  it("sin efemérides, la marca de dato ausente (cian con el anillo punteado), no solo el color", () => {
    const html = render(undefined, null);
    expect(html).toMatch(
      spanWithPictogram("mark c-cyan", "ring-dotted", "Sin efemérides: no se sabe cuándo lo verá Tierra."),
    );
    expect(html).not.toContain('class="earth c-cyan"');
  });

  it("con el enlace simulado caído no promete una hora: sale cuando se restablezca (lógica 6)", () => {
    const row = (sync: { state: "up" | "down" }) =>
      renderToStaticMarkup(
        createElement(AlertRow, { alert, state: undefined, status: status(COMMS), operator: "CDR", actions, sync }),
      );
    const down = row({ state: "down" });
    expect(down).toMatch(
      spanWithPictogram("mark c-cyan", "ring-dotted", "Enlace con Tierra caído: no se sabe cuándo lo verá Tierra."),
    );
    expect(textLines(down).join(" ")).not.toContain("Tierra lo sabrá a");
    // Arriba (o restablecido), la cuenta de siempre.
    expect(textLines(row({ state: "up" }))).toContain(
      "Tierra lo sabrá a MET 12/04:14:00 · su respuesta no puede llegar antes de MET 12/04:28:00",
    );
  });
});
