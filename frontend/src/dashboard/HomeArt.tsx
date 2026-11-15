import { type ReactElement, useMemo } from "react";

import { tr } from "../lib/i18n";

/**
 * El adorno del tablero «Inicio» (la maqueta «Panel EMMA: Rutas Espaciales y Salud», 2026-11-06):
 * degradados, planetas, la Tierra de noche, la ruta, el astronauta del retrato, las estrellas, la
 * estación, la cúpula, el logotipo y el icono de señal de la cabecera. Nada de esto es dato ni
 * pictograma: decisión del usuario (2026-11-07) de conservar el aspecto de la maqueta en la consola
 * y declararlo como desviación consciente de NASA-STD-3001 F.5.10 (color y degradados como adorno)
 * en `compliance/hmi-state-of-the-art.md`. Los colores los pone el CSS con mezclas de la paleta; la
 * prueba de pictogramas exime este fichero por nombre.
 *
 * Lo que no se copió de la maqueta (decisiones del usuario, 2026-11-06): sin foto del tripulante
 * (el backend no la da; el astronauta es un casco de EVA con el visor cerrado, sin rostro ni pelo,
 * así que sin género) y sin símbolos de agencias.
 */

/** Degradados de los dibujos; los colores los pone el CSS con mezclas de la paleta. */
export function Gradients() {
  return (
    <svg className="ref-defs" aria-hidden="true" focusable="false">
      <defs>
        <radialGradient id="ref-g-earth" cx="35%" cy="32%" r="72%">
          <stop offset="0%" className="ref-s-earth-hi" />
          <stop offset="35%" className="ref-s-land" />
          <stop offset="62%" className="ref-s-earth" />
          <stop offset="100%" className="ref-s-deep" />
        </radialGradient>
        <radialGradient id="ref-g-moon" cx="35%" cy="32%" r="72%">
          <stop offset="0%" className="ref-s-moon-hi" />
          <stop offset="70%" className="ref-s-moon" />
          <stop offset="100%" className="ref-s-black" />
        </radialGradient>
        <radialGradient id="ref-g-mars" cx="35%" cy="32%" r="72%">
          <stop offset="0%" className="ref-s-mars-hi" />
          <stop offset="65%" className="ref-s-mars" />
          <stop offset="100%" className="ref-s-black" />
        </radialGradient>
        <radialGradient id="ref-g-heat" cx="50%" cy="27%" r="75%">
          <stop offset="0%" className="ref-s-heat-0" />
          <stop offset="10%" className="ref-s-heat-1" />
          <stop offset="22%" className="ref-s-heat-2" />
          <stop offset="38%" className="ref-s-heat-3" />
          <stop offset="60%" className="ref-s-heat-4" />
          <stop offset="100%" className="ref-s-heat-5" />
        </radialGradient>
        <radialGradient id="ref-g-body" cx="50%" cy="30%" r="62%">
          <stop offset="0%" className="ref-s-heat-0" />
          <stop offset="14%" className="ref-s-heat-1" />
          <stop offset="30%" className="ref-s-heat-2" />
          <stop offset="46%" className="ref-s-heat-3" />
          <stop offset="68%" className="ref-s-heat-4" />
          <stop offset="100%" className="ref-s-heat-5" />
        </radialGradient>
        {/* La figura de «Cuerpo» en `SectionArt`: fría, sin el rojo ni el amarillo del calor, que junto a
            una sección de salud se leerían como nivel. */}
        <radialGradient id="ref-g-figure" cx="50%" cy="28%" r="70%">
          <stop offset="0%" className="sec-s-figure-hi" />
          <stop offset="50%" className="sec-s-figure" />
          <stop offset="100%" className="sec-s-figure-lo" />
        </radialGradient>
        <linearGradient id="ref-g-ring" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" className="ref-s-ring-a" />
          <stop offset="100%" className="ref-s-ring-b" />
        </linearGradient>
        <linearGradient id="ref-g-fade" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" className="ref-s-clear" />
          <stop offset="100%" className="ref-s-snow" />
        </linearGradient>
      </defs>
    </svg>
  );
}

function planetFill(id: string): string {
  if (id.startsWith("mars")) return "url(#ref-g-mars)";
  if (id.startsWith("lunar")) return "url(#ref-g-moon)";
  return "url(#ref-g-earth)";
}

/** Miniatura de cada perfil, a color: decorado, sin datos. */
export function PlanetThumb({ id }: { id: string }) {
  return (
    <svg className="ref-thumb" viewBox="0 0 48 48" aria-hidden="true">
      <circle cx="24" cy="24" r="18" fill={planetFill(id)} className="ref-planet" />
      {(id.startsWith("lunar") || id.startsWith("mars")) && (
        <>
          <circle className="ref-crater" cx="17" cy="20" r="3" />
          <circle className="ref-crater" cx="29" cy="29" r="4" />
          <circle className="ref-crater" cx="28" cy="15" r="2" />
        </>
      )}
      {id === "leo" && (
        <g className="ref-station">
          <rect x="30" y="5" width="16" height="3" />
          <rect x="30" y="12" width="16" height="3" />
          <rect x="36" y="5" width="4" height="10" />
        </g>
      )}
      {id === "cislunar" && (
        <>
          <ellipse className="ref-orbit" cx="28" cy="24" rx="19" ry="9" transform="rotate(-15 28 24)" />
          <circle cx="44" cy="18" r="4" fill="url(#ref-g-moon)" />
        </>
      )}
      {id === "mars-transit" && <path className="ref-orbit" d="M1 44 Q 14 4 47 6" />}
      {id === "mars-surface" && <path className="ref-flag" d="M24 7 V 0 M24 0.8 h8 v4 h-8" />}
    </svg>
  );
}

/**
 * La Tierra de noche detrás del carril, abajo a la izquierda, como en la muestra (lote «muestra», ronda
 * 4, 2026-11-08): el limbo con la atmósfera encendida, la cara de noche y las luces de las ciudades en
 * racimos. Va dentro del carril (`components/ConsoleTabs.tsx`), la última, en el hueco que las
 * pestañas dejan libre al pie. Es la única Tierra de la concha: había otra al pie de la página
 * (`EarthBackdrop`) y en las secciones cortas se montaba encima de esta; se quitó (Ellande,
 * 2026-11-09). Decorado, sin datos; los colores los pone `shell/rail.css` con mezclas de la paleta.
 */
export function EarthNightArt() {
  const { lights, glows } = useMemo(() => {
    const rand = (index: number, seed: number) => {
      const value = Math.sin(index * 17.231 + seed * 59.417) * 31337.5453;
      return value - Math.floor(value);
    };
    const inside = (x: number, y: number) =>
      x > 0 && x < 260 && y > 0 && y < 240 && Math.hypot(x - EARTH.cx, y - EARTH.cy) < EARTH.r - 6;
    const dots: { x: number; y: number; r: number; warm: boolean }[] = [];
    const halos: { x: number; y: number; r: number }[] = [];
    for (let cluster = 0; cluster < 14; cluster += 1) {
      // El centro de cada racimo, entre el limbo (a la izquierda, ángulo -1,55; a la derecha, -1,22) y
      // el pie del dibujo.
      const angle = -1.55 + rand(cluster, 1) * 0.36;
      const depth = 16 + rand(cluster, 2) * 140;
      const cx = EARTH.cx + Math.cos(angle) * (EARTH.r - depth);
      const cy = EARTH.cy + Math.sin(angle) * (EARTH.r - depth);
      const size = 5 + rand(cluster, 3) * 13;
      const count = 8 + Math.floor(rand(cluster, 4) * 22);
      if (inside(cx, cy) && size > 11) halos.push({ x: cx, y: cy, r: size * 0.7 });
      for (let index = 0; index < count; index += 1) {
        const seed = cluster * 100 + index;
        // Más juntas en el centro del racimo que en su borde.
        const spread = rand(seed, 5) * rand(seed, 6);
        const turn = rand(seed, 7) * Math.PI * 2;
        const x = cx + Math.cos(turn) * spread * size * 1.6;
        const y = cy + Math.sin(turn) * spread * size;
        if (inside(x, y)) dots.push({ x, y, r: 0.35 + rand(seed, 8) * rand(seed, 9) * 1.6, warm: rand(seed, 10) > 0.3 });
      }
    }
    // Y luces sueltas entre los racimos.
    for (let index = 0; index < 110; index += 1) {
      const x = rand(index, 11) * 260;
      const y = 80 + rand(index, 12) * 160;
      if (inside(x, y)) dots.push({ x, y, r: 0.3 + rand(index, 13) * 0.5, warm: rand(index, 14) > 0.5 });
    }
    return { lights: dots, glows: halos };
  }, []);
  return (
    <svg className="rail-earth" viewBox="0 0 260 240" preserveAspectRatio="xMinYMin slice" aria-hidden="true" focusable="false">
      <defs>
        <radialGradient id="rail-earth-night" gradientUnits="userSpaceOnUse" cx="150" cy="90" r="210">
          <stop offset="0%" className="rail-earth-s-lit" />
          <stop offset="45%" className="rail-earth-s-mid" />
          <stop offset="100%" className="rail-earth-s-deep" />
        </radialGradient>
      </defs>
      <circle className="rail-earth-glow" cx={EARTH.cx} cy={EARTH.cy} r={EARTH.r + 4} />
      <circle cx={EARTH.cx} cy={EARTH.cy} r={EARTH.r} fill="url(#rail-earth-night)" />
      {/* Nubes: vetas claras que siguen la curva, cerca del limbo. */}
      <path className="rail-earth-cloud" d="M10 98 C 34 92 58 93 80 98" />
      <path className="rail-earth-cloud" d="M104 104 C 130 100 156 104 178 112" />
      <path className="rail-earth-cloud thin" d="M196 124 C 214 126 230 132 246 138" />
      <path className="rail-earth-cloud thin" d="M40 122 C 62 118 82 122 98 128" />
      <path className="rail-earth-cloud" d="M150 148 C 172 146 196 152 214 160" />
      <path className="rail-earth-cloud thin" d="M6 156 C 24 152 44 156 58 162" />
      <path className="rail-earth-cloud thin" d="M96 182 C 122 178 146 184 164 192" />
      <path className="rail-earth-cloud thin" d="M196 204 C 214 204 232 212 248 222" />
      <circle className="rail-earth-limb" cx={EARTH.cx} cy={EARTH.cy} r={EARTH.r} />
      {glows.map((glow, index) => (
        <circle key={`g${index}`} className="rail-earth-halo" cx={glow.x} cy={glow.y} r={glow.r} />
      ))}
      {lights.map((light, index) => (
        <circle key={index} className={light.warm ? "rail-earth-light warm" : "rail-earth-light"} cx={light.x} cy={light.y} r={light.r} />
      ))}
    </svg>
  );
}

/**
 * El disco de `EarthNightArt`, en las unidades de su `viewBox` (260 × 240): centro muy por debajo del
 * dibujo, para que el limbo cruce todo el ancho casi plano, como en la muestra (de (0, 80) a (260, 129)).
 */
const EARTH = { cx: -20, cy: 900, r: 820 } as const;

/** Dibujo de la ruta: Tierra, la trayectoria punteada, la nave y el destino. Decorado, sin datos. */
export function RouteArt({ target, targetId }: { target: string; targetId: string }) {
  const destination = targetId.startsWith("mars") ? "url(#ref-g-mars)" : "url(#ref-g-moon)";
  return (
    <svg className="ref-route-art" viewBox="0 0 360 90" role="img" aria-label={tr(`Ruta de la Tierra a ${target}`, `Route from Earth to ${target}`)}>
      <circle cx="44" cy="52" r="40" className="ref-halo" />
      <circle cx="44" cy="52" r="34" fill="url(#ref-g-earth)" className="ref-planet" />
      {[
        [30, 60],
        [36, 66],
        [48, 70],
        [56, 62],
        [26, 50],
        [60, 74],
      ].map(([cx, cy]) => (
        <circle key={`${cx}-${cy}`} className="ref-light warm" cx={cx} cy={cy} r="1.2" />
      ))}
      <path className="ref-path" d="M80 56 C 140 24, 230 8, 296 44" />
      <circle className="ref-node" cx="96" cy="47" r="4" />
      <circle className="ref-node" cx="140" cy="31" r="4" />
      <circle className="ref-node" cx="262" cy="26" r="4" />
      <g className="ref-ship" transform="translate(186 12) rotate(-6)">
        <rect className="ref-ship-panel" x="-14" y="-6" width="10" height="6" />
        <rect className="ref-ship-panel" x="-14" y="10" width="10" height="6" />
        <path d="M-4 2 H18 Q30 5 18 8 H-4 Z" />
        <path className="ref-ship-flame" d="M-4 3 L-14 5 L-4 7 Z" />
      </g>
      {targetId !== "leo" && (
        <>
          <circle cx="324" cy="52" r="28" fill={destination} className="ref-planet" />
          <circle className="ref-crater" cx="314" cy="44" r="4" />
          <circle className="ref-crater" cx="332" cy="60" r="5" />
          <circle className="ref-crater" cx="330" cy="40" r="2.5" />
        </>
      )}
    </svg>
  );
}

