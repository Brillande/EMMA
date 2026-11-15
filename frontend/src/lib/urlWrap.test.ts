import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { addressesIn } from "./urlWrapMarkup";

/*
 * Una dirección web dentro de `.num` sin la clase `url` no se parte (`white-space: pre`): una
 * URL larga ensanchaba la rejilla entera y la página pasaba de 1400 px a casi 3000 al abrir un
 * plegable. Lo vio la pasada visual del 2026-10-16; ninguna prueba de componente lo veía, porque
 * el HTML era correcto y lo que fallaba era el ancho.
 */

const SRC = fileURLToPath(new URL("..", import.meta.url));

function components(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return components(path);
    return entry.name.endsWith(".tsx") ? [path] : [];
  });
}

/*
 * Una línea pone una URL en `.num` sin `url` si alguno de sus elementos lleva entre sus clases
 * `num` y no `url`, y lo que encierra nombra una dirección. Hasta §5.37.18 la guarda solo miraba
 * `className="num"` literal: `"secondary num"` se le escapaba, y había seis direcciones así (cuatro
 * en el panel del marco de NASA, una en el coste de medir y una en la PVT).
 */
// La clase entre comillas dobles o simples, o entre llaves con una cadena (`{"num"}`).
const ELEMENT = /className=(?:"([^"]*)"|'([^']*)'|\{["'`]([^"'`]*)["'`]\})[^>]*>([^<]*)/g;
// Lo que nombra una dirección: `url`, `urls`, `URL`, `sourceUrl`, `SOURCE_URL`…
const ADDRESS = /url/i;

function unwrappedUrl(line: string): boolean {
  return [...line.matchAll(ELEMENT)].some(([, double, single, braced, content = ""]) => {
    const names = (double ?? single ?? braced ?? "").split(/\s+/);
    // `wrap` también se parte (`pre-wrap`), como en la guarda pintada (`addressesIn`).
    return names.includes("num") && !names.includes("url") && !names.includes("wrap") && ADDRESS.test(content);
  });
}

describe("una dirección web en monoespaciada se parte", () => {
  it("la guarda ve `num` entre otras clases, y deja pasar `num url`", () => {
    expect(unwrappedUrl('<span className="num">{item.url}</span>')).toBe(true);
    expect(unwrappedUrl('<p className="secondary num">{imm.url}</p>')).toBe(true);
    expect(unwrappedUrl('<div className="num secondary">{reference.url}</div>')).toBe(true);
    expect(unwrappedUrl('<span className="secondary num url">{item.url}</span>')).toBe(false);
    expect(unwrappedUrl('<div className="secondary num wrap">{row.url}</div>')).toBe(false);
    expect(unwrappedUrl('<span className="number">{item.url}</span>')).toBe(false);
    expect(unwrappedUrl('<span className="num">{item.title}</span>')).toBe(false);
    // Otras comillas, llaves y otros nombres de una dirección.
    expect(unwrappedUrl("<span className='num'>{item.url}</span>")).toBe(true);
    expect(unwrappedUrl('<div className={"num"}>{x.url}</div>')).toBe(true);
    expect(unwrappedUrl('<span className="num">{item.urls.join(" · ")}</span>')).toBe(true);
    expect(unwrappedUrl('<span className="num">{SOURCE_URL}</span>')).toBe(true);
    expect(unwrappedUrl('<span className="num">{page.sourceUrl}</span>')).toBe(true);
    // Dos elementos en la línea: cuenta el que encierra la dirección.
    expect(unwrappedUrl('<span className="num url">{a.url}</span> <span className="num">{a.date}</span>')).toBe(false);
  });

  it("ningún componente pone una URL en `.num` sin la clase `url`", () => {
    const offenders = components(SRC).flatMap((path) =>
      readFileSync(path, "utf-8")
        .split("\n")
        .map((line, index) => ({ line, index }))
        .filter(({ line }) => unwrappedUrl(line))
        .map(({ index }) => `${path.slice(SRC.length)}:${index + 1}`),
    );
    expect(offenders).toEqual([]);
  });

  it("la hoja de estilo deja partir `.num.url`", () => {
    const css = readFileSync(join(SRC, "styles.css"), "utf-8");
    expect(css).toMatch(/\.num\.url\s*\{[^}]*white-space:\s*normal;[^}]*overflow-wrap:\s*anywhere;/);
  });

  it("y un identificador largo con `.num.wrap`, sin perder sus espacios", () => {
    const css = readFileSync(join(SRC, "styles.css"), "utf-8");
    expect(css).toMatch(/\.num\.wrap\s*\{[^}]*white-space:\s*pre-wrap;[^}]*overflow-wrap:\s*anywhere;/);
  });
});

