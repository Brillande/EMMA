import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { DisplayControls, VoiceToggle } from "../components/DisplayControls";
import { DEFAULT_MODES, parseModes } from "../components/displayModes";
import { ReadAloud, type Speaker, VoiceAvailabilityContext } from "../components/ReadAloud";
import type { Alert } from "./alerts";
import { formatNumber } from "./format";
import {
  type KeyLike,
  type SpokenAlert,
  type VoiceLike,
  newAlertSpeech,
  newAlerts,
  pickVoice,
  spokenAlert,
  statusSpeech,
  voiceAvailability,
  voiceShortcut,
} from "./speech";
import { UI_PICTOGRAMS } from "./uiMarks";

/**
 * La voz propia (§5.40) sin navegador: qué voz se elige (solo locales), qué se lee (las frases del
 * backend con rótulos de navegación y nada más), qué alertas son nuevas, a qué teclas responde y
 * cómo se pinta el mando, con voz y sin ella.
 */

const voice = (name: string, lang: string, localService: boolean, isDefault = false): VoiceLike => ({
  name,
  lang,
  localService,
  default: isDefault,
});

describe("la voz que se elige", () => {
  it("nunca una en línea, aunque sea la única en español y la de por defecto", () => {
    const online = voice("Google español", "es-ES", false, true);
    expect(pickVoice([online])).toBeNull();
    const local = voice("Microsoft Zira", "en-US", true);
    expect(pickVoice([online, local])).toBe(local);
  });

  it("de las locales, una en español; la de por defecto si la hay", () => {
    const english = voice("Zira", "en-US", true, true);
    const helena = voice("Helena", "es-ES", true);
    const sabina = voice("Sabina", "es-MX", true, true);
    expect(pickVoice([english, helena])).toBe(helena);
    expect(pickVoice([english, helena, sabina])).toBe(sabina);
    // `es_ES` (Android) y `es` a secas también son español; `est` (estonio) no.
    expect(pickVoice([english, voice("A", "es_ES", true)])?.name).toBe("A");
    expect(pickVoice([english, voice("B", "es", true)])?.name).toBe("B");
    expect(pickVoice([voice("C", "et-EE", true), voice("D", "est", true)])?.name).toBe("C");
  });

  it("sin API, sin voces o sin voces locales, no disponible y con su motivo", () => {
    expect(voiceAvailability(null)).toBe("no-api");
    expect(voiceAvailability([])).toBe("no-local-voice");
    expect(voiceAvailability([voice("Google", "es-ES", false)])).toBe("no-local-voice");
    expect(voiceAvailability([voice("Helena", "es-ES", true)])).toBe("ready");
  });
});

const SUMMARY = "Atención en el dominio Sueño (PALABRA-C) y 1 dominio(s) más bajo vigilancia.";
const DRIVER_A = "Sueño total 5,1 h, -18 % frente a su línea base";
const DRIVER_B = "PVT: lapsos al alza.";

const ALERTS: SpokenAlert[] = [
  { id: "sleep:concern", level: "PALABRA-C", domain: "Sueño", drivers: [DRIVER_A, DRIVER_B], silenced: null },
  { id: "cardio:watch", level: "PALABRA-W", domain: "Cardiovascular", drivers: [], silenced: "Suprimida" },
];

