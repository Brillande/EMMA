import { useEffect, useRef } from "react";

import type { Speaker } from "../components/ReadAloud";
import { dueRule, type TimeRule } from "./announcements";
import { plannerApi } from "./plannerApi";
import { timePhrase } from "./timePhrase";

/**
 * Dice la hora en voz alta cuando lo pide una regla del planificador (Marplanner): «Son las siete».
 *
 * Por qué aquí y así: Marplanner lo hace en el navegador del quiosco con su propio motor de voz,
 * que acepta cualquier voz del navegador, también las «en línea», que sintetizan en un servidor de
 * fuera. En EMMA habla el `Speaker` de la consola (`components/ReadAloud.tsx`), que solo usa voces
 * locales; sin voz local, no dice nada. Va a la cola: un aviso de hora nunca corta el de una
 * alerta. No pinta nada; se monta una vez, fuera de las secciones, como `AlertAnnouncer`.
 */

const TIME_ZONE = Intl.DateTimeFormat().resolvedOptions().timeZone;
const RULES_EVERY_MS = 5 * 60 * 1000;
const CLOCK_EVERY_MS = 15 * 1000;

export function TimeAnnouncer({ speaker }: { speaker: Speaker }) {
  const rules = useRef<readonly TimeRule[]>([]);
  const said = useRef(new Set<string>());
  const say = useRef(speaker.say);
  say.current = speaker.say;
  const ready = speaker.availability === "ready";

  useEffect(() => {
    let alive = true;
    const load = () =>
      plannerApi
        .timeAnnouncements()
        .then((list) => {
          if (alive) rules.current = list;
        })
        .catch(() => {
          // Sin planificador (no arrancado) no hay avisos: no es un fallo de la consola.
        });
    void load();
    const every = window.setInterval(load, RULES_EVERY_MS);
    return () => {
      alive = false;
      window.clearInterval(every);
    };
  }, []);

  useEffect(() => {
    if (!ready) return;
    const tick = () => {
      const due = dueRule(rules.current, new Date(), TIME_ZONE, said.current);
      if (due === null) return;
      said.current.add(due.key);
      const [hour, minute] = due.rule.time.split(":").map(Number);
      say.current([`${timePhrase(hour!, minute!)}.`], false);
    };
    tick();
    const every = window.setInterval(tick, CLOCK_EVERY_MS);
    return () => window.clearInterval(every);
  }, [ready]);

  return null;
}
