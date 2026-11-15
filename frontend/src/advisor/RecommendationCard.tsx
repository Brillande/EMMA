import { type ReactNode, useState } from "react";

import { BoardDetail } from "../components/BoardDetail";
import { useLook } from "../components/BoardOnly";
import { Command } from "../components/Command";
import { DomainName } from "../components/DomainName";
import { FieldLabel } from "../components/FieldLabel";
import { Fold } from "../components/Fold";
import { Mark, MarkOf } from "../components/Mark";
import { EvidenceList } from "../evidence/EvidenceList";
import type { Countermeasure, CountermeasureEffects, Recommendation } from "../lib/api";
import { formatNumber } from "../lib/format";
import { tr } from "../lib/i18n";
import { EMPTY_MARK, type RequestOutcome, type StateMark, prefixedPictogram, requestOutcome } from "../lib/marks";
import { uiPictogram } from "../lib/uiMarks";
import {
  basisPictogram,
  contraindicationsLine,
  decisionNote,
  declineState,
  DECLINE_REASON_MAX,
  type EffectsView,
  effectsView,
  priorHasDetail,
  priorResponse,
  type PriorAdoptionView,
  type PriorResponseView,
  resourcesLine,
  urgencyPictogram,
} from "./recommendation";
import {
  ADVERSE_EFFECTS_PICTOGRAM,
  CO_ADOPTION_PICTOGRAM,
  CONTRAINDICATIONS_PICTOGRAM,
  familyPictogram,
} from "./library";
import { RequestWarning } from "./RequestWarning";
import {
  resourceClarification,
  resourceStatus,
  type ResourceLine,
  type ResourceStatusView,
} from "./resources";

const URGENCY = {
  routine: tr("Rutina", "Routine"),
  soon: tr("Pronto", "Soon"),
  immediate: tr("Inmediata", "Immediate"),
} as const;

/**
 * Una recomendacion, tal y como la redacta el backend.
 *
 * Magenta: tabla F.5-2, *"Electronic Procedures and system directed"*. Marca que el
 * texto sale de la automatizacion, no de una persona. Y F.6.2: *"Automated systems
 * that provide decisions or recommendations must provide explanation with
 * rationale"*, asi que el motivo y la evidencia van siempre con la accion.
 *
 * Con la especificacion del equipo (§8) la accion es una contramedida de la biblioteca: se
 * ve que cuesta, en que se apoya y cuando se sabra si ha servido. Adoptarla es una decision
 * humana firmada (§14); la interfaz solo la ofrece.
 *
 * Decir que no tambien es una decision (§2, human-in-the-loop): se firma con su motivo y NO
 * retira la recomendacion, que sigue aqui con la nota de lo decidido —texto del backend— al
 * lado. La nota lleva pictograma y palabra y ningun color de alerta: no es una alarma ni la
 * apaga.
 *
 * Pictogramas (§5.32.5): junto a cada palabra del backend, nunca en su lugar. El rotulo lleva el
 * dominio con su dibujo, la urgencia con sus galones y la antena si hay que informar a Tierra; la
 * nota de lo decidido el circulo tachado; la adopcion en seguimiento la marca de hecho; el
 * respaldo una hoja o el guion de «no aplica», y el eje RIDGE su dibujo. Cada recurso lleva el de
 * su familia y cada estado el suyo con su color (`resources.ts`).
 *
 * Que se ve sin abrir nada (2026-10-13): con varias recomendaciones a la vez la tarjeta se habia
 * vuelto una pared de texto y lo que hay que leer primero —que se recomienda y por que— se
 * perdia. A la vista quedan el rotulo, la accion, el motivo, la nota de lo decidido, el respaldo,
 * las contraindicaciones y los efectos, los botones y UNA linea por bloque plegado. Plegado, con
 * `<details>` nativo (se abre con teclado): el coste y el seguimiento, la lista de recursos y el
 * detalle de cada adopcion anterior. Plegar no es callar: lo que falta a bordo se ve en el
 * resumen de su bloque, y la advertencia de la respuesta previa va fuera del suyo
 * (`foldedCard.test.ts` tiene una prueba por cada cosa que debe verse sin abrir).
 *
 * Segunda pasada (§5.33.5): el signo de cada cosa sale del vocabulario (`lib/uiMarks.ts`). El
 * motivo lleva el bocadillo de «lo que alguien dice»; los mandos, la marca de «dar por bueno» y
 * el circulo tachado de «no»; los plegables de concepto (evidencia, coste, adopciones anteriores)
 * su dibujo con `Fold`; las claves de la ficha el suyo con `FieldLabel`. Contraindicaciones y
 * efectos no tienen concepto en `uiMarks.ts`: desde la decimosexta ronda (§5.36.19) llevan los dos
 * dibujos de las cabeceras de la biblioteca (`library.ts`), los mismos y no otros, para que la
 * tarjeta y la tabla digan lo mismo con el mismo signo. Los dos resumenes cuyo dibujo es un
 * estado que cambia —recursos a bordo, respuesta previa— siguen con su `<Mark>` en un `<details>`,
 * como un mando cuyo dibujo es un estado: un segundo dibujo delante seria uno sin palabra. El
 * fallo de una peticion sigue en amarillo, con el triangulo delante.
 *
 * LO PASADO, SIN COLOR (`past`, decimoquinta ronda, §5.35.8). En un momento pasado de la cadena
 * anatómica la tarjeta conservaba el magenta de «lo propone la automatización» (rótulo y filete) y
 * el color de cada estado de recursos, y se leía como una recomendación vigente. Con `past` lleva
 * la forma sin su color, la convención del historial del hábitat: las mismas palabras y los
 * mismos dibujos (urgencia, dominio, estados de recursos), el rótulo y el filete en el color
 * secundario. La evidencia no cambia: describe la fuente, no el momento, y su alcance es una
 * advertencia que no se apaga.
 */
