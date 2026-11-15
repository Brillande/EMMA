import { describe, expect, it } from "vitest";

import { ApiError } from "../lib/api";
import { cleaningOf, uploadOutcome } from "./upload";

const CLEANED = {
  fields: ["descrip", "extensiones"],
  received_sha256: "a".repeat(64),
  received_size_bytes: 1234,
  note: "Cabecera limpiada en EMMA a petición de quien lo registró.",
};
const REFUSAL = {
  detail: "El volumen puede llevar datos personales: el NIfTI lleva texto en descrip. No se ha guardado nada.",
  cleanable: true,
  clean_offer: "EMMA puede vaciar la cabecera por ti y volver a comprobar el volumen.",
  clean_label: "Limpiar la cabecera y volver a comprobar",
};

describe("subida de un volumen: guardado, rechazado u ofrecido limpiar", () => {
  it("un volumen que entra tal como llego no dice que se limpio", () => {
    expect(uploadOutcome({ status: 201, body: { ledger_index: 7, shape: [2, 2, 2] } })).toEqual({
      kind: "saved",
      ledger_index: 7,
      cleaned: null,
    });
  });

  it("uno guardado limpio trae la declaracion del backend", () => {
    const outcome = uploadOutcome({ status: 201, body: { ledger_index: 8, cleaned: CLEANED } });
    expect(outcome).toEqual({ kind: "saved", ledger_index: 8, cleaned: CLEANED });
  });

  it("el rechazo ofrece limpiar con el texto y el rotulo del backend, tal cual", () => {
    expect(uploadOutcome({ status: 422, body: REFUSAL })).toEqual({
      kind: "refused",
      detail: REFUSAL.detail,
      offer: { text: REFUSAL.clean_offer, label: REFUSAL.clean_label },
    });
  });

  it("si el backend dice que limpiar no serviria, no hay boton", () => {
    const body = { ...REFUSAL, cleanable: false, clean_offer: null, clean_label: null };
    expect(uploadOutcome({ status: 422, body })).toEqual({ kind: "refused", detail: REFUSAL.detail, offer: null });
    // Ni aunque llegaran los textos: manda `cleanable`.
    expect(uploadOutcome({ status: 422, body: { ...REFUSAL, cleanable: false } })).toMatchObject({ offer: null });
  });

  it("sin texto del backend no se ofrece: la interfaz no redacta la oferta", () => {
    expect(uploadOutcome({ status: 422, body: { ...REFUSAL, clean_offer: null } })).toMatchObject({ offer: null });
    expect(uploadOutcome({ status: 422, body: { ...REFUSAL, clean_label: "" } })).toMatchObject({ offer: null });
  });

  it("un 422 que no viene de la puerta, o un 503, son errores y no una oferta", () => {
    expect(() => uploadOutcome({ status: 422, body: { detail: "el volumen tiene que ser 3D" } })).toThrow(ApiError);
    expect(() => uploadOutcome({ status: 503, body: { ...REFUSAL, detail: "no pudo ejecutarse" } })).toThrow(
      "no pudo ejecutarse",
    );
    expect(() => uploadOutcome({ status: 413, body: null })).toThrow(ApiError);
  });

  it("una declaracion de limpieza a medias no se ensena como limpieza", () => {
    expect(cleaningOf({ cleaned: { fields: ["descrip"] } })).toBeNull();
    expect(cleaningOf({})).toBeNull();
    expect(cleaningOf({ cleaned: CLEANED })).toEqual(CLEANED);
  });
});
