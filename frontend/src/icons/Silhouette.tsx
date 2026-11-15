/**
 * Silueta corporal de frente, con una zona por región del modo anatómico.
 *
 * Por qué vive en `icons/` y no en `anatomy/`: la regla del rediseño pictográfico es que ningún
 * fichero fuera de `icons/` escribe `<svg` ni un trazo (`pictograms.test.ts`), para que todo
 * dibujo de la interfaz esté en un sitio, sea geometría sin color propio y lo vigile la misma
 * prueba. La silueta es un dibujo, así que está aquí; pero no es un pictograma de 24×24 que
 * acompañe a una palabra, sino una figura con su propio lienzo (200×480) sobre la que el modo
 * anatómico coloca sus regiones. Por eso no entra en el registro ni en `PictogramName`, y
 * `pictograms.test.ts` la declara como excepción con este motivo.
 *
 * Qué es y qué no es: un esquema de dónde está cada región (`backend/app/anatomy.py:REGIONS`),
 * para que el nivel de cada dominio se vea sobre su sitio del cuerpo. No es una imagen del
 * tripulante ni un diagnóstico; la imagen de referencia del esqueleto (`SkeletonFigure`) y el
 * visor 3D siguen siendo otra cosa. Las dos regiones sin órgano propio —`immune` y
 * `whole-body`— no tienen zona aquí: quien monta la figura las coloca al pie.
 *
 * De dónde sale el contorno (segunda pasada, 2026-10-21, §5.33.3): el primero era un trazo a mano
 * con rectas, una cabeza elíptica suelta y dos rayas de cuello, y se leía como un muñeco de
 * jengibre. Este se recalcó sobre «Human silhouette gender neutral front.svg» (Wikimedia Commons,
 * Sebastian Wallroth, 2026-07-08, CC0 1.0; a su vez basada en «Wallace Rule of Nines.svg», CC0)
 * como plantilla de proporción: escalada a este lienzo con la escala uniforme
 * `min(200/147.998, 480/318.455)`, centrada, pies en y = 470; su mitad izquierda, ajustada con
 * diecinueve cúbicas (los dedos se cierran en una manopla, que es lo que se lee a 500 px), y la
 * derecha, su espejo. El SVG fuente no entra en el repositorio: lo que hay aquí son números
 * propios, en un solo trazo cerrado con la cabeza y el cuello incluidos.
 *
 * Los órganos se redibujaron con los rasgos que los hacen reconocibles, con el vocabulario de
 * Health Icons (CC0) como referencia de qué rasgo pinta cada uno y sin copiar ningún trazo: el
 * cerebro con su cisura y una circunvolución por hemisferio, los ojos almendrados con el iris,
 * el corazón con sus dos arcos, la columna con tres cuerpos vertebrales, el asa intestinal dentro
 * del marco del colon, la vejiga con su salida, un hueso largo con sus cóndilos, la cuña del
 * hígado con su cisura (decimoquinta ronda) y los pulmones con la tráquea y la escotadura del
 * corazón (decimosexta ronda). Solo las
 * primitivas de los pictogramas (`icons/types.ts`): trayecto, círculo, rectángulo y línea.
 *
 * Color: todo en `currentColor`. El contorno hereda el del texto; cada zona lleva la clase
 * `c-<token>` que le dé quien la monta (el color del nivel, de la paleta), y la zona elegida se
 * marca con `data-selected` para que el CSS la engrose. El relleno tenue de cada zona lo pone el
 * CSS; los trazos abiertos (la cisura, las circunvoluciones, el intestino) llevan la clase
 * `trace` para quedarse sin relleno, y los rasgos pequeños (ojos, iris, cisura y circunvoluciones)
 * la clase `fine` para un trazo más fino, que a 500 px no los empaste. Este fichero no importa la
 * paleta: el color no es suyo.
 *
 * Cada zona declara en la misma tabla su dibujo y su ancla (altura en el lienzo y lado por el
 * que se rotula), para que quien coloque un rótulo junto a ella lo haga desde aquí y no copie
 * la geometría a mano.
 */