export function RecommendationCard({
  item,
  operator = "",
  adopted = false,
  onAdopt,
  onDecline,
  resourcesClarified = false,
  past = false,
}: {
  item: Recommendation;
  operator?: string;
  /** Ya hay un seguimiento abierto de esta contramedida. */
  adopted?: boolean;
  onAdopt?: (countermeasureId: string, by: string) => Promise<void>;
  /** Deja firmado que no se adopta, con el motivo de quien decide. */
  onDecline?: (countermeasureId: string, by: string, reason: string) => Promise<void>;
  /**
   * La lista que contiene la tarjeta ya dice una vez la aclaracion de los recursos
   * (`RecommendationList`). Por defecto NO: una tarjeta suelta la lleva ella, para que usarla
   * fuera de la lista no la haga desaparecer.
   */
  resourcesClarified?: boolean;
  /** La de un momento pasado (recalculado, sin asiento): su forma, sin su color. */
  past?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<RequestOutcome | null>(null);
  const [reason, setReason] = useState("");
  const measure = item.countermeasure;
  const who = operator.trim();
  const note = decisionNote(item);
  const prior = priorResponse(item);
  const resources = resourceStatus(item);
  const look = useLook();
  const declining = declineState({
    hasHandler: onDecline !== undefined && measure !== null,
    adopted,
    operator,
    reason,
    busy,
  });
  const tag = (
    <span className={past ? "source-tag secondary" : "source-tag c-magenta"}>
      {tr("Recomendación del sistema", "System recommendation")}{" · "}
      <DomainName domain={item.domain} />
      {" · "}
      <Mark pictogram={urgencyPictogram(item.urgency)}>
        {tr("urgencia ", "urgency ")}{URGENCY[item.urgency] ?? item.urgency}
      </Mark>
      {item.notify_ground && (
        <>
          {" · "}
          <Mark pictogram="antenna-dish">{tr("informar a Tierra", "inform Earth")}</Mark>
        </>
      )}
    </span>
  );
  const rationale = (
    <p className="secondary">
      <Mark pictogram={uiPictogram("reason")}>{tr("Motivo: ", "Reason: ")}{item.rationale}</Mark>
    </p>
  );
  const decided = note !== null && (
    <p>
      <Mark pictogram="slash-circle">{note.text}</Mark>
      <br />
      {/* Con qué reglas se firmó el «no» (§5.39.9): la frase del backend, sin color. */}
      <span className="secondary">
        {note.meaning}
        {item.decision?.rules ? ` · ${item.decision.rules.text}` : ""}
      </span>
    </p>
  );
  // Las piezas de la tarjeta, una vez; el orden en que se montan depende de la concha (abajo).
  // Los efectos de la recomendacion (con la co-adopcion de este tripulante) o, si un backend
  // anterior no los manda ahi, los de la ficha de la biblioteca, si los trae.
  const factsOf = (part: "all" | "before-adopting" | "rest") =>
    measure !== null ? (
      <CountermeasureFacts measure={measure} effects={item.effects ?? measure.effects ?? null} part={part} />
    ) : null;
  const resourcesBlock = resources !== null ? <ResourceStatusBlock status={resources} past={past} /> : null;
  const clarification = !resourcesClarified ? <ResourceClarificationNote items={[item]} /> : null;
  const priorBlock = prior !== null ? <PriorResponseBlock prior={prior} /> : null;
  const adoptBlock = measure !== null && onAdopt !== undefined && (
    <p>
      {adopted ? (
        <Mark pictogram="check" className="secondary">
          {tr("Adoptada: en seguimiento.", "Adopted: in follow-up.")}
        </Mark>
      ) : (
        <Command
          concept="adopt"
          disabled={busy || who === ""}
          title={who === "" ? tr("Escriba quién está en consola", "Enter who is at the console") : undefined}
          onClick={() => {
            setBusy(true);
            setError(null);
            onAdopt(measure.id, who)
              .catch((cause: unknown) => setError(requestOutcome(cause)))
              .finally(() => setBusy(false));
          }}
        >
          {tr("Adoptar y seguir", "Adopt and follow")}
        </Command>
      )}
      {error !== null && <RequestWarning outcome={error} />}
    </p>
  );
  const declineBlock = measure !== null && onDecline !== undefined && declining.offered && (
    <form
      className="inline-form"
      onSubmit={(event) => {
        event.preventDefault();
        if (!declining.ready) return;
        setBusy(true);
        setError(null);
        onDecline(measure.id, who, reason.trim())
          .then(() => setReason(""))
          .catch((cause: unknown) => setError(requestOutcome(cause)))
          .finally(() => setBusy(false));
      }}
    >
      <input
        value={reason}
        maxLength={DECLINE_REASON_MAX}
        onChange={(event) => setReason(event.target.value)}
        placeholder={tr("motivo de no adoptarla", "reason for not adopting it")}
        aria-label={tr("Motivo de no adoptarla", "Reason for not adopting it")}
      />
      <Command
        concept="decline"
        type="submit"
        disabled={!declining.ready}
        title={declining.missing ?? undefined}
      >
        {tr("No adoptar", "Do not adopt")}
      </Command>
      {onAdopt === undefined && error !== null && <RequestWarning outcome={error} />}
    </form>
  );
  const evidence = item.evidence.length > 0 && (
    <Fold data-ui="recommendation-evidence" concept="evidence" label={<>{tr("Evidencia (", "Evidence (")}{formatNumber(item.evidence.length)})</>}>
      <EvidenceList items={item.evidence} />
    </Fold>
  );
  // Tablero (decisión del usuario, 2026-11-08: «una pantalla por sección»). Lo que se vio a 1672 px:
  // cada tarjeta medía unos 950 px —respaldo, contraindicaciones, efectos, coste, respuesta previa y
  // evidencia, una debajo de otra— y «Qué hacer» llenaba él solo una vista entera. En la concha de
  // la maqueta la tarjeta es un mosaico. A la vista: el rótulo magenta, la acción, el motivo (el
  // porqué de la alerta), la nota de lo decidido, lo que consta de los recursos (sus marcas de «sin
  // declarar» y «no disponible» no se pliegan nunca), las contraindicaciones —lo que hay que saber
  // antes de pulsar «Adoptar», justo encima del mando— y los dos mandos. Tras «Ver detalle», con el
  // mismo texto: el respaldo, los efectos (salvo si llevan la marca cian de «nada escrito», que va
  // con las contraindicaciones), el coste, la respuesta previa entera —su resumen y su advertencia
  // juntos: la advertencia no se separa del resumen que matiza— y la evidencia. La clásica conserva
  // su orden de siempre.
  if (look === "reference") {
    const folded = [
      measure !== null ? tr("ficha", "fact sheet") : null,
      prior !== null ? tr("respuesta previa", "prior response") : null,
      evidence !== false ? tr("evidencia", "evidence") : null,
    ].filter((word): word is string => word !== null);
    return (
      <article className={past ? "recommendation past" : "recommendation"}>
        {tag}
        <p>{item.action}</p>
        {rationale}
        {decided}
        {resourcesBlock}
        {clarification}
        {factsOf("before-adopting")}
        {(adoptBlock !== false || declineBlock !== false) && (
          <div className="recommendation-commands">
            {adoptBlock}
            {declineBlock}
          </div>
        )}
        {folded.length > 0 && (
          <BoardDetail label={folded.join(", ").replace(/, ([^,]*)$/, tr(" y $1", " and $1"))}>
            {factsOf("rest")}
            {priorBlock}
            {evidence}
          </BoardDetail>
        )}
      </article>
    );
  }
  return (
    <article className={past ? "recommendation past" : "recommendation"}>
      {tag}
      <p>{item.action}</p>
      {rationale}
      {decided}
      {factsOf("all")}
      {resourcesBlock}
      {clarification}
      {priorBlock}
      {adoptBlock}
      {declineBlock}
      {evidence}
    </article>
  );
}

