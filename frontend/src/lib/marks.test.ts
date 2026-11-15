import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { Unavailable } from "../components/Unavailable";
import { ApiError } from "./api";
import {
  FAILURE_MARK,
  REFUSED_MARK,
  UNREADABLE_CALIBRATION,
  isIntegrityBreak,
  isRefusal,
  requestMark,
  requestOutcome,
} from "./marks";

/*
 * Decisión del usuario (2026-10-21, §5.34.14): lo que sale mal en una petición se marca por lo que
 * es, en toda la interfaz. Un «no» del backend con su motivo (4xx) es un rechazo: el triángulo en
 * amarillo. Una petición caída (5xx, sin red, cualquier otra excepción) es un fallo: la cruz en
 * rojo. Antes cada panel elegía una de las dos para todo, y el mismo 422 salía en amarillo en el
 * asesor y en rojo en el modo seguro.
 */
describe("la marca de lo que salió mal en una petición", () => {
  it("un 4xx es un rechazo: el triángulo en amarillo", () => {
    for (const status of [400, 403, 404, 409, 422, 499]) {
      const reason = new ApiError(status, "MOTIVO");
      expect(isRefusal(reason), String(status)).toBe(true);
      expect(requestMark(reason), String(status)).toBe(REFUSED_MARK);
    }
    expect(REFUSED_MARK).toEqual({ pictogram: "shape-triangle", color: "yellow", className: "c-yellow" });
  });

  it("un 5xx, una red caída o cualquier otra excepción es un fallo: la cruz en rojo", () => {
    for (const reason of [
      new ApiError(500, "ROTO"),
      new ApiError(503, "SIN SERVICIO"),
      new TypeError("Failed to fetch"),
      new Error("la segmentación falló"),
      "texto suelto",
      null,
      undefined,
    ]) {
      expect(isRefusal(reason), String(reason)).toBe(false);
      expect(requestMark(reason), String(reason)).toBe(FAILURE_MARK);
    }
    expect(FAILURE_MARK).toEqual({ pictogram: "cross", color: "red", className: "c-red" });
  });

  it("el 409 del registro firmado roto no es un «no»: la cruz en rojo, con el motivo del backend (§5.35.12)", () => {
    // Decisión del usuario (2026-10-22): un asiento manipulado o la calibración firmada ilegible
    // de un estudio de ecografía no se corrige y se repite, como un rechazo: algo se rompió.
    const tampered = new ApiError(409, "integridad comprometida: asiento 7: hash no coincide", true);
    const calibration = new ApiError(409, UNREADABLE_CALIBRATION);
    for (const reason of [tampered, calibration]) {
      expect(isIntegrityBreak(reason), reason.detail).toBe(true);
      expect(isRefusal(reason), reason.detail).toBe(false);
      expect(requestOutcome(reason), reason.detail).toEqual({ mark: FAILURE_MARK, text: reason.detail });
    }
    // Lo decide el `integrity_ok: false` del backend, no el texto: el mismo motivo sin el campo es
    // otro 409, y un 409 cualquiera («ya adoptada», una firma que no cuadra) sigue siendo un «no».
    // Tampoco se reinterpreta el texto de la calibración dentro de otro motivo o con otro código.
    for (const reason of [
      new ApiError(409, tampered.detail),
      new ApiError(409, "ya adoptada"),
      new ApiError(409, `motivo: ${UNREADABLE_CALIBRATION}`),
      new ApiError(422, UNREADABLE_CALIBRATION),
      new ApiError(422, "otro motivo", true),
    ]) {
      expect(isIntegrityBreak(reason), reason.detail).toBe(false);
      expect(requestMark(reason), reason.detail).toBe(REFUSED_MARK);
    }
    expect(isIntegrityBreak(new ApiError(500, "x", true))).toBe(false);
    expect(requestMark(new ApiError(500, "x", true))).toBe(FAILURE_MARK);
  });

  it("lo que lee la regla es lo que escribe el backend, y la petición no lo pierde por el camino", () => {
    // Si el backend dejara el campo o cambiara el texto, el 409 volvería en silencio al amarillo.
    const read = (path: string): string => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");
    // El manejador de `TamperedRecordError`: 409 con `integrity_ok: False` junto al motivo.
    expect(read("../../../backend/app/main.py")).toMatch(
      /def _integrity_compromised\([^]*?status_code=409,\s+content=\{"detail": [^\n]*"integrity_ok": False\}/,
    );
    expect(read("../../../backend/app/api/imaging.py")).toContain(
      `raise HTTPException(status_code=409, detail="${UNREADABLE_CALIBRATION}")`,
    );
    // `request()` y la subida de volúmenes pasan el campo al `ApiError`.
    expect(read("./api.ts")).toMatch(/integrityBroken = body\.integrity_ok === false;/);
    expect(read("./api.ts")).toMatch(/throw new ApiError\(response\.status, detail, integrityBroken\);/);
    expect(read("../volumes/upload.ts")).toMatch(/new ApiError\(reply\.status, detail, body\.integrity_ok === false\)/);
  });

  it("una respuesta buena que no trae lo que debía (2xx sin asiento) no es un «no»: es un fallo", () => {
    // `volumes/upload.ts` lanza un `ApiError` con el estado de la respuesta 2xx que no trae asiento.
    expect(requestMark(new ApiError(201, "respuesta sin asiento"))).toBe(FAILURE_MARK);
  });

  it("el texto es el motivo del backend tal cual, o el error si no hubo respuesta", () => {
    expect(requestOutcome(new ApiError(422, "DETALLE-DEL-BACKEND"))).toEqual({
      mark: REFUSED_MARK,
      text: "DETALLE-DEL-BACKEND",
    });
    // Sin el prefijo técnico de `String(error)` («Error: HTTP 503: …»).
    expect(requestOutcome(new ApiError(503, "DETALLE"))).toEqual({ mark: FAILURE_MARK, text: "DETALLE" });
    expect(requestOutcome(new TypeError("Failed to fetch"))).toEqual({
      mark: FAILURE_MARK,
      text: "TypeError: Failed to fetch",
    });
  });

  it("«Sin datos» de un panel lleva la marca de la petición, no el cian de un dato ausente", () => {
    const refused = renderToStaticMarkup(createElement(Unavailable, { outcome: requestOutcome(new ApiError(404, "M")) }));
    expect(refused).toMatch(/^<p><span class="mark c-yellow"><svg[^>]*data-pictogram="shape-triangle"[^]*?<\/svg>Sin datos: M<\/span><\/p>$/);
    const down = renderToStaticMarkup(createElement(Unavailable, { outcome: requestOutcome(new TypeError("x")) }));
    expect(down).toMatch(/^<p><span class="mark c-red"><svg[^>]*data-pictogram="cross"/);
    expect(refused + down).not.toContain("c-cyan");
  });
});

describe("nadie decide la marca de una petición fuera de `lib/marks.ts`", () => {
  const sources = Object.entries(
    import.meta.glob("/src/**/*.{ts,tsx}", { query: "?raw", import: "default", eager: true }),
  ).filter(([path]) => !/\.test\.tsx?$/.test(path) && path !== "/src/lib/marks.ts");
  // Código de Polaris: el visor 3D carga con NiiVue, no con la API de EMMA; lo que falla ahí no
  // tiene código de estado y siempre es un fallo (`FAILURE_MARK`, anotado como cambio §5a).
  const POLARIS_VIEWER = "/src/volumes/VolumeViewer.tsx";

  it("ningún panel guarda el error de una petición como texto: pierde el código de estado", () => {
    for (const [path, source] of sources) {
      if (path === POLARIS_VIEWER) continue;
      const code = String(source);
      expect(code, path).not.toMatch(/instanceof ApiError \? \w+\.detail/);
      expect(code, path).not.toMatch(/set\w*\(String\((?:reason|cause|error|failure)\)\)/);
    }
  });

  it("ninguno decide por su cuenta si un 409 es el registro roto: lo dice `isIntegrityBreak`", () => {
    // El motivo del backend se enseña tal cual; leerlo para elegir la marca solo se hace aquí.
    for (const [path, source] of sources) {
      const code = String(source);
      expect(code, path).not.toMatch(/UNREADABLE_CALIBRATION|\.integrityBroken\b/);
      expect(code, path).not.toMatch(/integridad comprometida:|calibración del estudio ilegible/);
      expect(code, path).not.toMatch(/status === 409|\.detail\.(?:startsWith|includes|endsWith)\(/);
    }
  });

  it("ninguno pinta el error de una petición con una marca fija", () => {
    // Las dos marcas, escritas a mano junto a una variable de error, deciden por el panel lo que
    // solo sabe el código de estado. La rotura del registro firmado (`AuditPanel`, la franja) no es
    // una petición y lleva su cruz con su propio texto.
    for (const [path, source] of sources) {
      if (path === POLARIS_VIEWER) continue;
      expect(String(source), path).not.toMatch(
        /<MarkOf mark=\{(?:FAILURE_MARK|REFUSED_MARK)\}>[^<{]*\{\w*(?:[eE]rror|failure|message|unavailable)\}/,
      );
    }
  });
});
