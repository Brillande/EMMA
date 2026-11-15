import { useState } from "react";

import { Command } from "../components/Command";
import { Fold } from "../components/Fold";
import { MarkOf } from "../components/Mark";
import { PanelTitle } from "../components/PanelTitle";
import { formatNumber } from "../lib/format";
import { EMPTY_MARK, OK_MARK, UNAVAILABLE_MARK } from "../lib/marks";
import { State, today, useLoad, useWrite } from "./PlannerPanels";
import { type BriefingRead, briefingPreviewUrl, plannerApi } from "./plannerApi";
import { tr } from "../lib/i18n";

/**
 * La hoja diaria de Marplanner: el papel de cada mañana con el día de cada uno (eventos, comidas,
 * recordatorios, racha) y sus pasatiempos.
 *
 * Por qué así: Marplanner la compone y la pinta en un PNG en blanco y negro para una impresora
 * térmica; esa imagen se enseña tal cual, porque es el papel, no un mando de la consola. Lo que la
 * rodea sigue a EMMA. Imprimir no se ofrece aquí: Marplanner imprime desde el navegador del quiosco
 * por Bluetooth, y la consola no es ese quiosco. Un bloque que no pudo componerse (sin red no hay
 * cita del día; el tiempo de Open-Meteo no existe en EMMA) sale con el gris de «no disponible»: es
 * un dato que falta, no una alerta.
 */

/**
 * Los bloques de la hoja con su nombre en español, el de Marplanner
 * (`dailyBriefing.admin.blockType.*` de `marplanner/src/client/i18n/messages.ts`, MIT), y si vienen
 * activos cuando nadie los ha tocado (`defaultEnabled` de `src/shared/dailyBriefingBlocks.ts`).
 */
const BLOCKS: Record<string, { label: string; byDefault: boolean }> = {
  shotgun: { label: tr("Copiloto", "Copilot"), byDefault: true },
  message: { label: tr("Mensaje del día", "Message of the day"), byDefault: true },
  streak: { label: tr("Racha", "Streak"), byDefault: true },
  today: { label: tr("Agenda de hoy", "Today's schedule"), byDefault: true },
  weather: { label: tr("Tiempo", "Weather"), byDefault: true },
  meals: { label: tr("Comidas", "Meals"), byDefault: true },
  birthday: { label: tr("Cumpleaños", "Birthday"), byDefault: true },
  reminders: { label: tr("Recordatorios", "Reminders"), byDefault: true },
  dadJoke: { label: tr("Chiste", "Joke"), byDefault: true },
  wordOfDay: { label: tr("Palabra del día", "Word of the day"), byDefault: true },
  phonics: { label: tr("Fonética", "Phonics"), byDefault: false },
  animalFact: { label: tr("Curiosidad animal", "Animal fact"), byDefault: true },
  numberFact: { label: tr("Curiosidad numérica", "Number fact"), byDefault: true },
  onThisDay: { label: tr("Tal día como hoy", "On this day"), byDefault: false },
  quoteOfDay: { label: tr("Cita del día", "Quote of the day"), byDefault: true },
  trivia: { label: tr("Preguntas de cultura general", "Trivia questions"), byDefault: true },
  riddle: { label: tr("Acertijo", "Riddle"), byDefault: true },
  wouldYouRather: { label: tr("Qué prefieres", "Would you rather"), byDefault: true },
  wordSearch: { label: tr("Sopa de letras", "Word search"), byDefault: true },
  drawingPrompt: { label: tr("Idea para dibujar", "Drawing prompt"), byDefault: true },
  streakText: { label: tr("Racha (texto)", "Streak (text)"), byDefault: true },
  weatherText: { label: tr("Tiempo (texto)", "Weather (text)"), byDefault: true },
};

/** El tiempo de Marplanner es Open-Meteo, que en EMMA no existe (saca las coordenadas del hogar). */
const NOT_IN_EMMA = new Set(["weather", "weatherText"]);
/** Los que traen datos de fuera: solo con red, por la puerta de EMMA (`core/egress.py`). */
const ONLY_ONLINE = new Set(["onThisDay", "quoteOfDay"]);

export function blockLabel(type: string): string {
  return BLOCKS[type]?.label ?? type;
}

const BRIEFING_STATUS: Record<string, string> = {
  pending: "pendiente",
  ready: "lista",
  partial: "lista, con bloques sin datos",
  failed: "no se pudo componer",
  "render-failed": "compuesta, pero sin imagen",
};

