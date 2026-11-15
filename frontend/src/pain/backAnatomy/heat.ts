import { type BackHeat, bilateralSpots } from "../backSkin";

/**
 * El calor de fondo de la espalda: los colores de cámara térmica que tendría el render de «Inicio»
 * visto por detrás, ENTRE los músculos. Sin corazón: detrás no hay nada que lo dibuje.
 *
 * Por qué es un fondo sencillo (Volumen 5, 2026-11-10). Antes este fichero era un mosaico de manchas,
 * una por músculo, porque la espalda no tenía otra forma de dar a cada músculo su tono. Ahora cada
 * músculo se pinta a sí mismo (`BackMuscle`, vientre templado y borde frío, en `torso.ts`, `arms.ts`
 * y `legs.ts`), y las manchas pequeñas solo competían con él: por debajo de un músculo no se ven, y
 * entre dos dibujaban «manchurrones» (Ellande: «no veo huesos definidos, solo veo manchurrones»). Lo
 * que queda aquí es lo que hace el frente entre sus músculos: un campo templado y casi liso que va de
 * caliente en el centro del tronco a frío en los miembros, con muy pocas manchas y todas anchas.
 *
 * El equilibrio verde/amarillo sale del frente a la misma altura, para que al girar el cuerpo el
 * color no salte. En el frente de «Inicio» el pecho y el abdomen son amarillos y amarillo verdoso
 * (0,6-0,75 de la rampa, sin contar el corazón), y el costado, verde (0,45-0,5). La espalda de antes
 * se quedaba en verde (0,5) salvo una franja entre las escápulas, y al girar parecía otro cuerpo, más
 * frío. Ahora:
 * - el centro de la espalda, de las escápulas a la cintura, amarillo verdoso (0,65-0,72), como el
 *   pecho; se enfría hacia los costados (0,45) como el del frente;
 * - la lumbar, amarillo verdoso algo más fresco (0,55), como el abdomen bajo;
 * - la franja de los hombros y el cuello, verde (0,45-0,5);
 * - los glúteos, cian-verde (0,35-0,4), entre la lumbar y el muslo, como la ingle del frente;
 * - muslos y piernas, el azul del frente (0,07-0,12);
 * - brazo: hombro verde (0,5), brazo 0,4, la veta templada del final del brazo hacia el codo (a
 *   1,1-1,2 m, donde la tiene el frente) y el antebrazo que se enfría hacia la mano azul;
 * - cabeza, el azul del frente.
 *
 * Niveles de la rampa (`THERMAL_RAMP`): 0,07 azul de las piernas del frente, 0,3 cian, 0,5 verde,
 * 0,65 amarillo verdoso, 0,75 amarillo, 0,85 naranja. Formato y escala en `backSkin.ts`; para verlo,
 * `npm run preview:back`.
 */
export const BACK_HEAT: BackHeat = {
  base: 0.07,
  spots: [
    // --- tronco ---
    // El campo del tronco: una mancha muy ancha, de los hombros a las caderas, que da el verde de
    // los costados; encima, el centro amarillo verdoso, más estrecho, como el pecho del frente.
    { at: [0, 1.22], radius: [0.25, 0.26], heat: 0.55 },
    { at: [0, 1.22], radius: [0.12, 0.2], heat: 0.14 },
    // La franja de los hombros, verde: sin ella el trapecio alto quedaba cian.
    { at: [0, 1.38], radius: [0.2, 0.06], heat: 0.12 },
    // Lumbar: amarillo verdoso algo más fresco que el centro, como el abdomen bajo.
    { at: [0, 1.0], radius: [0.12, 0.08], heat: 0.14 },
    // Cuello: templado por el trapecio, enfriándose hacia la nuca.
    { at: [0, 1.47], radius: [0.06, 0.05], heat: 0.18 },
    ...bilateralSpots([
      // Glúteos: cian-verde, entre la lumbar y el muslo.
      { at: [0.09, 0.87], radius: [0.09, 0.07], heat: 0.05 },
      // --- piernas ---
      // La espalda del muslo, apenas sobre el azul: el color lo ponen los isquiotibiales.
      { at: [0.11, 0.62], radius: [0.06, 0.22], heat: 0.04 },
      // --- brazos ---
      // Hombro y brazo: verde que se enfría hacia el codo, como en el frente.
      { at: [0.22, 1.33], radius: [0.05, 0.07], heat: 0.2 },
      { at: [0.25, 1.21], radius: [0.035, 0.09], heat: 0.1 },
      // La veta templada del final del brazo hacia el codo, como la del frente.
      { at: [0.262, 1.15], radius: [0.026, 0.06], heat: 0.3 },
      // Antebrazo: se enfría hacia la muñeca; la mano queda en el azul de la base.
      { at: [0.29, 1.0], radius: [0.03, 0.07], heat: 0.16 },
    ]),
  ],
};
