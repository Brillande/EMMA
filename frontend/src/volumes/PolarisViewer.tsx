import { useState } from "react";

import { Command } from "../components/Command";
import { type VolumeSegmentation, polarisViewerUrl } from "../lib/api";

/** Presets que el visor web de Polaris sabe pintar (su `main.js` solo carga hígado, porta y vasos). */
export const POLARIS_PRESETS = new Set(["higado"]);

/**
 * El visor web de Polaris, copiado tal cual (`polaris/tools/visor3d_web/`), sobre esta
 * segmentación. Es el visor de EMMA para los presets que Polaris cubre: no se reimplementa ni se
 * adapta (regla del proyecto: primero se copia, los cambios se deciden después). El backend le
 * sirve los datos del ledger en sus rutas relativas. Su render (`render.html`) va aparte, como en
 * Polaris.
 *
 * Los dos mandos llevan el signo de su pagina (§5.33.9, `icons/sets/volumes.ts`): el marco con la
 * cruz del cursor para el visor, la esfera sombreada para el render; el pulsado lo dice
 * `aria-pressed`, con el estilo de los demas mandos.
 */
export function PolarisViewer({ segmentation }: { segmentation: VolumeSegmentation }) {
  const [page, setPage] = useState<"visor" | "render">("visor");
  const [height, setHeight] = useState<number | null>(null);
  return (
    <div className="polaris-viewer">
      <div className="measure-actions" data-ui-view="">
        <Command
          pictogram="frame-crosshair"
          type="button"
          aria-pressed={page === "visor"}
          onClick={() => setPage("visor")}
        >
          Visor de Polaris
        </Command>
        <Command
          pictogram="sphere-shaded"
          type="button"
          aria-pressed={page === "render"}
          onClick={() => setPage("render")}
        >
          Render de Polaris
        </Command>
      </div>
      <iframe
        key={page}
        className={`polaris-frame polaris-${page}`}
        title={page === "visor" ? "Visor de Polaris" : "Render de Polaris"}
        src={polarisViewerUrl(segmentation.ledger_index, page)}
        style={page === "visor" && height !== null ? { height } : undefined}
        onLoad={(event) => {
          // Misma procedencia: el marco crece con la pagina de Polaris y no hay doble scroll.
          const body = event.currentTarget.contentDocument?.body;
          if (page === "visor" && body) {
            const fit = () => setHeight(body.scrollHeight + 16);
            fit();
            new ResizeObserver(fit).observe(body);
          }
        }}
      />
    </div>
  );
}
