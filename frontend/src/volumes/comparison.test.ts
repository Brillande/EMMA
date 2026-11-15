import { describe, expect, it } from "vitest";

import type { VolumeLesion, VolumeSegmentation, VolumeStudy } from "../lib/api";
import { displayUnit } from "../lib/format";
import {
  type DensityBlock,
  type HuDensity,
  densityCell,
  densityNotes,
  densityOf,
  densitySides,
  densityUnit,
  previousSegmentation,
} from "./comparison";

const LESION: VolumeLesion = {
  id: 1,
  estado: "lesión candidata",
  diametro_mm: 12,
  volumen_ml: 1,
  centro_mm: [0, 0, 0],
  region: null,
  pequena: false,
  acuerdo_2o_modelo: null,
};

function segmentation(index: number, changes: Partial<VolumeSegmentation> = {}): VolumeSegmentation {
  return {
    ledger_index: index,
    recorded: "2026-10-06T00:00:00Z",
    preset: "higado",
    preset_nombre: "Hígado",
    estado: "segmentación automática sin validar",
    segmentador: "TotalSegmentator",
    modalidad: "CT",
    ventana_hu: [-30, 150],
    estructuras: [],
    lesiones: [LESION],
    volumen_organo_ml: 1500,
    ...changes,
  };
}

function study(index: number, segmentations: VolumeSegmentation[]): VolumeStudy {
  return {
    ledger_index: index,
    recorded: "2026-10-06T00:00:00Z",
    subject: "crew-01",
    modality: "CT",
    shape: [10, 10, 10],
    voxel_mm: [1, 1, 1],
    source: "console",
    recorded_by: "CMO",
    segmentations,
  };
}

describe("con que estudio anterior se compara una segmentacion", () => {
  it("la mas reciente de las anteriores, del mismo preset y segmentador", () => {
    const current = segmentation(9);
    const studies = [study(1, [segmentation(2)]), study(3, [segmentation(4)]), study(8, [current])];
    expect(previousSegmentation(studies, current)?.ledger_index).toBe(4);
  });

  it("vale otra segmentacion del mismo volumen", () => {
    const current = segmentation(5);
    expect(previousSegmentation([study(1, [segmentation(2), current])], current)?.ledger_index).toBe(2);
  });

  it("nunca otro preset ni otro segmentador: el backend lo rechazaria", () => {
    const current = segmentation(9);
    const studies = [
      study(1, [segmentation(2, { preset: "ojos" })]),
      study(3, [segmentation(4, { segmentador: "otro" })]),
      study(8, [current]),
    ];
    expect(previousSegmentation(studies, current)).toBeNull();
  });

  it("nunca una posterior ni ella misma", () => {
    const current = segmentation(4);
    expect(previousSegmentation([study(3, [current]), study(8, [segmentation(9)])], current)).toBeNull();
  });

  it("sin lesiones en ninguna de las dos no hay nada que emparejar", () => {
    const current = segmentation(9, { lesiones: [] });
    const empty = [study(1, [segmentation(2, { lesiones: [] })]), study(8, [current])];
    expect(previousSegmentation(empty, current)).toBeNull();
    const once = [study(1, [segmentation(2)]), study(8, [current])];
    expect(previousSegmentation(once, current)?.ledger_index).toBe(2);
  });
});

const MEASURED: HuDensity = {
  valorable: true,
  voxeles: 639,
  mediana_hu: 20,
  media_hu: 23.3,
  desviacion_hu: 7.1,
  p10_hu: 20,
  p90_hu: 40,
  motivo: null,
};
const TOO_SMALL: HuDensity = {
  valorable: false,
  voxeles: 27,
  mediana_hu: null,
  media_hu: null,
  desviacion_hu: null,
  p10_hu: null,
  p90_hu: null,
  motivo: "No valorable: 27 vóxeles, menos de los 50 que se piden.",
};

function block(changes: Partial<DensityBlock> = {}): DensityBlock {
  return {
    disponible: true,
    motivo: null,
    unidad: "[hnsf'U]",
    minimo_voxeles: 50,
    no_valorable: "no valorable",
    referencia: { nombre: "Hígado sin lesiones candidatas", ...MEASURED, mediana_hu: 60 },
    fase_contraste: null,
    notas: ["describe, no clasifica", "fase de contraste sin declarar"],
    ...changes,
  };
}

describe("densidad (HU) de las lesiones en la comparacion", () => {
  it("una lesion valorable da mediana y percentiles; ninguna otra cifra", () => {
    expect(densityCell(MEASURED)).toEqual({ kind: "cifra", mediana: 20, p10: 20, p90: 40, voxeles: 639 });
  });

  it("con pocos voxeles no hay cifra, y se dice por que con el texto del backend", () => {
    expect(densityCell(TOO_SMALL)).toEqual({ kind: "no-valorable", voxeles: 27, motivo: TOO_SMALL.motivo });
  });

  it("lo que el backend declara no valorable no se ensena aunque traiga cifras", () => {
    expect(densityCell({ ...MEASURED, valorable: false }).kind).toBe("no-valorable");
    expect(densityCell({ ...MEASURED, p90_hu: null }).kind).toBe("no-valorable");
  });

  it("sin dato (lesion sin pareja, backend sin densidad) es ausente, no un cero", () => {
    expect(densityCell(null)).toEqual({ kind: "ausente" });
    expect(densityOf(null)).toBeNull();
    expect(densityOf({ id: 1, diametro_mm: 12 })).toBeNull();
    expect(densityOf({ id: 1, densidad: null })).toBeNull();
    expect(densityOf({ id: 1, densidad: MEASURED })).toBe(MEASURED);
  });

  it("una comparacion sin bloque de densidad no pinta columnas", () => {
    expect(densitySides({ lesiones: [] })).toBeNull();
    expect(densitySides({ densidad: { antes: null, despues: null } })).toBeNull();
    const after = block();
    expect(densitySides({ densidad: { antes: null, despues: after } })).toEqual({ antes: null, despues: after });
  });

  it("las notas de los dos estudios salen una vez, en el orden del backend", () => {
    const failed = block({ disponible: false, motivo: "Sin densidad: no se pudo leer.", referencia: null, notas: [] });
    expect(densityNotes({ antes: block(), despues: block() })).toEqual([
      "describe, no clasifica",
      "fase de contraste sin declarar",
    ]);
    expect(densityNotes({ antes: failed, despues: block() })).toEqual([
      "Sin densidad: no se pudo leer.",
      "describe, no clasifica",
      "fase de contraste sin declarar",
    ]);
    expect(densityNotes({ antes: null, despues: null })).toEqual([]);
  });

  it("la unidad es la del backend y tiene forma de lectura declarada", () => {
    expect(densityUnit({ antes: block(), despues: null })).toBe("[hnsf'U]");
    expect(densityUnit({ antes: null, despues: null })).toBeNull();
    expect(displayUnit("[hnsf'U]")).toBe("HU");
  });
});