import type { ReactNode } from "react";

/** Lienzo de la figura: 200 de ancho por 480 de alto, cabeza arriba, vista anterior. */
export const SILHOUETTE_VIEWBOX = "0 0 200 480";
const WIDTH = 200;
const HEIGHT = 480;

export interface SiteAnchor {
  /** Altura del centro de la zona, como fracción del alto del lienzo (0 arriba, 1 abajo). */
  readonly y: number;
  /** Por qué lado del dibujo se rotula la zona. */
  readonly side: "left" | "right";
  /**
   * Hasta dónde llega la figura, desde el eje y en unidades del lienzo, en la franja de altura que
   * ocupa el rótulo (±24 unidades alrededor de `y`): el rótulo empieza pasado ese punto. Con la
   * silueta recalcada las manos llegan casi al borde del lienzo, y un desplazamiento único que las
   * salvara dejaba sin sitio a los rótulos de la cabeza y del tronco. Se mide sobre el contorno
   * (`reachAt`), no se escribe a mano: un retoque del dibujo mueve los rótulos con él.
   */
  readonly reach: number;
}

interface Site extends Omit<SiteAnchor, "reach"> {
  readonly shape: ReactNode;
}

/**
 * Las zonas: el órgano o la estructura, esquemáticos, en su sitio. El corazón y el hueso de
 * carga van a la izquierda del sujeto, que en la vista anterior es la derecha del dibujo; su
 * rótulo va por ese lado. Las claves son las de `anatomy.py`, en su orden.
 */
