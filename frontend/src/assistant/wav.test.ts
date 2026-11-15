import { describe, expect, it } from "vitest";

import { WAV_RATE, downsample, encodeWav } from "./wav";

/** El WAV que se manda al reconocimiento local y el remuestreo a 16 kHz (`wav.ts`). */

async function bytes(blob: Blob): Promise<DataView> {
  return new DataView(await blob.arrayBuffer());
}

function text(view: DataView, offset: number, length: number): string {
  return String.fromCharCode(...Array.from({ length }, (_, index) => view.getUint8(offset + index)));
}

describe("encodeWav", () => {
  it("cabecera RIFF/WAVE de PCM de 16 bits, mono, con la frecuencia y los tamaños", async () => {
    const blob = encodeWav(new Float32Array([0, 0.5, -0.5, 1]), WAV_RATE);
    expect(blob.type).toBe("audio/wav");
    expect(blob.size).toBe(44 + 4 * 2);
    const view = await bytes(blob);
    expect(text(view, 0, 4)).toBe("RIFF");
    expect(view.getUint32(4, true)).toBe(36 + 8);
    expect(text(view, 8, 4)).toBe("WAVE");
    expect(text(view, 12, 4)).toBe("fmt ");
    expect(view.getUint32(16, true)).toBe(16);
    expect(view.getUint16(20, true)).toBe(1);
    expect(view.getUint16(22, true)).toBe(1);
    expect(view.getUint32(24, true)).toBe(16_000);
    expect(view.getUint32(28, true)).toBe(32_000);
    expect(view.getUint16(32, true)).toBe(2);
    expect(view.getUint16(34, true)).toBe(16);
    expect(text(view, 36, 4)).toBe("data");
    expect(view.getUint32(40, true)).toBe(8);
  });

  it("las muestras, con signo y recortadas a ±1", async () => {
    const view = await bytes(encodeWav(new Float32Array([0, 1, -1, 2, -3, 0.5]), 8000));
    const samples = Array.from({ length: 6 }, (_, index) => view.getInt16(44 + index * 2, true));
    expect(samples).toEqual([0, 32767, -32768, 32767, -32768, 16384]);
  });

  it("sin muestras, solo la cabecera; una frecuencia imposible es un error", () => {
    expect(encodeWav(new Float32Array([]), WAV_RATE).size).toBe(44);
    expect(() => encodeWav(new Float32Array([0]), 0)).toThrow(RangeError);
  });
});

describe("downsample", () => {
  it("de 48 kHz a 16 kHz: un tercio de muestras, cada una la media de su tramo", () => {
    const out = downsample(new Float32Array([0, 0.3, 0.6, 1, 1, 1, -1, -1, -1]), 48_000, 16_000);
    expect(out).toHaveLength(3);
    expect(out[0]).toBeCloseTo(0.3);
    expect(out[1]).toBeCloseTo(1);
    expect(out[2]).toBeCloseTo(-1);
  });

  it("44,1 kHz a 16 kHz conserva la duración", () => {
    const second = new Float32Array(44_100).fill(0.25);
    const out = downsample(second, 44_100, 16_000);
    expect(out.length).toBe(16_000);
    expect(out.every((value) => Math.abs(value - 0.25) < 1e-6)).toBe(true);
  });

  it("no sube la frecuencia: devuelve una copia", () => {
    const input = new Float32Array([0.1, 0.2]);
    const out = downsample(input, 16_000, 16_000);
    expect([...out]).toEqual([...input]);
    expect(out).not.toBe(input);
    expect(() => downsample(input, 0, 16_000)).toThrow(RangeError);
  });
});
