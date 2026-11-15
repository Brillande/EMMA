import type { ReactNode } from "react";

import { BoardDetail } from "../components/BoardDetail";
import { Fold } from "../components/Fold";
import { Mark, MarkOf } from "../components/Mark";
import type { EphemerisCoverage, MissionProfile, ProfileCitation, SolarConjunction } from "../lib/api";
import { formatDay, formatNumber, formatSourceDate } from "../lib/format";
import { tr } from "../lib/i18n";
import { aspectPictogram, conjunctionPictogram, profilePictogram } from "./missionPictograms";
import {
  UNKNOWN_PROFILE_MARK,
  aspectDisplay,
  cachedStyle,
  conjunctionStyle,
  coverageStyle,
  ephemerisStyle,
  offlineCoverage,
} from "./missionProfile";

/**
 * El perfil de mision declarado (especificacion §3, MissionContext: location, gravity_regime,
 * comm_delay) con lo que una pagina oficial leida dice de el. Solo pinta: cada frase es del
 * backend, las citas van literales en su idioma, y lo que no se encontro sale «sin verificar»
 * en cian con su pictograma (tabla F.5-1: dato ausente). Lo que EMMA dice de si mismo junto a un
 * aspecto (`emma_note`, sin cita) va aparte, despues de las citas, para no leerse como de la fuente.
 * El perfil y cada aspecto llevan su
 * dibujo junto al nombre (`missionPictograms.ts`), sin color: nombrar no es avisar. Que es
 * descriptivo y no escala el riesgo se dice siempre a la vista, no dentro del desplegable; un
 * desajuste con las efemerides, igual (bajo la concha de la maqueta, desde la segunda ronda del lote
 * «muestra», la frase entera va tras el «Ver detalle» de la línea temporal y a la vista queda su
 * marca con su palabra, `MissionBoardWarnings`). La conjuncion solar del dia (`environment/conjunction.py`)
 * va debajo, con su dibujo junto al rotulo, su frase con la señal de su estado y la nota de que no
 * decide nada, a la vista; sus citas, plegadas. Bajo la concha de la maqueta (lote «muestra»,
 * 2026-11-08) esa nota y las citas van tras «Ver detalle»; la clásica no cambia.
 */
export function MissionProfileView({ profile }: { profile: MissionProfile }) {
  const ephemeris = profile.ephemeris;
  const mark = ephemeris === null ? null : ephemerisStyle(ephemeris.state);
  return (
    <div className="mission-profile">
      <p>
        {tr("Perfil de misión:", "Mission profile:")}{" "}
        <strong>
          <Mark pictogram={profilePictogram(profile.id)}>{profile.display}</Mark>
        </strong>{" "}
        <span className="secondary">({profile.note})</span>
      </p>
      {profile.unknown_text !== null && (
        <p>
          <MarkOf mark={UNKNOWN_PROFILE_MARK}>{profile.unknown_text}</MarkOf>
        </p>
      )}
      {ephemeris !== null && mark !== null && (
        <p className={mark.color === null ? "secondary" : undefined}>
          <MarkOf mark={mark}>{ephemeris.text}</MarkOf>
        </p>
      )}
      {profile.solar_conjunction != null && (
        <SolarConjunctionLine conjunction={profile.solar_conjunction} />
      )}
      {/* Lote «muestra» (2026-11-08): la nota y las fuentes de la conjunción y lo que dice la fuente
          del perfil, tras «Ver detalle»; el perfil con su nota, su marca de «sin verificar», la frase
          de las efemérides y la de la conjunción con su señal, a la vista. */}
      {(profile.solar_conjunction != null || profile.aspects.length > 0) && (
      <BoardDetail label={tr("nota y fuentes del perfil y de la conjunción", "note and sources for the profile and the conjunction")}>
      {profile.solar_conjunction != null && (
        <SolarConjunctionNotes conjunction={profile.solar_conjunction} />
      )}
      {profile.aspects.length > 0 && (
        <Fold data-ui="profile-source" concept="sourceText" label={tr("Lo que dice la fuente de este perfil", "What the source says about this profile")}>
          <ul className="drivers">
            {profile.aspects.map((aspect) => {
              return (
                <li key={aspect.key}>
                  <strong>
                    <Mark pictogram={aspectPictogram(aspect.key)}>{aspect.label}</Mark>:
                  </strong>{" "}
                  {aspect.statement !== null ? (
                    aspect.statement
                  ) : (
                    <AspectStatus status={aspect.status}>{aspect.status_text}</AspectStatus>
                  )}
                  {aspect.searched !== null && (
                    <span className="secondary"> {aspect.searched}</span>
                  )}
                  <Citations items={aspect.citations} />
                  {aspect.discrepancy !== null && (
                    <>
                      <br />
                      {aspect.discrepancy.text}
                      <Citations items={aspect.discrepancy.citations} />
                    </>
                  )}
                  {aspect.emma_note !== null && (
                    <>
                      <br />
                      <span className="secondary">{aspect.emma_note}</span>
                    </>
                  )}
                  {aspect.reused_from.length > 0 && (
                    <>
                      <br />
                      <span className="secondary">{tr("Leída antes para:", "Read earlier for:")} {aspect.reused_from.join(" · ")}</span>
                    </>
                  )}
                </li>
              );
            })}
          </ul>
          <p className="secondary">{profile.declared}</p>
          <p className="secondary">
            {tr("Páginas leídas:", "Pages read:")}{" "}
            {profile.pages_read.map((page, index) => (
              <span key={page.title}>
                {index > 0 && " · "}
                <Source title={page.title} url={page.url} /> (<ReadDates dates={page.read_on} />)
              </span>
            ))}
          </p>
        </Fold>
      )}
      </BoardDetail>
      )}
    </div>
  );
}

