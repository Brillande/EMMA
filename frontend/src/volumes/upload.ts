import { ApiError, type VolumeCleaning } from "../lib/api";

/**
 * Que ha pasado con un volumen subido: guardado, o rechazado por la puerta de datos personales.
 *
 * Por que existe aparte del panel: el rechazo de `POST /api/volumes` (422) ya no es solo un
 * motivo. Dice ademas si limpiar la cabecera en EMMA lo dejaria entrar, y trae escritos por el
 * backend el texto de la oferta y el rotulo del boton. La regla de cuando se ensena ese boton
 * merece su prueba, porque un boton de mas aqui acaba en un volumen guardado distinto del que el
 * operador subio:
 *   - solo se ofrece si el backend dice `cleanable: true` Y da los dos textos. La interfaz no
 *     redacta la oferta: sin texto del backend no hay boton;
 *   - cualquier otro fallo (503: no se pudo comprobar; 413; un 422 de un fichero ilegible) no es
 *     una oferta: se lanza como `ApiError` y el panel lo ensena como cualquier error.
 */
export type UploadOutcome =
  | { kind: "saved"; ledger_index: number; cleaned: VolumeCleaning | null }
  | { kind: "refused"; detail: string; offer: { text: string; label: string } | null };

export function uploadOutcome(reply: { status: number; body: unknown }): UploadOutcome {
  const body = (typeof reply.body === "object" && reply.body !== null ? reply.body : {}) as Record<string, unknown>;
  if (reply.status >= 200 && reply.status < 300) {
    if (typeof body.ledger_index !== "number") throw new ApiError(reply.status, "respuesta sin asiento");
    return { kind: "saved", ledger_index: body.ledger_index, cleaned: cleaningOf(body) };
  }
  const detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? null);
  // Un 422 sin `cleanable` es otro rechazo (no es un NIfTI, no es 3D): no pasa por la puerta.
  if (reply.status !== 422 || typeof body.cleanable !== "boolean") {
    throw new ApiError(reply.status, detail, body.integrity_ok === false);
  }
  const { clean_offer: text, clean_label: label } = body;
  const offered = body.cleanable && typeof text === "string" && text !== "" && typeof label === "string" && label !== "";
  return { kind: "refused", detail, offer: offered ? { text, label } : null };
}

/** La declaracion de limpieza de un estudio o de una respuesta, si la trae entera. */
export function cleaningOf(holder: object | null | undefined): VolumeCleaning | null {
  const cleaned = (holder as { cleaned?: Partial<VolumeCleaning> | null } | null | undefined)?.cleaned;
  if (cleaned === null || cleaned === undefined) return null;
  const { fields, received_sha256, received_size_bytes, note } = cleaned;
  if (!Array.isArray(fields) || typeof received_sha256 !== "string" || typeof note !== "string") return null;
  return { fields: fields.map(String), received_sha256, received_size_bytes: Number(received_size_bytes), note };
}