/*
 * La misma regla sobre lo pintado (§5.38.12): `addressesIn` lee el HTML de `renderToStaticMarkup`.
 * La llaman las pruebas de los paneles que pintan direcciones con sus datos de ejemplo (datos
 * humanos, bancos de prueba, instalaciones, cobertura del HRP, línea base). No sustituye a la
 * guarda del código: un panel sin ejemplo con dirección no se mira pintado, y la del código mira
 * todas las líneas. La pintada ve lo que la del código no: una dirección con otro nombre, una clase
 * hecha con plantilla, el `.num` heredado de un elemento de más arriba.
 */
describe("la guarda sobre lo pintado", () => {
  it("ve un `.num` sin `url` con una dirección, con otro nombre o heredado", () => {
    expect(addressesIn('<span class="num">https://a.example/x</span>').unwrapped).toEqual(["https://a.example/x"]);
    expect(addressesIn('<p class="secondary num"><!-- -->www.example.org<!-- --></p>').unwrapped).toEqual([
      "www.example.org",
    ]);
    expect(addressesIn('<div class="num"><span class="c-gray">ver <b>http://loinc.org</b></span></div>').unwrapped).toEqual([
      "http://loinc.org",
    ]);
  });

  it("ve la dirección hecha de varias expresiones, que React separa con comentarios", () => {
    expect(addressesIn('<span class="num">https<!-- -->://<!-- -->loinc.org</span>').unwrapped).toEqual([
      "https://loinc.org",
    ]);
  });

  it("y la que parte un elemento en línea, que en pantalla sigue siendo una tira", () => {
    expect(addressesIn('<span class="num">https://<b>loinc.org/x</b></span>').unwrapped).toEqual(["https://loinc.org/x"]);
    expect(addressesIn('<span class="num">ver <a href="#">https://loinc.org</a> hoy</span>').unwrapped).toEqual([
      "https://loinc.org",
    ]);
    // Un bloque o un salto sí la cortan: ninguno de los dos trozos es una dirección.
    expect(addressesIn('<div class="num">https://<div>loinc.org</div></div>').inNum).toBe(0);
  });

  it("deja pasar `num url`, `num wrap`, el `.num` que no encierra la dirección y el texto fuera de `.num`", () => {
    expect(addressesIn('<div class="secondary num url">https://a.example/x</div>')).toEqual({ inNum: 1, unwrapped: [] });
    expect(addressesIn('<div class="secondary num wrap">https://a.example/x</div>')).toEqual({ inNum: 1, unwrapped: [] });
    expect(addressesIn('<span class="num url"> · <span>https://a.example/x</span></span>')).toEqual({ inNum: 1, unwrapped: [] });
    expect(addressesIn('<span class="num">2026-10-26</span> https://a.example/x').unwrapped).toEqual([]);
    expect(addressesIn('<span class="number">https://a.example/x</span>')).toEqual({ inNum: 0, unwrapped: [] });
  });

  it("el `.num` más cercano manda, y lo cerrado deja de contar", () => {
    expect(addressesIn('<div class="num"><span class="num url">https://a.example/x</span></div>').unwrapped).toEqual([]);
    expect(addressesIn('<div class="num url"><span class="num">https://a.example/x</span></div>').unwrapped).toEqual([
      "https://a.example/x",
    ]);
    expect(addressesIn('<span class="num">1</span><br/><img src="x"/><p>https://a.example/x</p>').unwrapped).toEqual([]);
    expect(addressesIn('<span class="num">1<br>https://a.example/x</span>').unwrapped).toEqual(["https://a.example/x"]);
  });
});
