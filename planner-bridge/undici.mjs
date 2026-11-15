// SPDX-License-Identifier: AGPL-3.0-or-later
// `undici` para Marplanner: el de verdad, salvo `fetch`, que solo llega a esta máquina (egress.mjs).
import * as real from "undici";
import { guardUndiciFetch } from "./egress.mjs";

export * from "undici";
export const fetch = guardUndiciFetch(real.fetch);
export default { ...(real.default ?? real), fetch };