const SITES = {
  // Dos hemisferios con la cisura entre ellos y una circunvolución en cada uno.
  brain: {
    y: 55 / HEIGHT,
    side: "right",
    shape: (
      <>
        <path d="M100 47C94 45.5 87 48.5 87 55C87 60.5 93 64 100 63C107 64 113 60.5 113 55C113 48.5 106 45.5 100 47Z" />
        <line className="fine" x1={100} y1={47} x2={100} y2={63} />
        <path className="trace fine" d="M92.5 50C95.5 52 95.5 57.5 92.5 59.5" />
        <path className="trace fine" d="M107.5 50C104.5 52 104.5 57.5 107.5 59.5" />
      </>
    ),
  },
  // Dos almendras con su iris.
  eyes: {
    y: 72 / HEIGHT,
    side: "left",
    shape: (
      <>
        <path className="fine" d="M87.5 72C90.5 68.5 95.5 68.5 98.5 72C95.5 75.5 90.5 75.5 87.5 72Z" />
        <circle className="fine" cx={93} cy={72} r={1.6} />
        <path className="fine" d="M101.5 72C104.5 68.5 109.5 68.5 112.5 72C109.5 75.5 104.5 75.5 101.5 72Z" />
        <circle className="fine" cx={107} cy={72} r={1.6} />
      </>
    ),
  },
  // Los dos arcos de las aurículas y la punta abajo.
  heart: {
    y: 148 / HEIGHT,
    side: "right",
    shape: <path d="M109 156L100.5 147.5A5 5 0 0 1 109 141A5 5 0 0 1 117.5 147.5Z" />,
  },
  // Los pulmones (decimosexta ronda, §5.36.13): la tráquea con sus dos bronquios y un lóbulo a cada
  // lado, redondeado arriba y plano abajo, sobre el diafragma. El izquierdo del sujeto (la derecha
  // del dibujo) deja la escotadura del corazón, que queda delante y sin tocarlo; el derecho acaba
  // encima del hígado. Es una región sin nivel propio, como el hígado: quien la monta no le da
  // color de nivel. Se rotula por la derecha, aunque ese lado pase a cinco rótulos y la izquierda
  // se quede en cuatro: por la izquierda, con el hígado (tres líneas) y la espalda a esa altura,
  // los rótulos ya no caben junto a la figura ni a tamaño normal (`placeSites`); por la derecha
  // caben hasta el 125 % del texto.
  lungs: {
    y: 134 / HEIGHT,
    side: "right",
    shape: (
      <>
        <path className="trace fine" d="M100 104L100 116M100 116L95 120M100 116L105 120" />
        <path d="M90 117C82 117 76 128 74 140C73 147 73 152 74 156C80 154.5 89 154 96 155L96 123C96 119 93 117 90 117Z" />
        <path d="M110 117C118 117 124 128 126 140C127 147 127 152 126 156C124.5 155.5 123 155.2 121.5 155L121.5 141C121.5 137 115 134 104 134L104 123C104 119 107 117 110 117Z" />
      </>
    ),
  },
  // Un hueso largo de carga, el fémur: la diáfisis y dos cóndilos en cada extremo.
  bones: {
    y: 328 / HEIGHT,
    side: "right",
    shape: (
      <path d="M126 290A3.8 3.8 0 1 1 128 285A3.8 3.8 0 1 1 130 290L130 366A3.8 3.8 0 1 1 128 371A3.8 3.8 0 1 1 126 366Z" />
    ),
  },
  // Tres cuerpos vertebrales en el eje del tronco, como el pictograma del dominio.
  muscles: {
    y: 178 / HEIGHT,
    side: "left",
    shape: (
      <>
        <rect x={95.5} y={167} width={9} height={6.5} />
        <rect x={95.5} y={175} width={9} height={6.5} />
        <rect x={95.5} y={183} width={9} height={6.5} />
      </>
    ),
  },
  // La vejiga y su salida.
  bladder: {
    y: 247 / HEIGHT,
    side: "left",
    shape: (
      <>
        <path d="M91 243C91 237 109 237 109 243C109 250 104 254 100 254C96 254 91 250 91 243Z" />
        <line x1={100} y1={254} x2={100} y2={259} />
      </>
    ),
  },
  // El marco del colon y, dentro, el asa del intestino delgado.
  digestive: {
    y: 212 / HEIGHT,
    side: "right",
    shape: (
      <>
        <path className="trace" d="M84 228L84 202C84 199 86 197 89 197L111 197C114 197 116 199 116 202L116 228" />
        <path
          className="trace"
          d="M90 203L108 203C111.5 203 111.5 210 108 210L92 210C88.5 210 88.5 217 92 217L108 217C111.5 217 111.5 224 108 224L96 224"
        />
      </>
    ),
  },
  // El hígado (decimoquinta ronda, §5.35.11): la cuña del lóbulo derecho, gruesa por fuera y
  // afilada hacia el eje, bajo el diafragma y a la derecha del sujeto (la izquierda del dibujo),
  // con la cisura entre sus lóbulos. Queda a la izquierda de la columna y encima del colon. Es una
  // región sin nivel propio: quien la monta no le da color de nivel.
  liver: {
    y: 174 / HEIGHT,
    side: "left",
    shape: (
      <>
        <path d="M71 171C71 163 78.5 158.5 87 159C90.5 159.2 93 160.5 93 162.5C93 167 88.5 171 83 175C78.5 178.5 75 184 73 189C71.5 184 71 178 71 171Z" />
        <path className="trace fine" d="M85 159.5C84 164 82 168 79 171.5" />
      </>
    ),
  },
} as const satisfies Record<string, Site>;

export type SitedRegion = keyof typeof SITES;

/**
 * Regiones del backend con un sitio en la figura, en el orden del backend. La prueba de la
 * silueta comprueba que, junto con las que van al pie, son exactamente las de `anatomy.py`.
 */
export const SITED_REGIONS = Object.keys(SITES) as readonly SitedRegion[];

export function isSitedRegion(key: string): key is SitedRegion {
  return Object.hasOwn(SITES, key);
}

