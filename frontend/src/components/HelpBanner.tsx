import { useCallback, useEffect, useRef, useState } from "react";

import { Pictogram } from "../icons";
import { type HelpRequests, type LinkSync, helpRequestsApi } from "../lib/api";
import { formatMinutes, formatUtc } from "../lib/format";
import { tr } from "../lib/i18n";
import {
  HELP_REFRESH_MS,
  HELP_REQUESTED_EVENT,
  type HelpRequestedDetail,
  LOCATING,
  freshRequests,
  groundArrival,
  groundHelpCut,
  spokenRequest,
  withProvisional,
} from "../lib/help";
import { type RequestOutcome, requestOutcome } from "../lib/marks";
import { useOperator } from "../lib/operator";
import { uiPictogram } from "../lib/uiMarks";
import { Command } from "./Command";
import { MarkOf } from "./Mark";
import type { Speaker } from "./ReadAloud";
import "./helpBanner.css";

/**
 * La banda de ayuda urgente, encima de cualquier sección de las dos consolas (decisión del usuario,
 * 2026-11-14: «tiene que alertar a quien tengas más cerca y, obviamente, a Tierra»).
 *
 * - **A bordo** se ve en cuanto se firma, con quién la pide, dónde está y el resto de la tripulación
 *   de más a menos cerca; dice cuándo le llega a Tierra (la firma más un tiempo de luz) y deja darla
 *   por atendida con un nombre.
 * - **En Tierra** se pide con su corte de reloj (`groundHelpCut`): lo firmado a bordo después no ha
 *   llegado. Tierra no la cierra: la atiende quien está allí.
 *
 * Se lee en voz alta al aparecer una nueva y es una región `alert`: el lector de pantalla la dice
 * sin que nadie la busque. Todo texto de la petición es del backend; aquí solo van los rótulos.
 * Rojo de la paleta (`--c-red`): en la tabla F.5-1 es lo que pide atención inmediata.
 */
/** El titular antes de la primera lectura; después, el del backend. */
const HELP_HEADLINE = tr("Ayuda urgente", "Urgent help");

export function HelpBanner({
  console: side,
  oneWayMinutes,
  sync,
  speaker,
}: {
  console: "crew" | "ground";
  oneWayMinutes: number | null;
  sync: LinkSync | null;
  speaker: Speaker;
}) {
  const [data, setData] = useState<HelpRequests | null>(null);
  const [failure, setFailure] = useState<RequestOutcome | null>(null);
  const seen = useRef<Set<number> | null>(null);
  const latest = useRef({ oneWayMinutes, sync, speaker });
  latest.current = { oneWayMinutes, sync, speaker };

  const load = useCallback(async () => {
    const { oneWayMinutes: oneWay, sync: link, speaker: voice } = latest.current;
    const until = side === "ground" ? groundHelpCut(oneWay, link, Date.now()) : undefined;
    try {
      const next = await helpRequestsApi.list(until);
      // La primera lectura no se dice: lo abierto al montar la consola ya está a la vista.
      if (seen.current !== null) {
        const fresh = freshRequests(seen.current, next.open);
        if (fresh.length > 0) voice.say(fresh.map((item) => spokenRequest(next.headline, item)), false);
      }
      seen.current = new Set(next.open.map((item) => item.ledger_index));
      setData(next);
      setFailure(null);
    } catch (error) {
      setFailure(requestOutcome(error));
    }
  }, [side]);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), HELP_REFRESH_MS);
    // La consola que pide la enseña y la dice ya, con lo que el backend confirmó al firmar; la
    // ubicación y la cercanía llegan con la lectura que se pide a continuación.
    const now = (event: Event) => {
      const detail = (event as CustomEvent<HelpRequestedDetail | undefined>).detail;
      if (detail !== undefined) {
        setData((previous) => {
          const headline = previous?.headline ?? HELP_HEADLINE;
          const next = withProvisional(previous, detail, headline);
          if (!(seen.current?.has(detail.ledger_index) ?? false)) {
            latest.current.speaker.say([spokenRequest(headline, next.open[0]!)], false);
            seen.current = new Set([...(seen.current ?? []), detail.ledger_index]);
          }
          return next;
        });
      }
      void load();
    };
    window.addEventListener(HELP_REQUESTED_EVENT, now);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener(HELP_REQUESTED_EVENT, now);
    };
  }, [load]);

  if (data === null || data.open.length === 0) {
    // Sin poder leer la lista no se calla: sin ella, nadie sabría que alguien pide ayuda.
    return failure === null ? null : (
      <p className="help-failure" role="status">
        <MarkOf mark={failure.mark}>
          {tr("No se pudo leer si alguien pide ayuda:", "Could not read whether anyone is asking for help:")} {failure.text}
        </MarkOf>
      </p>
    );
  }
  return (
    <section className="help-banner" role="alert" aria-label={data.headline}>
      {data.open.map((item) => (
        <HelpItem key={item.ledger_index} side={side} headline={data.headline} item={item} oneWayMinutes={oneWayMinutes} onClosed={load} />
      ))}
      {data.basis !== "" && <p className="help-basis">{data.basis}</p>}
    </section>
  );
}