/**
 * Las lineas de los efectos, texto del backend y en secundario: el beneficio esperado (sin
 * magnitud), donde cae cada efecto adverso declarado con lo que la nota dice y de donde sale, o la
 * frase de «no declarado». La tarjeta y la tabla de la biblioteca pintan las mismas lineas.
 */
export function EffectsLines({ effects }: { effects: EffectsView }) {
  return (
    <ul className="effects">
      <li>{effects.benefit}</li>
      {effects.adverse.map((line) => (
        <li key={line.key}>
          {line.display}: {line.text}
          {line.basis !== "" && <span className="secondary"> — {line.basis}</span>}
        </li>
      ))}
      {effects.adverseText !== null && <li>{effects.adverseText}</li>}
      {/* Declara efectos y no llega ninguno legible: el hueco se ve, no se lee como «no tiene». */}
      {effects.adverseEmpty && (
        <li>
          <MarkOf mark={EMPTY_MARK}>{tr("nada escrito", "nothing written")}</MarkOf>
        </li>
      )}
    </ul>
  );
}

function PriorAdoptionLines({ adoption }: { adoption: PriorAdoptionView }) {
  return (
    <p>
      {adoption.lines.map((line, index) => (
        <span key={index}>
          {index > 0 && <br />}
          {line}
        </span>
      ))}
    </p>
  );
}

