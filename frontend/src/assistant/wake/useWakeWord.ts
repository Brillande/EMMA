import { useEffect, useState } from "react";

import { emit } from "../bus";
import { OFF, type WakeState, wakeAllowed } from "./machine";

/**
 * El modo «Escuchar "EMMA"» de los mandos de pantalla, puesto en marcha: vive una vez, con el
 * estado de los modos (`useStoredDisplayModes`), aunque los mandos se pinten en dos sitios.
 *
 * El micrófono solo está abierto con el modo puesto, sin la privacidad y con la ventana a la
 * vista (`wakeAllowed`). Ocultar la ventana o decir «EMMA, deja de escuchar» **apaga el modo**,
 * no lo pausa: al volver nadie ha pedido que se reabra el micrófono. Cada frase grabada sale por
 * el canal del asistente (`assistant/bus.ts`); quien la lee no es asunto de este módulo.
 */
export function useWakeWord(
  modes: { wakeWord: boolean; privacy: boolean },
  switchOff: () => void,
): WakeState {
  const [state, setState] = useState<WakeState>(OFF);
  const [visible, setVisible] = useState(() => typeof document === "undefined" || document.visibilityState !== "hidden");
  const on = wakeAllowed({ wakeWord: modes.wakeWord, privacy: modes.privacy, visible });

  // Ventana oculta (otra pestaña, minimizada, pantalla apagada): el micrófono se cierra ya (`on`)
  // y el modo se apaga.
  useEffect(() => {
    if (typeof document === "undefined") return undefined;
    const changed = () => {
      const now = document.visibilityState !== "hidden";
      setVisible(now);
      if (!now) switchOff();
    };
    document.addEventListener("visibilitychange", changed);
    return () => document.removeEventListener("visibilitychange", changed);
  }, [switchOff]);

  useEffect(() => {
    if (!on) {
      setState(OFF);
      return undefined;
    }
    let cancelled = false;
    let stop = (): void => undefined;
    setState({ kind: "loading" });
    import("./listener").then(
      ({ watchWakeWord }) => {
        if (cancelled) return;
        stop = watchWakeWord({
          state: (next) => {
            if (cancelled) return;
            setState(next);
            // «EMMA, deja de escuchar»: la máquina se apagó sola; el modo, con ella.
            if (next.kind === "off") switchOff();
          },
          utterance: (audio) => {
            if (!cancelled) emit({ kind: "utterance", audio });
          },
        });
      },
      () => {
        if (!cancelled) setState({ kind: "unavailable", reason: "sin modelo" });
      },
    );
    return () => {
      cancelled = true;
      stop();
    };
  }, [on, switchOff]);

  return state;
}