/**
 * Astronauta del avatar: casco de EVA con el visor cerrado y reflectante, sin rostro ni pelo, así
 * que sin género (decisión del usuario, 2026-11-06). Encuadre como el retrato de la maqueta: el
 * casco llena el círculo, la Tierra asoma tras los hombros y el anillo del cuello es azul. Figura
 * genérica, sin símbolos de agencias. Decorado: el backend no da imagen del tripulante.
 */
export function AstronautArt() {
  return (
    <svg className="ref-astronaut" viewBox="0 0 80 80">
      <defs>
        <linearGradient id="ref-a-suit" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" className="ref-s-suit-hi" />
          <stop offset="100%" className="ref-s-suit-lo" />
        </linearGradient>
        <linearGradient id="ref-a-ring-blue" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" className="ref-s-ringb-hi" />
          <stop offset="100%" className="ref-s-ringb-lo" />
        </linearGradient>
        <radialGradient id="ref-a-helmet" cx="36%" cy="28%" r="78%">
          <stop offset="0%" className="ref-s-suit-hi" />
          <stop offset="62%" className="ref-s-ring-mid" />
          <stop offset="100%" className="ref-s-ring-lo" />
        </radialGradient>
        <radialGradient id="ref-a-visor" cx="35%" cy="28%" r="82%">
          <stop offset="0%" className="ref-s-visor-hi" />
          <stop offset="55%" className="ref-s-visor" />
          <stop offset="100%" className="ref-s-visor-edge" />
        </radialGradient>
        <clipPath id="ref-a-visor-clip">
          <ellipse cx="40" cy="35" rx="19" ry="16.5" />
        </clipPath>
      </defs>
      {[
        [8, 10],
        [70, 14],
        [14, 34],
        [66, 40],
        [24, 6],
        [58, 4],
        [6, 50],
        [74, 52],
      ].map(([cx, cy]) => (
        <circle key={`${cx}-${cy}`} className="ref-a-star" cx={cx} cy={cy} r="0.7" />
      ))}
      <circle className="ref-a-atmo" cx="40" cy="112" r="72" />
      <circle cx="40" cy="112" r="70" fill="url(#ref-g-earth)" />
      <path d="M0 80 Q2 62 22 58 L58 58 Q78 62 80 80 Z" fill="url(#ref-a-suit)" />
      <path className="ref-a-seam" d="M16 66 Q20 74 18 80 M64 66 Q60 74 62 80 M40 68 V80" />
      <circle className="ref-a-patch" cx="13" cy="72" r="4.6" />
      <circle className="ref-a-patch-in" cx="13" cy="72" r="2.4" />
      <rect className="ref-a-flag" x="60" y="68" width="9" height="6" rx="0.8" />
      <rect className="ref-a-flag-band" x="60" y="70" width="9" height="2" />
      <ellipse cx="40" cy="58.5" rx="22" ry="6.2" fill="url(#ref-a-ring-blue)" className="ref-a-ring-blue" />
      {[22, 31, 40, 49, 58].map((x) => (
        <rect key={x} className="ref-a-latch" x={x - 1.4} y={x === 40 ? 62.6 : x === 22 || x === 58 ? 59.4 : 61.6} width="2.8" height="1.6" rx="0.5" />
      ))}
      <circle cx="40" cy="33" r="26.5" fill="url(#ref-a-helmet)" className="ref-a-helmet" />
      <ellipse className="ref-a-helmet-hi" cx="27" cy="15" rx="9" ry="4.5" transform="rotate(-30 27 15)" />
      <rect className="ref-a-cam" x="34.5" y="5.5" width="11" height="4.2" rx="1.4" />
      <rect className="ref-a-lamp" x="9.5" y="27" width="4.2" height="9" rx="1.6" />
      <rect className="ref-a-lamp" x="66.3" y="27" width="4.2" height="9" rx="1.6" />
      <ellipse className="ref-a-rim" cx="40" cy="35" rx="21.5" ry="19" />
      <ellipse cx="40" cy="35" rx="19" ry="16.5" fill="url(#ref-a-visor)" className="ref-a-visor" />
      <g clipPath="url(#ref-a-visor-clip)">
        <circle className="ref-a-reflect-atmo" cx="40" cy="86" r="42" />
        <circle cx="40" cy="86" r="40" fill="url(#ref-g-earth)" className="ref-a-reflect-earth" />
      </g>
      <path className="ref-a-shine" d="M26 27 Q32 20 43 21" />
      <path className="ref-a-shine-soft" d="M24.5 35 Q25 31 27 28.5" />
      <ellipse className="ref-a-glint" cx="52" cy="26" rx="2.6" ry="1.4" transform="rotate(25 52 26)" />
    </svg>
  );
}

/** Campo de estrellas de fondo, fijo y pseudoaleatorio. Decorado, sin datos. */
export function StarField() {
  const stars = useMemo(
    () =>
      Array.from({ length: 170 }, (_, index) => {
        const rand = (seed: number) => {
          const value = Math.sin(index * 91.345 + seed * 47.853) * 24634.6345;
          return value - Math.floor(value);
        };
        return { x: rand(1) * 1600, y: rand(2) * 1000, r: 0.4 + rand(3) * rand(4) * 1.4 };
      }),
    [],
  );
  return (
    <svg className="ref-stars" viewBox="0 0 1600 1000" preserveAspectRatio="xMidYMid slice" aria-hidden="true" focusable="false">
      {stars.map((star, index) => (
        <circle key={index} cx={star.x} cy={star.y} r={star.r} />
      ))}
    </svg>
  );
}

/** Estación espacial sobre la Tierra, para la tarjeta de conexión social. Decorado. */
export function StationArt() {
  return (
    <svg className="ref-foot-art" viewBox="0 0 160 80" preserveAspectRatio="xMaxYMid slice" aria-hidden="true">
      <circle cx="110" cy="170" r="120" className="ref-halo" />
      <circle cx="110" cy="170" r="114" fill="url(#ref-g-earth)" className="ref-planet" />
      <g className="ref-station" transform="translate(30 6)">
        <rect x="0" y="20" width="100" height="3" />
        {[6, 22, 70, 86].map((x) => (
          <g key={x}>
            <rect className="ref-solar" x={x} y="2" width="12" height="16" transform="skewX(-12)" />
            <rect className="ref-solar" x={x} y="25" width="12" height="16" transform="skewX(12)" />
          </g>
        ))}
        <rect x="40" y="15" width="22" height="12" rx="3" />
        <circle cx="66" cy="21" r="4" />
      </g>
      <circle className="ref-play" cx="142" cy="62" r="9" />
      <path className="ref-play-tri" d="M139 57 L147 62 L139 67 Z" />
    </svg>
  );
}

/** Cúpula de campaña sobre nieve, para la tarjeta de extensión terrestre. Decorado. */
export function ShelterArt() {
  return (
    <svg className="ref-foot-art" viewBox="0 0 160 80" preserveAspectRatio="xMaxYMid slice" aria-hidden="true">
      <rect x="0" y="0" width="160" height="80" fill="url(#ref-g-fade)" />
      <path className="ref-mountain" d="M20 50 L52 18 L74 40 L98 14 L140 52 Z" />
      <path className="ref-snow" d="M0 62 Q 50 48 100 56 T 160 50 V 80 H 0 Z" />
      <path className="ref-tent" d="M64 64 Q 64 30 98 30 Q 132 30 132 64 Z" />
      <path className="ref-tent-rib" d="M80 64 Q 82 36 98 30 M116 64 Q 114 36 98 30 M66 50 H130" />
      <path className="ref-tent-door" d="M90 64 Q 90 50 98 50 Q 106 50 106 64 Z" />
      <circle className="ref-light warm" cx="98" cy="58" r="2.4" />
    </svg>
  );
}

/** La flecha de «ir a» de los accesos rápidos, como en la maqueta. Decorado. */
export function Chevron() {
  return (
    <svg className="ref-chevron" viewBox="0 0 12 20" aria-hidden="true">
      <path d="M2 2 L10 10 L2 18" />
    </svg>
  );
}

/** El logotipo de la cabecera de la maqueta: la elipse y el latido. Decorado. */
export function BrandLogo() {
  return (
    <svg className="ref-logo" viewBox="0 0 64 64" aria-hidden="true">
      <ellipse cx="32" cy="32" rx="29" ry="24" transform="rotate(-25 32 32)" />
      <path d="M6 34 H20 L25 22 L31 44 L37 16 L42 34 H58" />
    </svg>
  );
}

/**
 * El dibujo de cada sección, a la derecha del título de su marco (lote «muestra», 2026-11-08: «más
 * dibujos», como la nave de «Rutas espaciales» y los mosaicos de la muestra). Adorno puro: cada uno
 * es un `svg` con `aria-hidden` y `focusable="false"`, sin texto ni datos, coloreado por `art.css`
 * con la paleta, los degradados de `Gradients` y el acento de su sección (`--sec-acc`, adorno).
 * «Inicio» ya lleva sus dibujos y no repite ninguno; una clave sin dibujo no pinta nada.
 *
 * Por qué no se reutiliza `AstronautArt` en «Cuerpo»: define sus degradados con `id` propios, y dos
 * copias en el DOM (la de «Inicio» queda montada y oculta) se pisarían las referencias; la figura de
 * «Cuerpo» usa un degradado compartido de `Gradients` (`ref-g-figure`).
 */
export function SectionArt({ section, console: consoleId }: { section: string; console: string }) {
  if (section.startsWith("env-") && section.length > "env-".length) {
    // El planeta del perfil, el mismo de la tira de ubicación de «Inicio», en grande.
    return (
      <span className="sec-art sec-art-env" aria-hidden="true">
        <PlanetThumb id={section.slice("env-".length)} />
      </span>
    );
  }
  if (consoleId === "ground" && section === "habitat") {
    return (
      <span className="sec-art sec-art-wide" aria-hidden="true">
        <ShelterArt />
      </span>
    );
  }
  const draw = (consoleId === "ground" ? GROUND_ART : CREW_ART).get(section);
  if (draw === undefined) return null;
  return (
    <svg className="sec-art" data-art={section} viewBox="0 0 120 64" aria-hidden="true" focusable="false">
      {draw()}
    </svg>
  );
}

/** Sector anular (las aspas del trébol), en grados desde las tres en punto. */
function sector(cx: number, cy: number, inner: number, outer: number, from: number, to: number): string {
  const at = (r: number, deg: number) => {
    const rad = (deg * Math.PI) / 180;
    return `${(cx + r * Math.cos(rad)).toFixed(2)} ${(cy + r * Math.sin(rad)).toFixed(2)}`;
  };
  return `M${at(inner, from)} L${at(outer, from)} A${outer} ${outer} 0 0 1 ${at(outer, to)} L${at(inner, to)} A${inner} ${inner} 0 0 0 ${at(inner, from)} Z`;
}

/** Esfera de reloj con sus doce marcas y dos agujas fijas. */
function Dial({ cx, cy, r }: { cx: number; cy: number; r: number }) {
  return (
    <g>
      <circle className="sec-art-dial" cx={cx} cy={cy} r={r} />
      {Array.from({ length: 12 }, (_, hour) => {
        const rad = (hour * Math.PI) / 6;
        const [x1, y1] = [cx + (r - 2.5) * Math.sin(rad), cy - (r - 2.5) * Math.cos(rad)];
        const [x2, y2] = [cx + (r - 5.5) * Math.sin(rad), cy - (r - 5.5) * Math.cos(rad)];
        return <line key={hour} className="sec-art-tick" x1={x1} y1={y1} x2={x2} y2={y2} />;
      })}
      <path className="sec-art-hand" d={`M${cx} ${cy} V${cy - r * 0.62} M${cx} ${cy} L${cx + r * 0.45} ${cy + r * 0.18}`} />
      <circle className="sec-art-pin" cx={cx} cy={cy} r="1.8" />
    </g>
  );
}

