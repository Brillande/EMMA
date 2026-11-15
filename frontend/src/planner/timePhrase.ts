/**
 * La frase con que se dice la hora en voz alta: «Son las cinco y cuarto».
 *
 * Origen: `marplanner/src/client/time-announcements/phrases.ts` (`buildPhraseEs`) y sus frases de
 * `marplanner/src/client/i18n/messages.ts` (MIT, © 2026 Diego Mariño). Cambios al portarlo: solo el
 * español, sin su capa de i18n (las frases van aquí, literales), y sin su motor de voz: en EMMA se
 * habla con `useSpeaker`, que solo usa voces locales (`lib/speech.ts`): una voz «en línea» enviaría
 * el texto fuera de la nave. Su tabla de casos de prueba va copiada en `timePhrase.test.ts`.
 */

const HOUR_WORDS: Record<number, string> = {
  1: "una", 2: "dos", 3: "tres", 4: "cuatro", 5: "cinco", 6: "seis",
  7: "siete", 8: "ocho", 9: "nueve", 10: "diez", 11: "once", 12: "doce",
};

const MINUTE_WORDS: Record<number, string> = {
  1: "uno", 2: "dos", 3: "tres", 4: "cuatro", 5: "cinco", 6: "seis", 7: "siete", 8: "ocho",
  9: "nueve", 10: "diez", 11: "once", 12: "doce", 13: "trece", 14: "catorce", 15: "quince",
  16: "dieciséis", 17: "diecisiete", 18: "dieciocho", 19: "diecinueve", 20: "veinte",
  21: "veintiuno", 22: "veintidós", 23: "veintitrés", 24: "veinticuatro", 25: "veinticinco",
  26: "veintiséis", 27: "veintisiete", 28: "veintiocho", 29: "veintinueve",
};

function hour12(hour: number): number {
  const h = ((hour % 12) + 12) % 12;
  return h === 0 ? 12 : h;
}

/** «Es la una…» o «Son las cinco…», según la hora. */
function lead(h12: number): string {
  return h12 === 1 ? `Es la ${HOUR_WORDS[h12]}` : `Son las ${HOUR_WORDS[h12]}`;
}

export function timePhrase(hour: number, minute: number): string {
  if (!Number.isInteger(hour) || !Number.isInteger(minute) || hour < 0 || hour > 23 || minute < 0 || minute > 59) {
    throw new RangeError(`hora no válida: ${hour}:${minute}`);
  }
  if (hour === 0 && minute === 0) return "Es medianoche";
  if (hour === 12 && minute === 0) return "Es mediodía";
  const h12 = hour12(hour);
  if (minute === 0) return lead(h12);
  if (minute === 15) return `${lead(h12)} y cuarto`;
  if (minute === 30) return `${lead(h12)} y media`;
  if (minute === 45) return `${lead(hour12(hour + 1))} menos cuarto`;
  if (minute < 30) return `${lead(h12)} y ${MINUTE_WORDS[minute]}`;
  return `${lead(hour12(hour + 1))} menos ${MINUTE_WORDS[60 - minute]}`;
}
