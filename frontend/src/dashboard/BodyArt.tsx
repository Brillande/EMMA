import { useEffect, useMemo, useRef } from "react";

import type { BodyPixels } from "./referenceBody.generated";

/** Los datos de un cuerpo generado (`referenceBodyMosaic.py`): el varón de la maqueta o su variante. */
export interface BodyArtData {
  readonly BODY_W: number;
  readonly BODY_H: number;
  readonly BODY_ONE: BodyPixels;
  readonly BODY_VECTOR_W: number;
  readonly BODY_VECTOR_H: number;
  readonly BODY_VECTOR: readonly (readonly [string, string])[];
}

/**
 * Pintor de los cuerpos de la maqueta (el varón y su variante femenina, petición del usuario, 2026-11-14).
 * El cuerpo de la maqueta del tablero de referencia (adorno, decisión del usuario, 2026-11-06): a 100 % el
 * lienzo píxel a píxel; con zoom o HiDPI el calco vectorial. Los datos van en `referenceBody.generated.ts`
 * y este módulo se carga perezoso desde el tablero: 1,5 MB que la consola no debe cargar hasta abrirlo.
 * La silueta real con los órganos en alerta se dibuja encima, en el tablero.
 */

/**
 * Los estilos del cuerpo (petición del usuario, 2026-11-15, maqueta «Salud gravitacional»: «coger el
 * modelo 2 femenino y masculino y darle diferentes estilos»). No hay figuras nuevas: el mismo render
 * (varón o mujer) se recolorea por su brillo, así la forma, los filos y el relieve son los de siempre.
 * - `thermal`: el de partida, sin tocar.
 * - `muscle`: rojos de la lámina muscular de la maqueta.
 * - `bone`: azul de rayos X, apagado para que se lean los huesos dibujados encima (`BodyBonesArt`).
 * - `vessels`: holograma azul para los vasos dibujados encima (`BodyVesselsArt`).
 * Todo es adorno (§2.5 de `compliance/hmi-state-of-the-art.md`): ningún color de estos dice un nivel.
 */
export type BodyLook = "thermal" | "muscle" | "bone" | "vessels";

type Rgb = readonly [number, number, number];

const RAMPS: Readonly<Record<Exclude<BodyLook, "thermal">, readonly (readonly [number, Rgb])[]>> = {
  // Calibrada contra la maqueta (2026-11-15): el torso medido allí da (150, 89, 83) de media.
  muscle: [
    [0, [22, 5, 5]],
    [0.3, [82, 30, 26]],
    [0.55, [121, 58, 51]],
    [0.75, [132, 73, 68]],
    [0.9, [176, 114, 100]],
    [1, [216, 164, 150]],
  ],
  bone: [
    [0, [2, 8, 24]],
    [0.45, [4, 62, 112]],
    [0.8, [8, 132, 192]],
    [1, [180, 226, 255]],
  ],
  // Calibrada contra el cristal de la maqueta entre vasos (mediana): muslo (12, 102, 171), abdomen (8, 76, 130): azul verdoso, casi sin rojo.
  vessels: [
    [0, [2, 8, 26]],
    [0.45, [6, 44, 92]],
    [0.75, [12, 84, 150]],
    [1, [160, 214, 248]],
  ],
};

/** El brillo de un color del render: media de luminancia y valor, para que el azul y el verde pesen igual. */
function brightness([r, g, b]: Rgb): number {
  const luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
  const value = Math.max(r, g, b) / 255;
  return Math.min(1, Math.max(0, 0.45 * luminance + 0.55 * value));
}

function rgbOf(hex: string): Rgb {
  return [parseInt(hex.slice(1, 3), 16), parseInt(hex.slice(3, 5), 16), parseInt(hex.slice(5, 7), 16)];
}

/** El color de un estilo para un color del render. Exportada para la prueba. */
export function lookColor(hex: string, look: BodyLook): string {
  if (look === "thermal") return hex;
  const ramp = RAMPS[look];
  const t = brightness(rgbOf(hex));
  const upper = ramp.findIndex(([stop]) => stop >= t);
  const [hiStop, hi] = ramp[Math.max(0, upper)] ?? ramp[ramp.length - 1]!;
  const [loStop, lo] = ramp[Math.max(0, upper - 1)] ?? ramp[0]!;
  const k = hiStop === loStop ? 0 : (t - loStop) / (hiStop - loStop);
  const mix = lo.map((channel, index) => Math.round(channel + (hi[index]! - channel) * k));
  return `#${mix.map((channel) => channel.toString(16).padStart(2, "0")).join("")}`;
}