/** Planeta pequeño de fondo, con halo. */
function Orb({ cx, cy, r, fill }: { cx: number; cy: number; r: number; fill: "earth" | "moon" | "mars" }) {
  return (
    <g>
      <circle className="ref-halo" cx={cx} cy={cy} r={r + 4} />
      <circle className="ref-planet" cx={cx} cy={cy} r={r} fill={`url(#ref-g-${fill})`} />
      {fill !== "earth" && <circle className="ref-crater" cx={cx - r * 0.3} cy={cy - r * 0.2} r={r * 0.22} />}
    </g>
  );
}

/** Peligros: el escudo con el trébol y la órbita alrededor de la Tierra. */
function HazardsArt() {
  return (
    <>
      <Orb cx={96} cy={42} r={13} fill="earth" />
      <ellipse className="ref-orbit" cx={72} cy={34} rx={44} ry={13} transform="rotate(-10 72 34)" />
      <path className="sec-art-shield" d="M56 6 L77 13 V30 Q77 48 56 58 Q35 48 35 30 V13 Z" />
      {[-90, 30, 150].map((deg) => (
        <path key={deg} className="sec-art-blade" d={sector(56, 31, 4, 13, deg - 30, deg + 30)} />
      ))}
      <circle className="sec-art-blade" cx={56} cy={31} r={2.4} />
    </>
  );
}

/** Rutinas: el reloj y la estación sobre la Tierra. */
function RoutinesArt() {
  return (
    <>
      <Orb cx={98} cy={46} r={14} fill="earth" />
      <g className="ref-station" transform="translate(72 6)">
        <rect x="0" y="7" width="34" height="2" />
        {[2, 24].map((x) => (
          <g key={x}>
            <rect className="ref-solar" x={x} y="0" width="7" height="6" />
            <rect className="ref-solar" x={x} y="10" width="7" height="6" />
          </g>
        ))}
        <rect x="12" y="5" width="9" height="6" rx="2" />
      </g>
      <Dial cx={42} cy={32} r={22} />
    </>
  );
}

/** Cuerpo: la figura, en azules como el cuerpo de la maqueta, y un latido al lado. */
function BodyArt() {
  return (
    <>
      <ellipse className="ref-halo" cx={74} cy={34} rx={24} ry={30} />
      <path className="sec-art-pulse" d="M4 40 H22 L27 28 L33 52 L38 34 L41 40 H54" />
      <circle cx={74} cy={10} r={7} fill="url(#ref-g-figure)" className="sec-art-figure" />
      <path
        className="sec-art-figure"
        fill="url(#ref-g-figure)"
        d="M74 18 C66 18 64 21 63 25 L57 40 L60.5 41.5 L66 30 L66 44 L64 62 H69.5 L73 46 H75 L78.5 62 H84 L82 44 L82 30 L87.5 41.5 L91 40 L85 25 C84 21 82 18 74 18 Z"
      />
    </>
  );
}

/** Misión: la ruta de la Tierra a Marte con la nave, como la de «Rutas espaciales». */
function MissionArt() {
  return (
    <>
      <Orb cx={18} cy={42} r={14} fill="earth" />
      <path className="ref-path" d="M32 38 C 50 12, 82 8, 96 30" />
      <circle className="ref-node" cx={40} cy={27} r={2.4} />
      <circle className="ref-node" cx={86} cy={19} r={2.4} />
      <g className="ref-ship" transform="translate(58 13) rotate(-8) scale(0.7)">
        <rect className="ref-ship-panel" x="-14" y="-6" width="10" height="6" />
        <rect className="ref-ship-panel" x="-14" y="10" width="10" height="6" />
        <path d="M-4 2 H18 Q30 5 18 8 H-4 Z" />
        <path className="ref-ship-flame" d="M-4 3 L-14 5 L-4 7 Z" />
      </g>
      <Orb cx={104} cy={42} r={12} fill="mars" />
    </>
  );
}

/** Datos: la antena de los sensores emitiendo hacia la Luna. */
function DataArt() {
  return (
    <>
      <Orb cx={102} cy={16} r={8} fill="moon" />
      <path className="sec-art-ground" d="M12 62 Q48 50 92 62 Z" />
      <path className="sec-art-mast" d="M46 58 L50 34 L54 58 M47.5 50 H52.5" />
      <path className="sec-art-dish" d="M30 26 Q44 48 66 30 Z" />
      <path className="sec-art-mast" d="M48 33 L60 22" />
      <circle className="sec-art-pin" cx={60} cy={22} r={2} />
      {[8, 15, 22].map((r) => (
        <path key={r} className="sec-art-wave" d={`M${60 + r * 0.6} ${22 - r * 0.8} A${r} ${r} 0 0 1 ${60 + r * 0.95} ${22 + r * 0.3}`} />
      ))}
    </>
  );
}

/** Bitácora: el portapapeles con renglones y el lápiz. */
function LogArt() {
  return (
    <>
      <Orb cx={20} cy={20} r={9} fill="moon" />
      <circle className="ref-halo" cx={60} cy={34} r={26} />
      <rect className="sec-art-paper" x={42} y={9} width={36} height={50} rx={4} />
      <rect className="sec-art-clip" x={52} y={5} width={16} height={8} rx={2} />
      {[22, 30, 38, 46].map((y) => (
        <line key={y} className="sec-art-rule" x1={48} y1={y} x2={y === 46 ? 62 : 72} y2={y} />
      ))}
      <g transform="rotate(32 92 32)">
        <rect className="sec-art-pen" x={88.5} y={8} width={7} height={36} rx={2} />
        <path className="sec-art-nib" d="M88.5 44 L92 52 L95.5 44 Z" />
      </g>
    </>
  );
}

/** Imagen: la sonda de ecografía con su abanico. */
function ImagingArt() {
  return (
    <>
      <circle className="ref-halo" cx={60} cy={40} r={26} />
      <path className="sec-art-beam" d="M60 34 L36 62 Q60 70 84 62 Z" />
      {[12, 19, 26].map((r) => (
        <path key={r} className="sec-art-echo" d={`M${60 - r * 0.62} ${34 + r * 0.78} Q60 ${34 + r * 1.12} ${60 + r * 0.62} ${34 + r * 0.78}`} />
      ))}
      <path className="sec-art-cable" d="M60 6 C 60 0, 80 0, 92 8 S 108 20, 114 14" />
      <rect className="sec-art-probe" x={53} y={4} width={14} height={22} rx={6} />
      <path className="sec-art-probe" d="M50 25 H70 L67.5 35 H52.5 Z" />
    </>
  );
}

/** Biblioteca: los libros en su estante y un planeta. */
function LibraryArt() {
  return (
    <>
      <Orb cx={100} cy={16} r={9} fill="earth" />
      <circle className="ref-halo" cx={56} cy={36} r={24} />
      <rect className="sec-art-book a" x={34} y={14} width={10} height={44} rx={1.5} />
      <rect className="sec-art-book b" x={45} y={20} width={12} height={38} rx={1.5} />
      <rect className="sec-art-book c" x={58} y={10} width={9} height={48} rx={1.5} />
      <rect className="sec-art-book a" x={70} y={16} width={10} height={42} rx={1.5} transform="rotate(14 75 58)" />
      {[39, 51, 62.5].map((x) => (
        <line key={x} className="sec-art-band" x1={x - 3} y1={24} x2={x + 3} y2={24} />
      ))}
      <line className="sec-art-shelf" x1={26} y1={59} x2={96} y2={59} />
    </>
  );
}

/** Tierra, recibido: la antena de espacio profundo apuntando a la nave. */
function ReceivedArt() {
  return (
    <>
      <Orb cx={104} cy={14} r={8} fill="mars" />
      <path className="ref-path" d="M58 24 C 72 14, 86 10, 96 14" />
      <path className="sec-art-ground" d="M10 62 Q50 52 96 62 Z" />
      <path className="sec-art-mast" d="M40 58 L46 38 H52 L58 58 Z" />
      <path className="sec-art-dish" d="M24 30 Q42 54 70 26 Z" />
      <path className="sec-art-mast" d="M46 38 L58 24" />
      <circle className="sec-art-pin" cx={58} cy={24} r={2.2} />
    </>
  );
}

/** Tierra, historial: el reloj con la flecha que vuelve atrás. */
function HistoryArt() {
  return (
    <>
      <Orb cx={100} cy={46} r={11} fill="earth" />
      <circle className="ref-halo" cx={56} cy={32} r={28} />
      <path className="sec-art-arrow" d="M33 22 A26 26 0 1 1 31 42" />
      <path className="sec-art-arrowhead" d="M27 15 L35 25 L25 26 Z" />
      <Dial cx={56} cy={32} r={19} />
    </>
  );
}

/** Tierra, tendencias: una gráfica que sube, con sus puntos. */
function TrendsArt() {
  const points: [number, number][] = [
    [30, 48],
    [44, 40],
    [58, 44],
    [72, 30],
    [86, 22],
  ];
  return (
    <>
      <Orb cx={8} cy={14} r={7} fill="moon" />
      <rect className="sec-art-panel" x={18} y={6} width={82} height={54} rx={5} />
      {[18, 30, 42].map((y) => (
        <line key={y} className="sec-art-grid" x1={26} y1={y} x2={94} y2={y} />
      ))}
      <path className="sec-art-axis" d="M26 12 V54 H94" />
      <path className="sec-art-area" d={`M30 54 L${points.map(([x, y]) => `${x} ${y}`).join(" L")} V54 Z`} />
      <path className="sec-art-line" d={`M${points.map(([x, y]) => `${x} ${y}`).join(" L")}`} />
      {points.map(([x, y]) => (
        <circle key={x} className="sec-art-dot" cx={x} cy={y} r={2.4} />
      ))}
    </>
  );
}

/** Tierra, marco: los documentos apilados con su sello. */
function FrameworkArt() {
  return (
    <>
      <circle className="ref-halo" cx={58} cy={34} r={26} />
      <rect className="sec-art-paper back" x={50} y={6} width={32} height={42} rx={3} transform="rotate(10 66 27)" />
      <rect className="sec-art-paper" x={38} y={10} width={32} height={46} rx={3} />
      {[20, 27, 34, 41].map((y) => (
        <line key={y} className="sec-art-rule" x1={43} y1={y} x2={y === 41 ? 55 : 65} y2={y} />
      ))}
      <path className="sec-art-ribbon" d="M70 50 L66 62 L71 59 L74 63 L76 51 Z" />
      <circle className="sec-art-seal" cx={72} cy={48} r={7} />
      <circle className="sec-art-seal-in" cx={72} cy={48} r={3.6} />
    </>
  );
}

/** Tierra, registro: la cadena de eslabones y el candado. */
function LedgerArt() {
  return (
    <>
      <circle className="ref-halo" cx={60} cy={34} r={26} />
      {[
        [14, 0],
        [30, 1],
        [46, 0],
      ].map(([x, tilt]) => (
        <rect key={x} className="sec-art-link" x={x} y={tilt === 1 ? 31 : 27} width={22} height={tilt === 1 ? 6 : 14} rx={tilt === 1 ? 3 : 7} />
      ))}
      <path className="sec-art-shackle" d="M76 30 V22 A10 10 0 0 1 96 22 V30" />
      <rect className="sec-art-lock" x={70} y={29} width={32} height={26} rx={4} />
      <circle className="sec-art-keyhole" cx={86} cy={39} r={3} />
      <rect className="sec-art-keyhole" x={84.8} y={40} width={2.4} height={8} rx={1} />
    </>
  );
}

// `Map` y no objeto literal: una clave como «toString» no debe encontrar nada heredado.
const CREW_ART: ReadonlyMap<string, () => ReactElement> = new Map([
  ["hazards", HazardsArt],
  ["routines", RoutinesArt],
  ["body", BodyArt],
  ["mission", MissionArt],
  ["data", DataArt],
  ["log", LogArt],
  ["imaging", ImagingArt],
  ["library", LibraryArt],
]);

const GROUND_ART: ReadonlyMap<string, () => ReactElement> = new Map([
  ["received", ReceivedArt],
  ["history", HistoryArt],
  ["trends", TrendsArt],
  ["framework", FrameworkArt],
  ["ledger", LedgerArt],
  ["library", LibraryArt],
]);

