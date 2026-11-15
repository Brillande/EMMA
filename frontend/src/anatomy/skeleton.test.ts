import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { isPictogramName } from "../icons/registry";
import type { PainOnSubjectSkeleton, SubjectSkeleton } from "../lib/api";
import { mark } from "../lib/marks";
import { noticeTone, painIsOnThisFigure, skeletonImageUrl, sourceTone } from "./skeleton";

/**
 * Dos esqueletos con el mismo contrato (el de referencia y el del TAC del tripulante) no se
 * pueden confundir: la imagen, las marcas de dolor y el rotulo tienen que ser de la misma figura.
 */

const REFERENCE: SubjectSkeleton = {
  region: "bones",
  width: 880,
  height: 2212,
  bones: {},
  attribution: "BodyParts3D",
  source: "reference",
  label: "Esqueleto de referencia (BodyParts3D): no es el cuerpo del tripulante.",
  alt: "Esqueleto humano de referencia",
  caption: "Figura de referencia, no del tripulante.",
  simulated: false,
  ledger: null,
  extent_mm: null,
  absent_bones: [],
  truncated_bones: [],
  notes: [],
  spine: null,
  fallback_reason: null,
  fallback_kind: null,
};

const OWN: SubjectSkeleton = {
  ...REFERENCE,
  source: "own-ct",
  attribution: null,
  ledger: {
    segmentation_index: 12,
    segmentation_recorded: "2026-10-07T10:00:00+00:00",
    study_index: 11,
    study_recorded: "2026-10-07T09:00:00+00:00",
  },
  extent_mm: { x: [200, -200], z: [1090, 430] },
};

function pain(source: "own-ct" | "reference", index: number | null): PainOnSubjectSkeleton {
  return {
    superposable: true,
    error_px: { mean: 10, worst: 20, threshold: 90 },
    window_days: 7,
    marks: [],
    source,
    segmentation_index: index,
    anchors: 11,
    reason: null,
    outside_study: [],
  };
}

describe("la imagen es la de la respuesta", () => {
  it("la de referencia viaja con la app", () => {
    expect(skeletonImageUrl(REFERENCE)).toBe("/api/anatomy/skeleton.png");
  });

  it("la del TAC se pide por el asiento de su segmentacion", () => {
    expect(skeletonImageUrl(OWN)).toBe("/api/anatomy/skeleton/own/12.png");
  });

  it("si se cae a la de referencia, no se pide la del TAC aunque haya motivo con asiento", () => {
    const fallen: SubjectSkeleton = {
      ...REFERENCE,
      fallback_kind: "not-usable",
      fallback_reason: "La segmentacion (asiento 12) no se usa.",
    };
    expect(skeletonImageUrl(fallen)).toBe("/api/anatomy/skeleton.png");
  });
});

describe("el dolor solo se pinta sobre la figura en la que se coloco", () => {
  it("referencia sobre referencia y TAC sobre el mismo asiento", () => {
    expect(painIsOnThisFigure(REFERENCE, pain("reference", null))).toBe(true);
    expect(painIsOnThisFigure(OWN, pain("own-ct", 12))).toBe(true);
  });

  it("no mezcla la figura de referencia con marcas colocadas sobre un TAC, ni al reves", () => {
    expect(painIsOnThisFigure(REFERENCE, pain("own-ct", 12))).toBe(false);
    expect(painIsOnThisFigure(OWN, pain("reference", null))).toBe(false);
  });

  it("no mezcla dos TAC distintos del mismo tripulante", () => {
    expect(painIsOnThisFigure(OWN, pain("own-ct", 15))).toBe(false);
  });
});

describe("de donde sale la figura se dice con pictograma y palabra", () => {
  it("el TAC y la referencia sin mas no son una señal: van sin color, marco lleno y marco vacio", () => {
    expect(sourceTone(OWN)).toEqual({
      ...mark("frame-filled", null),
      word: "TAC del tripulante",
    });
    expect(sourceTone(REFERENCE)).toEqual({ ...mark("frame-empty", null), word: "Referencia" });
    expect(sourceTone(OWN).className).toBeUndefined();
    expect(sourceTone(REFERENCE).color).toBeNull();
  });

  it("un TAC de ejemplo no se rotula como el del tripulante", () => {
    expect(sourceTone({ ...OWN, simulated: true }).word).toBe("TAC de ejemplo");
    expect(sourceTone({ ...OWN, simulated: true }).pictogram).toBe("frame-filled");
  });

  it("sin esqueleto propio es dato ausente (cian); con uno que no vale, no disponible (gris)", () => {
    const missing = sourceTone({ ...REFERENCE, fallback_kind: "no-segmentation" });
    const unusable = sourceTone({ ...REFERENCE, fallback_kind: "not-usable" });
    expect(missing).toEqual({ ...mark("ring-dotted", "cyan"), word: "Referencia" });
    expect(unusable).toEqual({ ...mark("cross", "gray"), word: "Referencia" });
    expect(missing.className).toBe("c-cyan");
    expect(unusable.className).toBe("c-gray");
    expect(missing.pictogram).not.toBe(unusable.pictogram);
  });

  it("los cuatro pictogramas existen y son distintos entre si", () => {
    const names = [
      sourceTone(OWN),
      sourceTone(REFERENCE),
      sourceTone({ ...REFERENCE, fallback_kind: "no-segmentation" }),
      sourceTone({ ...REFERENCE, fallback_kind: "not-usable" }),
    ].map((tone) => tone.pictogram);
    for (const name of names) expect(name !== null && isPictogramName(name), String(name)).toBe(true);
    expect(new Set(names).size).toBe(names.length);
  });
});

describe("avisos del control de la segmentacion", () => {
  it("un nivel desconocido se pinta como atencion, no como dato ausente", () => {
    expect(noticeTone("dato_ausente")).toEqual(mark("ring-dotted", "cyan"));
    expect(noticeTone("atencion")).toEqual(mark("shape-triangle", "yellow"));
    expect(noticeTone("otro")).toEqual(mark("shape-triangle", "yellow"));
  });
});

describe("los plegables de lo que falta en el esqueleto (§5.33.12)", () => {
  it("son `Fold` con la marca de dato ausente como signo: el cian solo en el dibujo", () => {
    const source = readFileSync(fileURLToPath(new URL("./SkeletonFigure.tsx", import.meta.url)), "utf8");
    expect(source).not.toMatch(/<details\b/);
    expect(source.match(/<Fold\s+(?:data-ui="[^"]+"\s+)?mark=\{MISSING_MARK\}/g)).toHaveLength(2);
  });
});
