import { useSyncExternalStore } from "react";

/**
 * Qué cuerpo dibuja la consola: el varón de la maqueta o su variante femenina.
 *
 * Por qué existe (petición del usuario, 2026-11-14): «respetar el estilo gráfico de los cuerpos 3D y 2D y
 * colores, pero también un avatar femenino». Es una preferencia de presentación de este equipo, como los
 * modos de pantalla: el cuerpo es adorno (§2.5 de `compliance/hmi-state-of-the-art.md`), no dice nada del
 * tripulante y no es su sexo —el perfil no tiene ese campo, a propósito (§5.36.19)—. No pasa por el
 * registro firmado ni por el backend; se guarda en `localStorage` y, sin almacén, queda el de partida.
 *
 * Un solo almacén para todos los cuerpos de la consola (Inicio, Cuerpo, Radiación y el 3D de Dolor): al
 * cambiarlo en uno cambian todos, también en otra pestaña del mismo equipo.
 */

export type Avatar = "male" | "female";

export const AVATARS: readonly Avatar[] = ["male", "female"];

/** Rótulo de cada avatar en la interfaz. */
export const AVATAR_LABEL: Readonly<Record<Avatar, string>> = { male: "Masculino", female: "Femenino" };

export const AVATAR_KEY = "emma.avatar";

/** Lo guardado, tolerante: cualquier otra cosa (o ningún almacén) es el de partida, el de la maqueta. */
export function parseAvatar(raw: string | null | undefined): Avatar {
  return raw === "female" ? "female" : "male";
}

function read(): Avatar {
  try {
    return parseAvatar(localStorage.getItem(AVATAR_KEY));
  } catch {
    return "male";
  }
}

const listeners = new Set<() => void>();
let current: Avatar | undefined;

function snapshot(): Avatar {
  current ??= read();
  return current;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  const fromOtherTab = (event: StorageEvent) => {
    if (event.key !== AVATAR_KEY) return;
    current = parseAvatar(event.newValue);
    listener();
  };
  window.addEventListener("storage", fromOtherTab);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", fromOtherTab);
  };
}

export function setAvatar(next: Avatar): void {
  current = next;
  try {
    localStorage.setItem(AVATAR_KEY, next);
  } catch {
    // sin almacén: vale para esta sesión
  }
  listeners.forEach((listener) => listener());
}

/** El avatar elegido; se vuelve a pintar quien lo use cuando cambia. */
export function useAvatar(): Avatar {
  return useSyncExternalStore(subscribe, snapshot, () => "male");
}