/**
 * La onda del espectro de «Radiación» (maqueta del 2026-11-14): se estira de izquierda (más
 * frecuencia) a derecha (menos), con el degradado de adorno de `radiationBoard.css`. Sin cifras.
 */
export function SpectrumWave() {
  return (
    <svg className="rad-wave" viewBox="0 0 400 34" preserveAspectRatio="none" aria-hidden="true">
      <defs>
        <linearGradient id="rad-g-spectrum" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" className="rad-s-0" />
          <stop offset="0.3" className="rad-s-1" />
          <stop offset="0.45" className="rad-s-2" />
          <stop offset="0.52" className="rad-s-3" />
          <stop offset="0.6" className="rad-s-4" />
          <stop offset="1" className="rad-s-5" />
        </linearGradient>
      </defs>
      <path d={WAVE_PATH} />
    </svg>
  );
}

const WAVE_PATH = (() => {
  const points: string[] = [];
  let phase = 0;
  for (let x = 0; x <= 400; x += 1) {
    phase += 0.9 - (x / 400) * 0.82;
    points.push(`${x === 0 ? "M" : "L"}${x} ${(17 - 13 * Math.sin(phase)).toFixed(1)}`);
  }
  return points.join(" ");
})();

/**
 * Las miniaturas de laboratorio de «Pruebas y control» (maqueta de radiación, 2026-11-14): una hélice,
 * unas barras y dos cortes. Adorno: no son datos ni imágenes de nadie.
 */
export function LabArt() {
  return (
    <svg className="rad-lab-art" viewBox="0 0 120 64" aria-hidden="true">
      <rect className="rad-lab-tile" x="1" y="2" width="58" height="60" rx="4" />
      <path className="rad-lab-helix" d={helixPath(0)} />
      <path className="rad-lab-helix b" d={helixPath(Math.PI)} />
      {Array.from({ length: 8 }, (_, i) => {
        const x = 6 + i * 6.6;
        const phase = ((x - 4) / 2.2) * 0.5;
        return <line key={i} className="rad-lab-rung" x1={x} x2={x} y1={32 + 12 * Math.sin(phase)} y2={32 + 12 * Math.sin(phase + Math.PI)} />;
      })}
      <rect className="rad-lab-tile" x="62" y="2" width="57" height="29" rx="4" />
      {[6, 12, 9, 15, 11, 18, 14].map((height, i) => (
        <rect key={i} className="rad-lab-bar" data-i={i % 3} x={66 + i * 7.3} y={28 - height} width="5" height={height} />
      ))}
      <rect className="rad-lab-tile" x="62" y="33" width="27.5" height="29" rx="4" />
      <rect className="rad-lab-tile" x="91.5" y="33" width="27.5" height="29" rx="4" />
      <ellipse className="rad-lab-scan" cx="75.7" cy="47.5" rx="10" ry="11" />
      <ellipse className="rad-lab-scan" cx="105.2" cy="47.5" rx="10" ry="11" />
      <path className="rad-lab-fold" d="M70 44 q5 -4 10 0 M69 50 q6 4 12 0 M99 44 q5 -4 10 0 M98 50 q6 4 12 0" />
    </svg>
  );
}

function helixPath(shift: number): string {
  return Array.from({ length: 25 }, (_, i) => `${i === 0 ? "M" : "L"}${(4 + i * 2.2).toFixed(1)} ${(32 + 12 * Math.sin(i * 0.5 + shift)).toFixed(1)}`).join(" ");
}

/**
 * El corte de una nave con su refugio en el centro, para «Zonas de blindaje» (maqueta de radiación,
 * 2026-11-14). Adorno: no es la geometría de ninguna nave ni dice dónde está el blindaje.
 */
export function ShipArt() {
  return (
    <svg className="rad-ship-art" viewBox="0 0 160 80" aria-hidden="true">
      <rect className="rad-ship-hull" x="8" y="14" width="144" height="52" rx="22" />
      <rect className="rad-ship-deck" x="18" y="22" width="124" height="36" rx="15" />
      {[30, 46, 106, 122].map((x) => (
        <rect key={x} className="rad-ship-rack" x={x} y="27" width="9" height="26" rx="2" />
      ))}
      <rect className="rad-ship-core" x="62" y="24" width="36" height="32" rx="6" />
      <rect className="rad-ship-core-glow" x="68" y="30" width="24" height="20" rx="4" />
      <path className="rad-ship-ring" d="M2 40 h6 M152 40 h6 M80 6 v8 M80 66 v8" />
    </svg>
  );
}

/**
 * Tres figuras unidas en triángulo, como la tarjeta «Interacciones de la tripulación» de la maqueta de
 * aislamiento (2026-11-15). Adorno: no dice quién habla con quién (EMMA no lo mide).
 */
export function CrewTriangleArt() {
  const people = [
    { x: 60, y: 22 },
    { x: 26, y: 78 },
    { x: 94, y: 78 },
  ];
  return (
    <svg className="iso-crew-art" viewBox="0 0 120 104" aria-hidden="true">
      <polygon className="iso-crew-link" points={people.map((p) => `${p.x},${p.y}`).join(" ")} />
      {people.map((p) => (
        <g key={`${p.x}-${p.y}`} transform={`translate(${p.x} ${p.y})`}>
          <circle className="iso-crew-node" r="19" />
          <circle className="iso-crew-head" cy="-6" r="5.5" />
          <path className="iso-crew-head" d="M-10 11 C-10 1 10 1 10 11 Z" />
        </g>
      ))}
    </svg>
  );
}

/** Una campana de luz con el degradado del espectro (tarjeta «Exposición a la luz»). Adorno, sin escala. */
export function LightBellArt() {
  const points: string[] = [];
  for (let x = 0; x <= 200; x += 2) {
    const a = Math.exp(-((x - 70) ** 2) / 900) * 0.55 + Math.exp(-((x - 140) ** 2) / 1300);
    points.push(`${x} ${(44 - a * 38).toFixed(1)}`);
  }
  return (
    <svg className="iso-light-art" viewBox="0 0 200 46" preserveAspectRatio="none" aria-hidden="true">
      <defs>
        <linearGradient id="iso-g-light" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" className="rad-s-5" />
          <stop offset="0.35" className="rad-s-4" />
          <stop offset="0.55" className="rad-s-3" />
          <stop offset="0.75" className="rad-s-2" />
          <stop offset="1" className="rad-s-0" />
        </linearGradient>
      </defs>
      <path d={`M0 44 L${points.join(" L")} L200 44 Z`} fill="url(#iso-g-light)" />
    </svg>
  );
}

/**
 * Los puntos del cuerpo de la maqueta (varón y su variante femenina) en el lienzo de 152 × 310 de
 * `BodyArt`, medidos a ojo sobre el render (2026-11-15). Solo sirven para que los huesos, los músculos
 * y los vasos caigan encima del cuerpo; no son anatomía ni medida. Cada par es [izquierda, derecha] en x.
 */
interface BodyFrame {
  head: readonly [number, number];
  shoulders: readonly [number, number];
  elbows: readonly [number, number];
  wrists: readonly [number, number];
  hips: readonly [number, number];
  knees: readonly [number, number];
  ankles: readonly [number, number];
  y: { shoulder: number; elbow: number; wrist: number; hip: number; knee: number; ankle: number; pelvis: number };
}

const BODY_FRAMES: Record<"male" | "female", BodyFrame> = {
  male: {
    head: [74, 30],
    shoulders: [33, 115],
    elbows: [29, 121],
    wrists: [16, 133],
    hips: [58, 91],
    knees: [59, 94],
    ankles: [55, 96],
    y: { shoulder: 67, elbow: 115, wrist: 156, hip: 150, knee: 212, ankle: 282, pelvis: 140 },
  },
  female: {
    head: [75, 30],
    shoulders: [38, 112],
    elbows: [32, 120],
    wrists: [15, 135],
    hips: [57, 94],
    knees: [60, 92],
    ankles: [57, 95],
    y: { shoulder: 70, elbow: 115, wrist: 156, hip: 152, knee: 212, ankle: 282, pelvis: 142 },
  },
};

type Point = readonly [number, number];

const f1 = (n: number) => n.toFixed(1);

/** Un punto a `t` de `a` a `b`, desplazado `side` a la normal (positiva a la derecha del avance). */
function along(a: Point, b: Point, t: number, side = 0): Point {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const len = Math.hypot(dx, dy) || 1;
  return [a[0] + dx * t + (-dy / len) * side, a[1] + dy * t + (dx / len) * side];
}

/**
 * Un hueso largo con forma: diáfisis estrecha y epífisis anchas (cabeza y cóndilos), como una
 * silueta cerrada. `w` es el medio ancho de la diáfisis; las cabezas son `head` veces más anchas.
 */
function bonePath(a: Point, b: Point, w: number, head = 2.1): string {
  const ends = w * head;
  const left = [along(a, b, 0.02, -ends), along(a, b, 0.12, -ends * 0.9), along(a, b, 0.25, -w), along(a, b, 0.75, -w), along(a, b, 0.88, -ends * 0.9), along(a, b, 0.98, -ends)];
  const right = [along(a, b, 0.02, ends), along(a, b, 0.12, ends * 0.9), along(a, b, 0.25, w), along(a, b, 0.75, w), along(a, b, 0.88, ends * 0.9), along(a, b, 0.98, ends)];
  const top = along(a, b, -0.03);
  const bottom = along(a, b, 1.03);
  const p = (q: Point | undefined) => `${f1((q ?? a)[0])} ${f1((q ?? a)[1])}`;
  return [
    `M${p(top)}`,
    `Q${p(left[0])} ${p(left[1])}`,
    `C${p(left[1])} ${p(left[2])} ${p(left[2])}`,
    `L${p(left[3])}`,
    `C${p(left[3])} ${p(left[4])} ${p(left[4])}`,
    `Q${p(left[5])} ${p(bottom)}`,
    `Q${p(right[5])} ${p(right[4])}`,
    `C${p(right[4])} ${p(right[3])} ${p(right[3])}`,
    `L${p(right[2])}`,
    `C${p(right[2])} ${p(right[1])} ${p(right[1])}`,
    `Q${p(right[0])} ${p(top)}`,
    "Z",
  ].join(" ");
}

/** Mano o pie: abanico de huesecillos desde un punto en la dirección dada. */
function Fan({ at, toward, spread, length, rays }: { at: Point; toward: Point; spread: number; length: number; rays: number }) {
  const angle = Math.atan2(toward[1] - at[1], toward[0] - at[0]);
  return (
    <g className="grav-smallbones">
      {Array.from({ length: rays }, (_, i) => {
        const a = angle + (i / (rays - 1) - 0.5) * spread;
        // Metacarpo (o metatarso) y tres falanges, cada vez más cortas, con su articulación.
        const cuts = [0, 0.5, 0.72, 0.88, 1];
        const at_ = (t: number): Point => [at[0] + Math.cos(a) * length * t, at[1] + Math.sin(a) * length * t];
        return (
          <g key={i}>
            {cuts.slice(0, -1).map((t, k) => {
              const p0 = at_(t + 0.02);
              const p1 = at_(cuts[k + 1]! - 0.02);
              return <line key={k} x1={f1(p0[0])} y1={f1(p0[1])} x2={f1(p1[0])} y2={f1(p1[1])} />;
            })}
            {cuts.slice(1, -1).map((t) => {
              const q = at_(t);
              return <circle key={t} className="grav-knuckle" cx={f1(q[0])} cy={f1(q[1])} r="0.45" />;
            })}
          </g>
        );
      })}
    </g>
  );
}

/**
 * El esqueleto del estilo «hueso» (maqueta «Salud gravitacional», 2026-11-15), encima del cuerpo
 * recoloreado: cráneo con mandíbula, columna con su curva, costillas que cierran en el esternón,
 * escápulas, pelvis, huesos largos con cabezas, dos huesos en antebrazo y pierna, manos y pies.
 * `marks`: las zonas de las que hay medida de densitometría, señaladas con un anillo. Adorno: el
 * anillo dice dónde se mide, no cómo está.
 */
