/**
 * Formato de numeros, tiempos y unidades segun NASA-STD-3001 Vol 2, Apendice F.
 *
 * Existe para que ninguna cifra llegue a la pantalla formateada a mano. Las reglas
 * de F.5.6 parecen triviales hasta que se incumplen: ".25" se lee "25", "03.14"
 * se confunde con una hora, y un "+" de mas hace pensar que el signo importa. Cada
 * regla tiene su prueba en `format.test.ts`.
 *
 * Dos desviaciones declaradas en `compliance/hmi-state-of-the-art.md` §2.3: en
 * espanol la coma es el separador decimal y los millares se separan con un espacio
 * fino. Con la coma de F.5.6 j, "12,345" se leeria como doce coma tres. En ingles
 * (`lib/i18n.ts`, 2026-11-15) el decimal es el punto de F.5.6; el espacio fino de los
 * millares se queda en los dos idiomas, para que una cifra no cambie de forma al
 * cambiar de idioma mas que en su decimal.
 */

import { language } from "./i18n";

const DECIMAL_ES = ",";
const DECIMAL_EN = ".";

/** El separador decimal del idioma de la interfaz. */
export function decimalMark(): string {
  return language() === "en" ? DECIMAL_EN : DECIMAL_ES;
}
// Espacio fino que no parte linea: una cifra nunca se divide entre dos renglones.
const GROUP = " ";
// F.5.6 j: el separador de millares aparece a partir de cinco digitos.
const GROUP_FROM_DIGITS = 5;

/**
 * Una cifra con los decimales que pida la tarea (F.5.6 c).
 *
 * F.5.6 f-i: cero inicial si |x| < 1, sin ceros a la izquierda, sin "+", y el
 * menos siempre. Un valor que redondea a cero no lleva signo: "-0" no es un dato.
 */
export function formatNumber(value: number, decimals = 0): string {
  if (!Number.isFinite(value)) {
    throw new RangeError(`no es una cifra representable: ${value}`);
  }
  const fixed = Math.abs(value).toFixed(decimals);
  const isZero = Number(fixed) === 0;
  const [whole = "0", fraction] = fixed.split(".");

  const grouped =
    whole.length >= GROUP_FROM_DIGITS ? whole.replace(/\B(?=(\d{3})+(?!\d))/g, GROUP) : whole;
  const sign = value < 0 && !isZero ? "-" : "";
  return sign + grouped + (fraction === undefined ? "" : decimalMark() + fraction);
}

export interface Field {
  text: string;
  /** F.4.3.1 g-h: el campo desbordado se pinta en amarillo. */
  overflow: boolean;
}

/**
 * Una cifra dentro de un campo de ancho fijo (F.4.3.1 f).
 *
 * Si no cabe, F.4.3.1 h: *"each character of the entire field must be replaced by
 * yellow asterisks, except for the signed field and the decimal point."* Mostrar
 * la cifra recortada seria peor que no mostrarla: "150" cortado a "15" es un
 * pulso normal.
 */
export function formatField(value: number, decimals: number, width: number): Field {
  const text = formatNumber(value, decimals);
  if ([...text].length <= width) {
    return { text: text.padStart(width, " "), overflow: false };
  }
  const sign = value < 0 ? "-" : "";
  const fraction = decimals > 0 ? decimalMark() + "*".repeat(decimals) : "";
  const whole = "*".repeat(Math.max(1, width - sign.length - fraction.length));
  return { text: sign + whole + fraction, overflow: true };
}

/**
 * Tiempo de mision, F.6.1: *"label dddd/hh:mm:ss (e.g., MET 57/14:08:33 [...])"*,
 * con los ceros a la izquierda suprimidos en el campo del dia. Antes del origen
 * el tiempo es negativo, como pide el mismo apartado para los temporizadores.
 */