/**
 * Que paso las otras veces que se adopto esta contramedida (KB H5). Todo el texto es del backend.
 *
 * Pictograma y palabra, y ningun color de alerta: es historia, no un aviso ni un resultado. El
 * dibujo es el del estado de la ultima adopcion (`priorPictogram`: nada, en curso, cerrada). A la
 * vista queda el resumen del backend; las lineas de cada adopcion y con que compara la evaluacion
 * van plegadas. La advertencia —lo que paso despues no prueba que fuera por la contramedida— va
 * SIEMPRE visible, fuera del desplegable: es la que impide leer el resumen como eficacia.
 */
export function PriorResponseBlock({ prior }: { prior: PriorResponseView }) {
  const summary = <Mark pictogram={prior.pictogram}>{tr("Respuesta previa: ", "Prior response: ")}{prior.summary}</Mark>;
  return (
    // Grupo con nombre y no región (lo que sería una `<section>` con nombre): cada ficha lleva el
    // suyo, y cinco regiones «Respuesta previa» en la lista de puntos de referencia del lector no se
    // distinguen (§5.41). Sigue siendo `<section>` para el inventario del asistente (un apartado).
    <section role="group" data-ui="recommendation-prior-response" aria-label={tr("Respuesta previa", "Prior response")}>
      {priorHasDetail(prior) ? (
        <details data-ui="recommendation-prior-response-detail">
          <summary className="lead">{summary}</summary>
          {prior.last !== null && prior.last.lines.length > 0 && (
            <PriorAdoptionLines adoption={prior.last} />
          )}
          {prior.earlier.length > 0 && (
            <Fold data-ui="recommendation-earlier-adoptions"
              concept="history"
              label={<>{tr("Adopciones anteriores (", "Earlier adoptions (")}{formatNumber(prior.earlier.length)})</>}
            >
              {prior.earlier.map((adoption) => (
                <PriorAdoptionLines key={adoption.key} adoption={adoption} />
              ))}
            </Fold>
          )}
          {prior.basis !== null && <p className="secondary">{prior.basis}</p>}
        </details>
      ) : (
        <p>{summary}</p>
      )}
      <p className="secondary">{prior.caveat}</p>
    </section>
  );
}