export function BodyBonesArt({ figure, marks = [] }: { figure: "male" | "female"; marks?: readonly ("lumbar" | "hip")[] }) {
  const f = BODY_FRAMES[figure];
  const cx = f.head[0];
  const hy = f.head[1];
  const { y } = f;
  const [ls, rs] = f.shoulders;
  const [le, re] = f.elbows;
  const [lw, rw] = f.wrists;
  const [lh, rh] = f.hips;
  const [lk, rk] = f.knees;
  const [la, ra] = f.ankles;
  const neckTop = hy + 14;
  const sternumTop = y.shoulder + 1;
  const sternumBottom = y.shoulder + 38;
  const vertebrae = Array.from({ length: 22 }, (_, i) => {
    const t = i / 21;
    const yy = neckTop + t * (y.pelvis - 6 - neckTop);
    const size = 2.2 + t * 2.6;
    return { y: yy, x: cx + Math.sin(t * Math.PI * 2) * 0.8, size };
  });
  const ribs = Array.from({ length: 12 }, (_, i) => ({ y: y.shoulder + 4 + i * 3.45, i }));
  // Diferencias reales del esqueleto femenino (dimorfismo): caja torácica más estrecha, pelvis más ancha y
  // baja, con el arco púbico más abierto. A ojo, sin medida: adorno.
  const female = figure === "female";
  // Más estrecha que los hombros, como en la maqueta (~60 % de su ancho); la femenina, algo más.
  const halfChest = ((rs - ls) / 2 - 7) * (female ? 0.7 : 0.76);
  const pw = female ? 2.5 : 0;
  return (
    <svg className="grav-art grav-bones" viewBox="0 0 152 310" aria-hidden="true">
      {/* Cráneo de frente: bóveda redonda, órbitas, abertura nasal en pera, pómulos, maxilar con dientes y mandíbula en U. */}
      <path className="grav-skull" d={`M${cx} ${hy - 15} C${cx - 9} ${hy - 15} ${cx - 11} ${hy - 7} ${cx - 10.5} ${hy} C${cx - 10.5} ${hy + 3} ${cx - 9.5} ${hy + 5} ${cx - 8.5} ${hy + 6} C${cx - 7} ${hy + 7.5} ${cx - 5.5} ${hy + 8.5} ${cx - 5} ${hy + 9.5} L${cx + 5} ${hy + 9.5} C${cx + 5.5} ${hy + 8.5} ${cx + 7} ${hy + 7.5} ${cx + 8.5} ${hy + 6} C${cx + 9.5} ${hy + 5} ${cx + 10.5} ${hy + 3} ${cx + 10.5} ${hy} C${cx + 11} ${hy - 7} ${cx + 9} ${hy - 15} ${cx} ${hy - 15} Z`} />
      <path className="grav-jaw" d={`M${cx - 7.5} ${hy + 7} C${cx - 7.5} ${hy + 12} ${cx - 5} ${hy + 16} ${cx} ${hy + 16.5} C${cx + 5} ${hy + 16} ${cx + 7.5} ${hy + 12} ${cx + 7.5} ${hy + 7} L${cx + 5.5} ${hy + 11} C${cx + 3} ${hy + 13} ${cx - 3} ${hy + 13} ${cx - 5.5} ${hy + 11} Z`} />
      <path className="grav-socket" d={`M${cx - 8.2} ${hy - 1.5} C${cx - 8.2} ${hy - 4.5} ${cx - 2.2} ${hy - 4.5} ${cx - 2} ${hy - 1.5} C${cx - 2} ${hy + 1.5} ${cx - 8.2} ${hy + 2} ${cx - 8.2} ${hy - 1.5} Z M${cx + 8.2} ${hy - 1.5} C${cx + 8.2} ${hy - 4.5} ${cx + 2.2} ${hy - 4.5} ${cx + 2} ${hy - 1.5} C${cx + 2} ${hy + 1.5} ${cx + 8.2} ${hy + 2} ${cx + 8.2} ${hy - 1.5} Z`} />
      <path className="grav-socket" d={`M${cx} ${hy + 1.5} C${cx - 1.8} ${hy + 3} ${cx - 2} ${hy + 5.5} ${cx - 0.8} ${hy + 6} L${cx + 0.8} ${hy + 6} C${cx + 2} ${hy + 5.5} ${cx + 1.8} ${hy + 3} ${cx} ${hy + 1.5} Z`} />
      <path className="grav-cheek" d={`M${cx - 9.5} ${hy + 2.5} Q${cx - 6} ${hy + 4} ${cx - 3.5} ${hy + 3} M${cx + 9.5} ${hy + 2.5} Q${cx + 6} ${hy + 4} ${cx + 3.5} ${hy + 3}`} />
      {Array.from({ length: 8 }, (_, k) => (
        <rect key={k} className="grav-tooth" x={f1(cx - 4.4 + k * 1.1)} y={f1(hy + 8.3)} width="0.9" height="2.2" rx="0.3" />
      ))}
      {/* Columna: cervicales a lumbares, cada vez más gruesas, con su leve curva. */}
      {vertebrae.map((v) => (
        <rect key={v.y} className="grav-vertebra" x={f1(v.x - v.size)} y={f1(v.y)} width={f1(v.size * 2)} height={f1(v.size * 1.15)} rx="1" />
      ))}
      {/* Clavículas (las escápulas, por detrás, no se ven de frente en la maqueta: quitadas). */}
      <path className="grav-bone" d={`M${ls + 3} ${y.shoulder - 1} C${cx - 16} ${y.shoulder - 5} ${cx - 8} ${y.shoulder - 2} ${cx - 2} ${sternumTop}`} />
      <path className="grav-bone" d={`M${rs - 3} ${y.shoulder - 1} C${cx + 16} ${y.shoulder - 5} ${cx + 8} ${y.shoulder - 2} ${cx + 2} ${sternumTop}`} />
      {/* Costillas: salen de la columna, bajan por el costado y cierran en el esternón (las de abajo, flotantes). */}
      {ribs.map(({ y: r, i }) => {
        // Caja cónica, como en la maqueta: estrecha bajo el cuello y más ancha en el tercio inferior.
        // Las dos últimas (flotantes) son más cortas; de la 8.ª a la 10.ª cierran cada vez más fuera: el arco costal.
        const w = halfChest * (0.5 + Math.sin(((i + 1.5) / 13) * Math.PI * 0.8) * 0.55) * (i > 9 ? 0.86 - (i - 10) * 0.12 : 1);
        const front = i < 7 ? Math.max(sternumTop + 3, Math.min(sternumBottom, r + 12)) : r + 13;
        const end = i < 7 ? 1.5 : i < 10 ? 3 + (i - 7) * 4.5 : w * 0.82;
        return (
          <g key={r} className="grav-rib">
            <path d={`M${cx - 2} ${f1(r - 4)} C${f1(cx - w * 0.6)} ${f1(r - 6)} ${f1(cx - w - 1)} ${f1(r + 1)} ${f1(cx - w - 0.5)} ${f1(r + 9)} C${f1(cx - w)} ${f1(r + 15)} ${f1(cx - w * 0.45)} ${f1(front + 3)} ${f1(cx - end)} ${f1(front + 2)}`} />
            <path d={`M${cx + 2} ${f1(r - 4)} C${f1(cx + w * 0.6)} ${f1(r - 6)} ${f1(cx + w + 1)} ${f1(r + 1)} ${f1(cx + w + 0.5)} ${f1(r + 9)} C${f1(cx + w)} ${f1(r + 15)} ${f1(cx + w * 0.45)} ${f1(front + 3)} ${f1(cx + end)} ${f1(front + 2)}`} />
          </g>
        );
      })}
      <path className="grav-sternum" d={`M${cx - 2} ${sternumTop} L${cx + 2} ${sternumTop} L${cx + 1.5} ${sternumBottom} L${cx} ${sternumBottom + 4} L${cx - 1.5} ${sternumBottom} Z`} />
      {/* Pelvis: alas ilíacas, agujeros obturadores y sacro. */}
      {(() => {
        // Pelvis en mariposa, como la de la maqueta: dos alas ilíacas que suben desde el sacro, bajan al
        // acetábulo y cierran por isquion y pubis; el estrecho superior y los obturadores son huecos de verdad.
        const p = y.pelvis;
        const half = (s: 1 | -1, x: number) => (s === 1 ? x : cx * 2 - x);
        const side = (s: 1 | -1) => {
          const q = (x: number, yy: number) => `${f1(half(s, x))} ${f1(yy)}`;
          return [
            // Del sacro sube hacia fuera hasta la cresta (el punto más alto, en el tercio exterior) y baja al acetábulo.
            `C${q(cx - 7, p - 5)} ${q(lh - 1, p - 16 + pw)} ${q(lh - 7 - pw, p - 13 + pw)}`,
            `C${q(lh - 12 - pw, p - 11 + pw)} ${q(lh - 10 - pw, p - 1)} ${q(lh - 5 - pw * 0.5, p + 4)}`,
            `C${q(lh - 4, p + 6)} ${q(lh - 3, p + 7)} ${q(lh - 3, p + 8)}`,
            `C${q(lh - 1, p + 11)} ${q(lh, p + 14)} ${q(lh + 2, p + 17)}`,
            `C${q(lh + 4, p + 21)} ${q(cx - 6, p + 22)} ${q(cx - 3, p + 20)}`,
          ];
        };
        const left = side(1);
        // El lado derecho se recorre al revés: se pinta como otro contorno que empieza en el mismo sitio.
        const right = side(-1);
        const rx = 9 + pw * 0.6;
        const ox = 6.5 + pw * 0.6;
        const hole = (hx: number, hyy: number, a: number, b: number) => `M${f1(hx - a)} ${f1(hyy)} a${a} ${b} 0 1 0 ${a * 2} 0 a${a} ${b} 0 1 0 ${-a * 2} 0 Z`;
        const d = [
          `M${cx - 4} ${p - 3} ${left.join(" ")} L${cx} ${p + 17.5} L${cx} ${p - 4} Z`,
          `M${cx + 4} ${p - 3} ${right.join(" ")} L${cx} ${p + 17.5} L${cx} ${p - 4} Z`,
          hole(cx, p + 5, rx, 5.5),
          hole(cx - ox, p + 15, 3, 3.2),
          hole(cx + ox, p + 15, 3, 3.2),
        ].join(" ");
        return (
          <>
            <path className="grav-pelvis" fillRule="evenodd" d={d} />
            <ellipse className="grav-socket grav-obturator" cx={cx - ox} cy={p + 15} rx="3" ry="3.2" />
            <ellipse className="grav-socket grav-obturator" cx={cx + ox} cy={p + 15} rx="3" ry="3.2" />
            <ellipse className="grav-inlet" cx={cx} cy={p + 5} rx={rx} ry="5.5" />
            <path className="grav-sacrum" d={`M${cx - 4.5} ${p - 5} L${cx + 4.5} ${p - 5} L${cx + 1.2} ${p + 8} L${cx - 1.2} ${p + 8} Z`} />
          </>
        );
      })()}
      {/* Brazos: húmero; radio y cúbito; manos. */}
      <path className="grav-longbone" d={bonePath([ls + 1, y.shoulder + 1], [le, y.elbow], 2.1, 1.9)} />
      <path className="grav-longbone" d={bonePath([rs - 1, y.shoulder + 1], [re, y.elbow], 2.1, 1.9)} />
      <path className="grav-longbone" d={bonePath([le - 1.7, y.elbow + 1], [lw - 1.7, y.wrist], 1, 1.8)} />
      <path className="grav-longbone" d={bonePath([le + 1.7, y.elbow + 1], [lw + 1.9, y.wrist], 1, 1.8)} />
      <path className="grav-longbone" d={bonePath([re - 1.7, y.elbow + 1], [rw - 1.9, y.wrist], 1, 1.8)} />
      <path className="grav-longbone" d={bonePath([re + 1.7, y.elbow + 1], [rw + 1.7, y.wrist], 1, 1.8)} />
      <Fan at={[lw, y.wrist + 2]} toward={[lw - 1, y.wrist + 20]} spread={0.9} length={16} rays={5} />
      <Fan at={[rw, y.wrist + 2]} toward={[rw + 1, y.wrist + 20]} spread={0.9} length={16} rays={5} />
      {/* Piernas: fémur con cuello; rótula; tibia y peroné; pies. */}
      <path className="grav-longbone" d={bonePath([lh, y.hip], [lk, y.knee], 2.4, 2)} />
      <path className="grav-longbone" d={bonePath([rh, y.hip], [rk, y.knee], 2.4, 2)} />
      <path className="grav-longbone" d={bonePath([lk + 0.5, y.knee + 3], [la + 0.5, y.ankle], 1.8, 1.9)} />
      <path className="grav-longbone" d={bonePath([rk - 0.5, y.knee + 3], [ra - 0.5, y.ankle], 1.8, 1.9)} />
      <path className="grav-longbone thin" d={bonePath([lk - 4, y.knee + 5], [la - 3.5, y.ankle - 2], 0.6, 1.8)} />
      <path className="grav-longbone thin" d={bonePath([rk + 4, y.knee + 5], [ra + 3.5, y.ankle - 2], 0.6, 1.8)} />
      {/* Carpo y tarso: el bloque de huesecillos de la muñeca y el del tobillo con el talón, de donde salen los dedos. */}
      <ellipse className="grav-joint" cx={lw} cy={y.wrist + 2} rx="2.6" ry="1.7" />
      <ellipse className="grav-joint" cx={rw} cy={y.wrist + 2} rx="2.6" ry="1.7" />
      <ellipse className="grav-joint" cx={la} cy={y.ankle + 3} rx="3" ry="2.3" />
      <ellipse className="grav-joint" cx={ra} cy={y.ankle + 3} rx="3" ry="2.3" />
      {/* Articulaciones: cabeza del fémur hacia la pelvis con su trocánter, y cabeza del húmero en el hombro. */}
      <circle className="grav-joint" cx={lh + 3.5} cy={y.hip - 3} r="3.3" />
      <circle className="grav-joint" cx={rh - 3.5} cy={y.hip - 3} r="3.3" />
      <circle className="grav-joint" cx={lh - 3} cy={y.hip + 2} r="2.3" />
      <circle className="grav-joint" cx={rh + 3} cy={y.hip + 2} r="2.3" />
      <circle className="grav-joint" cx={ls + 2} cy={y.shoulder + 1.5} r="3.2" />
      <circle className="grav-joint" cx={rs - 2} cy={y.shoulder + 1.5} r="3.2" />
      <ellipse className="grav-patella" cx={lk} cy={y.knee - 1} rx="3.2" ry="3.8" />
      <ellipse className="grav-patella" cx={rk} cy={y.knee - 1} rx="3.2" ry="3.8" />
      <Fan at={[la, y.ankle + 2]} toward={[la - 4, y.ankle + 18]} spread={0.9} length={16} rays={5} />
      <Fan at={[ra, y.ankle + 2]} toward={[ra + 4, y.ankle + 18]} spread={0.9} length={16} rays={5} />
      {marks.includes("lumbar") && <circle className="grav-site" cx={cx} cy={y.pelvis - 14} r="6" />}
      {marks.includes("hip") && (
        <>
          <circle className="grav-site" cx={lh} cy={y.hip + 2} r="5.5" />
          <circle className="grav-site" cx={rh} cy={y.hip + 2} r="5.5" />
        </>
      )}
    </svg>
  );
}