/** Dónde cae la zona de una región: para colocar su rótulo a la misma altura y por su lado. */
export function siteAnchor(region: SitedRegion): SiteAnchor {
  const { y, side } = SITES[region];
  return { y, side, reach: reachAt(y * HEIGHT) };
}

/** Alto del lienzo, en sus unidades: para pasar a ellas un alto medido en píxeles. */
export const SILHOUETTE_HEIGHT = HEIGHT;

/** Una cúbica: primer control, segundo control y punto final (x, y de cada uno). */
type Cubic = readonly [number, number, number, number, number, number];

/** La coronilla, sobre el eje: de aquí sale la mitad izquierda y aquí vuelve la derecha. */
const CROWN = [100, 41] as const;

/**
 * La mitad izquierda del dibujo (la derecha del sujeto), de la coronilla a la entrepierna: cabeza,
 * mandíbula, cuello, hombro, brazo por fuera, mano, brazo por dentro, axila, costado, cadera,
 * pierna por fuera, pie y pierna por dentro. Termina sobre el eje (x = 100), como empieza.
 */
const LEFT_HALF: readonly Cubic[] = [
  [92.5, 41, 86.2, 45, 82.9, 51.8],
  [69.6, 79.7, 91.6, 79.2, 84.8, 93.7],
  [77, 110.3, 56.8, 99.4, 46.4, 118.6],
  [36.1, 137.8, 36.2, 156.8, 31.2, 176.9],
  [28.9, 186.5, 25.4, 190.5, 23.7, 202.1],
  [22.6, 209.5, 21.5, 231.4, 19.1, 236.8],
  [15.8, 244.4, 4.4, 252.2, 0.7, 262.2],
  [2.9, 267.1, 12, 282.4, 18.5, 281.4],
  [38.5, 278.4, 30.8, 249.9, 33, 236.3],
  [34.2, 228.6, 54.2, 167.8, 59.3, 157.7],
  [71.6, 203.3, 49.9, 233.5, 51.1, 278.5],
  [51.6, 296.4, 56.7, 315.2, 56.6, 332.4],
  [56.4, 349.6, 52.6, 365.8, 54.9, 383.7],
  [56.9, 399.5, 64.3, 413.8, 65.9, 429.4],
  [67, 440.1, 57.2, 466.3, 57.4, 466.7],
  [59.4, 470.7, 78.4, 471.4, 80.8, 464.9],
  [81.9, 462.1, 79.5, 454.4, 79.9, 450.7],
  [82.7, 420.5, 82.8, 388.2, 85.4, 357.3],
  [88.1, 325.4, 97.2, 296.1, 100, 264.7],
];

/** Media altura de la franja que ocupa un rótulo, en unidades del lienzo (≈ 25 px a 500 px). */
const LABEL_BAND = 24;

/**
 * Hasta dónde llega el contorno desde el eje en la franja `centre ± LABEL_BAND`, redondeado hacia
 * arriba: cada cúbica de la mitad izquierda muestreada en cuarenta pasos.
 */
function reachAt(centre: number): number {
  return reachBetween(centre - LABEL_BAND, centre + LABEL_BAND);
}

/**
 * Hasta dónde llega el contorno desde el eje entre dos alturas del lienzo (`top` ≤ `bottom`),
 * redondeado hacia arriba. Es la medida de `reach` para la franja que ocupa de verdad un rótulo
 * cuando se coloca por su alto medido (`anatomy/siteLayout.ts`), y no por la franja supuesta.
 */
export function reachBetween(top: number, bottom: number): number {
  let widest = 0;
  let [px, py]: readonly [number, number] = CROWN;
  for (const [x1, y1, x2, y2, x, y] of LEFT_HALF) {
    for (let step = 0; step <= 40; step += 1) {
      const t = step / 40;
      const a = (1 - t) ** 3;
      const b = 3 * (1 - t) ** 2 * t;
      const c = 3 * (1 - t) * t ** 2;
      const d = t ** 3;
      const sy = a * py + b * y1 + c * y2 + d * y;
      if (sy < top || sy > bottom) continue;
      const sx = a * px + b * x1 + c * x2 + d * x;
      widest = Math.max(widest, WIDTH / 2 - sx);
    }
    [px, py] = [x, y];
  }
  return Math.ceil(widest);
}

