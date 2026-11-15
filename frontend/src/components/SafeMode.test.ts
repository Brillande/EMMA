import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { taggedPictogram, textNodes } from "../advisor/visibleText";
import type { HaltNoticeText, SafeModeState } from "../lib/api";
import { formatUtc } from "../lib/format";
import { uiPictogram } from "../lib/uiMarks";
import { HaltDetails, HaltNotice, NetworkStatus, SAFE_MODE_REFRESH_MS, haltDetailsId } from "./SafeMode";
import { StatusStrip } from "./StatusStrip";

/*
 * La franja entera con un estado de la red ya leído: sin red, el gancho no llega a leerlo, así que
 * aquí devuelve el que ponga la prueba (`watched.state`). El resto de `SafeMode.tsx`, tal cual.
 */
const watched = vi.hoisted(() => ({ state: null as unknown }));
vi.mock("./SafeMode", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./SafeMode")>();
  return {
    ...actual,
    useNetworkWatch: () => ({ state: watched.state, stale: false, apply: () => Promise.resolve() }),
  };
});

/**
 * El freno HALT de Polaris en la franja común: el aviso lo redacta el backend
 * (`api/safe_mode.halt_notice`) y la consola lo pinta tal cual, a la vista y sin que nadie lo
 * pida. Sin freno, nada. La fecha pasa por `formatUtc`; el color es el amarillo de la tabla F.5-1
 * ("off-nominal, attention required") con su triángulo, nunca el color solo.
 */
const notice: HaltNoticeText = {
  title: "TITULO-DEL-BACKEND",
  headline: "TITULAR-DEL-BACKEND",
  summary: "LO-QUE-SIGUE-DEL-BACKEND",
  since: "2026-09-01T12:30:15+00:00",
  since_label: "ETIQUETA-DE-FECHA",
  details_label: "ETIQUETA-DEL-DETALLE",
  details: ["DETALLE-1", "DETALLE-2"],
};

const open: SafeModeState = {
  active: false,
  reason: null,
  declared_by: null,
  since: null,
  version: 0,
  store_epoch: 1,
  halt: { active: false, file: "estado/.HALT", since: null, notice: null },
};
const halted: SafeModeState = {
  ...open,
  halt: { active: true, file: "estado/.HALT", since: notice.since, notice },
};

function render(element: Parameters<typeof renderToStaticMarkup>[0]): string {
  return renderToStaticMarkup(element);
}

