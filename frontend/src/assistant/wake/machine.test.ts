import { describe, expect, it } from "vitest";

import {
  GRAMMAR,
  OFF,
  SILENCE,
  type WakeEvent,
  type WakeState,
  heardStop,
  heardWakeWord,
  microphoneOpen,
  readVoskResult,
  rms,
  sameState,
  silenceTracker,
  step,
  wakeAllowed,
  wakeLabel,
} from "./machine";

/** Manos libres con «EMMA»: lo que se decide sin navegador. */

const run = (events: WakeEvent[], from: WakeState = OFF) => events.reduce(step, from);
const partial = (text: string, speaking = false): WakeEvent => ({ type: "heard", text, final: false, speaking });
const final = (text: string, speaking = false): WakeEvent => ({ type: "heard", text, final: true, speaking });
const LISTENING = run([{ type: "enable" }, { type: "ready" }]);

describe("la máquina de estados", () => {
  it("apagado, cargando y escuchando la palabra; sin nada que la active no graba", () => {
    expect(step(OFF, { type: "enable" })).toEqual({ kind: "loading" });
    expect(LISTENING).toEqual({ kind: "listening", armed: true });
    expect(run([partial("[unk]"), final("[unk] [unk]")], LISTENING)).toEqual({ kind: "listening", armed: true });
    // Lo que no sea encender, en apagado, no hace nada.
    expect(run([partial("emma"), { type: "ready" }])).toEqual(OFF);
  });

  it("la palabra abre la grabación; el silencio la cierra y la manda; al acabar vuelve a escuchar", () => {
    const recording = step(LISTENING, partial("emma"));
    expect(recording).toEqual({ kind: "recording", settled: false });
    const settled = step(recording, final("emma [unk]"));
    expect(settled).toEqual({ kind: "recording", settled: true });
    const sending = step(settled, { type: "phrase", outcome: "end" });
    expect(sending).toEqual({ kind: "sending", settled: true });
    expect(step(sending, { type: "sent" })).toEqual({ kind: "listening", armed: true });
  });

  it("los parciales de la misma frase no abren otra grabación hasta su final", () => {
    // Grabación cerrada antes de que llegara el final de Vosk: queda desarmada.
    const after = run([partial("emma"), { type: "phrase", outcome: "end" }, { type: "sent" }], LISTENING);
    expect(after).toEqual({ kind: "listening", armed: false });
    expect(step(after, partial("emma"))).toEqual(after);
    const rearmed = step(after, final("emma"));
    expect(rearmed).toEqual({ kind: "listening", armed: true });
    expect(step(rearmed, partial("emma"))).toEqual({ kind: "recording", settled: false });
  });

  it("un final con la palabra que ningún parcial dio también abre la grabación, ya asentada", () => {
    expect(step(LISTENING, final("emma"))).toEqual({ kind: "recording", settled: true });
  });

  it("una frase vacía tras la palabra no se manda", () => {
    expect(run([partial("emma"), { type: "phrase", outcome: "empty" }], LISTENING)).toEqual({
      kind: "listening",
      armed: false,
    });
  });

  it("«EMMA, deja de escuchar» apaga, escuchando, grabando o enviando", () => {
    expect(step(LISTENING, final("emma deja de escuchar"))).toEqual(OFF);
    const recording = step(LISTENING, partial("emma deja"));
    expect(step(recording, final("emma deja de escuchar"))).toEqual(OFF);
    const sending = run([partial("emma"), { type: "phrase", outcome: "end" }], LISTENING);
    expect(step(sending, final("emma deja de escuchar"))).toEqual(OFF);
    // Solo el final: un parcial puede cambiar todavía.
    expect(step(recording, partial("emma deja de escuchar"))).toEqual(recording);
  });

  it("apagar gana siempre; no disponible se queda así hasta apagar", () => {
    for (const state of [LISTENING, step(LISTENING, partial("emma")), { kind: "loading" } as const]) {
      expect(step(state, { type: "disable" })).toEqual(OFF);
    }
    const unavailable = step({ kind: "loading" }, { type: "unavailable", reason: "sin permiso" });
    expect(unavailable).toEqual({ kind: "unavailable", reason: "sin permiso" });
    expect(run([{ type: "ready" }, partial("emma"), { type: "enable" }], unavailable)).toEqual(unavailable);
    expect(step(unavailable, { type: "disable" })).toEqual(OFF);
  });

  it("mientras habla la voz propia, ni la palabra ni la frase de apagar cuentan", () => {
    // «Hola, soy EMMA», dicho por el altavoz: no abre nada y desarma.
    expect(step(LISTENING, partial("emma", true))).toEqual({ kind: "listening", armed: false });
    expect(step(LISTENING, final("emma deja de escuchar", true))).toEqual({ kind: "listening", armed: true });
    // Su final llega cuando ya calló: cierra la frase sin abrir grabación.
    const after = step(LISTENING, partial("emma", true));
    expect(step(after, final("emma"))).toEqual({ kind: "listening", armed: true });
  });

  it("si la voz propia empieza a hablar con la grabación abierta, la grabación se tira", () => {
    const recording = step(LISTENING, partial("emma"));
    expect(step(recording, { type: "speaking" })).toEqual({ kind: "listening", armed: false });
    // Lo que diga la voz durante la grabación o el envío no cambia nada.
    const sending = step(recording, { type: "phrase", outcome: "end" });
    expect(step(sending, final("emma deja de escuchar", true))).toEqual(sending);
  });

  it("un resultado que no cambia nada da el mismo estado: la consola no se repinta", () => {
    expect(sameState(step(LISTENING, partial("[unk]")), LISTENING)).toBe(true);
    expect(sameState(step(LISTENING, final("[unk]")), LISTENING)).toBe(true);
    expect(sameState(LISTENING, { kind: "listening", armed: false })).toBe(false);
    const recording = step(LISTENING, partial("emma"));
    expect(sameState(step(recording, partial("emma [unk]")), recording)).toBe(true);
    expect(sameState(step(recording, final("emma")), recording)).toBe(false);
    expect(sameState({ kind: "recording", settled: true }, { kind: "sending", settled: true })).toBe(false);
    expect(sameState(OFF, { kind: "off" })).toBe(true);
  });

  it("el micrófono está abierto escuchando, grabando y enviando; no apagado, cargando ni sin él", () => {
    expect(microphoneOpen(LISTENING)).toBe(true);
    expect(microphoneOpen({ kind: "recording", settled: false })).toBe(true);
    expect(microphoneOpen({ kind: "sending", settled: false })).toBe(true);
    expect(microphoneOpen(OFF)).toBe(false);
    expect(microphoneOpen({ kind: "loading" })).toBe(false);
    expect(microphoneOpen({ kind: "unavailable", reason: "sin modelo" })).toBe(false);
  });

  it("los rótulos son de navegación, con el motivo cuando no hay escucha", () => {
    expect(wakeLabel({ kind: "recording", settled: false })).toBe("Te escucho");
    expect(wakeLabel({ kind: "unavailable", reason: "sin audio del navegador" })).toBe("Escucha no disponible: sin audio del navegador");
    expect(wakeLabel(LISTENING)).toContain("«EMMA, deja de escuchar» lo apaga");
  });
});

