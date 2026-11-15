/**
 * Canal entre quien oye (pulsar y hablar, la palabra «EMMA», el gesto de emergencia) y el
 * asistente que contesta (`assistant/`). Un `EventTarget` y nada más, para que cada pieza se
 * monte sola y se pruebe sin las demás.
 */
export type AssistantEvent =
  | { kind: "utterance"; audio: Blob }
  | { kind: "listen" }
  | { kind: "say"; text: string };

export const assistantBus = new EventTarget();

export function emit(event: AssistantEvent): void {
  assistantBus.dispatchEvent(new CustomEvent<AssistantEvent>("assistant", { detail: event }));
}

export function listen(handler: (event: AssistantEvent) => void): () => void {
  const wrapped = (e: Event) => handler((e as CustomEvent<AssistantEvent>).detail);
  assistantBus.addEventListener("assistant", wrapped);
  return () => assistantBus.removeEventListener("assistant", wrapped);
}