describe("aviso del freno HALT", () => {
  it("sin freno no pinta nada", () => {
    expect(render(createElement(HaltNotice, { notice: null }))).toBe("");
  });

  it("con freno pinta el texto del backend, entero y tal cual: la línea en la franja y lo demás en la página", () => {
    const html = render(createElement(HaltNotice, { notice })) + render(createElement(HaltDetails, { notice }));
    for (const text of [
      notice.title,
      notice.headline,
      notice.summary,
      notice.since_label,
      notice.details_label,
      ...notice.details,
    ]) {
      expect(html).toContain(text);
    }
  });

  it("la fecha del fichero sale por formatUtc, no en ISO crudo", () => {
    const html = render(createElement(HaltNotice, { notice })) + render(createElement(HaltDetails, { notice }));
    expect(html).toContain(formatUtc(new Date(notice.since as string)));
    expect(html).toContain("2026-09-01 12:30 UTC");
    expect(html).not.toContain(notice.since as string);
  });

  it("sin fecha no se inventa una", () => {
    const undated = { ...notice, since: null };
    const html = render(createElement(HaltNotice, { notice: undated })) + render(createElement(HaltDetails, { notice: undated }));
    expect(html).not.toContain(notice.since_label);
    expect(html).not.toContain("UTC");
  });

  it("es una precaución en amarillo con triángulo, y se anuncia sola (role=status)", () => {
    const html = render(createElement(HaltNotice, { notice }));
    expect(html).toContain('role="status"');
    // El triángulo es el pictograma `shape-triangle` junto a la palabra (§5.32), no un carácter.
    expect(html).toMatch(
      /<span class="mark c-yellow"><svg [^>]*data-pictogram="shape-triangle"[^>]*>.*?<\/svg>TITULO-DEL-BACKEND · TITULAR-DEL-BACKEND<\/span>/,
    );
    expect(html).not.toContain("△");
    expect(textNodes(html)[0]).toBe("TITULO-DEL-BACKEND · TITULAR-DEL-BACKEND");
    // Ni rojo (no ha fallado nada), ni cian (no falta un dato), ni gris (no es "no disponible").
    expect(html).not.toMatch(/c-red|c-cyan|c-gray/);
  });

  it("el mando, con el rótulo del backend y el círculo de la i de «cómo leerlo», dice si está desplegado", () => {
    const closed = render(createElement(HaltNotice, { notice }));
    expect(closed).toMatch(
      taggedPictogram(
        "button",
        uiPictogram("howToRead"),
        notice.details_label,
        ` class="command" type="button" aria-expanded="false"`,
      ),
    );
    // Abierto, apunta a la explicación; cerrado no, porque no está en la página.
    const opened = render(createElement(HaltNotice, { notice, open: true }));
    expect(opened).toContain(`aria-expanded="true" aria-controls="${haltDetailsId}"`);
    expect(closed).not.toContain("aria-controls");
    // Lo que se anuncia solo es el aviso; el mando, fuera de la región viva.
    expect(closed).toMatch(/^<div class="halt-notice"><span class="halt-line" role="status">(?:(?!<button)[^])*<\/span><button /);
    expect(closed.match(/role="status"/g)).toHaveLength(1);
    // La explicación es la región a la que apunta el mando, con el mismo rótulo.
    expect(render(createElement(HaltDetails, { notice }))).toMatch(
      // `tabindex="-1"`: al abrirse recibe el foco, para que se lea que el mando hizo algo.
      new RegExp(`^<section tabindex="-1" class="halt-details" id="${haltDetailsId}" aria-label="${notice.details_label}">`),
    );
  });

  it("en la franja, una línea: triángulo, título, titular, fecha y el mando; nada plegado (§5.35.12)", () => {
    const html = render(createElement(HaltNotice, { notice }));
    // Ni pliegue ni lo que sigue funcionando: eso va en la página (`HaltDetails`).
    expect(html).not.toMatch(/<details|<summary/);
    expect(html).not.toContain(notice.summary);
    for (const line of notice.details) expect(html).not.toContain(line);
    // El rótulo de la fecha va como su `title` y, para quien no pasa el ratón, en la explicación.
    expect(html).toContain(`title="${notice.since_label}"`);
    expect(render(createElement(HaltDetails, { notice }))).toContain(
      `${notice.since_label} <span class="num">${formatUtc(new Date(notice.since as string))}</span>`,
    );
    // Tres piezas en una fila: la marca, la fecha y el mando.
    expect(html.match(/<span class="mark|<span class="secondary num"|<button /g)).toHaveLength(3);
  });
});

describe("la explicación del freno se despliega en la página, no en la franja fija (§5.35.12)", () => {
  function strip(): string {
    return renderToStaticMarkup(
      createElement(StatusStrip, {
        status: null,
        loading: false,
        counts: { warning: 0, caution: 0, advisory: 0, unacknowledged: 0, suppressed: 0, inhibited: 0 },
        consoleTitle: "T",
      }),
    );
  }

  it("con el freno puesto, la franja lleva la línea y el mando, y nada de la explicación", () => {
    watched.state = halted;
    try {
      const html = strip();
      const header = html.slice(0, html.indexOf("</header>"));
      expect(header).toContain(notice.title);
      expect(header).toContain('aria-expanded="false"');
      expect(html).not.toContain(notice.summary);
      expect(html).not.toContain('class="halt-details"');
    } finally {
      watched.state = null;
    }
  });

  it("abierta, va detrás de la franja (fuera del `<header>`), no dentro", () => {
    const source = readFileSync(fileURLToPath(new URL("./StatusStrip.tsx", import.meta.url)), "utf8");
    expect(source).toMatch(/<\/header>\s*\{haltOpen && halt !== null && <HaltDetails notice=\{halt\} \/>\}\s*<\/>/);
    // Abierta es la de un aviso concreto (fecha y texto): uno nuevo, aunque llegue entre dos
    // relecturas, sale cerrado.
    expect(source).toMatch(/const haltOpen = haltKey !== null && openFor === haltKey;/);
    expect(source).toMatch(/\[halt\.since \?\? "", halt\.title, halt\.headline\]/);
    // Sin DOM en estas pruebas, se mira la fuente: al montarse, la explicación se lleva bajo la
    // franja si quedó fuera de la vista y recibe el foco (la captura de §5.35.12 lo comprueba).
    const details = readFileSync(fileURLToPath(new URL("./SafeMode.tsx", import.meta.url)), "utf8");
    expect(details).toMatch(/if \(top < covered \|\| top > window\.innerHeight\) window\.scrollBy\(\{ top: top - covered \}\);/);
    expect(details).toMatch(/section\.focus\(\{ preventScroll: true \}\);\n {2}\}, \[\]\);/);
  });
});