/** La marca de un estado de recursos: con su color, o en un momento pasado solo su forma. */
function ResourceStateWord({ mark, past, children }: { mark: StateMark; past: boolean; children: ReactNode }) {
  return past ? <Mark pictogram={mark.pictogram}>{children}</Mark> : <MarkOf mark={mark}>{children}</MarkOf>;
}

function ResourceLineItem({ line, past }: { line: ResourceLine; past: boolean }) {
  return (
    <li>
      <Mark pictogram={line.pictogram}>{line.description}</Mark> ·{" "}
      <ResourceStateWord mark={line.mark} past={past}>
        {line.stateDisplay}
      </ResourceStateWord>
      {line.note !== null && <span className="secondary"> · {line.note}</span>}
    </li>
  );
}

/**
 * Que le consta a EMMA de los recursos que pide la contramedida. Todo el texto es del backend.
 *
 * Es un aviso al lado, no un veto: la contramedida se sigue ofreciendo y se puede adoptar. Cada
 * recurso lleva el dibujo de su familia junto a su nombre, y pictograma, palabra y color de su
 * estado (`resources.ts`): «sin declarar» es un dato ausente (cian), nunca un «disponible».
 *
 * La lista va plegada; el resumen dice lo esencial con la frase del backend y, delante, la marca
 * y la palabra de cada estado que no sea «declarado disponible»: un recurso que falta se ve sin
 * abrir. El rotulo del bloque lleva la forma del peor estado presente, sin color. El rotulo de
 * quien declara —una persona; EMMA no lleva inventario— y la advertencia no van aqui: se dicen
 * una vez por lista (`ResourceClarificationNote`). En un momento pasado (`past`) cada estado
 * lleva su forma y su palabra, sin su color.
 */
export function ResourceStatusBlock({ status, past = false }: { status: ResourceStatusView; past?: boolean }) {
  return (
    // Grupo, no región: uno por ficha (como «Respuesta previa», §5.41).
    <section role="group" data-ui="recommendation-resources" aria-label={tr("Recursos a bordo", "Onboard resources")}>
      <details data-ui="recommendation-resources-detail">
        <summary className="lead">
          <Mark pictogram={status.statusPictogram}>{tr("Recursos a bordo", "Onboard resources")}</Mark>
          {status.summaryMarks.map((item) => (
            <span key={item.state}>
              {" · "}
              <ResourceStateWord mark={item.mark} past={past}>
                {item.stateDisplay}
              </ResourceStateWord>
            </span>
          ))}
          {" — "}
          {status.text}
        </summary>
        <ul>
          {status.lines.map((line) => (
            <ResourceLineItem key={line.key} line={line} past={past} />
          ))}
        </ul>
      </details>
      {status.exposed.length > 0 && (
        <ul>
          {status.exposed.map((line) => (
            <ResourceLineItem key={line.key} line={line} past={past} />
          ))}
        </ul>
      )}
    </section>
  );
}

/**
 * La aclaracion de los recursos de a bordo, una vez: que los declara una persona y EMMA no lleva
 * inventario, y que «sin declarar» no es «disponible». Texto del backend, sin color: no es una
 * alerta. La pinta la cabecera de una lista de recomendaciones, o la propia tarjeta si va suelta.
 * No pinta nada si ninguna recomendacion lleva bloque de recursos.
 */
export function ResourceClarificationNote({ items }: { items: readonly Recommendation[] }) {
  const clarification = resourceClarification(items);
  if (clarification === null) return null;
  return (
    <p className="secondary" role="note">
      {tr("Recursos a bordo · ", "Onboard resources · ")}{clarification.labels.join(" · ")}
      {clarification.caveats.map((caveat) => (
        <span key={caveat}>
          <br />
          {caveat}
        </span>
      ))}
    </p>
  );
}