export function PlannerBriefingPanel({ subject }: { subject?: string } = {}) {
  const date = today();
  const members = useLoad(() => plannerApi.members(), "members");
  const optIns = useLoad(() => plannerApi.briefingOptIns(), "briefing-opt-in");
  const [chosen, setChosen] = useState("");
  const enabled = new Map((optIns.data ?? []).map((o) => [o.memberId, o.enabled]));
  const active = (members.data ?? []).filter((m) => m.lifecycle === "active");
  // Por defecto, el tripulante que se está mirando (su miembro lleva su mismo nombre,
  // `backend/app/planner_link.py` `ensure_crew`).
  const memberId =
    chosen !== ""
      ? chosen
      : (active.find((m) => m.displayName === subject)?.id ??
        active.find((m) => enabled.get(m.id))?.id ??
        active[0]?.id ??
        "");
  const briefing = useLoad<BriefingRead>(
    () => (memberId === "" ? Promise.resolve({ generated: false }) : plannerApi.briefing(memberId, date)),
    `${memberId}|${date}`,
  );
  const reloadAll = () => {
    optIns.reload();
    briefing.reload();
  };
  const write = useWrite(reloadAll);
  const sheet = briefing.data?.generated === true ? briefing.data.briefing : undefined;
  const blocks = sheet?.payload.blocks ?? [];
  const missing = blocks.filter((b) => b.status !== "ok");

  return (
    <section data-ui="planner-briefing" className="panel" aria-label="Hoja diaria">
      <PanelTitle concept="docs">Hoja diaria</PanelTitle>
      <State loaded={members} reading="Leyendo los miembros…" />
      {write.notice}
      {active.length > 0 && (
      <div className="inline-form">
        <select value={memberId} aria-label="De quién es la hoja" onChange={(e) => setChosen(e.target.value)}>
          {active.map((m) => (
            <option key={m.id} value={m.id}>
              {m.displayName}
              {enabled.get(m.id) ? "" : " (sin hoja)"}
            </option>
          ))}
        </select>
        {memberId !== "" && (
          <Command
            pictogram={enabled.get(memberId) ? "slash-circle" : "check"}
            disabled={write.busy}
            onClick={() => void write.run(() => plannerApi.setBriefingOptIn(memberId, !enabled.get(memberId)))}
          >
            {enabled.get(memberId) ? "Dejar de recibirla" : "Recibirla cada mañana"}
          </Command>
        )}
        {memberId !== "" && enabled.get(memberId) && (
          <Command
            concept="register"
            disabled={write.busy}
            onClick={() => void write.run(() => plannerApi.generateBriefing(memberId, date))}
          >
            {sheet === undefined ? "Componer la de hoy" : "Volver a componer"}
          </Command>
        )}
      </div>
      )}
      <State loaded={briefing} reading="Leyendo la hoja…" />
      {members.data !== null && active.length === 0 && (
        // Sin miembros no hay «esta persona»: antes salía «Esta persona no recibe hoja diaria» con
        // el selector vacío (visto por el usuario en el instalador, 2026-11-12).
        <p className="secondary">
          <MarkOf mark={EMPTY_MARK}>
            Aún no hay nadie en el planificador: dé de alta a cada tripulante en «Miembros» y vuelva aquí
            para activar su hoja diaria.
          </MarkOf>
        </p>
      )}
      {briefing.data !== null && sheet === undefined && memberId !== "" && (
        <p className="secondary">
          <MarkOf mark={EMPTY_MARK}>
            {enabled.get(memberId) ? "Aún no está compuesta la de hoy." : "Esta persona no recibe hoja diaria."}
          </MarkOf>
        </p>
      )}
      {sheet !== undefined && (
        <>
          <p>
            <MarkOf mark={sheet.status === "ready" ? OK_MARK : UNAVAILABLE_MARK}>
              {BRIEFING_STATUS[sheet.status] ?? sheet.status}
            </MarkOf>{" "}
            <span className="secondary">
              · <span className="num">{formatNumber(blocks.length)}</span> bloques
              {missing.length > 0 && (
                <>
                  {" "}
                  · sin datos: {missing.map((b) => blockLabel(b.type)).join(", ")}
                </>
              )}
            </span>
          </p>
          {sheet.status !== "render-failed" && (
            <img
              className="planner-slip"
              src={briefingPreviewUrl(sheet.memberId, sheet.date, sheet.id)}
              alt={`Hoja diaria de hoy, ${formatNumber(blocks.length)} bloques`}
            />
          )}
        </>
      )}
      {memberId !== "" && enabled.get(memberId) && (
        <Fold data-ui="planner-briefing-blocks" concept="detail" label="Qué bloques lleva su hoja">
          <BlockSettings memberId={memberId} />
        </Fold>
      )}
    </section>
  );
}

function BlockSettings({ memberId }: { memberId: string }) {
  const settings = useLoad(() => plannerApi.briefingSettings(), "briefing-settings");
  const write = useWrite(settings.reload);
  const own = new Map(
    (settings.data?.memberBlockSettings ?? [])
      .filter((s) => s.memberId === memberId)
      .map((s) => [s.blockType, s.enabled]),
  );
  // En una base nueva `blockOrder` viene vacío y Marplanner compone con su orden canónico
  // (`BRIEFING_BLOCKS`, el mismo de `BLOCKS`); antes la lista salía en blanco (2026-11-12).
  const saved = (settings.data?.blockOrder ?? []).map((b) => b.type);
  const order = [...new Set(saved.length > 0 ? saved : Object.keys(BLOCKS))];
  return (
    <>
      <State loaded={settings} reading="Leyendo los bloques…" />
      {write.notice}
      <ul className="planner-list">
        {order.map((type) => {
          const on = own.get(type) ?? BLOCKS[type]?.byDefault ?? false;
          if (NOT_IN_EMMA.has(type)) {
            return (
              <li key={type}>
                <MarkOf mark={UNAVAILABLE_MARK}>{blockLabel(type)}</MarkOf>{" "}
                <span className="secondary">· no disponible en EMMA (sacaría la ubicación del hogar)</span>
              </li>
            );
          }
          return (
            <li key={type} className="planner-row">
              <span>
                <MarkOf mark={on ? OK_MARK : EMPTY_MARK}>{blockLabel(type)}</MarkOf>
                {ONLY_ONLINE.has(type) && <span className="secondary"> · solo con red</span>}
              </span>
              <Command
                pictogram={on ? "ring-dotted" : "check"}
                disabled={write.busy}
                onClick={() => void write.run(() => plannerApi.setBriefingBlock(memberId, type, !on))}
              >
                {on ? "Quitar" : "Poner"}
              </Command>
            </li>
          );
        })}
      </ul>
    </>
  );
}