describe("estado de la red en la franja", () => {
  it("sin freno ni modo seguro, la red está abierta y no hay aviso", () => {
    const html = render(createElement(NetworkStatus, { state: open }));
    expect(html).toContain("abierta");
    expect(html).not.toContain(notice.title);
  });

  it("abierta: la puerta abierta junto a la palabra, en texto secundario y sin color de alerta", () => {
    const html = render(createElement(NetworkStatus, { state: open }));
    expect(html).toMatch(/<span class="mark secondary"><svg [^>]*data-pictogram="door-open"[^>]*>.*?<\/svg>abierta<\/span>/);
    expect(html).not.toMatch(/c-red|c-yellow|c-cyan|c-gray/);
    expect(textNodes(html)).toEqual(["abierta"]);
  });

  it("con el freno puesto la red no se rotula abierta", () => {
    const html = render(createElement(NetworkStatus, { state: halted }));
    expect(html).not.toContain("abierta");
    expect(html).toContain(notice.title);
  });

  it("modo seguro activo: triángulo amarillo junto a la palabra, con motivo y persona en el title", () => {
    const html = render(
      createElement(NetworkStatus, { state: { ...open, active: true, reason: "MOTIVO", declared_by: "QUIEN" } }),
    );
    expect(html).toMatch(
      /<span class="mark c-yellow" title="MOTIVO · QUIEN"><svg [^>]*data-pictogram="shape-triangle"[^>]*>.*?<\/svg>Modo seguro · sin salida a internet<\/span>/,
    );
    expect(html).not.toContain("△");
    expect(html).not.toContain("abierta");
  });

  it("sin motivo ni persona (modo seguro por configuración) no hay tooltip, no un «·» solo", () => {
    const html = render(createElement(NetworkStatus, { state: { ...open, active: true } }));
    expect(html).toContain('<span class="mark c-yellow"><svg');
    expect(html).not.toContain("title=");
    const onlyWho = render(createElement(NetworkStatus, { state: { ...open, active: true, declared_by: "QUIEN" } }));
    expect(onlyWho).toContain('title="QUIEN"');
  });

  it("con modo seguro y freno se ven los dos: se levantan por separado", () => {
    const html = render(createElement(NetworkStatus, { state: { ...halted, active: true } }));
    expect(html).toContain("Modo seguro");
    expect(html).toContain(notice.title);
    expect(html.match(/data-pictogram="shape-triangle"/g)).toHaveLength(2);
  });
});

describe("avisa solo", () => {
  const source = readFileSync(fileURLToPath(new URL("./SafeMode.tsx", import.meta.url)), "utf8");
  const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

  it("vuelve a leer el estado sin que nadie recargue, al ritmo del estado del tripulante", () => {
    expect(code).toMatch(/setInterval\([\s\S]*?load\(\)[\s\S]*?SAFE_MODE_REFRESH_MS\)/);
    expect(SAFE_MODE_REFRESH_MS).toBeLessThanOrEqual(30_000);
  });

  it("una relectura que falla no borra de la franja lo que ya se veía: lo marca en cian con el anillo punteado", () => {
    expect(code).not.toContain("setState(null)");
    expect(code).toContain("setStale(true)");
    // Lo que se mira es que «sin actualizar» va dentro de la marca cian con el anillo, no el
    // formato del JSX: la expresión admite saltos de línea y fragmentos de por medio.
    expect(code).toMatch(/stale &&[\s\S]{0,80}?<MarkOf mark=\{MISSING_MARK\}>\s*\{tr\("sin actualizar", "not updated"\)\}\s*<\/MarkOf>/);
  });

  it("la interfaz no redacta el aviso: ninguna palabra del freno escrita aquí", () => {
    expect(code).not.toMatch(/HALT|[Ff]reno/);
  });

  it("el rótulo de la red lleva el mástil, y el mando el triángulo o la puerta según a dónde lleve", () => {
    expect(code).toMatch(/<Pictogram name="antenna"\s*\/>/);
    expect(code).toMatch(/const command: PictogramName =\s*state\.active \? "door-open" : "shape-triangle"/);
    expect(code).toMatch(
      /<Mark pictogram=\{command\}>\s*\{state\.active \? tr\("Levantar modo seguro", "Lift safe mode"\) : tr\("Activar modo seguro", "Activate safe mode"\)\}\s*<\/Mark>/,
    );
    // Ningún carácter de forma queda escrito: todos pasaron a pictogramas.
    expect(code).not.toMatch(/[△◌✓✕○◇■●◐▷⊘]/);
  });
});

describe("el formulario del modo seguro (§5.33.11)", () => {
  // Sin red el estado no llega y el formulario no se pinta: se mira la fuente.
  const source = readFileSync(fileURLToPath(new URL("./SafeMode.tsx", import.meta.url)), "utf8");

  it("el pliegue lleva el dibujo de a dónde lleva el mando, por la pieza común", () => {
    // `strip-pop`: el formulario cuelga encima de la página y la franja no crece (§5.40).
    expect(source).toMatch(/<Fold pictogram=\{command\} className="safe-mode strip-pop" label=\{/);
    expect(source).not.toMatch(/<details|<summary/);
  });

  it("«Quién» con la persona y «Motivo» con el bocadillo, por `FieldLabel`", () => {
    expect(source).toMatch(/<FieldLabel concept="person">\s*\{tr\("Quién", "Who"\)\}\{" "\}/);
    expect(source).toMatch(/<FieldLabel concept="reason">\s*\{tr\("Motivo", "Reason"\)\} <input/);
    expect(source).not.toMatch(/<label>/);
  });

  it("lo que sale mal, con la marca de lo que fue: rechazo en amarillo, caída en rojo (§5.34.14)", () => {
    expect(source).toMatch(/<MarkOf mark=\{error\.mark\}>\{error\.text\}<\/MarkOf>/);
    expect(source).toContain("setError(requestOutcome(failure))");
    expect(source).not.toMatch(/FAILURE_MARK|REFUSED_MARK/);
    expect(source).not.toContain("c-yellow");
  });
});
