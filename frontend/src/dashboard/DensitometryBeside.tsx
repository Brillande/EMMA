import { ObservationTypeBadge } from "../components/ObservationTypeBadge";
import type { DensitometryCheck, DensitometryReading, DensitometryRegion } from "../lib/api";
import { displayUnit, formatNumber } from "../lib/format";

/**
 * La densitometría (DXA) MEDIDA en Tierra junto a la banda ósea INFERIDA (decisión del usuario,
 * 2026-10-26; `analysis/densitometry.py`). Por qué existe: la banda estima en vuelo lo que solo se
 * mide antes del lanzamiento y después del regreso, y la conversación de ideación pedía
 * contrastar la estimación con esa medida. Es una comprobación de la inferencia, no un veredicto:
 * sin color, como la banda. Todo el texto es del backend (los rótulos, cuándo se tomó cada
 * medida, si cae dentro, por encima o por debajo, y por qué no se compara una región); aquí solo
 * se ponen las cifras con su formato y los rótulos de tipo. Se enseña en «Estados inferidos» y en
 * el hueso del mapa del cuerpo.
 */
export function DensitometryBeside({ check }: { check: DensitometryCheck }) {
  return (
    <div className="densitometry">
      <p>
        <ObservationTypeBadge type={check.observation_type} /> {check.relation}
      </p>
      <ul className="drivers">
        {check.regions.map((region) => (
          <li key={region.key}>
            <RegionLine region={region} check={check} />
          </li>
        ))}
      </ul>
      <p className="secondary">
        {check.precision_note}{" "}
        <a href={check.source.url} target="_blank" rel="noreferrer">
          {check.source.source}: {check.source.title}
        </a>
      </p>
    </div>
  );
}

function Reading({ region, reading }: { region: DensitometryRegion; reading: DensitometryReading }) {
  return (
    <>
      {" "}
      · {reading.label}: <span className="num">{formatNumber(reading.value, region.decimals)}</span>{" "}
      {displayUnit(region.unit)} <span className="secondary num">({reading.when_display})</span>
    </>
  );
}

function RegionLine({ region, check }: { region: DensitometryRegion; check: DensitometryCheck }) {
  return (
    <>
      <strong>{region.region}</strong>
      {region.preflight !== null && <Reading region={region} reading={region.preflight} />}
      {region.postflight !== null && <Reading region={region} reading={region.postflight} />}
      {region.measured_loss_pct !== null && (
        <>
          {" "}
          · {check.loss_label}:{" "}
          <span className="num">{formatNumber(region.measured_loss_pct, 2)}</span> % ·{" "}
          {check.band_label} <ObservationTypeBadge type="inferred" />:{" "}
          <span className="num">{formatNumber(check.band.loss_pct_low, 2)}</span>–
          <span className="num">{formatNumber(check.band.loss_pct_high, 2)}</span> %
        </>
      )}
      . {region.statement}
    </>
  );
}