/**
 * La conjuncion solar: frase y nota del backend; la interfaz solo elige la señal de su estado. La
 * frase con su señal va a la vista; la nota de que no decide nada y sus citas
 * (`SolarConjunctionNotes`), en el detalle del perfil bajo la concha de la maqueta (lote «muestra»:
 * la nota eran cuatro renglones de explicación).
 */
function SolarConjunctionLine({ conjunction }: { conjunction: SolarConjunction }) {
  const style = conjunctionStyle(conjunction.state);
  return (
    <p className={style.color === null ? "secondary" : undefined}>
      <strong>
        <Mark pictogram={conjunctionPictogram()}>{conjunction.label}</Mark>:
      </strong>{" "}
      <MarkOf mark={style}>{conjunction.text}</MarkOf>
    </p>
  );
}

function SolarConjunctionNotes({ conjunction }: { conjunction: SolarConjunction }) {
  return (
    <>
      <p className="secondary">{conjunction.note}</p>
      <Fold data-ui="solar-conjunction-sources" concept="sourceText" label={tr("Lo que dicen las fuentes de la conjunción", "What the sources say about the conjunction")}>
        <CitationList items={conjunction.citations} />
      </Fold>
    </>
  );
}

/**
 * Segunda ronda del lote «muestra» (2026-11-08): bajo la concha de la maqueta la línea temporal medía
 * 640 px, la mitad frases del perfil, la conjunción y las efemérides que ya llevaban su marca. Aquí,
 * en una fila de píldoras, cada una con la MISMA marca que su frase y una palabra de lo que avisa: el
 * perfil (cian si el backend no lo reconoce), las efemérides del perfil (que no casan, en ámbar, o sin
 * comprobar, en cian: dos palabras distintas, no solo dos colores) y la conjunción solar solo si su
 * frase lleva señal (ámbar o cian; sin señal no avisan de nada), la cuenta de días con efemérides
 * en caché (cifras del backend, por `formatNumber`, con la marca de su cobertura) y el día del estado
 * si no está en caché. Las frases enteras siguen en el DOM, tras el «Ver detalle» de la línea temporal.
 */
