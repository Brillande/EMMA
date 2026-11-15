import { useEffect, useState } from "react";

import { BoardOnly } from "../components/BoardOnly";
import { DomainName } from "../components/DomainName";
import { LevelBadge } from "../components/LevelBadge";
import { Mark, MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { Loading } from "../components/Unavailable";
import type { PictogramName } from "../icons/registry";
import { ANNUNCIATION_MARKS, type AlertCounts } from "../lib/alerts";
import { type CrewStatus, type Framework, frameworkApi } from "../lib/api";
import { commsMark, commsStatusOf } from "../lib/commsStatus";
import { formatMinutes, formatNumber } from "../lib/format";
import { tr } from "../lib/i18n";
import { LEVELS, LEVEL_ORDER, domainLabel, levelStyle } from "../lib/levels";
import { MISSING_MARK, type RequestOutcome, UNKNOWN_PICTOGRAM, prefixedPictogram, requestOutcome } from "../lib/marks";
import { uiPictogram } from "../lib/uiMarks";
import { LevelPill, Segments, levelToken } from "./HomeCharts";

/**
 * Los cinco peligros del reto, uno por tarjeta (§5.40): radiación, aislamiento y confinamiento,
 * distancia de la Tierra, campos gravitatorios y entorno hostil y cerrado (RIDGE de NASA). Es la
 * pestaña con que abre la consola: lo que las notas de voz del equipo pedían ver primero.
 *
 * Qué pinta, y de dónde: el peligro de cada dominio y su nombre, de `GET /api/framework` →
 * `ridge` (`ingest/codes.py`); el nivel de cada dominio, del estado (`domains`). **No se agrega
 * un nivel por peligro**: la tarjeta lista sus dominios, cada uno con la insignia que dio el
 * backend; sacar «el peor» sería un nivel que el motor no calculó. La distancia lleva además el
 * retardo de ida con Tierra (`comms`), porque es el dato que la define en EMMA (la autonomía que
 * obliga); sin efemérides, la marca de dato ausente. El orden es el de la sigla; un peligro que la
 * interfaz no conozca sale al final con su nombre del backend y el dibujo de «desconocido».
 *
 * Tablero (decisión del usuario, 2026-11-07): bajo la concha de la maqueta cada tarjeta lleva
 * además la letra de su peligro (adorno, como en «Inicio»: la desviación declarada de F.5-1), un
 * segmento por dominio en el color real del nivel que dio el backend (`levelToken`; adorno junto a
 * la lista, que es la que lo dice con palabras) y cuántos dominios tiene. Sigue sin agregarse
 * nada: la cuenta es de dominios, no un nivel del peligro.
 *
 * Al final del fichero van las demás piezas del tablero de «Peligros y alertas» (los recuentos del
 * resumen, de las alertas y de «Qué hacer»): viven aquí, con un solo dueño por sección, y
 * `CrewConsole` solo las monta dentro de `BoardOnly`.
 */

const RIDGE_ORDER = ["radiation", "isolation", "distance", "gravity", "environment"];

export interface HazardGroup {
  hazard: string;
  display: string;
  domains: string[];
}

/** Los dominios del estado agrupados por su peligro, en el orden de la sigla. */
export function hazardGroups(ridge: Framework["ridge"], domains: readonly string[]): HazardGroup[] {
  const groups = new Map<string, HazardGroup>();
  for (const [domain, item] of Object.entries(ridge)) {
    const group = groups.get(item.hazard) ?? { hazard: item.hazard, display: item.display, domains: [] };
    if (domains.includes(domain)) group.domains.push(domain);
    groups.set(item.hazard, group);
  }
  const rank = (hazard: string) => {
    const index = RIDGE_ORDER.indexOf(hazard);
    return index === -1 ? RIDGE_ORDER.length : index;
  };
  return [...groups.values()].sort((a, b) => rank(a.hazard) - rank(b.hazard));
}

/** El nombre del backend («radiación») con mayúscula inicial: solo cambia la caja. */
export function capitalized(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/**
 * La letra de la sigla: la inicial de la clave del peligro del backend (`radiation` → R). Solo
 * para los cinco de RIDGE: un peligro que la interfaz no conoce no recibe una letra que no es de
 * la sigla (lo señaló la revisión), y sale sin ficha.
 */
export function hazardLetter(hazard: string): string | null {
  return RIDGE_ORDER.includes(hazard) ? hazard.charAt(0).toUpperCase() : null;
}

export function HazardCards({ status }: { status: CrewStatus }) {
  const [ridge, setRidge] = useState<Framework["ridge"] | null>(null);
  const [failure, setFailure] = useState<RequestOutcome | null>(null);
  useEffect(() => {
    let current = true;
    frameworkApi
      .get()
      .then((body) => {
        if (current) setRidge(body.ridge);
      })
      .catch((reason: unknown) => {
        if (current) setFailure(requestOutcome(reason));
      });
    return () => {
      current = false;
    };
  }, []);
  if (ridge === null) {
    return (
      <section data-ui="hazards" className="panel" aria-label={tr("Los cinco peligros", "The five hazards")}>
        <PanelTitle concept="hazards">{tr("Los cinco peligros", "The five hazards")}</PanelTitle>
        {failure === null ? (
          <Loading />
        ) : (
          <p>
            <MarkOf mark={failure.mark}>{tr("Peligros no disponibles: ", "Hazards unavailable: ")}{failure.text}</MarkOf>
          </p>
        )}
      </section>
    );
  }
  return <HazardCardsView ridge={ridge} status={status} />;
}

/** Las tarjetas con el mapa ya recibido: aparte para pintarlas en las pruebas sin red. */
export function HazardCardsView({ ridge, status }: { ridge: Framework["ridge"]; status: CrewStatus }) {
  const groups = hazardGroups(ridge, Object.keys(status.domains));
  const oneWay = status.comms?.one_way_minutes ?? null;
  // Sin retardo, lo que dice el backend (`comms_status`, 2026-11-11): cian si falta, gris si no aplica.
  const comms = commsStatusOf(status);
  return (
    <section data-ui="hazards" className="panel" aria-label={tr("Los cinco peligros", "The five hazards")}>
      <PanelTitle concept="hazards">{tr("Los cinco peligros", "The five hazards")}</PanelTitle>
      <div className="hazards">
        {groups.map((group) => {
          const letter = hazardLetter(group.hazard);
          return (
            <article className="hazard" key={group.hazard} aria-label={capitalized(group.display)}>
              <h3>
                {letter !== null && (
                  <BoardOnly>
                    <span className="hazard-letter" aria-hidden="true">
                      {letter}
                    </span>
                  </BoardOnly>
                )}
                <Mark pictogram={prefixedPictogram("ridge", group.hazard)}>{capitalized(group.display)}</Mark>
              </h3>
              <ul className="hazard-domains">
                {group.domains.map((domain) => {
                  const risk = status.domains[domain];
                  if (risk === undefined) return null;
                  return (
                    <li key={domain}>
                      <DomainName domain={domain} label={domainLabel(domain)} /> <LevelBadge level={risk.level} />
                    </li>
                  );
                })}
              </ul>
              {group.hazard === "distance" && (
                <p>
                  {oneWay === null ? (
                    comms.state === "missing" ? (
                      <MarkOf mark={MISSING_MARK}>{tr("Retardo con Tierra: sin efemérides", "Delay to Earth: no ephemeris")}</MarkOf>
                    ) : (
                      <MarkOf mark={commsMark(comms.state)}>{tr("Retardo con Tierra: ", "Delay to Earth: ")}{comms.word}</MarkOf>
                    )
                  ) : (
                    <Mark pictogram={uiPictogram("lightTime")}>
                      {tr("Retardo de ida ", "One-way delay ")}<span className="num">{formatMinutes(oneWay)}</span>
                    </Mark>
                  )}
                </p>
              )}
              <BoardOnly>
                {/* Un segmento por dominio en el color real de su nivel y la cuenta de dominios: la
                    lista de arriba ya dice cada nivel con su palabra; esto solo lo resume. Va el último
                    para quedar al pie de la tarjeta (`hazards.css`), debajo también del retardo. */}
                <div className="board-row hazard-tally secondary">
                  <Segments
                    tones={group.domains.map((domain) => levelToken(status.domains[domain]?.level))}
                    titles={group.domains.map(domainLabel)}
                  />
                  <span>
                    <span className="num">{formatNumber(group.domains.length)}</span>{" "}
                    {group.domains.length === 1 ? tr("dominio", "domain") : tr("dominios", "domains")}
                  </span>
                </div>
              </BoardOnly>
            </article>
          );
        })}
      </div>
    </section>
  );
}

/* ---- Piezas del tablero de «Peligros y alertas» (2026-11-07), montadas por `CrewConsole` en `BoardOnly` ---- */

/**
 * Píldora de recuento por nivel: con alguna, la de `HomeCharts` (`LevelPill`, teñida con el color
 * real del nivel); a cero, la forma y la palabra del nivel en texto secundario y sin color, como
 * el contador de la franja (`StatusStrip`): un «Crítico 0» en rojo sería color sin aviso (F.5.10),
 * y la franja de arriba lo enseña en gris en ese mismo instante (lo señaló la revisión).
 */
export function LevelCountPill({ level, count }: { level: string; count: number }) {
  if (count > 0) return <LevelPill level={level} count={count} />;
  const style = levelStyle(level);
  return (
    <span className="ref-pill board-pill secondary">
      <Mark pictogram={style.pictogram} className="level">
        {style.label}
      </Mark>
      <span className="num">{formatNumber(count)}</span>
    </span>
  );
}

/** Píldora neutra de recuento: el dibujo de su concepto, la cifra y la palabra en singular o plural. */
export function CountPill({ pictogram, count, one, many }: { pictogram: PictogramName; count: number; one: string; many: string }) {
  return (
    <span className="ref-pill board-pill">
      <Mark pictogram={pictogram}>
        <span className="num">{formatNumber(count)}</span> {count === 1 ? one : many}
      </Mark>
    </span>
  );
}

/**
 * El resumen: cuántos dominios hay en cada nivel, de menos a más grave, y un segmento por dominio
 * en el color real del suyo (adorno junto a la cuenta, que lo dice con palabras). Un nivel que la
 * interfaz no conoce no se calla ni se pinta como nominal: va en su píldora, «sin nivel», con el
 * dibujo de desconocido, la misma palabra que «Inicio» (`HomeQuickHazards`). La sección es
 * compartida: solo niveles y recuentos.
 */
export function DomainLevelTally({ domains }: { domains: CrewStatus["domains"] }) {
  const entries = Object.entries(domains);
  const unknown = entries.filter(([, risk]) => levelToken(risk.level) === null).length;
  return (
    <>
      <div className="board-tally" role="group" aria-label={tr("Dominios por nivel", "Domains by level")}>
        {LEVEL_ORDER.map((level) => (
          <LevelCountPill key={level} level={level} count={entries.filter(([, risk]) => risk.level === level).length} />
        ))}
        {unknown > 0 && (
          <span className="ref-pill board-pill secondary">
            <Mark pictogram={UNKNOWN_PICTOGRAM}>
              {tr("sin nivel ", "no level ")}<span className="num">{formatNumber(unknown)}</span>
            </Mark>
          </span>
        )}
      </div>
      <div className="board-row summary-domains secondary">
        <Segments tones={entries.map(([, risk]) => levelToken(risk.level))} titles={entries.map(([domain]) => domainLabel(domain))} />
        <span>
          <span className="num">{formatNumber(entries.length)}</span>{tr(" dominios", " domains")}
        </span>
      </div>
    </>
  );
}

/**
 * Las alertas: los recuentos de F.6.4, los mismos de la franja (`counts`), de más a menos grave
 * con la forma y la palabra de su nivel (también a cero: la clase sin alertas se dice, sin color);
 * lo que nadie ha reconocido, con la palabra de la franja; y lo silenciado, solo si lo hay, con la
 * marca de su estado (`lib/alerts.ts`). Sin quién: la sección es compartida.
 */
export function AlertTally({ counts }: { counts: AlertCounts }) {
  const byClass = { W: counts.warning, C: counts.caution, A: counts.advisory } as const;
  return (
    <div className="board-tally" role="group" aria-label={tr("Recuento de alertas", "Alert counts")}>
      {[...LEVEL_ORDER].reverse().map((level) => {
        const alertClass = LEVELS[level].alertClass;
        return alertClass === null ? null : <LevelCountPill key={level} level={level} count={byClass[alertClass]} />;
      })}
      <span className="ref-pill board-pill">
        <Mark pictogram="box-empty">
          {tr("sin reconocer ", "unacknowledged ")}<span className="num">{formatNumber(counts.unacknowledged)}</span>
        </Mark>
      </span>
      {counts.suppressed > 0 && (
        <span className="ref-pill board-pill">
          <MarkOf mark={ANNUNCIATION_MARKS.suppressed}>
            {tr("suprimidas ", "suppressed ")}<span className="num">{formatNumber(counts.suppressed)}</span>
          </MarkOf>
        </span>
      )}
      {counts.inhibited > 0 && (
        <span className="ref-pill board-pill">
          <MarkOf mark={ANNUNCIATION_MARKS.inhibited}>
            {tr("inhibidas ", "inhibited ")}<span className="num">{formatNumber(counts.inhibited)}</span>
          </MarkOf>
        </span>
      )}
    </div>
  );
}