/** Los datos del cuerpo con su paleta y sus capas en el estilo pedido. */
function styled(data: BodyArtData, look: BodyLook): BodyArtData {
  if (look === "thermal") return data;
  return {
    ...data,
    BODY_ONE: { ...data.BODY_ONE, palette: data.BODY_ONE.palette.map((hex) => lookColor(hex, look)) },
    BODY_VECTOR: data.BODY_VECTOR.map(([color, d]) => [lookColor(color, look), d] as const),
  };
}

/** Pinta los datos del cuerpo 1x en un lienzo fuera de pantalla, a su resolución nativa. */
function paintBody(data: BodyArtData): HTMLCanvasElement {
  const pixels = data.BODY_ONE;
  const width = data.BODY_W * pixels.scale;
  const height = data.BODY_H * pixels.scale;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) return canvas;
  const image = context.createImageData(width, height);
  const rgb = pixels.palette.map((hex): [number, number, number] => [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16),
  ]);
  pixels.rows.forEach((row, y) => {
    if (!row) return;
    const bar = row.indexOf("|");
    const runs = bar >= 0 ? row.slice(bar + 1) : row;
    let x = bar >= 0 ? Number(row.slice(0, bar)) : 0;
    for (const token of runs.split(",")) {
      const [index, length] = token.split(":");
      const count = Number(length);
      const color = index === "-" ? undefined : rgb[Number(index)];
      if (color) {
        const [r, g, b] = color;
        for (let k = 0; k < count; k += 1) {
          const offset = (y * width + x + k) * 4;
          image.data[offset] = r;
          image.data[offset + 1] = g;
          image.data[offset + 2] = b;
          image.data[offset + 3] = 255;
        }
      }
      x += count;
    }
  });
  context.putImageData(image, 0, 0);
  return canvas;
}

/** Desenfoque de caja separable sobre un campo de `w` × `h`, radio `r` (para el relieve y el borde). */
function boxBlur(src: Float32Array, w: number, h: number, r: number): Float32Array {
  const tmp = new Float32Array(src.length);
  const out = new Float32Array(src.length);
  const span = 2 * r + 1;
  for (let y = 0; y < h; y += 1) {
    let acc = 0;
    for (let x = -r; x <= r; x += 1) acc += src[y * w + Math.min(w - 1, Math.max(0, x))]!;
    for (let x = 0; x < w; x += 1) {
      tmp[y * w + x] = acc / span;
      acc += src[y * w + Math.min(w - 1, x + r + 1)]! - src[y * w + Math.max(0, x - r)]!;
    }
  }
  for (let x = 0; x < w; x += 1) {
    let acc = 0;
    for (let y = -r; y <= r; y += 1) acc += tmp[Math.min(h - 1, Math.max(0, y)) * w + x]!;
    for (let y = 0; y < h; y += 1) {
      out[y * w + x] = acc / span;
      acc += tmp[Math.min(h - 1, y + r + 1) * w + x]! - tmp[Math.max(0, y - r) * w + x]!;
    }
  }
  return out;
}

/** El color de la rampa de un estilo para un brillo `t` en 0..1. */
function rampAt(look: Exclude<BodyLook, "thermal">, t: number): Rgb {
  const ramp = RAMPS[look];
  const upper = ramp.findIndex(([stop]) => stop >= t);
  const [hiStop, hi] = ramp[Math.max(0, upper)] ?? ramp[ramp.length - 1]!;
  const [loStop, lo] = ramp[Math.max(0, upper - 1)] ?? ramp[0]!;
  const k = hiStop === loStop ? 0 : (t - loStop) / (hiStop - loStop);
  return [lo[0] + (hi[0] - lo[0]) * k, lo[1] + (hi[1] - lo[1]) * k, lo[2] + (hi[2] - lo[2]) * k];
}

/** Cómo trata cada estilo el relieve, el borde y las líneas de barrido. */
const FINISH: Readonly<Record<Exclude<BodyLook, "thermal">, { detail: number; rim: Rgb; rimGain: number; scan: number; light: number; core: number }>> = {
  muscle: { detail: 1.7, rim: [214, 238, 255], rimGain: 0.6, scan: 0, light: 2.2, core: 0 },
  bone: { detail: 0.5, rim: [150, 235, 255], rimGain: 1.4, scan: 0, light: 0.6, core: 0.6 },
  vessels: { detail: 1.8, rim: [150, 240, 255], rimGain: 1.5, scan: 0.12, light: 1.2, core: 0.35 },
};