export function MissionBoardWarnings({
  profile,
  coverage,
}: {
  profile: MissionProfile | null | undefined;
  coverage: EphemerisCoverage | null | undefined;
}) {
  const ephemeris = profile?.ephemeris ?? null;
  const ephemerisMark = ephemeris === null ? null : ephemerisStyle(ephemeris.state);
  const conjunction = profile?.solar_conjunction ?? null;
  const conjunctionMark = conjunction === null ? null : conjunctionStyle(conjunction.state);
  const offline = coverage == null ? null : offlineCoverage(coverage);
  if (profile == null && coverage == null) return null;
  return (
    <ul className="board-tally mission-warnings" aria-label={tr("Perfil, conjunción y efemérides", "Profile, conjunction and ephemeris")}>
      {profile != null && (
        <li className="ref-pill board-pill">
          {profile.unknown_text !== null ? (
            <MarkOf mark={UNKNOWN_PROFILE_MARK}>{profile.display}</MarkOf>
          ) : (
            <Mark pictogram={profilePictogram(profile.id)}>{profile.display}</Mark>
          )}
        </li>
      )}
      {ephemerisMark !== null && ephemerisMark.color !== null && (
        <li className="ref-pill board-pill">
          <MarkOf mark={ephemerisMark}>
            {ephemeris?.state === "mismatch" ? tr("perfil y efemérides no casan", "profile and ephemeris do not match") : tr("efemérides del perfil sin comprobar", "profile ephemeris unchecked")}
          </MarkOf>
        </li>
      )}
      {conjunction !== null && conjunctionMark !== null && conjunctionMark.color !== null && (
        <li className="ref-pill board-pill">
          <MarkOf mark={conjunctionMark}>{conjunction.label}</MarkOf>
        </li>
      )}
      {/* Con la red cortada cuentan SPICE y la caché de Horizons (`offlineCoverage`, 2026-11-11):
          un día que SPICE calcula no es un día sin efemérides. */}
      {offline !== null && coverage != null && (
        <li className="ref-pill board-pill">
          <MarkOf mark={coverageStyle(offline.state)}>{offline.offline ? tr("efemérides sin red", "ephemeris without network") : tr("efemérides en caché", "cached ephemeris")}</MarkOf>{" "}
          <span className="num">{formatNumber(offline.covered)}</span> {tr("de", "of")}{" "}
          <span className="num">{formatNumber(coverage.days)}</span> {tr("días", "days")}
        </li>
      )}
      {offline !== null && !offline.dayCovered && (
        <li className="ref-pill board-pill">
          <MarkOf mark={cachedStyle(false)}>
            {offline.offline ? tr("día del estado sin efemérides", "status day without ephemeris") : tr("día del estado sin efemérides en caché", "status day without cached ephemeris")}
          </MarkOf>
        </li>
      )}
    </ul>
  );
}

/** Una cita por renglon, sin el salto inicial de `Citations` (que va detras de un texto). */
function CitationList({ items }: { items: ProfileCitation[] }) {
  return (
    <ul className="drivers">
      {items.map((item) => (
        <li key={`${item.ref}|${item.quote}`} className="secondary">
          <q lang="en">{item.quote}</q> — <Source title={item.title} url={item.url} />,{" "}
          {item.section}; {tr("leído el", "read on")} <span className="num">{formatSourceDate(item.read_on)}</span>
        </li>
      ))}
    </ul>
  );
}

/**
 * La cobertura de efemerides de la mision (§5.36.6, pintada desde §5.37.18): que dias, del
 * lanzamiento al regreso, tienen efemerides en cache. Es lo que dice de antemano que dias saldran
 * sin retardo ni conjuncion con la red cortada (`EMMA_OFFLINE`, el modo nominal). La linea temporal
 * la pone justo despues del perfil, que acaba con la conjuncion: las dos salen de la misma caché.
 *
 * A la vista: la frase del backend (sin señal si estan todos; si falta alguno, en cian con el anillo
 * punteado, F.5-1 "Missing or stale data"), el dia que enseña el estado con la misma señal si no
 * esta en cache, como precargarlos y la nota de que no decide nada. Plegados, los tramos (los
 * ausentes en cian) y las citas. Bajo la concha de la maqueta (lote «muestra», 2026-11-08) cómo
 * precargarlos y la nota van con ellos tras «Ver detalle»; la frase y el día, a la vista. Las fechas pasan por `formatDay`; las cuentas, por `formatNumber`.
 */
