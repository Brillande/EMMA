import { Suspense, lazy } from "react";

import { BodySilhouette } from "../anatomy/BodySilhouette";
import type { useAnatomyState } from "../anatomy/useAnatomyState";
import { BoardOnly, useLook } from "../components/BoardOnly";
import { DomainName } from "../components/DomainName";
import { LevelBadge } from "../components/LevelBadge";
import { Mark } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { QualityBadge } from "../components/QualityBadge";
import type { CrewStatus } from "../lib/api";
import { LEVEL_ORDER, domainLabel } from "../lib/levels";
import { hasDoubtfulReadings } from "../lib/provenance";
import { LevelPill } from "./HomeCharts";

/** El cuerpo de la maqueta (1,5 MB de datos): perezoso, como en «Inicio», y solo bajo la concha nueva. */
const ReferenceBody = lazy(() => import("./ReferenceBody"));

/**
 * «Dominios», el primer panel de «Cuerpo»: la silueta con el nivel de cada región y la rejilla de
 * dominios, cada uno con su nivel, su trayectoria, sus motivos y la confianza del dato. Vivía dentro
 * de `CrewConsole.tsx`; sale a su fichero (tablero por secciones, 2026-11-07) para que la sección
 * «Cuerpo» tenga dueño propio y pueda montar sus piezas sin tocar la tabla de la consola. El estado
 * por regiones y la región elegida siguen siendo de la consola (la silueta de «Inicio» enseña los
 * mismos), por eso llegan como props.
 *
 * En la concha de la maqueta, bajo el título va el recuento de dominios por nivel (`DomainTally`):
 * lo que se lee primero, antes de la silueta y las tarjetas. No lleva barra de `score`: el backend
 * da la cifra sin su escala, y una barra sin escala sería inventada.
 */
export function DomainsPanel({
  status,
  anatomy,
  region,
  setRegion,
}: {
  status: CrewStatus;
  anatomy: ReturnType<typeof useAnatomyState>;
  region: string | null;
  setRegion: (region: string | null) => void;
}) {
  // Indicadores con lecturas de baja confianza, por dominio: se dice junto al nivel que
  // se apoya en ellos (especificacion §10). El detalle, en "Calidad del dato".
  const quality = status.data.quality;
  const doubtful = new Map<string, string[]>();
  for (const item of quality.indicators.filter(hasDoubtfulReadings)) {
    doubtful.set(item.domain, [...(doubtful.get(item.domain) ?? []), item.display_es]);
  }
  // Detrás de la silueta, el cuerpo de la maqueta que ya luce «Inicio» (petición del usuario,
  // 2026-11-08: «tenemos un cuerpo bastante mejor ya hecho, estaría bien usarlo en Cuerpo»). Adorno:
  // los rótulos de cada región y el color de su nivel siguen siendo los del backend, encima.
  const look = useLook();
  const backdrop =
    look === "reference" ? (
      <Suspense fallback={null}>
        <ReferenceBody />
      </Suspense>
    ) : undefined;
  return (
    <section data-ui="domains" className="panel" aria-label="Dominios">
      <PanelTitle concept="domains">Dominios</PanelTitle>
      <BoardOnly>
        <DomainTally domains={status.domains} />
      </BoardOnly>
      {/* La silueta acompana a la rejilla, no la sustituye: cada dominio sobre su region del
          cuerpo, con el mismo nivel que su tarjeta (decision del usuario, 2026-10-20). */}
      <div className="domains-overview">
        <BodySilhouette view={anatomy} selected={region} onSelect={setRegion} backdrop={backdrop} />
        <DomainGrid status={status} doubtful={doubtful} />
      </div>
    </section>
  );
}

/**
 * Cuántos dominios hay en cada nivel (`status.domains[*].level`), en el orden de la escala y con la
 * píldora del tablero (palabra, forma y color real del nivel, y la cifra). Solo los niveles con algún
 * dominio: una píldora roja con un cero diría «crítico» donde no lo hay. Un nivel que la interfaz no
 * conozca no se omite ni se suma a otro: llega a su píldora, que falla igual que la insignia de su
 * tarjeta (`levelStyle`), como señaló la revisión.
 */
function DomainTally({ domains }: { domains: CrewStatus["domains"] }) {
  const counts = new Map<string, number>();
  for (const risk of Object.values(domains)) counts.set(risk.level, (counts.get(risk.level) ?? 0) + 1);
  const rank = (level: string) => {
    const index = (LEVEL_ORDER as readonly string[]).indexOf(level);
    return index < 0 ? LEVEL_ORDER.length : index;
  };
  const counted = [...counts].sort(([a], [b]) => rank(a) - rank(b));
  if (counted.length === 0) return null;
  return (
    <p className="board-tally">
      <span className="sr-only">Dominios por nivel: </span>
      {counted.map(([level, count]) => (
        <LevelPill key={level} level={level} count={count} />
      ))}
    </p>
  );
}

/**
 * La rejilla de dominios: cada uno con su nivel, trayectoria, motivos y la confianza del dato.
 *
 * En la concha de la maqueta (muestra, 2026-11-08: «Cuerpo» pedía una pantalla y sus nueve tarjetas
 * bajaban por debajo de la figura) el nombre y la insignia del nivel van en una línea
 * (`.domain-head`), como las tarjetas RIDGE de la maqueta. Los motivos no se pliegan, tampoco los de
 * un dominio nominal: el backend solo los da para hallazgos que cuentan (una deriva preocupante bajo
 * el umbral, la dosis acumulada), avisos tempranos aunque el nivel no suba (lo señaló la revisión).
 * Tampoco la trayectoria ni la confianza baja del dato. La clásica (`#clasica`) conserva su tarjeta de siempre.
 */
function DomainGrid({ status, doubtful }: { status: CrewStatus; doubtful: Map<string, string[]> }) {
  const quality = status.data.quality;
  const board = useLook() === "reference";
  return (
    <div className="domains">
      {Object.entries(status.domains).map(([key, risk]) => {
        const title = (
          <h3>
            <DomainName domain={key} label={domainLabel(key)} />
          </h3>
        );
        const drivers = risk.drivers.length > 0 && (
          <ul className="drivers">
            {risk.drivers.map((driver) => (
              <li key={driver}>{driver}</li>
            ))}
          </ul>
        );
        return (
          <div className="domain" data-level={risk.level} key={key}>
            {board ? (
              <div className="domain-head">
                {title}
                <LevelBadge level={risk.level} />
              </div>
            ) : (
              <>
                {title}
                <LevelBadge level={risk.level} />
              </>
            )}
            {risk.trajectory != null && (
              <p className="secondary" title={risk.trajectory.basis}>
                <Mark pictogram={risk.trajectory.direction === "recovering" ? "arrow-down-right" : "arrow-up-right"}>
                  {risk.trajectory.display}
                </Mark>
              </p>
            )}
            {drivers}
            {doubtful.has(key) && (
              <p>
                <QualityBadge state="low" label={quality.labels.low} />{" "}
                <span className="secondary">{doubtful.get(key)?.join(", ")}</span>
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}