/**
 * El cuerpo en un estilo, procesado píxel a píxel (petición del usuario, 2026-11-15: «yo le dedicaría todo
 * el cariño del mundo a los cuerpos»). Sobre el render de partida: el brillo de cada píxel con su relieve
 * realzado (el píxel menos la media de su entorno, amplificado), pasado por la rampa del estilo; una luz de
 * borde que entra desde el contorno (la máscara menos su desenfoque), como un holograma; y, en los vasos,
 * líneas de barrido tenues. Solo cambia cómo se ve el mismo cuerpo: adorno (§2.5).
 */
/** Cuántas veces la resolución de 1x se pintan los estilos (del calco vectorial): nitidez en pantallas HiDPI. */
export const STYLED_SCALE = 3;

/** El calco vectorial pintado en un lienzo de `BODY_W·k × BODY_H·k`: más detalle que el 1x para procesar. */
function paintVector(data: BodyArtData, k: number): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = data.BODY_W * k;
  canvas.height = data.BODY_H * k;
  const context = canvas.getContext("2d");
  if (!context) return canvas;
  context.scale((data.BODY_W * k) / data.BODY_VECTOR_W, (data.BODY_H * k) / data.BODY_VECTOR_H);
  for (const [color, d] of data.BODY_VECTOR) {
    context.fillStyle = color;
    context.fill(new Path2D(d), "evenodd");
  }
  return canvas;
}

function paintStyled(data: BodyArtData, look: Exclude<BodyLook, "thermal">): HTMLCanvasElement {
  const k = STYLED_SCALE;
  const canvas = paintVector(data, k);
  const context = canvas.getContext("2d");
  if (!context) return canvas;
  const { width: w, height: h } = canvas;
  const image = context.getImageData(0, 0, w, h);
  const px = image.data;
  const light = new Float32Array(w * h);
  const mask = new Float32Array(w * h);
  for (let i = 0; i < w * h; i += 1) {
    const a = px[i * 4 + 3]! / 255;
    mask[i] = a;
    light[i] = a > 0 ? brightness([px[i * 4]!, px[i * 4 + 1]!, px[i * 4 + 2]!]) : 0;
  }
  // El calor rojo del render (el corazón y los antebrazos) no es forma: en los estilos se borra, tomando el
  // brillo de su entorno, para que la piel quede pareja como en la maqueta.
  const hot = new Float32Array(w * h);
  const soft = new Float32Array(w * h);
  for (let i = 0; i < w * h; i += 1) {
    const r = px[i * 4]!;
    const g = px[i * 4 + 1]!;
    const b = px[i * 4 + 2]!;
    const reddish = r > 90 && r > b * 1.6 && g < r * 0.85;
    // Alrededor del corazón del render, también su borde amarillo (sin él queda un anillo en el pecho).
    const x = i % w;
    const y = (i - x) / w;
    const heart = ((x - w * 0.52) / (w * 0.15)) ** 2 + ((y - h * 0.27) / (h * 0.07)) ** 2;
    const nearHeart = heart < 1;
    // Fuera del borde, un fundido: sin él, la zona alisada se veía como una banda clara de borde duro en el pecho.
    soft[i] = heart >= 1 && heart < 1.7 ? (1.7 - heart) / 0.7 : 0;
    // Dentro de la zona del corazón todo se alisa: su borde oscuro tampoco es forma del cuerpo.
    const warm = nearHeart;
    hot[i] = mask[i]! > 0 && (reddish || warm) ? 1 : 0;
  }
  const coolLight = new Float32Array(w * h);
  for (let i = 0; i < w * h; i += 1) coolLight[i] = hot[i]! ? 0 : light[i]!;
  const coolMask = new Float32Array(w * h);
  for (let i = 0; i < w * h; i += 1) coolMask[i] = hot[i]! ? 0 : mask[i]!;
  // Radio mayor que la mancha más ancha (el corazón, ~22 px): con menos, su centro no tiene vecinos fríos.
  const fillL = boxBlur(coolLight, w, h, 16 * k);
  const fillM = boxBlur(coolMask, w, h, 16 * k);
  for (let i = 0; i < w * h; i += 1) {
    if (hot[i]! && fillM[i]! > 0) light[i] = fillL[i]! / fillM[i]!;
    else if (soft[i]! > 0 && mask[i]! > 0 && fillM[i]! > 0) light[i] = light[i]! * (1 - soft[i]!) + (fillL[i]! / fillM[i]!) * soft[i]!;
  }
  const near = boxBlur(light, w, h, 3 * k);
  const nearMask = boxBlur(mask, w, h, 3 * k);
  const edge = boxBlur(mask, w, h, 2 * k);
  // Lo hondo que queda cada píxel dentro del cuerpo: en el cristal de la maqueta el centro del tronco es oscuro y
  // el contorno y los miembros finos brillan (efecto Fresnel).
  const deep = boxBlur(mask, w, h, 9 * k);
  const finish = FINISH[look];
  for (let y = 0; y < h; y += 1) {
    for (let x = 0; x < w; x += 1) {
      const i = y * w + x;
      if (mask[i]! === 0) continue;
      // La media del entorno solo cuenta el cuerpo (sin el fondo transparente).
      const mean = nearMask[i]! > 0 ? near[i]! / nearMask[i]! : light[i]!;
      // Luz direccional desde arriba a la izquierda, como el render 3D de la maqueta: el brillo suavizado
      // del entorno sube hacia abajo-derecha → la cara mira a la luz y se aclara; al revés, se oscurece.
      const xl = Math.max(0, x - k);
      const xr = Math.min(w - 1, x + k);
      const yu = Math.max(0, y - k);
      const yd = Math.min(h - 1, y + k);
      const slope = near[y * w + xr]! - near[y * w + xl]! + near[yd * w + x]! - near[yu * w + x]!;
      // Estrías de fibra en el músculo: ondas finas casi verticales, como la textura de la lámina de la maqueta.
      const fiber = look === "muscle" ? Math.sin((x / k) * 2.4 + Math.sin((y / k) * 0.12) * 2.2) * 0.026 : 0;
      // En el músculo, la cara del render es oscura y no deja leer su musculatura: se aclara, con caída suave.
      const head = look === "muscle" ? Math.max(0, 1 - ((x / w - 0.487) / 0.085) ** 2 - ((y / h - 0.097) / 0.058) ** 2) : 0;
      const t = Math.min(1, Math.max(0, light[i]! + (light[i]! - mean) * finish.detail + slope * finish.light + head * 0.22 + fiber));
      let [r, g, b] = rampAt(look, t);
      const rim = Math.max(0, 1 - edge[i]!) * 2 * finish.rimGain;
      r += (finish.rim[0] - r) * Math.min(1, rim);
      g += (finish.rim[1] - g) * Math.min(1, rim);
      b += (finish.rim[2] - b) * Math.min(1, rim);
      const core = 1 - finish.core * Math.min(1, Math.max(0, (deep[i]! - 0.6) / 0.4));
      r *= core;
      g *= core;
      b *= core;
      const scan = finish.scan > 0 && Math.floor(y / k) % 3 === 0 ? 1 - finish.scan : 1;
      px[i * 4] = Math.round(r * scan);
      px[i * 4 + 1] = Math.round(g * scan);
      px[i * 4 + 2] = Math.round(b * scan);
    }
  }
  context.putImageData(image, 0, 0);
  return canvas;
}

