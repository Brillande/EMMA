import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import type { SensorBinding } from "../lib/api";
import {
  EMPTY_FORM,
  bindBody,
  bindingInstant,
  bindingRows,
  canBind,
  unbindBody,
} from "./sensorBindings";

const binding = (over: Partial<SensorBinding>): SensorBinding => ({
  source: "wearable-ble",
  source_display: "pulsómetro Bluetooth LE",
  device: "aa:bb",
  device_display: "aa:bb",
  crew: "crew-01",
  since: "2026-11-08T12:00:00+00:00",
  note: null,
  declared_by: "CDR",
  declarations: 1,
  ledger_index: 7,
  recorded: "2026-11-08T12:00:01+00:00",
  caveat: null,
  ...over,
});

describe("vínculo sensor-tripulante: lo que decide el panel", () => {
  it("enseña primero los del tripulante que se mira, y los demás sin perder ninguno", () => {
    const rows = bindingRows(
      {
        bindings: [
          binding({ crew: "crew-02", device: "zz" }),
          binding({ crew: "crew-01", device: "aa:bb" }),
          binding({ crew: "crew-02", source: "google-fit", device: null }),
        ],
      },
      "crew-01",
    );
    expect(rows.map((row) => [row.key, row.own])).toEqual([
      ["wearable-ble:aa:bb", true],
      ["wearable-ble:zz", false],
      ["google-fit:", false],
    ]);
    expect(bindingRows({ bindings: [] }, "crew-01")).toEqual([]);
  });

  it("solo se puede firmar con una fuente y con el nombre de quien declara", () => {
    expect(canBind(EMPTY_FORM, "CDR")).toBe(false);
    expect(canBind({ ...EMPTY_FORM, source: "google-fit" }, "  ")).toBe(false);
    expect(canBind({ ...EMPTY_FORM, source: "google-fit" }, undefined)).toBe(false);
    // El identificador y la nota son opcionales.
    expect(canBind({ ...EMPTY_FORM, source: "google-fit" }, "CDR")).toBe(true);
  });

  it("vincula al tripulante que se mira, y el identificador solo viaja si se escribió", () => {
    expect(
      bindBody({ source: "wearable-ble", device: " AA:BB ", note: " azul " }, "crew-02", " CDR ", "T"),
    ).toEqual({
      source: "wearable-ble",
      device: "AA:BB",
      action: "bind",
      crew: "crew-02",
      since: "T",
      note: "azul",
      declared_by: "CDR",
    });
    const whole = bindBody({ source: "google-fit", device: "  ", note: "" }, "crew-02", "CDR", "T");
    expect("device" in whole).toBe(false);
  });

  it("retirar es otra declaración del mismo dispositivo, sin tripulante", () => {
    const body = unbindBody(binding({}), " CDR ", "T");
    expect(body).toEqual({
      source: "wearable-ble",
      device: "aa:bb",
      action: "unbind",
      since: "T",
      note: "",
      declared_by: "CDR",
    });
    expect("crew" in body).toBe(false);
    expect("device" in unbindBody(binding({ device: null }), "CDR", "T")).toBe(false);
  });

  it("la declaración vale desde el instante de los datos; sin datos, desde ahora", () => {
    const now = new Date("2026-10-10T10:00:00Z");
    expect(bindingInstant("2026-11-08T12:00:00+00:00", now)).toBe("2026-11-08T12:00:00+00:00");
    expect(bindingInstant(null, now)).toBe("2026-10-10T10:00:00.000Z");
  });

  it("las acciones que manda son las que el backend sabe firmar", () => {
    const source = readFileSync(
      fileURLToPath(new URL("../../../backend/app/ingest/bindings.py", import.meta.url)),
      "utf-8",
    );
    expect(source).toContain('BIND = "bind"');
    expect(source).toContain('UNBIND = "unbind"');
  });

  it("el panel no pinta un vínculo de otro tripulante como un aviso ni redacta el rótulo", () => {
    const panel = readFileSync(
      fileURLToPath(new URL("./SensorBindingsPanel.tsx", import.meta.url)),
      "utf-8",
    );
    // El único color con significado es el del error de una petición, con la marca de lo que fue
    // (`requestOutcome`: rechazo en amarillo con el triángulo, caída en rojo con la cruz;
    // §5.34.14): ni una clase `c-*` ni un color escrito en el panel.
    expect(panel.match(/c-(yellow|red|blue|cyan|green)|color="(yellow|red|blue|cyan|green)"/g)).toBeNull();
    expect(panel.match(/<MarkOf mark=\{[A-Z_]+\}>/g)).toBeNull();
    expect(panel.match(/<MarkOf mark=\{[a-z.]+\}>/g)).toEqual(["<MarkOf mark={error.mark}>"]);
    // La fuente de cada dispositivo lleva su pictograma junto al nombre del backend, sin color.
    expect(panel).toContain("readingSourcePictogram(binding.source)");
    expect(panel).toContain("readingSourcePictogram(item.source)");
    // El rótulo y las explicaciones son del backend.
    for (const field of ["overview.label", "overview.note", "overview.device_basis",
      "overview.rule", "overview.scope", "overview.summary", "binding.caveat"]) {
      expect(panel).toContain(field);
    }
    expect(panel).not.toContain("declarado por una persona");
  });
});
