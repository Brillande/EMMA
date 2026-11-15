import { describe, expect, it } from "vitest";

import { BAND_SUBJECT, bandReply, deviceKey, frameFields, frameHex } from "./heartBand";

const view = (...bytes: number[]) => new DataView(Uint8Array.from(bytes).buffer);

describe("heartBand: la trama Heart Rate Measurement", () => {
  it("pasa la trama entera a hexadecimal, para que la interprete el backend", () => {
    expect(frameHex(view(0x10, 0x48, 0x00, 0x04))).toBe("10480004");
  });

  it("lee el pulso en uint8 y en uint16 según la bandera", () => {
    expect(frameFields(view(0x00, 72))?.heartRate).toBe(72);
    expect(frameFields(view(0x01, 0x2c, 0x01))?.heartRate).toBe(300);
    expect(frameFields(view(0x01, 0x2c))).toBeNull();
    expect(frameFields(view(0x00))).toBeNull();
  });

  it("lee todos los campos según las banderas del Bluetooth SIG", () => {
    // Solo pulso uint8, sin contacto informado.
    expect(frameFields(view(0x00, 72))).toEqual({
      heartRate: 72,
      rrMs: [],
      contact: "unsupported",
      energyKj: null,
    });
    // Contacto informado y presente; informado y ausente.
    expect(frameFields(view(0x06, 60))?.contact).toBe("detected");
    expect(frameFields(view(0x04, 60))?.contact).toBe("not_detected");
    // Pulso uint16 + energía (300 kJ) + dos R-R (1024 y 512 en 1/1024 s).
    expect(frameFields(view(0x19, 0x2c, 0x01, 0x2c, 0x01, 0x00, 0x04, 0x00, 0x02))).toEqual({
      heartRate: 300,
      rrMs: [1000, 500],
      contact: "unsupported",
      energyKj: 300,
    });
    // R-R sin energía, tras un pulso uint8; un byte suelto al final no es un intervalo.
    expect(frameFields(view(0x16, 72, 0x00, 0x04, 0x01))).toEqual({
      heartRate: 72,
      rrMs: [1000],
      contact: "detected",
      energyKj: null,
    });
  });

  it("no inventa campos de una trama más corta de lo que anuncia", () => {
    expect(frameFields(view(0x00))).toBeNull();
    expect(frameFields(view(0x01, 0x2c))).toBeNull();
    expect(frameFields(view(0x08, 72, 0x01))).toBeNull();
  });

  it("firma las lecturas para el tripulante real, no para uno simulado", () => {
    expect(BAND_SUBJECT).toBe("real-01");
  });

  it("lee la respuesta del backend, con o sin trama y variabilidad", () => {
    expect(
      bandReply({
        recorded: [4, 5],
        indicators: ["heart_rate", "rr_interval"],
        binding_notice: null,
        frame: { heart_rate: 61, rr_ms: [980.5, "x"], sensor_contact: "detected", energy_kj: null },
        hrv: { rmssd_ms: 42.1, sdnn_ms: 55 },
      }),
    ).toEqual({
      recorded: 2,
      frame: { heartRate: 61, rrMs: [980.5], contact: "detected", energyKj: null },
      hrv: { rmssdMs: 42.1, sdnnMs: 55 },
    });
    // Un backend que aún no da trama ni variabilidad: el panel sigue con lo suyo.
    expect(bandReply({ recorded: [], indicators: [] })).toEqual({ recorded: 0, frame: null, hrv: null });
    expect(bandReply({ recorded: [1], hrv: null, frame: { heart_rate: null } })).toEqual({
      recorded: 1,
      frame: null,
      hrv: null,
    });
    expect(bandReply(null)).toEqual({ recorded: null, frame: null, hrv: null });
  });

  it("da al dispositivo un identificador que el backend acepta", () => {
    expect(deviceKey("HW9 012345", "abc")).toBe("hw9-012345");
    expect(deviceKey(undefined, "XyZ+/=")).toBe("xyz-");
    expect(deviceKey("  ", "")).toBe("banda");
    expect(deviceKey("x".repeat(80), "a")).toHaveLength(64);
  });
});