export function formatMet(elapsedSeconds: number, label = "MET"): string {
  if (!Number.isFinite(elapsedSeconds)) {
    throw new RangeError(`tiempo no representable: ${elapsedSeconds}`);
  }
  const total = Math.floor(Math.abs(elapsedSeconds));
  const days = Math.floor(total / 86_400);
  const hours = Math.floor((total % 86_400) / 3_600);
  const minutes = Math.floor((total % 3_600) / 60);
  const seconds = total % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  const sign = elapsedSeconds < 0 && total > 0 ? "-" : "";
  return `${label} ${sign}${days}/${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
}

/** Segundos entre el origen de la mision (fecha UTC) y un instante. */
export function missionElapsedSeconds(missionStart: string, at: Date): number {
  const origin = Date.parse(`${missionStart}T00:00:00Z`);
  if (Number.isNaN(origin)) {
    throw new RangeError(`origen de mision no valido: ${missionStart}`);
  }
  return (at.getTime() - origin) / 1000;
}

/**
 * Un instante en hora UTC, con su etiqueta (F.6.1: el sistema de tiempo siempre se dice).
 *
 * Para lo que no esta en tiempo de mision: la hora de firma de un asiento es la del
 * ordenador, y con una mision simulada dista meses de la de los datos. Escrita como MET
 * pareceria un instante de la mision. Sin segundos, que aqui no aportan.
 */
export function formatUtc(at: Date): string {
  if (Number.isNaN(at.getTime())) {
    throw new RangeError("instante no representable");
  }
  return `${at.toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

/**
 * Como se lee en pantalla una unidad UCUM del catalogo.
 *
 * Solo cambia la escritura, nunca la magnitud: la unidad sigue a la propiedad
 * LOINC (invariante 2 de CLAUDE.md), y convertir aqui la romperia. F.5.6 b exige
 * mostrar la unidad de cada valor; las de recuento y puntuacion, que en UCUM son
 * anotaciones entre llaves, se nombran para que no quede un numero desnudo.
 */
const UNIT_DISPLAY: Record<string, string> = {
  "/min": "/min",
  Cel: "°C",
  "%": "%",
  "mm[Hg]": "mmHg",
  kPa: "kPa",
  "dB(A)": "dBA",
  "[ppm]": "ppm",
  "mL/(24.h)": "mL/día",
  mL: "mL",
  "1": "",
  "kcal/d": "kcal/día",
  kg: "kg",
  ms: "ms",
  h: "h",
  min: "min",
  mSv: "mSv",
  "uGy/h": "µGy/h",
  "ug/dL": "µg/dL",
  "nmol/L": "nmol/L",
  "{count}": "recuento",
  "{score}": "puntos",
  mm: "mm",
  mm2: "mm²",
  cm3: "cm³",
  "10*3/uL": "×10³/µL",
  "10*6/uL": "×10⁶/µL",
  "g/dL": "g/dL",
  "pg": "pg",
  "fL": "fL",
  "mg/dL": "mg/dL",
  "U/L": "U/L",
  "mmol/L": "mmol/L",
  "[arb'U]/mL": "U/mL",
  "ng/mL": "ng/mL",
  "mg/L": "mg/L",
  "ug/L": "µg/L",
  "u[IU]/mL": "µUI/mL",
  "ng/dL": "ng/dL",
  "pg/mL": "pg/mL",
  "m[IU]/mL": "mUI/mL",
  "[hnsf'U]": "HU",
  lx: "lx",
  "{CFU}/mL": "UFC/mL",
  "{CFU}/m3": "UFC/m³",
  "{CFU}/(100.cm2)": "UFC/100 cm²",
  "mL/min/kg{body_wt}": "mL/(kg·min)",
  kgf: "kgf",
  // La química de la orina de 24 horas: masa y sustancia por día, pH y osmolalidad.
  "mg/(24.h)": "mg/día",
  "mmol/(24.h)": "mmol/día",
  "[pH]": "pH",
  "mosm/kg": "mOsm/kg",
  "g/cm2": "g/cm²",
  // Sensoriomotor y músculo (descriptivos): segundos hasta la postura estable y newtons de la
  // tracción isométrica.
  s: "s",
  N: "N",
  // Nutrientes ingeridos al día: los de LOINC con la unidad de su ficha (24 h), los propios con
  // la forma de la energía (`kcal/d`). Se leen igual: por día.
  "g/(24.h)": "g/día",
  "mg/d": "mg/día",
  "ug/d": "µg/día",
};

/**
 * Las pocas unidades que llevan una palabra castellana, como se leen en ingles. La misma tabla
 * que `UNITS_EN` de `backend/app/core/display.py`.
 */
const UNIT_DISPLAY_EN: Record<string, string> = {
  "mL/(24.h)": "mL/day",
  "kcal/d": "kcal/day",
  "{count}": "count",
  "{score}": "points",
  "u[IU]/mL": "µIU/mL",
  "m[IU]/mL": "mIU/mL",
  "{CFU}/mL": "CFU/mL",
  "{CFU}/m3": "CFU/m³",
  "{CFU}/(100.cm2)": "CFU/100 cm²",
  "mg/(24.h)": "mg/day",
  "mmol/(24.h)": "mmol/day",
  "g/(24.h)": "g/day",
  "mg/d": "mg/day",
  "ug/d": "µg/day",
};

export function displayUnit(ucum: string): string {
  const shown = UNIT_DISPLAY[ucum];
  if (shown === undefined) {
    // Mejor fallar en la prueba que mostrar una unidad sin revisar.
    throw new RangeError(`unidad sin forma de lectura declarada: ${ucum}`);
  }
  return language() === "en" ? (UNIT_DISPLAY_EN[ucum] ?? shown) : shown;
}

/** Una duracion corta en minutos, como la del retardo de comunicaciones. */
export function formatMinutes(minutes: number): string {
  return minutes < 10 ? `${formatNumber(minutes, 1)} min` : `${formatNumber(minutes)} min`;
}

/**
 * La edad de un dato en minutos, como «hace …»: minutos enteros por debajo de una hora, horas con
 * un decimal hasta dos días y días después. Una edad negativa (el dato llegó después de la
 * referencia) es cero. Vivía en `dashboard/HomeBoard.tsx` para los vitales; la sububicación
 * estimada la usa también (2026-11-10), y una edad no se escribe de dos formas.
 */
export function formatAge(minutes: number): string {
  const age = Math.max(0, minutes);
  // El escalón se elige con la cifra ya redondeada, no con la cruda: si no, 59,7 min salía «60 min»
  // y 60 min «1,0 h», la misma edad escrita de dos formas (lógica 6).
  const wholeMinutes = Math.round(age);
  if (wholeMinutes < 60) return `${formatNumber(wholeMinutes)} min`;
  const tenthsOfHour = Math.round(age / 6);
  if (tenthsOfHour < 48 * 10) return `${formatNumber(tenthsOfHour / 10, 1)} h`;
  return `${formatNumber(age / (24 * 60), 1)} d`;
}

// Año, año y mes, o dia: la precision que de la fuente, sin completar lo que falta.
const SOURCE_DATE = /^\d{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?)?$/;

/**
 * Fecha de publicacion de una fuente citada, tal como la da el registro de evidencia del
 * backend. Se muestra en ISO 8601 (AAAA-MM-DD), que no admite la lectura dia/mes o mes/dia, y
 * con la precision que tenga: "2017" no se convierte en "2017-01-01", porque el dia no lo dice
 * nadie. Una fecha con otra forma falla en vez de mostrarse.
 */
export function formatSourceDate(iso: string): string {
  if (!SOURCE_DATE.test(iso)) {
    throw new RangeError(`fecha de fuente no valida: ${iso}`);
  }
  return iso;
}

/**
 * Un día declarado entero (AAAA-MM-DD), como el inicio o el fin de una misión previa: en ISO
 * 8601 por la misma razón que la fecha de una fuente (sin lectura día/mes o mes/día), pero con
 * el día obligatorio. Otra forma falla en vez de mostrarse.
 */
export function formatDay(iso: string): string {
  if (!/^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/.test(iso)) {
    throw new RangeError(`día no valido: ${iso}`);
  }
  return iso;
}

/**
 * La hora de un acontecimiento del planificador (Marplanner), en la zona horaria del hogar que lo
 * declara (`tzid`), a 24 horas: «07:30». El planificador vive en la hora del hogar, no en UTC ni
 * en la de la misión: una cita «a las 18:00» es a las 18:00 de quien la apuntó. Un instante o una
 * zona que no se pueden leer fallan en vez de mostrarse.
 */
export function formatHouseholdTime(iso: string, timeZone: string): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) {
    throw new RangeError(`instante no representable: ${iso}`);
  }
  // La hora a 24 h se escribe igual en los dos idiomas; el local solo sigue al de la interfaz.
  return new Intl.DateTimeFormat(language() === "en" ? "en-GB" : "es-ES", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone,
  }).format(at);
}
