/**
 * Lo que hay a mano para responder a una emergencia, dentro de «Ayuda urgente» en «Distancia y
 * nodos», como la lista de «Respuesta a emergencias» de la maqueta de la ISS (pedido por el usuario,
 * 2026-11-15). Por qué existe: la tarjeta de ayuda ocupaba la altura del diagnóstico con dos líneas
 * de texto y un botón; la maqueta pone ahí qué recursos hay. Aquí, solo lo que EMMA tiene de verdad,
 * contado por el backend:
 *   * Protocolos de ecografía (`/api/imaging/protocols`): la única imagen médica que vuela.
 *   * Guías de medida (`/api/guides`): cómo se toma cada constante, paso a paso.
 *   * Medicamentos y equipamiento médico (`/api/inventory`): tipos con un recuento firmado.
 *
 * Lo que NO se copió: «Preparado», «Autonomía: 72 h», «Protocolos médicos (34)» y las marcas verdes
 * de todo: EMMA no evalúa si la tripulación está preparada ni calcula una autonomía médica en horas.
 * Un recuento es un recuento: con algo, la marca de «hay» (sin color); sin nada, «sin declarar» en
 * gris; si el backend no responde, su motivo.
 */
import { useEffect, useState } from "react";

import { MarkOf } from "../components/Mark";
import { api } from "../lib/api";
import { formatNumber } from "../lib/format";
import { tr } from "../lib/i18n";
import { inventoryApi } from "../lib/inventoryApi";
import { LOADING_MARK, OK_MARK, UNAVAILABLE_MARK, requestOutcome } from "../lib/marks";
import type { Fetched } from "./HomeBoard";
import { categoryViews } from "./HomeReserves";

/** Un recurso: cuántos hay (`null` = sin declarar) o por qué no se sabe. */
export type KitCount = Fetched<number | null>;

export interface KitRow {
  key: string;
  label: string;
  count: KitCount;
  unit: string;
}

function settle<T>(promise: Promise<T>, pick: (value: T) => number | null, set: (value: KitCount) => void) {
  promise.then(
    (value) => set({ state: "ready", value: pick(value) }),
    (failure: unknown) => set({ state: "failed", outcome: requestOutcome(failure) }),
  );
}

export function useEmergencyKit(active: boolean): KitRow[] {
  const [protocols, setProtocols] = useState<KitCount>({ state: "loading" });
  const [guides, setGuides] = useState<KitCount>({ state: "loading" });
  const [medications, setMedications] = useState<KitCount>({ state: "loading" });
  const [equipment, setEquipment] = useState<KitCount>({ state: "loading" });

  useEffect(() => {
    if (!active) return;
    settle(api.imaging.protocols(), (value) => value.protocols.length, setProtocols);
    settle(api.measurementGuides(), (value) => value.guides.length, setGuides);
    const inventory = inventoryApi.get();
    const kinds = (id: string) => (value: Parameters<typeof categoryViews>[0]) => {
      const view = categoryViews(value).find((item) => item.id === id);
      return view === undefined || view.undeclared ? null : view.kinds;
    };
    settle(inventory, kinds("medications"), setMedications);
    settle(inventory, kinds("medical-equipment"), setEquipment);
  }, [active]);

  return [
    { key: "protocols", label: tr("Protocolos de ecografía", "Ultrasound protocols"), count: protocols, unit: "" },
    { key: "guides", label: tr("Guías de medida", "Measurement guides"), count: guides, unit: "" },
    { key: "medications", label: tr("Medicamentos", "Medications"), count: medications, unit: tr("tipos", "kinds") },
    { key: "equipment", label: tr("Equipamiento médico", "Medical equipment"), count: equipment, unit: tr("tipos", "kinds") },
  ];
}

function CountOf({ row }: { row: KitRow }) {
  const { count } = row;
  if (count.state === "loading") return <MarkOf mark={LOADING_MARK}>…</MarkOf>;
  if (count.state === "failed") {
    return (
      <MarkOf mark={count.outcome.mark} title={count.outcome.text}>
        {tr("sin dato", "no data")}
      </MarkOf>
    );
  }
  if (count.value === null || count.value === 0) {
    return <MarkOf mark={UNAVAILABLE_MARK}>{tr("sin declarar", "not declared")}</MarkOf>;
  }
  return (
    <MarkOf mark={OK_MARK}>
      <span className="num">{formatNumber(count.value)}</span>
      {/* El inglés concuerda en número; el castellano queda como estaba. */}
      {row.unit !== "" && ` ${count.value === 1 ? tr(row.unit, "kind") : row.unit}`}
    </MarkOf>
  );
}

export function EmergencyKitList({ rows }: { rows: readonly KitRow[] }) {
  return (
    <ul
      className="ref-emergency-kit"
      aria-label={tr("Recursos para responder a una emergencia", "Resources for responding to an emergency")}
    >
      {rows.map((row) => (
        <li key={row.key} data-kit={row.key}>
          <span>{row.label}</span>
          <CountOf row={row} />
        </li>
      ))}
    </ul>
  );
}

export function NodesEmergencyKit({ active }: { active: boolean }) {
  return <EmergencyKitList rows={useEmergencyKit(active)} />;
}