describe("lo que se lee", () => {
  const read = (privacy: boolean, alerts = ALERTS) =>
    statusSpeech({ console: "Consola de tripulación", subject: "crew-02", summary: SUMMARY, alerts, privacy });

  it("el resumen y los motivos tal cual del backend, en un trozo por alerta", () => {
    const chunks = read(false);
    expect(chunks).toHaveLength(4);
    expect(chunks[0]).toBe(`Consola de tripulación, tripulante crew-02. Estado: ${SUMMARY}`);
    expect(chunks[1]).toBe("Alertas activas: 2.");
    expect(chunks[2]).toBe(`PALABRA-C, Sueño. ${DRIVER_A}. ${DRIVER_B}`);
    expect(chunks[3]).toBe("PALABRA-W, Cardiovascular. Suprimida.");
  });

  it("la interfaz no redacta: quitadas las frases del backend y las palabras de la fila, solo quedan rótulos", () => {
    let rest = read(false).join(" ");
    for (const given of [SUMMARY, DRIVER_A, DRIVER_B, "PALABRA-C", "PALABRA-W", "Sueño", "Cardiovascular"]) {
      rest = rest.split(given).join(" ");
    }
    const words = rest.split(/[\s.,:]+/).filter((word) => word !== "");
    expect(words).toEqual([
      "Consola", "de", "tripulación", "tripulante", "crew-02", "Estado", "Alertas", "activas", "2", "Suprimida",
    ]);
  });

  it("con la privacidad no se dice de quién es, y las alertas se leen igual (no se callan)", () => {
    const chunks = read(true);
    expect(chunks.join(" ")).not.toContain("crew-02");
    expect(chunks.join(" ")).not.toContain("tripulante");
    expect(chunks[0]).toBe(`Consola de tripulación. Estado: ${SUMMARY}`);
    expect(chunks.slice(1)).toEqual(read(false).slice(1));
  });

  it("sin alertas lo dice con la cifra, y la cifra pasa por format.ts", () => {
    expect(read(false, [])).toEqual([
      `Consola de tripulación, tripulante crew-02. Estado: ${SUMMARY}`,
      "Alertas activas: 0.",
    ]);
    const many = Array.from({ length: 1200 }, (_, index) => ({ ...ALERTS[1]!, id: `d${index}:watch` }));
    expect(read(false, many)[1]).toBe(`Alertas activas: ${formatNumber(1200)}.`);
  });

  it("el aviso de una alerta nueva: el rótulo y la alerta", () => {
    expect(newAlertSpeech(ALERTS[0]!)).toBe(`Alerta nueva: PALABRA-C, Sueño. ${DRIVER_A}. ${DRIVER_B}`);
  });

  it("la alerta a leer lleva las palabras de su fila", () => {
    const alert: Alert = { id: "sleep:concern", domain: "sleep", level: "concern", drivers: [DRIVER_A] };
    const label = (level: string) => `L-${level}`;
    const domain = (key: string) => `D-${key}`;
    expect(spokenAlert(alert, label, domain, undefined)).toEqual({
      id: "sleep:concern",
      level: "L-concern",
      domain: "D-sleep",
      drivers: [DRIVER_A],
      silenced: null,
    });
    expect(spokenAlert(alert, label, domain, "normal").silenced).toBeNull();
    expect(spokenAlert(alert, label, domain, "suppressed").silenced).toBe("Suprimida");
    expect(spokenAlert(alert, label, domain, "inhibited").silenced).toBe("Inhibida");
  });
});

describe("qué alertas son nuevas", () => {
  const sleep = ALERTS[0]!;
  const quiet = ALERTS[1]!;
  const cardioUp: SpokenAlert = { ...sleep, id: "cardio:concern", domain: "Cardiovascular" };

  it("la primera vez no se anuncia nada: lo de ahora queda como visto", () => {
    const first = newAlerts(null, [sleep]);
    expect(first.announce).toEqual([]);
    expect([...first.seen]).toEqual(["sleep:concern"]);
  });

  it("cada alerta nueva se anuncia una vez", () => {
    const first = newAlerts(new Set(), [sleep]);
    expect(first.announce).toEqual([sleep]);
    const again = newAlerts(first.seen, [sleep]);
    expect(again.announce).toEqual([]);
    const third = newAlerts(again.seen, [sleep, cardioUp]);
    expect(third.announce).toEqual([cardioUp]);
  });

  it("la que sube de nivel es otra alerta y se anuncia; la que vuelve tras irse, también", () => {
    const higher = { ...sleep, id: "sleep:critical" };
    expect(newAlerts(new Set(["sleep:concern"]), [higher]).announce).toEqual([higher]);
    const gone = newAlerts(new Set(["sleep:concern"]), []);
    expect(gone.seen.size).toBe(0);
    expect(newAlerts(gone.seen, [sleep]).announce).toEqual([sleep]);
  });

  it("la silenciada no se anuncia ni queda vista: al habilitarla se anuncia", () => {
    const silenced = newAlerts(new Set(), [quiet]);
    expect(silenced.announce).toEqual([]);
    expect(silenced.seen.has(quiet.id)).toBe(false);
    const enabled = { ...quiet, silenced: null };
    expect(newAlerts(silenced.seen, [enabled]).announce).toEqual([enabled]);
  });
});

describe("las teclas", () => {
  const key = (code: string, extra: Partial<KeyLike> = {}): KeyLike => ({
    code,
    key: code.replace(/^Key/, ""),
    altKey: true,
    shiftKey: true,
    ctrlKey: false,
    metaKey: false,
    ...extra,
  });

  it("Alt + Mayús + L lee, o para si ya habla; Alt + Mayús + R repite", () => {
    expect(voiceShortcut(key("KeyL"), false)).toBe("read");
    expect(voiceShortcut(key("KeyL"), true)).toBe("stop");
    expect(voiceShortcut(key("KeyR"), false)).toBe("repeat");
    // Por la tecla física: con Alt y Mayús, `key` cambia con la distribución del teclado.
    expect(voiceShortcut(key("KeyL", { key: "¬" }), false)).toBe("read");
  });

  it("sin los dos modificadores, o con Control o Meta, nada", () => {
    expect(voiceShortcut(key("KeyL", { shiftKey: false }), false)).toBeNull();
    expect(voiceShortcut(key("KeyL", { altKey: false }), false)).toBeNull();
    expect(voiceShortcut(key("KeyL", { ctrlKey: true }), false)).toBeNull();
    expect(voiceShortcut(key("KeyL", { metaKey: true }), false)).toBeNull();
    expect(voiceShortcut(key("KeyX"), false)).toBeNull();
  });

  it("en un campo de texto las letras no cuentan (pueden escribir un carácter); Escape sí", () => {
    expect(voiceShortcut(key("KeyL"), false, true)).toBeNull();
    expect(voiceShortcut(key("KeyR"), true, true)).toBeNull();
    const escape = key("Escape", { key: "Escape", altKey: false, shiftKey: false });
    expect(voiceShortcut(escape, true, true)).toBe("stop");
  });

  it("Escape para la voz solo si habla: si no, es de quien lo tenga", () => {
    const escape = key("Escape", { key: "Escape", altKey: false, shiftKey: false });
    expect(voiceShortcut(escape, true)).toBe("stop");
    expect(voiceShortcut(escape, false)).toBeNull();
  });
});