/**
 * El eje RIDGE de la contramedida con su dibujo (`icons/sets/domains.ts`, `ridge-*`), sin color:
 * nombrar el eje no es avisar. La palabra es `ridge_display`, del backend; un eje que la interfaz
 * no conoce sale con su palabra y el dibujo de «desconocido».
 */
function RidgeName({ ridge, label }: { ridge: string; label: string }) {
  return <Mark pictogram={prefixedPictogram("ridge", ridge)}>RIDGE: {label}</Mark>;
}

/**
 * La familia de la contramedida (vocabulario cerrado del backend, §5.34.1) con su dibujo
 * (`library.ts`), sin color: nombrar la clase de acción no es avisar. La palabra es
 * `family_display`, del backend; sin ella (un backend anterior) no se pinta nada.
 */
export function FamilyName({ measure, inColumn = false }: { measure: Countermeasure; inColumn?: boolean }) {
  const display = measure.family_display?.trim() ?? "";
  if (display === "") return null;
  // En la columna «Familia» de la biblioteca el rótulo ya lo dice la cabecera.
  return (
    <Mark pictogram={familyPictogram(measure.family ?? "")}>
      {inColumn ? display : tr(`familia: ${display}`, `family: ${display}`)}
    </Mark>
  );
}

/** En qué se apoya la contramedida, con el dibujo del respaldo: protocolo o fuente, o demo. */
export function BasisText({ measure }: { measure: Countermeasure }) {
  return (
    <Mark pictogram={basisPictogram(measure.basis)}>
      {measure.basis === "evidence-backed"
        ? tr("protocolo o fuente propia", "own protocol or source") + (measure.protocol_ref ? `: ${measure.protocol_ref.source}` : "")
        : tr("demo: solo la respalda el riesgo del dominio", "demo: backed only by the domain's risk")}
    </Mark>
  );
}

/** Lo que se repite y cuándo, con la base de la ventana al lado: la cifra nunca va sola. */
export function FollowupText({ measure }: { measure: Countermeasure }) {
  return (
    <>
      {measure.followup_checks_display.length > 0
        ? tr(`repetir ${measure.followup_checks_display.join(" y ")}`, `repeat ${measure.followup_checks_display.join(" and ")}`)
        : tr("registro, sin medida que repetir", "log entry, no measurement to repeat")}{" "}
      {tr("en ", "in ")}<span className="num">{formatNumber(measure.followup_window_hours)}</span> h{" "}
      <span className="secondary">— {measure.followup_basis}</span>
    </>
  );
}

/**
 * La ficha de la contramedida. Cifras sin fuente no se muestran: se dice "sin fuente".
 *
 * A la vista, lo que hay que saber antes de adoptar: en que se apoya, las contraindicaciones y
 * los efectos. Plegado, lo que cuesta y como se sigue (recursos que pide, tiempo de tripulacion,
 * seguimiento). Por que se puede plegar: ninguno de los tres es una advertencia sobre adoptarla
 * —lo que falta a bordo lo dice el bloque de recursos en su resumen— y en casi toda la biblioteca
 * el tiempo es «sin fuente» y el seguimiento «diseño EMMA». El resumen no lleva la cifra de
 * tiempo: una cifra sin su procedencia al lado se leeria como medida.
 *
 * Los efectos (§5.39.17) van bajo la misma clave «Efectos a tener en cuenta» que la nota de la
 * biblioteca, con el mismo dibujo: sobre que se espera el beneficio, donde cae cada efecto adverso
 * declarado o la frase de «no declarado» del backend. Y, si este tripulante tiene otra
 * contramedida en seguimiento, la nota de co-adopcion bajo su propia clave, con los dos circulos
 * que se solapan y sin color: es informacion para decidir, no un aviso. Sin `effects` (un backend
 * anterior) la ficha es la de siempre.
 */
