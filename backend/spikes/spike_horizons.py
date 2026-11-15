"""Spike: JPL Horizons via astroquery — distancia Tierra-Marte y tiempo de luz.

Este es el unico uso legitimo de astroquery en el proyecto: efemerides reales
para calcular el retardo de comunicacion, que es el parametro que justifica
toda la autonomia del sistema.

Objetivo: confirmar la API de astroquery.jplhorizons, las columnas devueltas,
y validar el tiempo de luz contra valores conocidos (~3 min en oposicion
cercana, ~22 min en conjuncion).

Ejecutar:  .venv/Scripts/python.exe backend/spikes/spike_horizons.py
"""

import datetime as dt

from astroquery.jplhorizons import Horizons

# Constante IAU 2012: tiempo que tarda la luz en recorrer 1 UA (segundos).
LIGHT_SECONDS_PER_AU = 499.004783836

# Centro geocentrico de la Tierra como observador.
EARTH_GEOCENTER = "500@399"
MARS_BARYCENTER = "499"


def light_minutes(distance_au: float) -> float:
    return distance_au * LIGHT_SECONDS_PER_AU / 60.0


def probe(label: str, epoch: str) -> None:
    # HALLAZGO: Horizons no devuelve tabla si start == stop. Hay que pedir una
    # ventana real y quedarse con la primera fila.
    stop = (dt.date.fromisoformat(epoch) + dt.timedelta(days=1)).isoformat()
    obj = Horizons(id=MARS_BARYCENTER, location=EARTH_GEOCENTER, epochs={
        "start": epoch,
        "stop": stop,
        "step": "1d",
    })
    eph = obj.ephemerides()
    print(f"\n[{label}] epoca = {epoch}")
    if not hasattr(probe, "_columns_shown"):
        print(f"    columnas disponibles: {list(eph.columns)}")
        probe._columns_shown = True  # type: ignore[attr-defined]
    delta = float(eph["delta"][0])          # distancia observador-objetivo, UA
    owlt = light_minutes(delta)
    print(f"    delta = {delta:.6f} UA")
    print(f"    tiempo de luz (ida)    = {owlt:6.2f} min")
    print(f"    round-trip             = {owlt * 2:6.2f} min")
    # Horizons tambien devuelve lighttime en minutos si la columna existe
    if "lighttime" in eph.columns:
        print(f"    lighttime de Horizons  = {float(eph['lighttime'][0]):6.2f} min  <- contraste")


def main() -> None:
    print("=" * 70)
    print("SPIKE 4: JPL Horizons (astroquery) — tiempo de luz Tierra-Marte")
    print("=" * 70)

    # Oposicion 2027: Marte cerca -> retardo minimo
    probe("oposicion aprox (Marte cerca)", "2027-02-19")
    # Conjuncion aprox: Marte al otro lado del Sol -> retardo maximo
    probe("conjuncion aprox (Marte lejos)", "2028-02-10")
    # Fecha del hackathon, para la demo
    probe("dia del hackathon", "2026-11-14")

    print("\nValidacion esperada: ~3-4 min en oposicion, ~20-22 min en conjuncion.")


if __name__ == "__main__":
    main()
