import { describe, expect, it } from "vitest";

import { type HiddenNode, hiddenOutsideDetail } from "./uiTargets";

/**
 * El asistente llega a un pliegue del inventario aunque esté dentro de un «Ver detalle» cerrado (lote
 * «muestra», 2026-11-08), pero no a uno de una pestaña que no está abierta.
 */

const node = (parent: HiddenNode | null, hidden = false, className = ""): HiddenNode => ({
  hidden,
  classList: { contains: (token: string) => className.split(" ").includes(token) },
  parentElement: parent,
});

describe("hiddenOutsideDetail", () => {
  it("a la vista: nada oculto por encima", () => {
    expect(hiddenOutsideDetail(node(node(node(null))))).toBe(false);
  });

  it("dentro de un «Ver detalle» cerrado de la pestaña abierta: se puede alcanzar", () => {
    const tab = node(null);
    const detail = node(tab, true, "board-detail-body");
    expect(hiddenOutsideDetail(node(detail))).toBe(false);
  });

  it("en una pestaña oculta: no, aunque además esté en un «Ver detalle»", () => {
    const tab = node(null, true, "section-body");
    expect(hiddenOutsideDetail(node(tab))).toBe(true);
    expect(hiddenOutsideDetail(node(node(tab, true, "board-detail-body")))).toBe(true);
  });
});