describe("el modo voz se guarda con los demás", () => {
  it("lo guardado antes de existir la voz se lee igual, con la voz apagada", () => {
    const old = JSON.stringify({ lowVision: true, essential: false, privacy: true, rotation: 90 });
    expect(parseModes(old)).toEqual({ lowVision: true, essential: false, privacy: true, voice: false, proactive: false, rotation: 90, followSensor: false, followFace: false, wakeWord: false, highContrast: false, autoPrivacy: false });
    expect(DEFAULT_MODES.voice).toBe(false);
  });

  it("se lee puesta, y un valor que no es booleano queda apagado", () => {
    expect(parseModes(JSON.stringify({ voice: true })).voice).toBe(true);
    expect(parseModes(JSON.stringify({ voice: "sí" })).voice).toBe(false);
  });
});

const html = (element: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(element);

const speaker = (patch: Partial<Speaker> = {}): Speaker => ({
  availability: "ready",
  speaking: false,
  canRepeat: false,
  say: () => undefined,
  stop: () => undefined,
  repeat: () => undefined,
  ...patch,
});

describe("el mando de la cabecera", () => {
  it("con voz: «Leer en voz alta» con su atajo y «Repetir», que espera a que haya algo leído", () => {
    const out = html(createElement(ReadAloud, { speaker: speaker(), read: ["x"] }));
    expect(out).toContain("Leer en voz alta");
    expect(out).toContain('aria-keyshortcuts="Alt+Shift+L"');
    expect(out).toContain(`data-pictogram="${UI_PICTOGRAMS.voice}"`);
    expect(out).toMatch(/aria-keyshortcuts="Alt\+Shift\+R" disabled=""/);
    expect(out).toContain("Alt+Mayús+L");
  });

  it("mientras habla, «Parar la voz»; sin nada que leer, leer queda desactivado", () => {
    const speaking = html(createElement(ReadAloud, { speaker: speaker({ speaking: true, canRepeat: true }), read: ["x"] }));
    expect(speaking).toContain("Parar la voz");
    expect(speaking).toContain(`data-pictogram="${UI_PICTOGRAMS.stopVoice}"`);
    expect(speaking).not.toContain("Leer en voz alta");
    const empty = html(createElement(ReadAloud, { speaker: speaker(), read: [] }));
    expect(empty).toMatch(/disabled="">.*Leer en voz alta/);
  });

  it("sin voz, la marca gris de «no disponible» con el motivo, y ningún mando", () => {
    for (const availability of ["no-api", "no-local-voice"] as const) {
      const out = html(createElement(ReadAloud, { speaker: speaker({ availability }), read: ["x"] }));
      expect(out).toContain("Voz no disponible");
      expect(out).toContain('class="mark c-gray"');
      expect(out).toContain('data-pictogram="slash-circle"');
      expect(out).not.toContain("<button");
    }
  });

  it("en los mandos de pantalla, sin API de voz (node), el modo voz también se declara no disponible", () => {
    const toggle = html(createElement(VoiceToggle, { on: true, onChange: () => undefined }));
    expect(toggle).toContain("Voz no disponible: este navegador no tiene síntesis de voz");
    expect(toggle).not.toContain("<button");
    expect(html(createElement(DisplayControls))).toContain("Voz no disponible");
  });

  it("con voz (la misma fuente que la franja, por contexto), el modo voz es un mando con su estado", () => {
    const toggle = (on: boolean) =>
      html(
        createElement(
          VoiceAvailabilityContext.Provider,
          { value: "ready" },
          createElement(VoiceToggle, { on, onChange: () => undefined }),
        ),
      );
    expect(toggle(true)).toContain('aria-pressed="true"');
    expect(toggle(false)).toContain('aria-pressed="false"');
    expect(toggle(true)).toContain("Voz: leer cada alerta nueva");
    expect(toggle(true)).not.toContain("no disponible");
  });
});

describe("nada sale a la red", () => {
  it("la voz no hace peticiones: ni fetch ni XMLHttpRequest ni URLs", () => {
    for (const file of ["./speech.ts", "../components/ReadAloud.tsx"]) {
      const source = readFileSync(fileURLToPath(new URL(file, import.meta.url)), "utf8");
      const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
      expect(code, file).not.toMatch(/fetch\(|XMLHttpRequest|https?:|WebSocket|sendBeacon/);
    }
  });
});
