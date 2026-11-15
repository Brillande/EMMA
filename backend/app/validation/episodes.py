"""Agrupa lecturas marcadas en episodios: lo que de verdad ve un tripulante.

LA TASA POR LECTURA NO ES LO QUE PRODUCE FATIGA DE ALARMA.
----------------------------------------------------------
La validacion externa publica una tasa de alarma **por lectura** —0,23 % sobre los
22 sujetos sanos de MMASH—, y esa cifra sirve para comparar configuraciones del
motor. Pero no es lo que sufre quien esta al otro lado: veinte lecturas seguidas
del mismo indicador en la misma media hora son **un** aviso, no veinte.

Medido con este modulo sobre MMASH: las 43 lecturas marcadas son 17 episodios. La
diferencia entre las dos formas de contar es de 2,5 veces, y crece con la cadencia
del sensor —un wearable que muestrea cada minuto infla la tasa por lectura sin que
el tripulante vea un aviso mas—.

El corte por defecto es de media hora. No sale de ninguna fisiologia: sale de que
dos marcas del mismo indicador separadas por menos que eso llegan al panel como
una sola situacion. Se puede cambiar, y por eso es un parametro.

Un episodio agrupa por **sujeto e indicador**. No se mezclan indicadores aunque
coincidan en el tiempo: una caida de HRV y una subida de pulso a la misma hora son
dos hallazgos distintos sobre la misma persona, y el motor de riesgo los combina
por su cuenta.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.analysis.baseline import Deviation

# Separacion a partir de la cual dos lecturas marcadas del mismo indicador dejan de
# ser el mismo aviso.
EPISODE_GAP = dt.timedelta(minutes=30)


@dataclass(frozen=True)
class Episode:
    """Una racha de lecturas marcadas del mismo indicador, en el mismo sujeto."""

    subject: str
    key: str
    deviations: tuple[Deviation, ...]

    @property
    def start(self) -> dt.datetime:
        return self.deviations[0].effective

    @property
    def end(self) -> dt.datetime:
        return self.deviations[-1].effective

    @property
    def duration(self) -> dt.timedelta:
        return self.end - self.start

    @property
    def readings(self) -> int:
        return len(self.deviations)

    @property
    def peak(self) -> Deviation:
        """La lectura mas extrema del episodio: la que explica el aviso."""
        return max(self.deviations, key=lambda item: abs(item.z_score))

    def describe(self) -> str:
        when = f"{self.start:%H:%M}"
        if self.readings > 1:
            when += f"-{self.end:%H:%M}"
        return f"{self.subject} · {when} · {self.peak.describe()}"


@dataclass(frozen=True)
class EpisodeSummary:
    """Cuantos avisos distintos produce una corrida, y cada cuanto."""

    episodes: tuple[Episode, ...]
    flagged_readings: int
    subject_days: float

    @property
    def count(self) -> int:
        return len(self.episodes)

    @property
    def readings_per_episode(self) -> float:
        return self.flagged_readings / self.count if self.count else 0.0

    @property
    def per_crew_week(self) -> float:
        """Episodios por tripulante y semana: la cifra que importa para la fatiga.

        Extrapola desde el tiempo de registro disponible. MMASH son ~24 h por
        sujeto, asi que multiplicar por siete supone que una semana se parece al dia
        medido. Es una estimacion, y en un dataset de un dia no puede ser otra cosa.
        """
        return 7 * self.count / self.subject_days if self.subject_days else 0.0

    def describe(self) -> str:
        return (
            f"  lecturas marcadas        {self.flagged_readings}\n"
            f"  EPISODIOS                {self.count}\n"
            f"  lecturas por episodio    {self.readings_per_episode:.1f}\n"
            f"  registro                 {self.subject_days:.1f} días-sujeto\n"
            f"  EPISODIOS/TRIPULANTE-SEMANA {self.per_crew_week:.2f}"
        )


def group_episodes(
    deviations: Iterable[Deviation], gap: dt.timedelta = EPISODE_GAP
) -> list[Episode]:
    """Episodios de las desviaciones marcadas, ordenados por su inicio.

    Lo que no preocupa se ignora: una desviacion dentro de lo esperado no es parte
    de ningun aviso. Las marcas de tiempo salen de `Deviation.effective`, que es la
    de la lectura evaluada —no se reconstruyen emparejando por valor, que es
    ambiguo cuando un pulso entero se repite decenas de veces—.
    """
    by_series: dict[tuple[str, str], list[Deviation]] = defaultdict(list)
    for deviation in deviations:
        if deviation.is_concerning:
            by_series[(deviation.subject, deviation.key)].append(deviation)

    episodes: list[Episode] = []
    for (subject, key), items in by_series.items():
        items.sort(key=lambda item: item.effective)
        run = [items[0]]
        for previous, current in zip(items, items[1:], strict=False):
            if current.effective - previous.effective <= gap:
                run.append(current)
            else:
                episodes.append(Episode(subject, key, tuple(run)))
                run = [current]
        episodes.append(Episode(subject, key, tuple(run)))

    episodes.sort(key=lambda episode: (episode.start, episode.subject, episode.key))
    return episodes


def summarize(
    deviations: Sequence[Deviation],
    subject_days: float,
    gap: dt.timedelta = EPISODE_GAP,
) -> EpisodeSummary:
    """Resumen de avisos de una corrida completa.

    `subject_days` es el tiempo de registro que produjo esas desviaciones, sumado
    sobre todos los sujetos. Se pide en vez de deducirlo de las propias marcas
    porque un sujeto sin ninguna lectura marcada tambien cuenta: es justo el que
    baja la tasa.
    """
    episodes = group_episodes(deviations, gap=gap)
    flagged = sum(1 for item in deviations if item.is_concerning)
    return EpisodeSummary(
        episodes=tuple(episodes), flagged_readings=flagged, subject_days=subject_days
    )