describe("el resultado de Vosk", () => {
  it("la gramática solo sabe la palabra, la frase de apagar y lo desconocido", () => {
    expect(GRAMMAR).toEqual(["emma", "emma deja de escuchar", "[unk]"]);
  });

  it("se lee el parcial y el final; cualquier otra forma no es nada", () => {
    expect(readVoskResult({ event: "partialresult", result: { partial: "emma" } })).toEqual({ text: "emma", final: false });
    expect(readVoskResult({ event: "result", result: { text: "emma", result: [] } })).toEqual({ text: "emma", final: true });
    for (const bad of [null, undefined, "emma", {}, { result: null }, { result: { partial: 1 } }]) {
      expect(readVoskResult(bad)).toBeNull();
    }
  });

  it("la palabra cuenta sola o con más, en cualquier caja; [unk] y palabras parecidas no", () => {
    expect(heardWakeWord("emma")).toBe(true);
    expect(heardWakeWord("[unk] EMMA [unk]")).toBe(true);
    expect(heardWakeWord("Emma, abre")).toBe(true);
    expect(heardWakeWord("[unk]")).toBe(false);
    expect(heardWakeWord("")).toBe(false);
    expect(heardWakeWord("emmanuel")).toBe(false);
    expect(heardWakeWord("ema")).toBe(false);
  });

  it("la frase de apagar va entera y seguida", () => {
    expect(heardStop("emma deja de escuchar")).toBe(true);
    expect(heardStop("[unk] emma deja de escuchar [unk]")).toBe(true);
    expect(heardStop("emma deja de")).toBe(false);
    expect(heardStop("emma [unk] deja de escuchar")).toBe(true);
    expect(heardStop("deja de escuchar")).toBe(false);
    expect(heardStop("emma deja de escuchar")).toBe(heardStop("EMMA, deja de escuchar."));
  });
});

