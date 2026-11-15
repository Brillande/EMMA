import { tr } from "../lib/i18n";
import { LOADING_MARK, type RequestOutcome } from "../lib/marks";
import { MarkOf } from "./Mark";

/**
 * Un panel sin respuesta del backend: «Sin datos» y el motivo tal cual lo da el backend. Cuatro
 * paneles (diario, comida, descriptivos, PVT) tenían cada uno su copia; la palabra es la misma en
 * todos. La marca es la de lo que pasó con la petición (`requestOutcome`, §5.34.14): un «no» del
 * backend (4xx) con el triángulo en amarillo, una petición caída (5xx, sin red) con la cruz en
 * rojo. Hasta entonces iba en cian, como un dato ausente; el cian queda para un indicador concreto
 * sin dato, y las cifras de antes que se siguen viendo ya llevan su cursiva de caducadas.
 */
export function Unavailable({ outcome }: { outcome: RequestOutcome }) {
  return (
    <p>
      <MarkOf mark={outcome.mark}>
        {tr("Sin datos:", "No data:")} {outcome.text}
      </MarkOf>
    </p>
  );
}

/**
 * Un panel que espera su primera respuesta: la flecha que gira, sin color, con «Cargando…», en
 * texto secundario. Doce paneles escribían esta misma línea cada uno (§5.33.7 lo pidió como pieza);
 * la limpieza (§5.33.12) la deja aquí, junto a la de «sin datos», que es su otra cara.
 */
export function Loading() {
  return (
    <p className="secondary">
      <MarkOf mark={LOADING_MARK}>{tr("Cargando…", "Loading…")}</MarkOf>
    </p>
  );
}