/** El cuerpo a 100 %: el 1x tal cual, píxel exacto. El CSS lo oculta en cuanto hay zoom o HiDPI. */
function BodyCanvas({ data, look = "thermal" }: { data: BodyArtData; look?: BodyLook }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const context = ref.current?.getContext("2d");
    if (!context) return;
    context.clearRect(0, 0, context.canvas.width, context.canvas.height);
    context.drawImage(look === "thermal" ? paintBody(data) : paintStyled(data, look), 0, 0);
  }, [data, look]);
  const k = look === "thermal" ? 1 : STYLED_SCALE;
  return <canvas ref={ref} className="ref-body-canvas" width={data.BODY_W * k} height={data.BODY_H * k} aria-hidden="true" />;
}

/** El cuerpo con zoom o en HiDPI: capas de color apiladas, vectoriales, nítidas a cualquier escala. */
function BodyVector({ data }: { data: BodyArtData }) {
  return (
    <svg className="ref-body-vector" viewBox={`0 0 ${data.BODY_VECTOR_W} ${data.BODY_VECTOR_H}`} aria-hidden="true" focusable="false">
      {data.BODY_VECTOR.map(([color, d], index) => (
        <path key={index} fill={color} fillRule="evenodd" d={d} />
      ))}
    </svg>
  );
}

/**
 * El cuerpo de la maqueta, DETRÁS de la silueta real: lienzo píxel a píxel a 100 % y calco vectorial con
 * zoom (el CSS elige por resolución). Todo es adorno. La silueta de encima solo enseña los órganos con alerta.
 */
export function BodyArt({ data, look = "thermal" }: { data: BodyArtData; look?: BodyLook }) {
  const shown = useMemo(() => styled(data, look), [data, look]);
  return (
    <>
      <BodyCanvas data={data} look={look} />
      <BodyVector data={shown} />
    </>
  );
}