describe("el detector de silencio", () => {
  const voice = 0.1;
  const quiet = 0.001;

  it("la energía es la raíz cuadrática media", () => {
    expect(rms([])).toBe(0);
    expect(rms([0.5, -0.5, 0.5, -0.5])).toBeCloseTo(0.5);
    expect(rms(new Float32Array(100))).toBe(0);
  });

  it("tras hablar, el silencio seguido cierra la frase; un ruido en medio vuelve a contar", () => {
    const tracker = silenceTracker();
    expect(tracker.push(voice, 500)).toBeNull();
    expect(tracker.push(quiet, 600)).toBeNull();
    expect(tracker.push(voice, 100)).toBeNull();
    expect(tracker.push(quiet, 900)).toBeNull();
    expect(tracker.push(quiet, 100)).toBe("end");
    // Cerrada, no vuelve a decir nada.
    expect(tracker.push(quiet, 5000)).toBeNull();
  });

  it("la cola de la propia palabra no cuenta como haber empezado a hablar", () => {
    // «EMMA» y una pausa para pensar: no se manda solo el final de la palabra.
    const tracker = silenceTracker();
    expect(tracker.push(voice, SILENCE.graceMs)).toBeNull();
    expect(tracker.push(quiet, 1500)).toBeNull();
    expect(tracker.push(voice, 800)).toBeNull();
    expect(tracker.push(quiet, 1000)).toBe("end");
    // Solo la palabra y nada más: no hay frase.
    const alone = silenceTracker();
    expect(alone.push(voice, SILENCE.graceMs)).toBeNull();
    expect(alone.push(quiet, SILENCE.leadMs)).toBe("empty");
  });

  it("si no llega a hablar en la espera, no hay frase", () => {
    const tracker = silenceTracker();
    expect(tracker.push(quiet, SILENCE.leadMs - 1)).toBeNull();
    expect(tracker.push(quiet, 1)).toBe("empty");
  });

  it("la frase se corta en el tope aunque siga hablando", () => {
    const tracker = silenceTracker();
    let outcome: string | null = null;
    for (let elapsed = 0; outcome === null && elapsed < 60_000; elapsed += 100) outcome = tracker.push(voice, 100);
    expect(outcome).toBe("end");
    expect(SILENCE.maxMs).toBe(10_000);
    expect(SILENCE.silenceMs).toBe(1000);
  });
});

describe("qué apaga el modo", () => {
  it("solo escucha con el modo puesto, sin privacidad y con la ventana a la vista", () => {
    expect(wakeAllowed({ wakeWord: true, privacy: false, visible: true })).toBe(true);
    expect(wakeAllowed({ wakeWord: false, privacy: false, visible: true })).toBe(false);
    expect(wakeAllowed({ wakeWord: true, privacy: true, visible: true })).toBe(false);
    expect(wakeAllowed({ wakeWord: true, privacy: false, visible: false })).toBe(false);
  });
});