function HelpItem({
  side,
  headline,
  item,
  oneWayMinutes,
  onClosed,
}: {
  side: "crew" | "ground";
  headline: string;
  item: HelpRequests["open"][number];
  oneWayMinutes: number | null;
  onClosed: () => Promise<void>;
}) {
  const [operator, setOperator] = useOperator();
  const [name, setName] = useState(operator);
  const [closing, setClosing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const arrival = groundArrival(item.signed_at, oneWayMinutes);

  const close = async () => {
    const who = name.trim();
    if (who === "") {
      setError(tr("Escriba quién la atiende.", "Enter who is attending."));
      return;
    }
    setClosing(true);
    setError(null);
    try {
      await helpRequestsApi.close(item.ledger_index, who);
      setOperator(who);
      await onClosed();
    } catch (failure) {
      setError(requestOutcome(failure).text);
    } finally {
      setClosing(false);
    }
  };

  return (
    <article className="help-item">
      <span className="help-alarm" aria-hidden="true">
        <Pictogram name={uiPictogram("alerts")} />
      </span>
      <div className="help-body">
        <p className="help-head">
          <strong>
            {headline}: {item.subject}
          </strong>{" "}
          {item.signed_by !== null && (
            <span>
              · {tr("pedida por", "requested by")} {item.signed_by}
            </span>
          )}
          {item.reason !== null && <q className="help-reason">{item.reason}</q>}
        </p>
        <p>
          <span className="help-label">{tr("Dónde:", "Where:")}</span> {item.location_display}
        </p>
        <p>
          <span className="help-label">{tr("Más cerca:", "Nearest:")}</span>{" "}
          {item.nearby.length === 0
            ? (item.nearby_note ?? LOCATING)
            : item.nearby.map((other, index) => (
                <span key={other.subject}>
                  {index > 0 && " · "}
                  <strong>{other.subject}</strong> ({other.proximity_display}, {other.location_display})
                </span>
              ))}
        </p>
        <p className="help-when">
          {side === "crew" ? (
            arrival === null ? (
              tr(
                `Firmada a las ${formatUtc(new Date(item.signed_at))}. Sin efemérides: no se sabe cuándo le llega a Tierra.`,
                `Signed at ${formatUtc(new Date(item.signed_at))}. No ephemeris: it is not known when it reaches Earth.`,
              )
            ) : (
              tr(
                `Firmada a las ${formatUtc(new Date(item.signed_at))}. Tierra la recibe hacia las ${formatUtc(arrival)} (${formatMinutes(oneWayMinutes ?? 0)} de luz).`,
                `Signed at ${formatUtc(new Date(item.signed_at))}. Earth receives it at about ${formatUtc(arrival)} (${formatMinutes(oneWayMinutes ?? 0)} light time).`,
              )
            )
          ) : (
            tr(
              `Firmada a bordo a las ${formatUtc(new Date(item.signed_at))}; llega con el retardo de la luz.`,
              `Signed on board at ${formatUtc(new Date(item.signed_at))}; it arrives with the light delay.`,
            )
          )}
        </p>
      </div>
      {side === "crew" && (
        <div className="help-close">
          <label>
            <span className="help-label">{tr("Quién la atiende", "Who is attending")}</span>
            <input value={name} onChange={(event) => setName(event.target.value)} maxLength={64} autoComplete="off" />
          </label>
          <Command concept="resolved" type="button" disabled={closing} onClick={() => void close()}>
            {tr("Atendida", "Attended")}
          </Command>
          {error !== null && (
            <span className="help-error" role="status">
              {error}
            </span>
          )}
        </div>
      )}
    </article>
  );
}
