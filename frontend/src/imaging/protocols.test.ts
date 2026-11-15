import { describe, expect, it } from "vitest";

import { isPictogramName } from "../icons/registry";
import { indicatorFamily } from "../lib/indicatorFamily";
import { UNKNOWN_MARK } from "../lib/marks";
import { PROTOCOL_PICTOGRAMS, measurePictogram, protocolPictogram } from "./protocols";

/**
 * Un dibujo por protocolo del backend (`app/imaging/protocols.py`), el mismo en todos los paneles,
 * y la medida con el de la familia del indicador en que entra.
 */

/** Las claves de `PROTOCOLS` del backend, en su orden. */
const BACKEND_PROTOCOLS = ["optic-nerve", "jugular-vein", "bladder", "lung", "fast", "liver"];

describe("el pictograma de cada protocolo", () => {
  it("cada protocolo del backend tiene un dibujo, y ninguno de mas", () => {
    expect(Object.keys(PROTOCOL_PICTOGRAMS).sort()).toEqual([...BACKEND_PROTOCOLS].sort());
    for (const key of BACKEND_PROTOCOLS) {
      expect(isPictogramName(String(protocolPictogram(key))), key).toBe(true);
    }
  });

  it("los que miden un organo del catalogo comparten dibujo con la familia de su indicador", () => {
    expect(protocolPictogram("optic-nerve")).toBe(indicatorFamily("onsd-right"));
    expect(protocolPictogram("jugular-vein")).toBe(indicatorFamily("ijv-csa-left"));
    expect(protocolPictogram("bladder")).toBe(indicatorFamily("bladder-volume"));
    expect(protocolPictogram("lung")).toBe(indicatorFamily("respiratory-rate"));
  });

  it("el FAST de cuatro ventanas lleva la ventana en cuartos", () => {
    expect(protocolPictogram("fast")).toBe("circle-quartered");
  });

  it("seis protocolos, seis dibujos distintos", () => {
    expect(new Set(Object.values(PROTOCOL_PICTOGRAMS)).size).toBe(BACKEND_PROTOCOLS.length);
  });

  it("un protocolo que la interfaz no conoce lleva la marca de desconocido, no otro dibujo", () => {
    expect(protocolPictogram("inventado")).toBe(UNKNOWN_MARK.pictogram);
  });
});

describe("el pictograma de cada medida", () => {
  it("una medida con lado se mira por su indicador derecho; sin lado, por su nombre", () => {
    expect(measurePictogram({ name: "onsd", lateral: true })).toBe(indicatorFamily("onsd-right"));
    expect(measurePictogram({ name: "ijv-csa", lateral: true })).toBe(indicatorFamily("ijv-csa-right"));
    expect(measurePictogram({ name: "bladder-volume", lateral: false })).toBe(indicatorFamily("bladder-volume"));
  });

  it("una medida sin indicador conocido lleva la marca de desconocido", () => {
    expect(measurePictogram({ name: "inventada", lateral: false })).toBe(UNKNOWN_MARK.pictogram);
    expect(measurePictogram({ name: "bladder-volume", lateral: true })).toBe(UNKNOWN_MARK.pictogram);
  });
});
