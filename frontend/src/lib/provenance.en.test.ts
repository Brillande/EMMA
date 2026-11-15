/**
 * Los rótulos de `lib/` de la carcasa en inglés (`lib/i18n.ts`): tipo y entorno del dato, la palabra
 * de reserva del retardo, el aviso de otra persona delante y la banda de ayuda. Las claves (las de
 * la API) no cambian con el idioma.
 */
import "../test/english";

import { describe, expect, it } from "vitest";

import { commsStatusOf } from "./commsStatus";
import { PROPOSAL_TEXT, PROTECTED_TEXT, presenceText } from "./faceCompany";
import { LOCATING, withProvisional } from "./help";
import { UNREADABLE_CALIBRATION } from "./marks";
import { EVIDENCE_CONTEXTS, OBSERVATION_TYPES, OBSERVATION_TYPE_ORDER, contextLabel, typeStyle } from "./provenance";

describe("medido, inferido y predicho en inglés", () => {
  it("las tres palabras de la especificación, con las claves de siempre", () => {
    expect(OBSERVATION_TYPE_ORDER.map((type) => typeStyle(type).word)).toEqual(["MEASURED", "INFERRED", "PREDICTED"]);
    expect(Object.keys(OBSERVATION_TYPES)).toEqual(["measured", "inferred", "predicted"]);
    expect(typeStyle("predicted").meaning).toBe("projected into the future; not collected data");
  });

  it("cada entorno tiene nombre inglés", () => {
    expect(contextLabel("spaceflight")).toBe("actual spaceflight");
    expect(contextLabel("analog_bedrest")).toBe("analog: bed rest");
    expect(contextLabel("ground")).toBe("Earth");
    expect(contextLabel("iss")).toBe("ISS");
    for (const label of Object.values(EVIDENCE_CONTEXTS)) expect(label).not.toMatch(/[áéíóúñ]/);
  });
});

describe("el resto de la carcasa", () => {
  it("sin estado del backend, el retardo que falta se dice en inglés", () => {
    const fallback = commsStatusOf({ comms: null });
    expect(fallback.state).toBe("missing");
    expect(fallback.word).toBe("No ephemeris");
    expect(fallback.text).toBe("No ephemeris");
  });

  it("la palabra del backend no se toca", () => {
    const given = { state: "missing", source: null, source_text: null, word: "PALABRA", text: "FRASE", discrepancy: null };
    expect(commsStatusOf({ comms: null, comms_status: given } as never).word).toBe("PALABRA");
  });

  it("el aviso de otra persona delante, el que se ve y el que oye el lector", () => {
    expect(presenceText("proposed")).toBe(PROPOSAL_TEXT);
    expect(PROPOSAL_TEXT).toContain("shall I turn privacy on?");
    expect(presenceText("protected")).toBe(PROTECTED_TEXT);
    expect(PROTECTED_TEXT).toContain("I have turned privacy on");
  });

  it("la petición de ayuda recién firmada dice que se está localizando", () => {
    expect(LOCATING).toBe("locating…");
    const detail = { ledger_index: 7, subject: "crew-02", signed_by: "", at: "2026-11-15T10:00:00Z", signed_at: "2026-11-15T10:00:00Z" };
    expect(withProvisional(null, detail, "Urgent help").open[0]?.location_display).toBe("locating…");
  });

  it("lo que se compara con un texto del backend sigue en castellano", () => {
    expect(UNREADABLE_CALIBRATION).toBe("calibración del estudio ilegible");
  });
});