export function EphemerisCoverageView({ coverage }: { coverage: EphemerisCoverage }) {
  // La señal de la frase y la del día, con lo que vale sin red (SPICE y caché, 2026-11-11).
  const offline = offlineCoverage(coverage);
  const style = coverageStyle(offline.state);
  const day = coverage.day;
  // Con lo de sin red (2026-11-11): un tramo sin caché de Horizons que SPICE calcula no es «sin
  // efemérides»; se dice sin señal («sin caché de JPL Horizons») y en cian solo los que no tienen
  // ninguna de las dos (`offline_missing`).
  const runs = [
    ...coverage.covered.map((run) => ({ run, covered: true, word: tr("en caché", "cached") })),
    ...(offline.offline
      ? [
          ...coverage.missing.map((run) => ({ run, covered: true, word: tr("sin caché de JPL Horizons", "no JPL Horizons cache") })),
          ...offline.missing.map((run) => ({ run, covered: false, word: tr("sin efemérides", "no ephemeris") })),
        ]
      : coverage.missing.map((run) => ({ run, covered: false, word: tr("sin efemérides", "no ephemeris") }))),
  ].sort((a, b) => a.run.start.localeCompare(b.run.start));
  return (
    <div className="ephemeris-coverage">
      <p className={style.color === null ? "secondary" : undefined}>
        <strong>
          <Mark pictogram="calendar">{tr("Efemérides en caché", "Cached ephemeris")}</Mark>:
        </strong>{" "}
        <MarkOf mark={style}>{coverage.text}</MarkOf>
      </p>
      <p className="secondary">
        {tr("Día del estado:", "Status day:")} <span className="num">{formatDay(day.date)}</span> ·{" "}
        <MarkOf mark={cachedStyle(offline.dayCovered)}>
          {offline.dayText ?? (day.covered ? tr("en caché", "cached") : tr("sin efemérides en caché", "no cached ephemeris"))}
        </MarkOf>
        {!day.in_mission && tr(" · fuera de los días de la misión", " · outside the mission days")}
      </p>
      {/* Lote «muestra» (2026-11-08): cómo precargarlas, la nota y los dos pliegues (tramos y fuente
          de la precarga), tras un solo «Ver detalle»; la frase con su señal y el día, a la vista. */}
      <BoardDetail label={tr("cómo precargarlas, tramos y fuente", "how to preload them, runs and source")}>
      {coverage.how_to_preload !== null && <p className="secondary">{coverage.how_to_preload}</p>}
      <p className="secondary">{coverage.note}</p>
      {runs.length > 0 && (
        <Fold data-ui="ephemeris-cache" pictogram="calendar" label={tr("Tramos de días en caché y sin ella", "Runs of days cached and not cached")}>
          <ul className="drivers">
            {runs.map(({ run, covered, word }) => (
              <li key={`${word}|${run.start}`}>
                <MarkOf mark={cachedStyle(covered)}>{word}</MarkOf>:{" "}
                <span className="num">{formatDay(run.start)}</span>
                {run.end !== run.start && (
                  <>
                    {" "}
                    {tr("a", "to")} <span className="num">{formatDay(run.end)}</span>
                  </>
                )}{" "}
                (<span className="num">{formatNumber(run.days)}</span> {run.days === 1 ? tr("día", "day") : tr("días", "days")})
              </li>
            ))}
          </ul>
        </Fold>
      )}
      {coverage.citations.length > 0 && (
        <Fold data-ui="ephemeris-preload-source" concept="sourceText" label={tr("Lo que dice la fuente de la precarga", "What the preload source says")}>
          <CitationList items={coverage.citations} />
        </Fold>
      )}
      </BoardDetail>
    </div>
  );
}

/** Los dias de lectura de una pagina: cada pagina los suyos, no una fecha comun para todas. */
/**
 * La frase de un aspecto con la señal de su estado (`aspectDisplay`). Un estado que la interfaz no
 * conoce no tumba la vista: va «no disponible» en gris, con el estado tal cual lo mandó el backend.
 */
export function AspectStatus({ status, children }: { status: string; children: ReactNode }) {
  const { mark, known } = aspectDisplay(status);
  return (
    <MarkOf mark={mark}>
      {children}
      {!known && (
        <>
          {" "}
          <span className="secondary">
            {tr(`(estado no reconocido por la interfaz: «${status}»)`, `(state not recognized by the interface: «${status}»)`)}
          </span>
        </>
      )}
    </MarkOf>
  );
}

export function ReadDates({ dates }: { dates: string[] }) {
  return (
    <>
      {dates.map((date, index) => (
        <span key={date}>
          {index > 0 && (index === dates.length - 1 ? tr(" y ", " and ") : ", ")}
          <span className="num">{formatSourceDate(date)}</span>
        </span>
      ))}
    </>
  );
}

export function Source({ title, url }: { title: string; url: string | null }) {
  if (url === null) return <>{title}</>;
  return (
    <a href={url} target="_blank" rel="noreferrer">
      {title}
    </a>
  );
}

/** La frase tal cual se leyo, con su pagina, su apartado y el dia de lectura. */
function Citations({ items }: { items: ProfileCitation[] }) {
  return (
    <>
      {items.map((item) => (
        <span key={`${item.ref}|${item.quote}`} className="secondary">
          <br />
          <q lang="en">{item.quote}</q> — <Source title={item.title} url={item.url} />,{" "}
          {item.section}; {tr("leído el", "read on")} <span className="num">{formatSourceDate(item.read_on)}</span>
        </span>
      ))}
    </>
  );
}
