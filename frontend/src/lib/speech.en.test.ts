/**
 * La voz propia en inglés (`lib/i18n.ts`): la voz que se elige es del idioma de la interfaz, y los
 * rótulos de navegación que se dicen y se ven están en inglés. Lo demás (solo voces locales, qué
 * alertas son nuevas, las teclas) es lo de `speech.test.ts` y `emergencyVoice.test.ts`.
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { textNodes } from "../advisor/visibleText";
import { ReadAloud, type Speaker } from "../components/ReadAloud";
import type { Alert } from "./alerts";
import {
  BLOCKED_NOTICE,
  EMERGENCY_INTRO,
  NOTHING_TO_READ,
  NO_VOICE_NOTICE,
  emergencyPlan,
} from "./emergencyVoice";
import { ROUTINE_WORDS } from "./routineWords";
import {
  UNAVAILABLE_TEXT,
  type VoiceLike,
  newAlertSpeech,
  pickVoice,
  spokenAlert,
  statusSpeech,
  voiceAvailability,
} from "./speech";

const voice = (name: string, lang: string, localService: boolean, isDefault = false): VoiceLike => ({
  name,
  lang,
  localService,
  default: isDefault,
});

const SPANISH = /[áéíóúñ¿¡«»]/i;

describe("la voz que se elige con la interfaz en inglés", () => {
  it("una inglesa local antes que la española, aunque la española sea la del sistema", () => {
    const voices = [
      voice("Helena", "es-ES", true, true),
      voice("Zira", "en-US", true),
      voice("Hazel", "en-GB", true),
    ];
    expect(pickVoice(voices)?.name).toBe("Zira");
  });

  it("de las inglesas, la que el sistema marca por defecto; `en_US` y `en` a secas también valen", () => {
    expect(pickVoice([voice("Zira", "en-US", true), voice("Hazel", "en-GB", true, true)])?.name).toBe("Hazel");
    expect(pickVoice([voice("Helena", "es-ES", true), voice("Android", "en_US", true)])?.name).toBe("Android");
    expect(pickVoice([voice("Helena", "es-ES", true), voice("Plain", "EN", true)])?.name).toBe("Plain");
  });

  it("`eng` no es de otro idioma que empiece igual: `en` va seguido de guion o de nada", () => {
    expect(pickVoice([voice("Otra", "enx-XX", true), voice("Zira", "en-US", true)])?.name).toBe("Zira");
  });

  it("una inglesa «en línea» no se usa: el texto saldría del equipo", () => {
    const voices = [voice("Google US English", "en-US", false, true), voice("Helena", "es-ES", true)];
    expect(pickVoice(voices)?.name).toBe("Helena");
    expect(pickVoice([voice("Google US English", "en-US", false)])).toBeNull();
    expect(voiceAvailability([voice("Google US English", "en-US", false)])).toBe("no-local-voice");
  });

  it("sin ninguna inglesa, el mismo orden de siempre: la local por defecto o la primera", () => {
    expect(pickVoice([voice("Hedda", "de-DE", true), voice("Helena", "es-ES", true, true)])?.name).toBe("Helena");
    expect(pickVoice([voice("Hedda", "de-DE", true), voice("Helena", "es-ES", true)])?.name).toBe("Hedda");
    expect(pickVoice([])).toBeNull();
  });
});

describe("lo que se dice", () => {
  const alert: Alert = { id: "sleep:watch", domain: "sleep", level: "watch", drivers: ["Sleep 5 h"] };
  const spoken = spokenAlert(alert, () => "LEVEL", () => "Sleep", "suppressed");

  it("el estado: la consola, de quién es y cuántas alertas, con los rótulos en inglés", () => {
    const chunks = statusSpeech({
      console: "Crew console",
      subject: "crew-01",
      summary: "Backend summary",
      alerts: [],
      privacy: false,
    });
    expect(chunks).toEqual(["Crew console, crew member crew-01. Status: Backend summary.", "Active alerts: 0."]);
  });

  it("con la privacidad, sin el nombre", () => {
    const [head] = statusSpeech({ console: "Crew console", subject: "crew-01", summary: "S", alerts: [], privacy: true });
    expect(head).toBe("Crew console. Status: S.");
  });

  it("una alerta nueva y la palabra de la que está silenciada", () => {
    expect(spoken.silenced).toBe("Suppressed");
    expect(spokenAlert(alert, () => "L", () => "D", "inhibited").silenced).toBe("Inhibited");
    expect(newAlertSpeech(spoken)).toBe("New alert: LEVEL, Sleep. Suppressed. Sleep 5 h.");
  });

  it("los motivos de «no disponible» y las palabras de una medida que se debe", () => {
    expect(UNAVAILABLE_TEXT["no-api"]).toBe("Voice unavailable: this browser has no speech synthesis");
    expect(UNAVAILABLE_TEXT["no-local-voice"]).toBe("Voice unavailable: no voice is installed on this device");
    // Las claves son las de la API y no cambian con el idioma.
    expect(ROUTINE_WORDS).toEqual({ atrasada: "overdue", rota: "no good reading" });
  });
});

describe("el gesto de emergencia", () => {
  it("la frase fija, el «nada que leer» y los avisos, en inglés", () => {
    for (const text of [EMERGENCY_INTRO, NOTHING_TO_READ, NO_VOICE_NOTICE, BLOCKED_NOTICE]) {
      expect(text).not.toMatch(SPANISH);
      expect(text).not.toMatch(/Mayús|Narrador|Intro\b/);
    }
    expect(EMERGENCY_INTRO).toContain("Alt Shift L");
    expect(NO_VOICE_NOTICE).toContain("Windows Narrator");
    expect(emergencyPlan("ready", false, [])).toEqual({
      kind: "speak",
      enableVoice: true,
      chunks: [EMERGENCY_INTRO, "There is no status to read yet."],
    });
    expect(emergencyPlan("no-api", false, ["x"])).toEqual({ kind: "notice", text: NO_VOICE_NOTICE });
  });
});

describe("el mando de la franja", () => {
  const speaker = (overrides: Partial<Speaker> = {}): Speaker => ({
    availability: "ready",
    speaking: false,
    canRepeat: false,
    say: () => undefined,
    stop: () => undefined,
    repeat: () => undefined,
    ...overrides,
  });
  const render = (overrides: Partial<Speaker> = {}) =>
    renderToStaticMarkup(createElement(ReadAloud, { speaker: speaker(overrides), read: ["x"] }));

  it("los mandos y los atajos, en inglés; las teclas con su nombre inglés", () => {
    const markup = render();
    const text = textNodes(markup);
    expect(markup).toContain('role="group" aria-label="Voice"');
    for (const label of ["Read aloud", "Repeat", "Shortcuts"]) expect(text).toContain(label);
    expect(markup).toContain("<kbd>Alt+Shift+L</kbd> read or stop · <kbd>Alt+Shift+R</kbd> repeat · <kbd>Esc</kbd> stop");
    expect(markup).toContain("<kbd>Esc</kbd> three times or three fingers for one second");
    expect(markup).toContain("(desktop: <kbd>Ctrl+Alt+V</kbd>)");
    expect(textNodes(render({ speaking: true }))).toContain("Stop the voice");
    for (const label of ["Leer en voz alta", "Repetir", "Atajos", "Mayús", "Parar la voz"]) {
      expect(markup).not.toContain(label);
    }
  });

  it("sin voz, el motivo en inglés", () => {
    expect(textNodes(render({ availability: "no-local-voice" }))).toContain(UNAVAILABLE_TEXT["no-local-voice"]);
  });
});
