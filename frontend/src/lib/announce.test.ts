import { afterEach, describe, expect, it } from "vitest";

import type { Alert } from "./alerts";
import {
  type AnnouncerState,
  INITIAL_ANNOUNCER,
  LIVE_REGION_KEEP,
  type PlanInput,
  alertUrgency,
  announcementText,
  appendMessages,
  planAnnouncements,
} from "./announce";
import { adoptLevelLabels } from "./levels";

/**
 * Lo que se dice al lector de pantalla (§5.41): una vez cada alerta, por ámbito y cortés al entrar
 * en él, sin lo silenciado, asertivo solo para crítico y precaución, con la frase del backend sin
 * redactar y sin motivos con la privacidad.
 */

afterEach(() => adoptLevelLabels(null));

const alert = (domain: string, level: Alert["level"], drivers: string[] = []): Alert => ({
  id: `${domain}:${level}`,
  domain,
  level,
  drivers,
});

const CREW = "crew|crew-01";

const input = (alerts: Alert[], extra: Partial<PlanInput> = {}): PlanInput => ({
  scope: CREW,
  alerts,
  annunciation: new Map(),
  acknowledged: new Set(),
  privacy: false,
  ...extra,
});

/** Un ámbito ya abierto, con lo que había: lo que llegue después es nuevo de verdad. */
const opened = (alerts: Alert[] = [], scope = CREW): AnnouncerState =>
  planAnnouncements(INITIAL_ANNOUNCER, input(alerts, { scope })).state;

const urgencies = (state: AnnouncerState, alerts: Alert[], extra: Partial<PlanInput> = {}) =>
  planAnnouncements(state, input(alerts, extra)).announce.map((item) => item.urgency);

describe("urgencia", () => {
  it("asertiva para crítico (W) y precaución (C); cortés para vigilancia (A)", () => {
    expect(alertUrgency(alert("cardiovascular", "critical"), false)).toBe("assertive");
    expect(alertUrgency(alert("cardiovascular", "concern"), false)).toBe("assertive");
    expect(alertUrgency(alert("cardiovascular", "watch"), false)).toBe("polite");
  });

  it("ya reconocida, cortés aunque sea crítica: una persona ya la vio", () => {
    expect(alertUrgency(alert("cardiovascular", "critical"), true)).toBe("polite");
  });

  it("la que aparece con el ámbito abierto lleva su urgencia", () => {
    expect(urgencies(opened(), [alert("cardiovascular", "critical"), alert("bone", "watch")])).toEqual([
      "assertive",
      "polite",
    ]);
  });
});

describe("la frase", () => {
  it("la palabra del nivel del backend, el dominio y los motivos tal cual", () => {
    adoptLevelLabels({ critical: "Crítico" });
    expect(announcementText(alert("radiation", "critical", ["Dosis por encima del límite", "SPE en curso"]))).toBe(
      "Crítico: Radiación. Dosis por encima del límite. SPE en curso",
    );
  });

  it("no añade un punto a un motivo que ya acaba en signo de cierre, ni nada al último", () => {
    adoptLevelLabels({ concern: "Precaución" });
    expect(announcementText(alert("bone", "concern", ["Primero.", "¿Segundo?", "Tercero"]))).toBe(
      "Precaución: Óseo. Primero. ¿Segundo? Tercero",
    );
  });

  it("sin palabras del backend, la clave de la API: no se inventa una", () => {
    expect(announcementText(alert("immune", "watch"))).toBe("watch: Inmune");
  });

  it("un dominio que la interfaz no conoce se dice con su clave", () => {
    expect(announcementText(alert("nuevo", "watch", ["motivo"]))).toBe("watch: nuevo. motivo");
  });

  it("con la privacidad, nivel y dominio sin los motivos, que llevan cifras del tripulante", () => {
    adoptLevelLabels({ critical: "Crítico" });
    const radiation = alert("radiation", "critical", ["Dosis 412 mSv"]);
    expect(announcementText(radiation, true)).toBe("Crítico: Radiación");
    const plan = planAnnouncements(opened(), input([radiation], { privacy: true }));
    expect(plan.announce.map((item) => item.text)).toEqual(["Crítico: Radiación"]);
  });
});