/**
 * Las fibras del estilo «músculo» (maqueta «Salud gravitacional», 2026-11-15): los surcos que separan
 * los grandes grupos (pectoral, deltoides, abdominales, oblicuos, bíceps, cuádriceps, sartorio,
 * gemelos) y un brillo de relieve, encima del cuerpo recoloreado. Adorno: no dibuja ninguna medida.
 */
export function BodyMuscleArt({ figure }: { figure: "male" | "female" }) {
  const f = BODY_FRAMES[figure];
  const cx = f.head[0];
  const { y } = f;
  const [ls, rs] = f.shoulders;
  const [le, re] = f.elbows;
  const [lw, rw] = f.wrists;
  const [lh, rh] = f.hips;
  const [lk, rk] = f.knees;
  const [la, ra] = f.ankles;
  const chest = y.shoulder + 22;
  const waist = y.pelvis - 2;
  const half = (rs - ls) / 2;
  const sides = [-1, 1] as const;
  return (
    <svg className="grav-art grav-muscles" viewBox="0 0 152 310" aria-hidden="true">
      {/* La melena del avatar femenino no es músculo: va oscura, con la cara libre (medida a ojo sobre el render). */}
      {figure === "female" && (
        <path
          className="grav-hair"
          fillRule="evenodd"
          d="M75 5 C61 5 54 16 55 31 C55 43 56 52 57 60 L64 60 C64 54 65 50 66 47 L84 47 C85 50 86 54 86 60 L94 60 C95 51 96 42 95 31 C96 16 89 5 75 5 Z M75 15 a10 16 0 1 0 0.1 0 Z"
        />
      )}
      {figure === "female" && (
        <g className="grav-hair-strands">
          {[-14, -9, -4, 4, 9, 14].map((o) => (
            <path key={o} d={`M${75 + o * 0.35} 7 C${75 + o * 0.9} 12 ${75 + o * 1.25} 30 ${75 + o * 1.3 - Math.sign(o) * 1} 58`} />
          ))}
          <path className="grav-hair-sheen" d="M66 9 Q71 6 78 7" />
        </g>
      )}
      <g className="grav-groove">
        {/* Línea alba y abdominales. */}
        <path d={`M${cx} ${y.shoulder + 4} L${cx} ${waist + 6}`} />
        {/* Cuello: los esternocleidomastoideos en V hasta el esternón y el borde del trapecio hacia el hombro. */}
        <path d={`M${cx - 6.5} ${f.head[1] + 13} L${cx - 1.5} ${y.shoulder + 2} M${cx + 6.5} ${f.head[1] + 13} L${cx + 1.5} ${y.shoulder + 2}`} />
        <path className="fine" d={`M${cx - 7} ${f.head[1] + 16} Q${cx - 14} ${y.shoulder - 6} ${ls + 6} ${y.shoulder - 2} M${cx + 7} ${f.head[1] + 16} Q${cx + 14} ${y.shoulder - 6} ${rs - 6} ${y.shoulder - 2}`} />
        {/* Musculatura de la cara: orbiculares de ojos y boca, y maseteros. */}
        <ellipse className="grav-face" cx={cx - 4.5} cy={f.head[1] - 1} rx="3.2" ry="2.4" />
        <ellipse className="grav-face" cx={cx + 4.5} cy={f.head[1] - 1} rx="3.2" ry="2.4" />
        <ellipse className="grav-face" cx={cx} cy={f.head[1] + 9} rx="3.4" ry="1.8" />
        <path className="grav-face" d={`M${cx - 8.5} ${f.head[1] + 2} Q${cx - 8} ${f.head[1] + 9} ${cx - 4.5} ${f.head[1] + 13} M${cx + 8.5} ${f.head[1] + 2} Q${cx + 8} ${f.head[1] + 9} ${cx + 4.5} ${f.head[1] + 13}`} />
        <path className="grav-face" d={`M${cx - 7} ${f.head[1] - 9} Q${cx} ${f.head[1] - 12} ${cx + 7} ${f.head[1] - 9} M${cx} ${f.head[1] - 14} L${cx} ${f.head[1] - 5}`} />

        {sides.map((s) => {
          const sh = s < 0 ? ls : rs;
          const el = s < 0 ? le : re;
          const wr = s < 0 ? lw : rw;
          const hp = s < 0 ? lh : rh;
          const kn = s < 0 ? lk : rk;
          const an = s < 0 ? la : ra;
          return (
            <g key={s}>
              {/* Pectoral: borde inferior y fibras en abanico hacia el hombro. */}
              {figure === "female" ? (
                // En la mujer, el borde inferior del pecho en lugar del surco del pectoral.
                <path d={`M${f1(cx + s * 2)} ${chest - 1} C${f1(cx + s * 3)} ${chest + 7} ${f1(cx + s * half * 0.55)} ${chest + 8} ${f1(cx + s * half * 0.68)} ${chest - 2}`} />
              ) : (
                <path d={`M${cx} ${y.shoulder + 6} C${cx} ${chest + 6} ${f1(cx + s * half * 0.62)} ${chest + 9} ${f1(sh - s * 7)} ${y.shoulder + 16}`} />
              )}
              {(figure === "female" ? [0.3] : [0.3, 0.55, 0.8]).map((t) => (
                <path key={t} className="fine" d={`M${cx + s * 1.5} ${f1(y.shoulder + 5 + t * 18)} Q${f1(cx + s * half * 0.45)} ${f1(y.shoulder + 6 + t * 14)} ${f1(sh - s * 7)} ${y.shoulder + 13}`} />
              ))}
              {/* Deltoides. */}
              <path d={`M${f1(sh - s * 6)} ${y.shoulder + 1} Q${f1(sh + s * 3)} ${y.shoulder + 4} ${f1(sh + s * 0.5)} ${y.shoulder + 22}`} />
              {/* Serrato y oblicuo. */}
              {[0, 1, 2].map((i) => (
                <path key={i} className="fine" d={`M${f1(cx + s * half * 0.62)} ${chest + 4 + i * 5} l${s * 5} 3`} />
              ))}
              <path d={`M${f1(cx + s * half * 0.6)} ${chest + 6} Q${f1(cx + s * half * 0.62)} ${waist} ${f1(cx + s * 10)} ${waist + 12}`} />
              {/* Bíceps y separación del antebrazo. */}
              <path d={`M${f1(sh - s * 1)} ${y.shoulder + 22} Q${f1((sh + el) / 2 - s * 2.5)} ${(y.shoulder + y.elbow) / 2} ${el} ${y.elbow - 2}`} />
              <path className="fine" d={`M${el} ${y.elbow + 2} Q${f1((el + wr) / 2 + s * 1.2)} ${(y.elbow + y.wrist) / 2} ${wr} ${y.wrist - 4}`} />
              {/* Inguinal, sartorio y cuádriceps (vasto lateral, recto y medial). */}
              <path d={`M${f1(hp + s * 6)} ${y.pelvis - 2} Q${f1(cx + s * 5)} ${y.pelvis + 12} ${cx + s * 2} ${y.pelvis + 22}`} />
              <path d={`M${f1(hp + s * 5)} ${y.hip - 2} C${f1(hp)} ${y.hip + 20} ${f1(kn - s * 7)} ${y.knee - 30} ${f1(kn - s * 5)} ${y.knee - 4}`} />
              <path className="fine" d={`M${f1(hp + s * 1)} ${y.hip + 6} Q${f1(hp + s * 2.5)} ${(y.hip + y.knee) / 2} ${f1(kn + s * 1.5)} ${y.knee - 8}`} />
              <path d={`M${f1(kn - s * 6)} ${y.knee - 14} Q${f1(kn - s * 3)} ${y.knee - 4} ${f1(kn)} ${y.knee - 4}`} />
              <path d={`M${f1(kn + s * 6)} ${y.knee - 12} Q${f1(kn + s * 4)} ${y.knee - 4} ${f1(kn)} ${y.knee - 4}`} />
              {/* Rodilla, tibial y gemelos. */}
              <ellipse className="fine" cx={kn} cy={y.knee + 1} rx="3.5" ry="4" />
              <path d={`M${f1(kn + s * 4)} ${y.knee + 8} Q${f1(kn + s * 6.5)} ${y.knee + 26} ${f1(an + s * 2.5)} ${y.ankle - 22}`} />
              <path className="fine" d={`M${f1(kn - s * 1)} ${y.knee + 8} L${f1(an - s * 0.5)} ${y.ankle - 6}`} />
            </g>
          );
        })}
      </g>
      {/* Fibras: estrías finas que siguen la dirección de cada vientre muscular. */}
      <g className="grav-fibers">
        {sides.flatMap((s) => {
          const sh = s < 0 ? ls : rs;
          const el = s < 0 ? le : re;
          const hp = s < 0 ? lh : rh;
          const kn = s < 0 ? lk : rk;
          const an = s < 0 ? la : ra;
          const quad = [-3, -1, 1, 3].map((o) => `M${f1(hp + s * 2 + o)} ${y.hip + 4} Q${f1((hp + kn) / 2 + o * 1.2)} ${(y.hip + y.knee) / 2} ${f1(kn + o * 0.6)} ${y.knee - 9}`);
          const bicep = [-1.2, 0, 1.2].map((o) => `M${f1(sh + o)} ${y.shoulder + 14} Q${f1((sh + el) / 2 + o - s * 1.5)} ${(y.shoulder + y.elbow) / 2} ${f1(el + o * 0.5)} ${y.elbow - 4}`);
          const calf = [-1.5, 0, 1.5].map((o) => `M${f1(kn + s * 2 + o)} ${y.knee + 10} Q${f1(kn + s * 4 + o)} ${y.knee + 24} ${f1(an + s * 1.5 + o * 0.5)} ${y.ankle - 26}`);
          const delt = [-2, 0, 2].map((o) => `M${f1(sh - s * 3 + o)} ${y.shoulder + 2} L${f1(sh + o * 0.4)} ${y.shoulder + 18}`);
          return [...quad, ...bicep, ...calf, ...delt].map((d) => <path key={`${s}${d}`} d={d} />);
        })}
      </g>
      {/* Tendones y aponeurosis, nacarados como en la lámina de la maqueta. */}
      <g className="grav-tendon">
        {/* Intersecciones tendinosas del recto abdominal, blancas como en la maqueta. */}
        {[0, 1, 2, 3].map((i) => {
          const yy = chest + 8 + i * ((waist - chest - 8) / 4);
          return <path key={`abs${i}`} d={`M${cx - 7} ${f1(yy)} Q${cx - 3.5} ${f1(yy + 1.4)} ${cx} ${f1(yy + 0.6)} Q${cx + 3.5} ${f1(yy + 1.4)} ${cx + 7} ${f1(yy)}`} />;
        })}
        <path className="wide" d={`M${cx} ${y.shoulder + 6} L${cx} ${waist + 6}`} />
        {/* Líneas semilunares: el borde blanco a cada lado del recto abdominal, como en la lámina. */}
        <path d={`M${cx - 8.5} ${chest + 7} Q${cx - 9.5} ${waist - 8} ${cx - 5.5} ${waist + 7} M${cx + 8.5} ${chest + 7} Q${cx + 9.5} ${waist - 8} ${cx + 5.5} ${waist + 7}`} />
        <path d={`M${f1(lh - 6)} ${y.pelvis - 6} Q${cx - 6} ${y.pelvis + 8} ${cx} ${y.pelvis + 16} Q${cx + 6} ${y.pelvis + 8} ${f1(rh + 6)} ${y.pelvis - 6}`} />
        {sides.flatMap((s) => {
          const wr = s < 0 ? lw : rw;
          // La mano de la figura femenina cae algo más adentro que su muñeca medida: sin esto, los tendones se salen.
          const hand = figure === "female" ? 2.5 : 0.5;
          const kn = s < 0 ? lk : rk;
          const an = s < 0 ? la : ra;
          return [
            // Tendón del cuádriceps, rótula y cresta de la tibia hasta el tobillo: la línea blanca de la pierna en la lámina.
            `M${f1(kn)} ${y.knee - 12} L${f1(kn)} ${y.knee + 6}`,
            // La cresta de la tibia, fina y con la curva de la pierna («M » con espacio: el CSS la afina).
            `M ${f1(kn)} ${y.knee + 8} Q${f1((kn + an) / 2 + s * 1.8)} ${(y.knee + y.ankle) / 2} ${f1(an)} ${y.ankle - 10}`,
            `M${f1(kn - 4)} ${y.knee} a4 5.5 0 1 0 8 0 a4 5.5 0 1 0 -8 0 Z`,
            `M${f1((s < 0 ? ls : rs) - s * 4)} ${y.shoulder} Q${f1(cx + s * 8)} ${y.shoulder - 3} ${f1(cx + s * 2)} ${y.shoulder + 3}`,
            `M${f1((s < 0 ? le : re) - 2)} ${y.elbow - 1} q2 2 4 0`,
            // Surco entre el deltoides y el pectoral, y la inserción del deltoides en el brazo (finos).
            `M ${f1((s < 0 ? ls : rs) - s * 9)} ${y.shoulder + 1} Q${f1((s < 0 ? ls : rs) - s * 7.5)} ${y.shoulder + 10} ${f1((s < 0 ? ls : rs) - s * 5)} ${y.shoulder + 19}`,
            `M ${f1((s < 0 ? ls : rs) + s * 1.5)} ${y.shoulder + 20} q${f1(-s * 2)} 3 ${f1(-s * 4)} 1`,
            `M${f1(kn - 3)} ${y.knee - 4} Q${f1(kn)} ${y.knee + 2} ${f1(kn + 3)} ${y.knee - 4}`,
            `M ${f1(wr - 1)} ${y.wrist - 8} L${f1(wr - 0.5)} ${y.wrist}`,
            `M ${f1(wr + 1)} ${y.wrist - 8} L${f1(wr + 1.2)} ${y.wrist}`,
            // Muñeca y dorso de la mano: banda y tendones de los dedos, blancos como en la lámina.
            `M${f1(wr - s * hand - 3)} ${y.wrist + 1} q3 2.2 6 0`,
            ...[-2, -0.7, 0.7, 2].map((o) => `M${f1(wr - s * hand + o * 0.5)} ${y.wrist + 3} L${f1(wr - s * hand + o)} ${y.wrist + 12}`),
            `M ${f1(an - 1)} ${y.ankle - 14} L${f1(an)} ${y.ankle - 1}`,
            `M ${f1(an + s * 2)} ${y.ankle - 12} L${f1(an + s * 2.5)} ${y.ankle}`,
          ].map((d) => <path key={`${s}${d}`} d={d} />);
        })}
      </g>
      {/* Volumen del pecho: luz arriba y sombra en el borde inferior de cada pectoral (degradados, sin filtros). */}
      <defs>
        <radialGradient id="grav-pec-light" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0" className="grav-pec-light-0" />
          <stop offset="1" className="grav-pec-light-1" />
        </radialGradient>
        <radialGradient id="grav-pec-shadow" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0" className="grav-pec-shadow-0" />
          <stop offset="1" className="grav-pec-shadow-1" />
        </radialGradient>
      </defs>
      {sides.map((s) => (
        <g key={`pec${s}`}>
          <ellipse fill="url(#grav-pec-shadow)" cx={f1(cx + s * half * 0.36)} cy={chest + 5} rx={f1(half * 0.42)} ry="4.5" />
          <ellipse fill="url(#grav-pec-light)" cx={f1(cx + s * half * 0.32)} cy={y.shoulder + 11} rx={f1(half * 0.36)} ry="6" />
        </g>
      ))}
      <g className="grav-sheen">
        {sides.map((s) => (
          <g key={s}>
            <ellipse cx={f1(cx + s * half * 0.35)} cy={y.shoulder + 12} rx="6" ry="3" />
            <ellipse cx={f1((s < 0 ? ls : rs) - s * 1)} cy={y.shoulder + 8} rx="2.5" ry="5" />
            <ellipse cx={f1(((s < 0 ? lh : rh) + (s < 0 ? lk : rk)) / 2 - s * 1)} cy={(y.hip + y.knee) / 2 - 6} rx="2.5" ry="12" />
          </g>
        ))}
      </g>
    </svg>
  );
}

