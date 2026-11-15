"""Spike: NAIF SPICE en local frente a JPL Horizons — tiempo de luz, distancia y elongación.

Objetivo: comprobar que, con los núcleos genéricos mínimos de NAIF (`naif0012.tls` y
`de432s.bsp`, que baja `scripts/fetch_spice_kernels.py`), el cálculo local de
`app/environment/spice.py` da lo mismo que Horizons en los días de la misión configurada
(2026-11-01 a 2027-04-30), para declarar un error máximo. También se mira qué cuerpos trae el SPK
y qué cubre.

Necesita `spiceypy` (extra `[spice]`) y red para Horizons (una consulta de rango, con paso de un
día, como la precarga). A Horizons solo sale el objetivo, el observador y las fechas.

Ejecutar:  python backend/spikes/spike_spice.py [--step 1]
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.environment import ephemeris, spice  # noqa: E402

START = dt.date(2026, 11, 1)
STOP = dt.date(2027, 4, 30)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", type=int, default=1, help="días entre filas de Horizons")
    args = parser.parse_args()
    settings = get_settings()

    print("=" * 70)
    print("SPIKE: NAIF SPICE frente a JPL Horizons")
    print("=" * 70)
    state = spice.availability(settings)
    print(f"spiceypy {state.version}; disponible={state.available}; {state.reason or ''}")
    if not state.available:
        return
    import spiceypy as sp

    spk = str(spice.kernel_dir(settings) / spice.spk_name())
    ids = sp.spkobj(spk)
    bodies = [sp.bodc2n(ids[i]) if sp.bodc2s(ids[i]) else str(ids[i]) for i in range(sp.card(ids))]
    print(f"cuerpos en {spice.spk_name()}: {bodies}")
    print(f"cobertura para Marte (4), Tierra (399) y Sol: {spice.coverage_span(settings, '499')}")

    from astroquery.jplhorizons import Horizons

    table = Horizons(
        id="499", location=settings.observer_body,
        epochs={"start": START.isoformat(), "stop": STOP.isoformat(), "step": f"{args.step}d"},
    ).ephemerides()
    rows, unusable = ephemeris.rows_by_day(table)
    print(f"Horizons: {len(table)} filas, {unusable} inservibles")

    worst = {"lt_s": 0.0, "dist_km": 0.0, "elong_deg": 0.0}
    flags_differ: list[str] = []
    sample: list[str] = []
    for day, row in sorted(rows.items()):
        hz = ephemeris.window_from_row(table, row, day, "499")
        local = spice.window(settings, day, "499")
        lt_s = abs(hz.one_way_minutes - local.one_way_minutes) * 60
        dist_km = abs(hz.distance_au - local.distance_au) * spice.AU_KM
        elong = (
            abs((hz.solar_elongation_deg or 0) - (local.solar_elongation_deg or 0))
            if hz.solar_elongation_deg is not None else float("nan")
        )
        worst["lt_s"] = max(worst["lt_s"], lt_s)
        worst["dist_km"] = max(worst["dist_km"], dist_km)
        worst["elong_deg"] = max(worst["elong_deg"], elong)
        if hz.solar_elongation_flag != local.solar_elongation_flag:
            flags_differ.append(
                f"{day} {hz.solar_elongation_flag} vs {local.solar_elongation_flag}"
            )
        if day.day in (1, 15):
            sample.append(
                f"{day}  HZ {hz.one_way_minutes:9.5f} min {hz.distance_au:.8f} UA "
                f"{hz.solar_elongation_deg:7.3f}{hz.solar_elongation_flag}  | SPICE "
                f"{local.one_way_minutes:9.5f} min {local.distance_au:.8f} UA "
                f"{local.solar_elongation_deg:7.3f}{local.solar_elongation_flag}  "
                f"Δt={lt_s * 1000:.3f} ms Δd={dist_km:.2f} km Δe={elong:.5f}°"
            )
    print("\n".join(sample))
    print(f"\npeor diferencia en {len(rows)} días: tiempo de luz {worst['lt_s'] * 1000:.3f} ms, "
          f"distancia {worst['dist_km']:.2f} km, elongación {worst['elong_deg']:.5f}°")
    print(f"marcas /T-/L distintas: {flags_differ or 'ninguna'}")

    # Lo que pasa fuera de la cobertura del SPK.
    try:
        spice.window(settings, dt.date(2051, 1, 1), "499")
    except spice.SpiceUnavailable as exc:
        print(f"\nfuera de cobertura: {exc}")


if __name__ == "__main__":
    main()