describe("una vez cada alerta", () => {
  it("la primera vez se dice; en el sondeo siguiente, con las mismas alertas, nada", () => {
    const alerts = [alert("cardiovascular", "critical"), alert("bone", "watch")];
    const first = planAnnouncements(opened(), input(alerts));
    expect(first.announce).toHaveLength(2);
    const second = planAnnouncements(first.state, input(alerts));
    expect(second.announce).toEqual([]);
    expect(second.entered).toBe(false);
  });

  it("solo se dice la nueva cuando aparece otra", () => {
    const state = opened([alert("bone", "watch")]);
    const next = planAnnouncements(state, input([alert("cardiovascular", "concern"), alert("bone", "watch")]));
    expect(next.announce.map((item) => item.key)).toEqual(["cardiovascular:concern"]);
  });

  it("una escalada es otra alerta: se dice, con su urgencia", () => {
    const state = opened([alert("bone", "concern")]);
    const next = planAnnouncements(state, input([alert("bone", "critical")]));
    expect(next.announce.map((item) => [item.key, item.urgency])).toEqual([["bone:critical", "assertive"]]);
    expect([...next.state.seen]).toEqual(["bone:critical"]);
  });

  it("la que deja de estar activa y vuelve, se dice otra vez", () => {
    const state = opened([alert("bone", "watch")]);
    const gone = planAnnouncements(state, input([])).state;
    expect(gone.seen.size).toBe(0);
    expect(planAnnouncements(gone, input([alert("bone", "watch")])).announce).toHaveLength(1);
  });

  it("reconocerla no la vuelve a decir", () => {
    const alerts = [alert("bone", "critical")];
    const state = opened(alerts);
    expect(planAnnouncements(state, input(alerts, { acknowledged: new Set(["bone:critical"]) })).announce).toEqual([]);
  });

  it("poner o quitar la privacidad no repite nada", () => {
    const alerts = [alert("bone", "critical")];
    expect(planAnnouncements(opened(alerts), input(alerts, { privacy: true })).announce).toEqual([]);
  });
});

describe("por ámbito, cortés al entrar", () => {
  it("al abrir la consola se dice lo que hay, todo cortés: no es una ráfaga de interrupciones", () => {
    const alerts = [alert("radiation", "critical"), alert("bone", "concern"), alert("immune", "watch")];
    const plan = planAnnouncements(INITIAL_ANNOUNCER, input(alerts));
    expect(plan.entered).toBe(true);
    expect(plan.announce.map((item) => item.urgency)).toEqual(["polite", "polite", "polite"]);
  });

  it("otro tripulante u otra consola es entrar otra vez: se dice lo que hay allí", () => {
    const alerts = [alert("radiation", "critical")];
    const crew2 = planAnnouncements(opened(alerts), input(alerts, { scope: "crew|crew-02" }));
    expect(crew2.entered).toBe(true);
    expect(crew2.announce).toHaveLength(1);
    const ground = planAnnouncements(crew2.state, input(alerts, { scope: "ground|crew-02" }));
    expect(ground.announce).toHaveLength(1);
  });

  it("volver a un ámbito dice lo que hay: no se pierde la que se fue y volvió mientras se miraba otro", () => {
    const alerts = [alert("cardiovascular", "concern")];
    const ground = planAnnouncements(opened(alerts), input([], { scope: "ground|crew-01" })).state;
    const back = planAnnouncements(ground, input(alerts));
    expect(back.announce.map((item) => [item.key, item.urgency])).toEqual([["cardiovascular:concern", "polite"]]);
    // Y lo visto es solo de la pantalla de ahora: no crece con cada ámbito visitado.
    expect([...back.state.seen]).toEqual(["cardiovascular:concern"]);
  });
});

describe("lo silenciado no se anuncia", () => {
  it("suprimida o inhibida, nada; habilitada otra vez, se dice", () => {
    const alerts = [alert("bone", "concern"), alert("immune", "watch")];
    const quiet = new Map([
      ["bone:concern", "suppressed"],
      ["immune:watch", "inhibited"],
    ]);
    const silenced = planAnnouncements(opened(), input(alerts, { annunciation: quiet }));
    expect(silenced.announce).toEqual([]);
    expect(silenced.state.seen.size).toBe(0);
    expect(planAnnouncements(silenced.state, input(alerts)).announce).toHaveLength(2);
  });

  it("silenciar una ya dicha no la vuelve a decir; habilitarla, sí", () => {
    const alerts = [alert("bone", "concern")];
    const state = opened(alerts);
    const silenced = planAnnouncements(state, input(alerts, { annunciation: new Map([["bone:concern", "suppressed"]]) }));
    expect(silenced.announce).toEqual([]);
    expect(planAnnouncements(silenced.state, input(alerts)).announce).toHaveLength(1);
  });
});

describe("mensajes de la región viva", () => {
  it("cada mensaje es un nodo nuevo, también si repite la frase, y de lo anterior se quedan los últimos", () => {
    const once = appendMessages([], ["a"], 0);
    const twice = appendMessages(once, ["a"], 1);
    expect(twice).toEqual([
      { id: 0, text: "a" },
      { id: 1, text: "a" },
    ]);
    const old = appendMessages([], ["o1", "o2", "o3", "o4", "o5"], 0);
    expect(appendMessages(old, ["n"], 5).map((item) => item.text)).toEqual(["o2", "o3", "o4", "o5", "n"]);
  });

  it("lo que llega en un sondeo nunca se recorta: los primeros son los más graves", () => {
    const texts = Array.from({ length: LIVE_REGION_KEEP + 3 }, (_, index) => `m${index}`);
    const many = appendMessages([{ id: 0, text: "viejo" }], texts, 10);
    expect(many.map((item) => item.text)).toEqual(texts);
  });
});
