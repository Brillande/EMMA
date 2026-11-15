/**
 * La palabra «EMMA» con la interfaz en inglés (`machine.ts`, `listener.ts`): qué gramática se le da
 * a Vosk, qué frase apaga, qué modelo se pide y qué dice el rótulo. Lo que se prueba aquí es la
 * lógica; que el modelo inglés reconozca de verdad «EMMA» está SIN VERIFICAR (no está en el
 * repositorio) y ninguna prueba de este fichero lo afirma.
 */
import "../../test/english";

import { describe, expect, it } from "vitest";

import { MODEL_PATH, MODEL_PATH_EN, MODEL_URL, modelPath, startsLikeGzip } from "./listener";
import {
  ENGLISH_WAKE_FORMS,
  GRAMMAR,
  OFF,
  STOP_PHRASE,
  WAKE_VOCABULARY,
  WAKE_WORD,
  type WakeState,
  heardStop,
  heardWakeWord,
  step,
  stopPhrases,
  wakeGrammar,
  wakeLabel,
} from "./machine";

describe("la gramática por idioma", () => {
  it("la castellana es la de siempre, tal cual", () => {
    expect(wakeGrammar("es")).toEqual([...GRAMMAR]);
    expect(wakeGrammar("es")).toEqual(["emma", "emma deja de escuchar", "[unk]"]);
    expect(stopPhrases("es")).toEqual([STOP_PHRASE]);
    expect(WAKE_VOCABULARY.es.wake).toEqual([WAKE_WORD]);
  });

  it("la inglesa se construye igual: las formas de la palabra, las frases de apagar y [unk]", () => {
    expect(ENGLISH_WAKE_FORMS).toContain("emma");
    expect(stopPhrases("en")).toEqual(ENGLISH_WAKE_FORMS.map((form) => `${form} stop listening`));
    expect(wakeGrammar("en")).toEqual([...ENGLISH_WAKE_FORMS, ...stopPhrases("en"), "[unk]"]);
    // Sin argumento, la del idioma de la interfaz.
    expect(wakeGrammar()).toEqual(wakeGrammar("en"));
    expect(stopPhrases()).toContain("emma stop listening");
  });

  it("cada entrada es lo que Vosk admite: palabras en minúsculas separadas por un espacio", () => {
    for (const lang of ["es", "en"] as const) {
      for (const entry of wakeGrammar(lang)) {
        if (entry !== "[unk]") expect(entry, entry).toMatch(/^[a-z]+(?: [a-z]+)*$/);
      }
      expect(new Set(wakeGrammar(lang)).size).toBe(wakeGrammar(lang).length);
    }
  });
});

describe("lo oído, en inglés", () => {
  it("la palabra, sola o con algo más; no como trozo de otra", () => {
    expect(heardWakeWord("emma")).toBe(true);
    expect(heardWakeWord("[unk] emma [unk]")).toBe(true);
    expect(heardWakeWord("Emma, stop listening")).toBe(true);
    expect(heardWakeWord("[unk]")).toBe(false);
    expect(heardWakeWord("dilemma")).toBe(false);
    expect(heardWakeWord("")).toBe(false);
  });

  it("«EMMA, stop listening» apaga; la frase castellana, con la interfaz en inglés, no", () => {
    expect(heardStop("emma stop listening")).toBe(true);
    expect(heardStop("[unk] Emma, stop listening.")).toBe(true);
    expect(heardStop("emma stop")).toBe(false);
    expect(heardStop("stop listening")).toBe(false);
    expect(heardStop("stop listening emma")).toBe(false);
    expect(heardStop("emma deja de escuchar")).toBe(false);
  });

  it("la máquina: la palabra abre la grabación y la frase de apagar apaga, también a media frase", () => {
    const listening: WakeState = { kind: "listening", armed: true };
    expect(step(listening, { type: "heard", text: "emma", final: false })).toEqual({ kind: "recording", settled: false });
    expect(step(listening, { type: "heard", text: "emma stop listening", final: true })).toEqual(OFF);
    expect(step({ kind: "recording", settled: false }, { type: "heard", text: "emma stop listening", final: true })).toEqual(OFF);
    // La voz propia diciendo «Hello, I am EMMA» no abre nada.
    expect(step(listening, { type: "heard", text: "emma", final: false, speaking: true })).toEqual({
      kind: "listening",
      armed: false,
    });
  });
});

describe("el modelo que se pide", () => {
  it("uno por idioma, del propio paquete; el castellano no cambia", () => {
    expect(modelPath("es")).toBe(MODEL_PATH);
    expect(MODEL_PATH).toBe("vosk/vosk-model-small-es-0.42.tar.gz");
    expect(modelPath("en")).toBe(MODEL_PATH_EN);
    expect(MODEL_PATH_EN).toBe("vosk/vosk-model-small-en-us-0.15.tar.gz");
    expect(modelPath()).toBe(MODEL_PATH_EN);
    expect(MODEL_URL.endsWith(MODEL_PATH_EN)).toBe(true);
    expect(MODEL_URL).not.toMatch(/^https?:/);
  });

  it("si falta, lo que contesta el origen no pasa por modelo: solo vale lo que empieza como un gzip", () => {
    expect(startsLikeGzip(new Uint8Array([0x1f, 0x8b, 0x08]))).toBe(true);
    expect(startsLikeGzip(new TextEncoder().encode("<!doctype html>"))).toBe(false);
    expect(startsLikeGzip(new Uint8Array([0x1f]))).toBe(false);
    expect(startsLikeGzip(new Uint8Array(0))).toBe(false);
  });
});

describe("el rótulo del modo", () => {
  it("cada estado, en inglés; el motivo se traduce y su clave no", () => {
    expect(wakeLabel(OFF)).toBe("");
    expect(wakeLabel({ kind: "loading" })).toBe("Preparing to listen");
    expect(wakeLabel({ kind: "listening", armed: true })).toBe(
      "Say “EMMA” and what you want; “EMMA, stop listening” turns it off",
    );
    expect(wakeLabel({ kind: "recording", settled: false })).toBe("I'm listening");
    expect(wakeLabel({ kind: "sending", settled: true })).toBe("Sending what was said to the assistant");
    const reasons = {
      "sin micrófono": "no microphone",
      "sin permiso": "no permission",
      "sin modelo": "no model",
      "sin audio del navegador": "no browser audio",
    } as const;
    for (const [reason, text] of Object.entries(reasons)) {
      expect(wakeLabel({ kind: "unavailable", reason: reason as keyof typeof reasons })).toBe(
        `Listening unavailable: ${text}`,
      );
    }
  });

  it("la frase de apagar que enseña el rótulo es la que la máquina entiende", () => {
    const shown = /“(EMMA, [^”]+)”/.exec(wakeLabel({ kind: "listening", armed: true }))?.[1] ?? "";
    expect(heardStop(shown)).toBe(true);
  });
});