/** Una rama de vaso con ramitas laterales cada cierto trecho, deterministas (sin azar). */
function vesselTree(points: readonly Point[], twigs: number, reach: number, seed: number): string[] {
  // El tronco, curvo: por los puntos medios con curvas cuadráticas y una leve ondulación lateral (los vasos
  // de la maqueta serpentean siguiendo los músculos; en recto parecían varillas).
  const wave = (k: number) => Math.sin((k + 1) * 1.7 + seed) * 1.6;
  const pts = points.map((q, k) => (k === 0 || k === points.length - 1 ? q : ([q[0] + wave(k), q[1]] as Point)));
  // «M » con espacio marca el tronco (las ramitas empiezan por «M» pegado): quien pinta lo distingue así.
  let trunk = `M ${f1(pts[0]![0])} ${f1(pts[0]![1])}`;
  for (let k = 1; k < pts.length; k += 1) {
    const a = pts[k - 1]!;
    const b = pts[k]!;
    const ctrl = along(a, b, 0.5, wave(k + 3));
    trunk += ` Q${f1(ctrl[0])} ${f1(ctrl[1])} ${f1(b[0])} ${f1(b[1])}`;
  }
  const out: string[] = [trunk];
  for (let s = 0; s < points.length - 1; s += 1) {
    const a = points[s]!;
    const b = points[s + 1]!;
    for (let k = 1; k <= twigs; k += 1) {
      const t = k / (twigs + 1);
      const side = (k + s + seed) % 2 === 0 ? 1 : -1;
      const len = reach * (0.6 + 0.4 * Math.abs(Math.sin((k + 1) * (s + 2) * (seed + 3))));
      const base = along(a, b, t);
      const tip = along(a, b, t + 0.18, side * len);
      const mid = along(a, b, t + 0.06, side * len * 0.5);
      out.push(`M${f1(base[0])} ${f1(base[1])} Q${f1(mid[0])} ${f1(mid[1])} ${f1(tip[0])} ${f1(tip[1])}`);
      const fork = along(base, tip, 0.6, side * len * 0.35);
      out.push(`M${f1(mid[0])} ${f1(mid[1])} Q${f1((mid[0] + fork[0]) / 2)} ${f1((mid[1] + fork[1]) / 2 + 1)} ${f1(fork[0])} ${f1(fork[1])}`);
    }
  }
  return out;
}

/**
 * Los vasos del estilo holograma (maqueta «Salud gravitacional», 2026-11-15): aorta con su cayado,
 * carótidas y red craneal, arterias y venas de brazos y piernas con ramitas, y el corazón, encima del
 * cuerpo recoloreado. Adorno: no dibuja ninguna medida.
 */