/** Una cifra con una decimal como mucho, sin el «.0» ni el ruido de la resta en coma flotante. */
const num = (value: number): string => String(Math.round(value * 10) / 10);

/**
 * Contorno del cuerpo en un solo trayecto cerrado: la mitad izquierda tal cual, y la derecha, su
 * espejo (x → 200 − x) recorrido al revés, de la entrepierna a la coronilla. Cada cúbica
 * invertida cambia el orden de sus dos controles.
 */
function outline(): string {
  const parts = [`M${num(CROWN[0])} ${num(CROWN[1])}`];
  for (const [x1, y1, x2, y2, x, y] of LEFT_HALF) {
    parts.push(`C${num(x1)} ${num(y1)} ${num(x2)} ${num(y2)} ${num(x)} ${num(y)}`);
  }
  const starts = [CROWN, ...LEFT_HALF.map((cubic) => [cubic[4], cubic[5]] as const)];
  for (let index = LEFT_HALF.length - 1; index >= 0; index -= 1) {
    const [x1, y1, x2, y2] = LEFT_HALF[index] as Cubic;
    const [x, y] = starts[index] as readonly [number, number];
    parts.push(`C${num(WIDTH - x2)} ${num(y2)} ${num(WIDTH - x1)} ${num(y1)} ${num(WIDTH - x)} ${num(y)}`);
  }
  return `${parts.join("")}Z`;
}

/** El `d` del contorno, exportado para su prueba (`silhouette.test.ts`). */
export const BODY_OUTLINE = outline();

/** La zona de la figura en que cayó un clic (su `<g data-region>`), o `null` fuera de toda zona. */
export function zoneOf(target: EventTarget | null): SitedRegion | null {
  const element = target as { closest?: (selector: string) => { getAttribute(name: string): string | null } | null } | null;
  const region = element?.closest?.("g.zone[data-region]")?.getAttribute("data-region") ?? null;
  return region !== null && isSitedRegion(region) ? region : null;
}

export function Silhouette({
  zoneClassName,
  selected = null,
  className,
  onZone,
}: {
  /** La clase `c-<token>` de cada zona (el color de su nivel), o `undefined` para heredar. */
  zoneClassName?: ((region: SitedRegion) => string | undefined) | undefined;
  /** La región elegida en el modo anatómico, si la hay. */
  selected?: string | null | undefined;
  className?: string | undefined;
  /**
   * Pulsar una zona con el puntero. Es un atajo: el dibujo sigue oculto al lector de pantalla y
   * cada región tiene su botón con nombre (`BodySilhouette`); en «Inicio» y «Radiación», donde esos
   * rótulos no se ven, la zona era lo único que había que pulsar (2026-11-15).
   */
  onZone?: ((region: SitedRegion) => void) | undefined;
}) {
  return (
    <svg
      onClick={
        onZone === undefined
          ? undefined
          : (event) => {
              const region = zoneOf(event.target);
              if (region !== null) onZone(region);
            }
      }
      className={className === undefined ? "silhouette" : `silhouette ${className}`}
      viewBox={SILHOUETTE_VIEWBOX}
      aria-hidden="true"
      focusable="false"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      data-silhouette="front"
    >
      <g className="outline">
        <path d={BODY_OUTLINE} />
      </g>
      {SITED_REGIONS.map((region) => {
        const tone = zoneClassName?.(region);
        return (
          <g
            key={region}
            className={tone === undefined ? "zone" : `zone ${tone}`}
            data-region={region}
            data-selected={selected === region ? "true" : undefined}
          >
            {SITES[region].shape}
          </g>
        );
      })}
    </svg>
  );
}