export function CountermeasureFacts({
  measure,
  effects = null,
  part = "all",
}: {
  measure: Countermeasure;
  effects?: CountermeasureEffects | null;
  /**
   * El mosaico del tablero (`RecommendationCard`) parte la ficha en dos: `"before-adopting"`, lo
   * que se ve junto a los mandos —las contraindicaciones y, si hay, la marca cian de efectos
   * declarados sin nada legible—; `"rest"`, lo demás, tras «Ver detalle». Por defecto, entera.
   */
  part?: "all" | "before-adopting" | "rest";
}) {
  const resources = resourcesLine(measure);
  const contraindications = contraindicationsLine(measure);
  const view = effectsView(effects);
  // Los efectos van con los mandos solo si llevan la marca de dato ausente: esa no se pliega nunca.
  const effectsBefore = view?.adverseEmpty === true;
  const shows = (row: "basis" | "contraindications" | "effects" | "coAdoption"): boolean => {
    if (part === "all") return true;
    const before = row === "contraindications" || (row === "effects" && effectsBefore);
    return part === "before-adopting" ? before : !before;
  };
  const rows = (
    <>
      {shows("basis") && (
        <>
          <FieldLabel as="dt" concept="source">
            {tr("Respaldo", "Basis")}
          </FieldLabel>
          <dd>
            <BasisText measure={measure} />{" "}
            <span className="secondary">
              · <RidgeName ridge={measure.ridge} label={measure.ridge_display} />
              {(measure.family_display?.trim() ?? "") !== "" && (
                <>
                  {" "}
                  · <FamilyName measure={measure} />
                </>
              )}
            </span>
          </dd>
        </>
      )}
      {shows("contraindications") && contraindications !== null && (
        <>
          <FieldLabel as="dt" pictogram={CONTRAINDICATIONS_PICTOGRAM}>
            {tr("Contraindicaciones", "Contraindications")}
          </FieldLabel>
          <dd>
            {contraindications.pending ? (
              <span className="secondary">{contraindications.text}</span>
            ) : (
              contraindications.text
            )}
          </dd>
        </>
      )}
      {shows("effects") && (measure.adverse_effects_note !== null || view !== null) && (
        <>
          <FieldLabel as="dt" pictogram={ADVERSE_EFFECTS_PICTOGRAM}>
            {tr("Efectos a tener en cuenta", "Effects to keep in mind")}
          </FieldLabel>
          <dd>
            {measure.adverse_effects_note}
            {view !== null && <EffectsLines effects={view} />}
          </dd>
        </>
      )}
      {shows("coAdoption") && view !== null && view.coAdopted.length > 0 && (
        <>
          <FieldLabel as="dt" pictogram={CO_ADOPTION_PICTOGRAM}>
            {tr("Con otras en seguimiento", "With others in follow-up")}
          </FieldLabel>
          <dd>
            {view.coAdopted.map((note) => (
              <div key={note.key}>{note.text}</div>
            ))}
            {view.coAdoptionBasis !== "" && <span className="secondary">{view.coAdoptionBasis}</span>}
          </dd>
        </>
      )}
    </>
  );
  if (part === "before-adopting") {
    const empty = contraindications === null && !effectsBefore;
    return empty ? null : <dl className="kv countermeasure">{rows}</dl>;
  }
  return (
    <>
      <dl className="kv countermeasure">{rows}</dl>
      <Fold data-ui="countermeasure-cost" concept="measurementCost" label={tr("Coste y seguimiento", "Cost and follow-up")}>
        <dl className="kv countermeasure">
          {resources !== null && (
            <>
              <FieldLabel as="dt" concept="resources">
                {tr("Recursos", "Resources")}
              </FieldLabel>
              <dd>{resources}</dd>
            </>
          )}
          <FieldLabel as="dt" concept="during">
            {tr("Tiempo de tripulación", "Crew time")}
          </FieldLabel>
          <dd>
            {measure.crew_time_minutes === null ? (
              <span className="secondary">{measure.crew_time_basis}</span>
            ) : (
              <>
                <span className="num">{formatNumber(measure.crew_time_minutes)}</span> min{" "}
                <span className="secondary">— {measure.crew_time_basis}</span>
              </>
            )}
          </dd>
          <FieldLabel as="dt" concept="followUp">
            {tr("Seguimiento", "Follow-up")}
          </FieldLabel>
          <dd>
            <FollowupText measure={measure} />
          </dd>
        </dl>
      </Fold>
    </>
  );
}