export function BodyVesselsArt({ figure }: { figure: "male" | "female" }) {
  const f = BODY_FRAMES[figure];
  const cx = f.head[0];
  const hy = f.head[1];
  const { y } = f;
  const heart: Point = [cx + 3, y.shoulder + 16];
  const arm = (left: boolean, o: number): Point[] => {
    const i = left ? 0 : 1;
    const s = left ? -1 : 1;
    return [
      // Del cayado sube en arco bajo la clavícula y baja por la axila (no una barra horizontal por el hombro).
      [cx + s * 4 + o, y.shoulder + 5],
      [cx + s * 14 + o, y.shoulder + 4],
      [f.shoulders[i] + o - s * 7, y.shoulder + 15],
      [f.elbows[i] + o, y.elbow],
      [f.wrists[i] + o, y.wrist],
      [f.wrists[i] + o + s * 0.5, y.wrist + 12],
    ];
  };
  const leg = (left: boolean, o: number): Point[] => {
    const i = left ? 0 : 1;
    return [
      [cx + o * 0.4, y.pelvis - 8],
      [f.hips[i] + o, y.hip + 2],
      [f.knees[i] + o, y.knee],
      [f.ankles[i] + o, y.ankle],
      [f.ankles[i] + o, y.ankle + 12],
    ];
  };
  const arteries = [
    ...vesselTree(arm(true, 0), 3, 4, 1),
    ...vesselTree(arm(false, 0), 3, 4, 2),
    ...vesselTree(leg(true, 0), 3, 5, 3),
    ...vesselTree(leg(false, 0), 3, 5, 4),
    ...vesselTree([[cx - 4, heart[1] - 14], [cx - 4, hy + 8], [cx - 6, hy - 2]], 2, 5, 6),
    ...vesselTree([[cx + 4, heart[1] - 14], [cx + 4, hy + 8], [cx + 6, hy - 2]], 2, 5, 7),
  ];
  // La aorta descendente, aparte: en la maqueta es el vaso más grueso, y se bifurca en la pelvis.
  const aorta = vesselTree([[cx - 2, heart[1] - 10], [cx - 1, y.pelvis - 8]], 6, 9, 5);
  const veins = [
    ...vesselTree(arm(true, -2.5), 2, 3, 8),
    ...vesselTree(arm(false, 2.5), 2, 3, 9),
    ...vesselTree(leg(true, -2.5), 2, 4, 10),
    ...vesselTree(leg(false, 2.5), 2, 4, 11),
    ...vesselTree([[cx + 3, y.pelvis - 8], [cx + 3, heart[1] + 4]], 4, 7, 12),
    ...vesselTree([[cx + 7, hy + 6], [cx + 6, heart[1] - 8]], 1, 4, 13),
    ...vesselTree([[cx - 7, hy + 6], [cx - 1, heart[1] - 8]], 1, 4, 14),
  ];
  // Red craneal, renales y mesentéricas, arcos palmares (arterias) y yugulares (venas): adorno.
  const head = [
    `M${cx - 4} ${hy + 6} Q${cx - 11} ${hy - 2} ${cx - 6} ${hy - 12}`,
    `M${cx + 4} ${hy + 6} Q${cx + 11} ${hy - 2} ${cx + 6} ${hy - 12}`,
    `M${cx - 6} ${hy - 12} Q${cx} ${hy - 17} ${cx + 6} ${hy - 12}`,
    `M${cx - 8} ${hy - 4} q4 -2 6 -8`,
    `M${cx + 8} ${hy - 4} q-4 -2 -6 -8`,
    `M${cx} ${hy - 15} q-2 6 0 10`,
  ];
  const trunk = [0.42, 0.52, 0.62].flatMap((t, i) => {
    const yy = heart[1] + t * (y.pelvis - heart[1]);
    const reach = i === 0 ? 13 : 9;
    return [
      `M${cx - 2} ${f1(yy)} Q${f1(cx - reach * 0.6)} ${f1(yy - 2)} ${f1(cx - reach)} ${f1(yy + 1)} M${f1(cx - reach * 0.7)} ${f1(yy - 1)} l-2 4`,
      `M${cx - 2} ${f1(yy)} Q${f1(cx + reach * 0.6)} ${f1(yy - 2)} ${f1(cx + reach)} ${f1(yy + 1)} M${f1(cx + reach * 0.7)} ${f1(yy - 1)} l2 4`,
    ];
  });
  const hands = ([0, 1] as const).map((i) => {
    const wx = f.wrists[i];
    return `M${wx - 3} ${y.wrist + 8} Q${wx} ${y.wrist + 13} ${wx + 3} ${y.wrist + 8} M${wx - 2} ${y.wrist + 10} l-1 6 M${wx} ${y.wrist + 11} l0 7 M${wx + 2} ${y.wrist + 10} l1 6`;
  });
  // Arcos y ramitas hasta los dedos de manos y pies, como en la maqueta (los vasos no se cortan en la muñeca).
  const digits = ([0, 1] as const).flatMap((i) => {
    const wx = f.wrists[i];
    const ax = f.ankles[i];
    const side = i === 0 ? -1 : 1;
    const hand = [-2.4, -1.2, 0, 1.2, 2.4].map((o) => `M${f1(wx + o * 0.4)} ${y.wrist + 12} q${f1(o * 0.5)} 5 ${f1(o * 0.9)} 10`);
    const foot = [-2, -0.5, 1, 2.5].map((o) => `M${f1(ax)} ${y.ankle + 6} q${f1(side * 2 + o * 0.6)} 4 ${f1(side * 3 + o * 1.3)} 9`);
    return [...hand, ...foot];
  });
  const jugulars = [`M${cx - 6} ${hy + 8} Q${cx - 7} ${hy + 20} ${cx - 3} ${heart[1] - 12}`, `M${cx + 8} ${hy + 8} Q${cx + 9} ${hy + 20} ${cx + 5} ${heart[1] - 12}`];
  return (
    <svg className="grav-art grav-vessels" viewBox="0 0 152 310" aria-hidden="true">
      <g className="grav-vein">
        {veins.map((d, i) => (
          <path key={i} d={d} className={d.startsWith("M ") ? undefined : "fine"} />
        ))}
      </g>
      {/* Órganos del abdomen apenas esbozados, como en la maqueta: riñones e intestino. Adorno. */}
      <g className="grav-organ">
        <path d={`M${cx - 9} ${y.pelvis - 30} c-5 1 -6 9 -1 11 c2 1 3 -1 2 -3 c-1 -2 1 -4 2 -4 c1 -2 0 -4 -3 -4 Z`} />
        <path d={`M${cx + 9} ${y.pelvis - 30} c5 1 6 9 1 11 c-2 1 -3 -1 -2 -3 c1 -2 -1 -4 -2 -4 c-1 -2 0 -4 3 -4 Z`} />
        <path d={`M${cx - 9} ${y.pelvis - 14} q0 -6 9 -6 q9 0 9 6 q0 6 -9 7 q-9 -1 -9 -7 Z`} />
        <path d={`M${cx - 6} ${y.pelvis - 15} q3 -3 6 0 q3 3 6 0 M${cx - 6} ${y.pelvis - 11} q3 3 6 0 q3 -3 6 0`} />
      </g>
      {/* Un tercer vaso por pierna y por brazo, anaranjado, como los haces de la maqueta (varios vasos en paralelo). */}
      {/* Intercostales: arcos anaranjados que salen de la aorta siguiendo las costillas, como en el pecho de la maqueta. */}
      <g className="grav-lung grav-intercostal">
        {[0, 1, 2, 3, 4, 5].flatMap((i) => {
          const yy = y.shoulder + 9 + i * 5.5;
          const reach = 17 + Math.sin(((i + 1) / 7) * Math.PI) * 5;
          return ([-1, 1] as const).map((side) => (
            <path key={`${i}${side}`} className="fine" d={`M${cx + side * 2} ${f1(yy)} Q${f1(cx + side * reach * 0.6)} ${f1(yy - 2.5)} ${f1(cx + side * reach)} ${f1(yy + 5)}`} />
          ));
        })}
      </g>
      <g className="grav-lung grav-deep">
        {[...vesselTree(leg(true, 4), 2, 3, 21), ...vesselTree(leg(false, -4), 2, 3, 22), ...vesselTree(arm(true, 2.5), 1, 2.5, 23), ...vesselTree(arm(false, -2.5), 1, 2.5, 24)].map((d, i) => (
          <path key={i} d={d} className={d.startsWith("M ") ? undefined : "fine"} />
        ))}
      </g>
      <g className="grav-lung">
        {([-1, 1] as const).flatMap((side) =>
          vesselTree(
            [
              [cx + side * 6, heart[1] - 10],
              [cx + side * 18, y.shoulder + 12],
              [cx + side * 22, y.shoulder + 26],
              [cx + side * 19, y.shoulder + 40],
            ],
            4,
            7,
            side < 0 ? 15 : 16,
          ),
        ).map((d, i) => (
          <path key={i} d={d} className={d.startsWith("M ") ? undefined : "fine"} />
        ))}
      </g>
      <g className="grav-vein">
        {jugulars.map((d) => (
          <path key={d} d={d} />
        ))}
      </g>
      <g className="grav-artery">
        {[...head, ...trunk, ...hands, ...digits].map((d) => (
          <path key={d} d={d} className="fine" />
        ))}
        <path d={`M${heart[0] - 2} ${heart[1] - 6} C${cx - 10} ${heart[1] - 26} ${cx + 8} ${heart[1] - 26} ${cx - 2} ${heart[1] - 10}`} />
        {arteries.map((d, i) => (
          <path key={i} d={d} className={d.startsWith("M ") ? undefined : "fine"} />
        ))}
        {aorta.map((d, i) => (
          <path key={`a${i}`} d={d} className={d.startsWith("M ") ? "grav-trunk" : "fine"} />
        ))}
      </g>
      <g transform={`translate(${heart[0]} ${heart[1]}) scale(1.65) translate(${-heart[0]} ${-heart[1]})`}>
      <circle className="grav-heart-glow" cx={heart[0]} cy={heart[1]} r="12" />
      {/* Corazón de frente, inclinado a la izquierda del tripulante: ventrículos con su surco, aurícula
          derecha, cayado de la aorta (rojo) y tronco pulmonar (azul), y las coronarias. Adorno. */}
      <path className="grav-pulmonary" d={`M${heart[0] + 1} ${heart[1] - 5} C${heart[0] + 2} ${heart[1] - 11} ${heart[0] + 6} ${heart[1] - 12} ${heart[0] + 9} ${heart[1] - 10}`} />
      <path className="grav-aorta" d={`M${heart[0] - 2} ${heart[1] - 5} C${heart[0] - 3} ${heart[1] - 14} ${heart[0] + 5} ${heart[1] - 17} ${heart[0] + 6} ${heart[1] - 12} M${heart[0] - 1} ${heart[1] - 14} l-1 -4 M${heart[0] + 2} ${heart[1] - 15.5} l0 -4 M${heart[0] + 4.5} ${heart[1] - 15} l1 -3.5`} />
      <path className="grav-vena-cava" d={`M${heart[0] - 5} ${heart[1] - 14} L${heart[0] - 5} ${heart[1] - 3}`} />
      <path
        className="grav-heart"
        d={`M${heart[0] - 6} ${heart[1] - 4} C${heart[0] - 8} ${heart[1] - 1} ${heart[0] - 7} ${heart[1] + 5} ${heart[0] - 2} ${heart[1] + 8} C${heart[0] + 1} ${heart[1] + 10} ${heart[0] + 5} ${heart[1] + 11} ${heart[0] + 7} ${heart[1] + 10} C${heart[0] + 9} ${heart[1] + 6} ${heart[0] + 9} ${heart[1]} ${heart[0] + 7} ${heart[1] - 4} C${heart[0] + 5} ${heart[1] - 7} ${heart[0] + 1} ${heart[1] - 7} ${heart[0] - 1} ${heart[1] - 5} C${heart[0] - 3} ${heart[1] - 7} ${heart[0] - 5} ${heart[1] - 6} ${heart[0] - 6} ${heart[1] - 4} Z`}
      />
      {/* Brillo del corazón: en la maqueta es un volumen lustroso, no una forma plana. */}
      <ellipse className="grav-heart-shine" cx={heart[0] + 3.5} cy={heart[1] + 1} rx="1.6" ry="3.4" transform={`rotate(-24 ${heart[0] + 3.5} ${heart[1] + 1})`} />
      <ellipse className="grav-heart-shade" cx={heart[0] - 1} cy={heart[1] + 5.5} rx="4.5" ry="2.2" transform={`rotate(28 ${heart[0] - 1} ${heart[1] + 5.5})`} />
      <path className="grav-atrium" d={`M${heart[0] - 6} ${heart[1] - 4} C${heart[0] - 8.5} ${heart[1] - 2} ${heart[0] - 8} ${heart[1] + 3} ${heart[0] - 5} ${heart[1] + 3} C${heart[0] - 4} ${heart[1]} ${heart[0] - 4} ${heart[1] - 3} ${heart[0] - 6} ${heart[1] - 4} Z`} />
      <path className="grav-heart-line" d={`M${heart[0]} ${heart[1] - 5} C${heart[0] + 1} ${heart[1]} ${heart[0] + 3} ${heart[1] + 5} ${heart[0] + 6} ${heart[1] + 9}`} />
      <path className="grav-coronary" d={`M${heart[0] - 1} ${heart[1] - 4} C${heart[0] - 4} ${heart[1]} ${heart[0] - 4} ${heart[1] + 4} ${heart[0] - 1} ${heart[1] + 7} M${heart[0] + 2} ${heart[1] - 4} C${heart[0] + 5} ${heart[1] - 2} ${heart[0] + 7} ${heart[1] + 1} ${heart[0] + 8} ${heart[1] + 4} M${heart[0] + 1} ${heart[1] + 1} l-2.5 2 M${heart[0] + 2.5} ${heart[1] + 4} l2.5 1.5`} />
      </g>
    </svg>
  );
}

/**
 * La estación de la pestaña «Entorno» (2026-11-15): una estación con su viga y sus cuatro pares de alas solares, como la foto de la maqueta. Adorno
 * (§2.5): los colores salen de las variables de la paleta y no dicen nada.
 */
export function IssArt() {
  const wings = [-62, -40, 40, 62];
  return (
    <svg className="env-iss" viewBox="-90 -60 180 120" preserveAspectRatio="xMidYMid meet">
      <g transform="rotate(-18)">
        <rect className="env-iss-truss" x="-80" y="-2.5" width="160" height="5" rx="1" />
        {wings.map((x) => (
          <g key={x}>
            <rect className="env-iss-wing" x={x - 7} y="-46" width="14" height="40" />
            <rect className="env-iss-wing" x={x - 7} y="6" width="14" height="40" />
            {[-36, -26, -16, 16, 26, 36].map((y) => (
              <line key={y} className="env-iss-cell" x1={x - 7} x2={x + 7} y1={y} y2={y} />
            ))}
          </g>
        ))}
        <rect className="env-iss-module" x="-22" y="-7" width="44" height="14" rx="5" />
        <rect className="env-iss-module" x="-5" y="-24" width="10" height="48" rx="4" />
        <rect className="env-iss-radiator" x="-16" y="12" width="10" height="20" />
        <rect className="env-iss-radiator" x="6" y="-32" width="10" height="20" />
      </g>
    </svg>
  );
}
