import { useEffect, useRef, useState } from "react";
import {
  AdditiveBlending,
  BufferAttribute,
  BufferGeometry,
  CanvasTexture,
  Color,
  DataTexture,
  EdgesGeometry,
  LineBasicMaterial,
  LinearFilter,
  LinearMipmapLinearFilter,
  LineSegments,
  Mesh,
  MeshBasicMaterial,
  PerspectiveCamera,
  PlaneGeometry,
  Raycaster,
  SRGBColorSpace,
  Scene,
  ShaderMaterial,
  Sprite,
  SpriteMaterial,
  type Texture,
  Vector2,
  Vector4,
  WebGLRenderer,
} from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

import { AvatarSwitch } from "../components/AvatarSwitch";
import { Command } from "../components/Command";
import { MarkOf } from "../components/Mark";
import { UNAVAILABLE_MARK } from "../lib/marks";
import { palette } from "../lib/palette";
import { type Avatar, useAvatar } from "../lib/avatar";
import { BODY, BODY_HEIGHT, isClick, surfaceOf, surfacePoint, toNormalized } from "./bodyModel";
import { feminizeSurface, hairSurface } from "./feminine";
import { cavityOf, fadeCavities, weldSurfaces } from "./cavity";
import { blendCrossings, creaseCavities, smoothstep } from "./crossing";
import { BACK_ART } from "./backAnatomy";
import { BACK_PROJECTION, backCoefficients, rasterizeBack } from "./backSkin";
import { blur, decodeBody, dilate, THERMAL_PROJECTION, thermalCoefficients } from "./thermalSkin";

type View = "front" | "back";

// Distancia de la camara al cuerpo: lo bastante lejos para verlo entero de pie.
const CAMERA_DISTANCE = 3.1;
// Un poco por debajo de la mitad del cuerpo y algo más lejos: así cabe también el anillo de luz
// del suelo, sin cortar la cabeza.
const TARGET_Y = BODY_HEIGHT / 2 - 0.03;
// Intervalo mínimo entre dos rayos del puntero, en ms: un fotograma a 60 Hz.
const HOVER_INTERVAL = 16;

// Surcos y crestas del cuerpo, y las normales con los cruces entre piezas fundidos (`crossing.ts`):
// el cuerpo es fijo, así que se calculan la primera vez que se monta el mapa y se reutilizan (como
// `surfaceOf` guarda cada zona). Uno por avatar (`lib/avatar.ts`): la variante femenina mueve los vértices
// (`feminine.ts`) y sus surcos y normales son los suyos.
const bodyShading = new Map<Avatar, { cavities: Float32Array[]; normals: Float32Array[] }>();

/**
 * Los colores de «Inicio» ya dilatados (`thermalSkin.ts`), una vez por sesión: el módulo de píxeles
 * (~1,5 MB) se pide la primera vez que se monta el mapa, perezoso, como en «Inicio». Mientras llega,
 * el cuerpo se pinta con el holograma azul de antes.
 */
type ThermalPixels = { sharp: Uint8Array; soft: Uint8Array; width: number; height: number };
const thermalPixels = new Map<Avatar, Promise<ThermalPixels>>();
/** Los píxeles del cuerpo 2D del mismo avatar: el femenino lleva la misma deformación que su 3D. */
function loadThermal(avatar: Avatar) {
  let pending = thermalPixels.get(avatar);
  if (pending === undefined) {
    const source =
      avatar === "female" ? import("../dashboard/referenceBodyFemale.generated") : import("../dashboard/referenceBody.generated");
    pending = source.then(({ BODY_ONE, BODY_W, BODY_H }) => {
      const { data, width, height } = decodeBody(BODY_ONE, BODY_W, BODY_H);
      const sharp = dilate(data, width, height, THERMAL_PROJECTION.inset);
      const soft = blur(sharp, width, height, THERMAL_PROJECTION.blurRadius);
      return { sharp, soft, width, height };
    });
    thermalPixels.set(avatar, pending);
    // Si falla (no debería: es un trozo del propio paquete), se puede reintentar en el montaje siguiente.
    pending.catch(() => {
      thermalPixels.delete(avatar);
    });
  }
  return pending;
}

/**
 * La textura trasera dibujada a mano (`backSkin.ts`), una vez por sesión. El dibujo pesa poco (va
 * en el paquete), pero rasterizarlo cuesta CPU: cuatro campos de líneas (contornos y trazos, surcos,
 * crestas y sombras de hueso) más el relleno de cada músculo, unos 120 ms en `back-preview.mjs`
 * (Node) con los primeros músculos («Volumen 1»). Se hace tras ceder el turno (`setTimeout`), para
 * que el mapa se monte y se pinte antes; mientras, la espalda lleva la copia borrosa del frente.
 */
let backPixels: Promise<Uint8Array> | null = null;
function loadBack() {
  backPixels ??= new Promise<void>((resolve) => setTimeout(resolve, 0)).then(() => rasterizeBack(BACK_ART));
  backPixels.catch(() => {
    backPixels = null;
  });
  return backPixels;
}

/**
 * Cuánta sombra de cavidades conserva cada punto: toda en el cuerpo y un 20 % en la cara, de la
 * barbilla a la frente (1,50-1,69 m) y por delante de la oreja (`fadeCavities`). La transición es
 * gradual, para que no se vea dónde empieza la cara, y depende solo de la posición, así que la junta
 * de la cara con el cuello o la cabeza recibe el mismo valor a los dos lados.
 *
 * Neutro 1 (2026-11-10, «la cara sigue viéndose rara»): con un 30 % la sombra oscurecía los lados
 * del mentón y el borde de la cuenca, y la cara de maniquí salía con perilla y ojos hundidos. La
 * forma ya la da el relieve y la luz; la sombra de cavidades solo la asienta.
 */
function faceCavityKeep(_x: number, y: number, z: number): number {
  const band = smoothstep(1.47, 1.51, y) * (1 - smoothstep(1.68, 1.72, y));
  return 1 - 0.8 * band * smoothstep(0.01, 0.05, z);
}

/**
 * Cuerpo en 3D donde se toca la zona que duele.
 *
 * Aspecto de holograma, como el cuerpo de «Inicio» (petición del usuario, 2026-11-09: «el cuerpo
 * puede ser más chulo»): un contorno luminoso donde la superficie se ve de canto (Fresnel), unas
 * líneas de barrido finas y quietas, un halo detrás y un anillo de luz en el suelo, sobre un fondo
 * azul marino que se aclara en el centro como el marco del cuerpo de «Inicio».
 *
 * **La piel lleva los colores de cámara térmica de «Inicio»** (decisión del usuario, 2026-11-10:
 * «Todo, colores incluidos»), proyectados de frente desde su imagen (`thermalSkin.ts`). Antes el
 * cuerpo se quedaba en la familia del azul de la paleta porque es un mando; ahora el adorno del
 * cuerpo de «Inicio» se extiende a este y lo declara el §2.5 de `compliance/hmi-state-of-the-art.md`.
 * El verde, el amarillo y el rojo del tórax son adorno y no dicen nada: la intensidad de una zona
 * se lee como cifra en la lista, no como color. Mientras llegan los píxeles (perezosos), el cuerpo
 * sale con el holograma azul de la paleta de antes.
 *
 * **Lo que es dato sigue siendo de la paleta y no se confunde con el adorno.** Una zona marcada se
 * pinta en verde de selección (F.5-2) liso, sin la textura, con el borde claro; y mientras haya
 * alguna marcada, el resto del cuerpo se destiñe y se apaga, así que sus verdes y amarillos de
 * adorno no compiten con ella. La zona bajo el puntero se aclara y se perfila con el verde de
 * cursor por encima de las juntas. Las juntas entre zonas casi no se ven en reposo (un cuerpo no
 * tiene costuras).
 *
 * Se dibuja solo cuando algo cambia (giro, seleccion, tamano), no en bucle: en una nave el
 * portatil de a bordo no tiene por que gastar bateria en repintar un cuerpo quieto. Por eso el
 * holograma no parpadea ni se desplaza: las líneas de barrido están quietas.
 *
 * Frente y Espalda llevan los dos el signo de alternar entre dos vistas de lo mismo (`switchView`,
 * §5.33.9): es un solo concepto, y la palabra dice cuál. Sin WebGL, el aviso va con la marca de
 * «no disponible» (gris con el círculo tachado), no con el gris solo.
 */
export function BodyMap({
  selected,
  names,
  onToggle,
}: {
  selected: readonly string[];
  /** Nombre de cada zona, tal como lo declara el backend. */
  names: Record<string, string>;
  onToggle: (zone: string) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const scene = useRef<{
    render: () => void;
    setView: (view: View) => void;
    paint: (selected: readonly string[], hovered: string | null) => void;
  } | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const [available, setAvailable] = useState(true);
  // Referencias vivas para los manejadores del puntero, que se registran una sola vez.
  const toggle = useRef(onToggle);
  toggle.current = onToggle;
  // El avatar (`lib/avatar.ts`): al cambiarlo se rehace la escena con el otro cuerpo.
  const avatar = useAvatar();

  useEffect(() => {
    const element = host.current;
    if (element === null) return;
    let renderer: WebGLRenderer;
    try {
      renderer = new WebGLRenderer({ antialias: true });
    } catch {
      setAvailable(false);
      return;
    }
    renderer.setPixelRatio(window.devicePixelRatio);
    element.appendChild(renderer.domElement);

    // Fondo como el marco del cuerpo de «Inicio»: azul marino que se aclara hacia el centro. La
    // textura se estira al lienzo, así que el círculo sale elipse, como el `radial-gradient(ellipse…)`
    // de ese marco.
    const world = new Scene();
    const backdrop = radialTexture([
      [0, mix(palette.blue, palette.bg, 0.2)],
      [0.55, mix(palette.blue, palette.bg, 0.09)],
      [1, mix(palette.blue, palette.bg, 0.03)],
    ]);
    world.background = backdrop;

    // Halo detrás del cuerpo. Va en la lista de los opacos (`transparent: false`), se pinta el
    // primero (`renderOrder`) y sin profundidad: queda siempre detrás aunque se gire, y suma luz al
    // fondo (mezcla aditiva) en vez de taparlo.
    const haloTexture = radialTexture([
      [0, mix(palette.blue, palette.bg, 0.2)],
      [0.4, mix(palette.blue, palette.bg, 0.1), 0.7],
      [1, mix(palette.blue, palette.bg, 0.1), 0],
    ]);
    const haloMaterial = new SpriteMaterial({
      map: haloTexture,
      blending: AdditiveBlending,
      transparent: false,
      depthTest: false,
      depthWrite: false,
    });
    const halo = new Sprite(haloMaterial);
    halo.position.set(0, BODY_HEIGHT * 0.55, 0);
    halo.scale.set(1.15, BODY_HEIGHT * 1.25, 1);
    halo.renderOrder = -1;
    world.add(halo);

    // Anillo de luz en el suelo, bajo los pies: lo tapan los pies, no al revés.
    const floorTexture = radialTexture([
      [0, mix(palette.blue, palette.bg, 0.3)],
      [0.55, mix(palette.blue, palette.bg, 0.12)],
      [0.78, mix(palette.blue, palette.text, 0.75)],
      [0.86, mix(palette.blue, palette.bg, 0.3), 0.5],
      [1, mix(palette.blue, palette.bg, 0.3), 0],
    ]);
    const floorMaterial = new MeshBasicMaterial({
      map: floorTexture,
      blending: AdditiveBlending,
      transparent: true,
      depthWrite: false,
    });
    const floorGeometry = new PlaneGeometry(0.8, 0.8);
    const floor = new Mesh(floorGeometry, floorMaterial);
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = 0.002;
    world.add(floor);

    const pixelRatio = renderer.getPixelRatio();
    const blueSkin: Skin = {
      deep: mix(palette.blue, palette.bg, 0.1),
      core: mix(palette.blue, palette.bg, 0.7),
      rim: mix(palette.blue, palette.text, 0.75),
    };
    // La zona marcada, verde de selección liso de punta a punta: sobre la piel térmica, que ya tiene
    // verdes, un verde en degradado se confundiría con el adorno; uno liso y sin textura, no. El
    // hondo casi igual que el encendido para que también en un brazo o un pie salga el mismo verde.
    const greenSkin: Skin = {
      deep: mix(palette.green, palette.bg, 0.9),
      core: new Color(palette.green),
      rim: mix(palette.green, palette.text, 0.6),
    };
    // Surcos, crestas y colores de «Inicio» solo en el resto: la zona marcada se queda lisa, para
    // que se siga leyendo marcada igual de un vistazo.
    const neutral = hologram(blueSkin, 0, pixelRatio, 1);
    const neutralOver = hologram(blueSkin, 0.22, pixelRatio, 1);
    const marked = hologram(greenSkin, 0, pixelRatio, 0);
    const markedOver = hologram(greenSkin, 0.18, pixelRatio, 0);
    const thermalOf = (material: ShaderMaterial) => material.uniforms as unknown as ThermalUniforms;
    const thermalTextures: DataTexture[] = [];
    let alive = true;
    // Las juntas en reposo, casi invisibles (humano 6, 2026-11-09): aun con 0,28 de opacidad, la
    // raya oscura del hombro, el codo, la muñeca y la cintura hacía leer el cuerpo como un maniquí
    // articulado. Una persona no tiene costuras; dónde acaba cada zona lo dicen el contorno verde
    // bajo el puntero y el borde de la zona marcada, que es cuando hace falta saberlo.
    const seam = new LineBasicMaterial({
      color: mix(palette.blue, palette.bg, 0.1),
      transparent: true,
      opacity: 0.05,
    });
    // Borde de una zona marcada: claro, casi el color del texto, para que el verde liso se recorte
    // sobre el resto atenuado sin confundirse con el contorno verde vivo del puntero.
    const markedSeam = new LineBasicMaterial({
      color: mix(palette.green, palette.text, 0.25),
      transparent: true,
      opacity: 0.95,
    });
    // También en la lista de los transparentes (opaco del todo): si fuera en la de los opacos se
    // pintaría antes que las juntas, y la junta de la vecina, a la misma profundidad, lo taparía.
    const cursor = new LineBasicMaterial({ color: palette.green, transparent: true, opacity: 1 });

    const meshes: Mesh[] = [];
    const edges = new Map<string, LineSegments>();
    const geometries: BufferGeometry[] = [];
    // Surcos y crestas (`cavity.ts`), una vez para todas las zonas juntas: soldadas por posición,
    // las juntas reciben el mismo valor a los dos lados y no salen manchas en las costuras.
    // Donde se cruzan dos piezas (el brazo en el tronco, la pierna en la pelvis, un dedo en la
    // palma, la oreja en la cabeza), la normal se funde con la de la vecina y el pliegue ahonda la
    // cavidad: sin eso, cada tubo traía su luz y el brazo se leía encajado, de quita y pon.
    const rests = BODY.map(surfaceOf);
    const surfaces = avatar === "female" ? rests.map(feminizeSurface) : rests;
    let shading = bodyShading.get(avatar);
    if (shading === undefined) {
      const weld = weldSurfaces(surfaces);
      const cavities = cavityOf(surfaces, weld);
      const crossings = blendCrossings(surfaces, weld);
      creaseCavities(cavities, crossings.crease);
      fadeCavities(cavities, surfaces, faceCavityKeep);
      shading = { cavities, normals: crossings.normals };
      bodyShading.set(avatar, shading);
    }
    const { cavities, normals } = shading;
    for (const [index, item] of BODY.entries()) {
      const surface = surfaces[index]!;
      const geometry = new BufferGeometry();
      geometry.setAttribute("position", new BufferAttribute(surface.positions, 3));
      geometry.setAttribute("normal", new BufferAttribute(normals[index]!, 3));
      geometry.setAttribute("cavity", new BufferAttribute(cavities[index]!, 1));
      geometry.setAttribute("rest", new BufferAttribute(rests[index]!.positions, 3));
      geometry.setIndex(new BufferAttribute(surface.indices, 1));
      // Esfera y caja de cada zona: `Mesh.raycast` las prueba antes de recorrer los triángulos, y
      // la caja descarta mucho más que la esfera en zonas alargadas (un brazo, una pierna).
      geometry.computeBoundingSphere();
      geometry.computeBoundingBox();
      const mesh = new Mesh(geometry, neutral);
      mesh.userData.zone = item.zone;
      world.add(mesh);
      meshes.push(mesh);
      // El borde de la zona: la superficie es lisa, así que solo salen los bordes del trozo.
      const outline = new EdgesGeometry(geometry, 60);
      const line = new LineSegments(outline, seam);
      world.add(line);
      edges.set(item.zone, line);
      geometries.push(geometry, outline);
    }

    // La melena del avatar femenino (`feminine.ts`): con el material del cuerpo (misma piel térmica,
    // proyectada desde el 2D, que ya trae el pelo pintado), mechones como surcos y fuera de `meshes`: no es una
    // zona, el clic la atraviesa y cae en la cabeza.
    if (avatar === "female") {
      const hair = hairSurface((height, degrees) => surfacePoint("column", false, height, degrees));
      const geometry = new BufferGeometry();
      geometry.setAttribute("position", new BufferAttribute(hair.positions, 3));
      geometry.setAttribute("normal", new BufferAttribute(hair.normals, 3));
      geometry.setAttribute("cavity", new BufferAttribute(hair.cavity, 1));
      // Detrás, el pelo no es la nuca: lee la espalda dibujada en el cráneo (liso, sin los trazos del
      // cuello y el trapecio), a la altura de la coronilla.
      const crown = Float32Array.from(hair.positions);
      for (let i = 0; i < crown.length; i += 3) {
        crown[i] = crown[i]! * 0.6;
        crown[i + 1] = 1.69;
      }
      geometry.setAttribute("rest", new BufferAttribute(crown, 3));
      geometry.setIndex(new BufferAttribute(hair.indices, 1));
      geometry.computeBoundingSphere();
      world.add(new Mesh(geometry, neutral));
      geometries.push(geometry);
    }

    const camera = new PerspectiveCamera(35, 1, 0.1, 20);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(0, TARGET_Y, 0);
    controls.enablePan = false;
    controls.minDistance = 1.2;
    controls.maxDistance = 5;

    const render = () => renderer.render(world, camera);
    const setView = (view: View) => {
      camera.position.set(0, TARGET_Y, view === "front" ? CAMERA_DISTANCE : -CAMERA_DISTANCE);
      controls.update();
      render();
    };
    const paint = (chosen: readonly string[], over: string | null) => {
      // Con alguna zona marcada, el adorno se aparta: el resto del cuerpo, desteñido y apagado.
      const dim = chosen.length > 0 ? 1 : 0;
      for (const material of [neutral, neutralOver]) thermalOf(material).dim.value = dim;
      for (const mesh of meshes) {
        const zone = String(mesh.userData.zone);
        const isMarked = chosen.includes(zone);
        if (zone === over) mesh.material = isMarked ? markedOver : neutralOver;
        else mesh.material = isMarked ? marked : neutral;
        const line = edges.get(zone);
        if (line === undefined) continue;
        line.material = zone === over ? cursor : isMarked ? markedSeam : seam;
        // Un borde compartido sale en las dos zonas vecinas, a la misma profundidad: el perfil
        // del cursor se pinta el último para que la junta de la vecina no lo tape, y el de la
        // marcada después de las juntas en reposo.
        line.renderOrder = zone === over ? 2 : isMarked ? 1 : 0;
      }
      render();
    };
    controls.addEventListener("change", render);

    const resize = () => {
      const { width, height } = element.getBoundingClientRect();
      if (width === 0 || height === 0) return;
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      render();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(element);

    const raycaster = new Raycaster();
    const zoneAt = (event: PointerEvent): string | null => {
      const point = toNormalized(
        event.clientX,
        event.clientY,
        renderer.domElement.getBoundingClientRect(),
      );
      raycaster.setFromCamera(new Vector2(point.x, point.y), camera);
      const [hit] = raycaster.intersectObjects(meshes, false);
      return hit === undefined ? null : String(hit.object.userData.zone);
    };
    let down: { x: number; y: number } | null = null;
    const onDown = (event: PointerEvent) => {
      down = { x: event.clientX, y: event.clientY };
    };
    const onUp = (event: PointerEvent) => {
      if (down === null) return;
      const released = { x: event.clientX, y: event.clientY };
      const wasClick = isClick(down, released);
      down = null;
      if (!wasClick) return;
      const zone = zoneAt(event);
      if (zone !== null) toggle.current(zone);
    };
    // El puntero puede mandar muchos más movimientos que fotogramas (ratones de 500-1000 Hz), y
    // cada uno recorre los triángulos de las zonas que cruza el rayo: como mucho un rayo cada
    // `HOVER_INTERVAL` ms, y el último movimiento se mira siempre al acabar el intervalo. Por
    // tiempo y no por fotograma: con un repintado lento (sin GPU) el nombre de la zona no se
    // quedaría atrás esperando al fotograma siguiente.
    let pendingMove: PointerEvent | null = null;
    let lastProbe = -Infinity;
    let probeTimer: ReturnType<typeof setTimeout> | undefined;
    const probe = () => {
      probeTimer = undefined;
      const last = pendingMove;
      pendingMove = null;
      if (last === null || down !== null) return;
      lastProbe = performance.now();
      setHovered(zoneAt(last));
    };
    const onMove = (event: PointerEvent) => {
      if (down !== null) return;
      pendingMove = event;
      if (probeTimer !== undefined) return;
      const wait = lastProbe + HOVER_INTERVAL - performance.now();
      if (wait <= 0) probe();
      else probeTimer = setTimeout(probe, wait);
    };
    const stopProbe = () => {
      clearTimeout(probeTimer);
      probeTimer = undefined;
      pendingMove = null;
    };
    const onLeave = () => {
      stopProbe();
      setHovered(null);
    };
    const canvas = renderer.domElement;
    canvas.addEventListener("pointerdown", onDown);
    canvas.addEventListener("pointerup", onUp);
    canvas.addEventListener("pointermove", onMove);
    canvas.addEventListener("pointerleave", onLeave);

    scene.current = { render, setView, paint };
    setView("front");
    resize();

    // Los colores de «Inicio», en cuanto llegan: se cambian en los materiales (sin recompilar) y se
    // redibuja una vez. Es un solo cambio del azul a los colores, sin fundido: la escena no se
    // repinta en bucle.
    loadThermal(avatar)
      .then(({ sharp, soft, width, height }) => {
        if (!alive) return;
        const [sharpTexture, softTexture] = [sharp, soft].map((data) => {
          const texture = new DataTexture(data, width, height);
          texture.colorSpace = SRGBColorSpace;
          texture.magFilter = LinearFilter;
          texture.minFilter = LinearFilter;
          texture.needsUpdate = true;
          thermalTextures.push(texture);
          return texture;
        });
        for (const material of [neutral, neutralOver]) {
          const uniforms = thermalOf(material);
          uniforms.thermal.value = sharpTexture ?? null;
          uniforms.thermalSoft.value = softTexture ?? null;
          uniforms.thermalMix.value = 1;
        }
        render();
      })
      .catch(() => {
        // Sin los píxeles se queda el holograma azul: es adorno, el mapa funciona igual.
      });
    // La espalda dibujada, cuando esté: hasta entonces (o si falla) lleva la copia borrosa del frente.
    loadBack()
      .then((data) => {
        if (!alive) return;
        const texture = new DataTexture(data, BACK_PROJECTION.width, BACK_PROJECTION.height);
        texture.colorSpace = SRGBColorSpace;
        texture.magFilter = LinearFilter;
        // Con mipmaps (512×1024 es potencia de dos): el cuerpo ocupa en pantalla unas tres veces
        // menos píxeles que la textura, y sin ellos las líneas finas salían a trozos.
        texture.minFilter = LinearMipmapLinearFilter;
        texture.generateMipmaps = true;
        texture.anisotropy = renderer.capabilities.getMaxAnisotropy();
        texture.needsUpdate = true;
        thermalTextures.push(texture);
        for (const material of [neutral, neutralOver]) {
          const uniforms = thermalOf(material);
          uniforms.thermalBack.value = texture;
          uniforms.backMix.value = 1;
        }
        render();
      })
      .catch(() => {
        // Adorno: sin la textura trasera, el mapa funciona igual.
      });

    return () => {
      alive = false;
      for (const texture of thermalTextures) texture.dispose();
      scene.current = null;
      stopProbe();
      observer.disconnect();
      canvas.removeEventListener("pointerdown", onDown);
      canvas.removeEventListener("pointerup", onUp);
      canvas.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("pointerleave", onLeave);
      controls.dispose();
      for (const geometry of geometries) geometry.dispose();
      floorGeometry.dispose();
      const materials = [
        neutral,
        neutralOver,
        marked,
        markedOver,
        seam,
        markedSeam,
        cursor,
        haloMaterial,
        floorMaterial,
      ];
      for (const material of materials) material.dispose();
      for (const texture of [backdrop, haloTexture, floorTexture]) texture.dispose();
      renderer.dispose();
      canvas.remove();
    };
  }, [avatar]);

  // Tras rehacer la escena (otro avatar) también: el efecto de arriba va antes en el mismo cambio.
  useEffect(() => {
    scene.current?.paint(selected, hovered);
  }, [selected, hovered, avatar]);

  if (!available) {
    return (
      <p>
        <MarkOf mark={UNAVAILABLE_MARK}>
          Vista 3D no disponible en este equipo. Las zonas se pueden elegir en la lista.
        </MarkOf>
      </p>
    );
  }

  return (
    <figure className="body-map">
      <div ref={host} className="body-map-canvas" />
      <figcaption>
        <Command concept="switchView" onClick={() => scene.current?.setView("front")}>
          Frente
        </Command>
        <Command concept="switchView" onClick={() => scene.current?.setView("back")}>
          Espalda
        </Command>
        <AvatarSwitch />
        <span className="secondary">
          {hovered === null
            ? "Arrastre para girar; toque una zona para marcarla o desmarcarla."
            : (names[hovered] ?? hovered)}
        </span>
      </figcaption>
    </figure>
  );
}

/** Mezcla de dos colores de la paleta: `share` del primero (como `color-mix` en el CSS). */
function mix(a: string, b: string, share: number): Color {
  return new Color(b).lerp(new Color(a), share);
}

/** Una parada de un degradado radial: posición (0 centro, 1 borde), color y opacidad. */
type Stop = readonly [offset: number, color: Color, opacity?: number];

/**
 * Degradado radial en una textura pequeña: el fondo, el halo y el anillo del suelo. Los colores
 * llegan ya mezclados de la paleta. El halo y el anillo acaban en opacidad cero: suman luz, y donde
 * no hay nada que sumar no debe verse el borde cuadrado de la textura.
 */
function radialTexture(stops: readonly Stop[]): CanvasTexture {
  const size = 256;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const context = canvas.getContext("2d");
  if (context !== null) {
    const middle = size / 2;
    const gradient = context.createRadialGradient(middle, middle, 0, middle, middle, middle);
    for (const [offset, color, opacity = 1] of stops) {
      const { r, g, b } = color.getRGB(new Color(), SRGBColorSpace);
      const channel = (value: number) => Math.round(value * 255);
      gradient.addColorStop(offset, `rgb(${channel(r)} ${channel(g)} ${channel(b)} / ${opacity})`);
    }
    context.fillStyle = gradient;
    context.fillRect(0, 0, size, size);
  }
  const texture = new CanvasTexture(canvas);
  texture.colorSpace = SRGBColorSpace;
  return texture;
}

/** Los tres tonos de un holograma: el hondo, el encendido del tórax y el del contorno. */
interface Skin {
  deep: Color;
  core: Color;
  rim: Color;
}

/** Los uniformes de la piel térmica que se cambian después de crear el material. */
interface ThermalUniforms {
  thermal: { value: Texture | null };
  thermalSoft: { value: Texture | null };
  thermalMix: { value: number };
  thermalBack: { value: Texture | null };
  backMix: { value: number };
  dim: { value: number };
}

/**
 * Material del holograma. Sin luces: el color lo da la propia forma.
 * - Por dentro, del tono hondo al encendido según la altura y la distancia al eje del cuerpo: el
 *   tórax y la cabeza brillan; los brazos y las piernas se apagan hacia las manos y los pies.
 * - El contorno se enciende donde la superficie se ve de canto (Fresnel), como el halo del cuerpo
 *   de «Inicio».
 * - Luz envolvente de piel: sombra ancha que no llega a negro y una dispersión subsuperficial falsa
 *   en la línea de sombra.
 * - Las líneas de barrido van en la pantalla, una fila de cada tres, quietas, y solo apagan el
 *   contorno: no hay animación porque la escena no se repinta en bucle.
 * - `lift` aclara la zona entera bajo el puntero.
 * - `relief` (0 o 1) oscurece un poco los surcos y aclara las crestas con el atributo `cavity`
 *   (`cavity.ts`): una oclusión ambiental falsa y suave, calculada una vez, que sugiere el músculo
 *   bajo la piel. Solo con los tonos del propio holograma.
 * - `thermalMix` (0 o 1) cambia el interior azul por los colores de «Inicio» (`thermal`), proyectados
 *   de frente por x y altura (`thermalSkin.ts`); en los costados, su copia borrosa. Detrás, con
 *   `backMix` (0 o 1), la textura trasera dibujada a mano (`thermalBack`, `backSkin.ts`), proyectada
 *   igual por x y altura; las dos se funden en el costado. Encima van la misma luz, los surcos y el
 *   contorno Fresnel, para que se siga leyendo el volumen; la luz se suaviza un poco con la textura
 *   para que los colores salgan vivos, como en «Inicio».
 * - `dim` (0 o 1) destiñe y apaga: el resto del cuerpo mientras hay una zona marcada.
 * Es opaco a propósito: con transparencia de verdad, las zonas de detrás asomarían por las de
 * delante según el orden de pintado, y la espalda se confundiría con el pecho. La transparencia la
 * sugiere el interior oscuro con el borde claro.
 * Desplaza un poco la profundidad para que las juntas entre zonas se dibujen encima sin parpadeo.
 */
function hologram(skin: Skin, lift: number, pixelRatio: number, relief: number): ShaderMaterial {
  const { u0, uScale, v0, vScale } = thermalCoefficients();
  const backSide = backCoefficients();
  return new ShaderMaterial({
    uniforms: {
      deep: { value: skin.deep },
      core: { value: skin.core },
      rim: { value: skin.rim },
      lift: { value: lift },
      relief: { value: relief },
      bodyHeight: { value: BODY_HEIGHT },
      thermal: { value: null },
      thermalSoft: { value: null },
      thermalMix: { value: 0 },
      thermalBack: { value: null },
      backMix: { value: 0 },
      backProjection: { value: new Vector4(backSide.u0, backSide.uScale, backSide.v0, backSide.vScale) },
      dim: { value: 0 },
      // Tono del resto atenuado: el azul de la paleta, no un gris (el gris diría «no disponible»).
      dimTint: { value: new Color(palette.blue) },
      projection: { value: new Vector4(u0, uScale, v0, vScale) },
      // Un número entero de píxeles del dispositivo: con 1,25 o 1,5 (portátiles con Windows) un
      // periodo fraccionario daría bandas desiguales, con muaré.
      scanPeriod: { value: 3 * Math.max(1, Math.round(pixelRatio)) },
    },
    vertexShader: /* glsl */ `
      attribute float cavity;
      // Dónde estaba el punto en el cuerpo de partida: la espalda dibujada a mano (backSkin.ts) se
      // dibujó sobre él, así que con el avatar femenino (feminine.ts), que mueve los vértices, se
      // sigue leyendo desde ahí y cada músculo de la espalda acompaña a su sitio.
      attribute vec3 rest;
      varying vec3 vRest;
      varying float vCavity;
      varying vec3 vModel;
      varying vec3 vNormal;
      varying vec3 vView;
      varying vec3 vFacing;
      void main() {
        vModel = position;
        vRest = rest;
        // Hacia dónde mira la superficie en el cuerpo (no en la vista): z +1 de frente, −1 de espalda.
        vFacing = normal;
        vCavity = cavity;
        vec4 viewPosition = modelViewMatrix * vec4(position, 1.0);
        vView = -viewPosition.xyz;
        vNormal = normalize(normalMatrix * normal);
        gl_Position = projectionMatrix * viewPosition;
      }
    `,
    fragmentShader: /* glsl */ `
      uniform vec3 deep;
      uniform vec3 core;
      uniform vec3 rim;
      uniform float lift;
      uniform float relief;
      uniform float bodyHeight;
      uniform float scanPeriod;
      uniform sampler2D thermal;
      uniform sampler2D thermalSoft;
      uniform float thermalMix;
      uniform sampler2D thermalBack;
      uniform float backMix;
      uniform vec4 backProjection;
      uniform float dim;
      uniform vec3 dimTint;
      uniform vec4 projection;
      varying vec3 vFacing;
      varying vec3 vModel;
      varying vec3 vRest;
      varying vec3 vNormal;
      varying vec3 vView;
      varying float vCavity;
      void main() {
        vec3 normal = normalize(vNormal);
        if (!gl_FrontFacing) normal = -normal;
        float facing = abs(dot(normal, normalize(vView)));
        float fresnel = pow(1.0 - facing, 3.0);
        // Altura relativa: 0 en los pies, 1 en la coronilla.
        float height = vModel.y / bodyHeight;
        // Cuadrados multiplicando: «pow» con base negativa no está definido en GLSL (en Windows,
        // por ANGLE sobre D3D, da NaN y el cuerpo saldría negro de cintura para abajo).
        float toChest = (height - 0.74) / 0.2;
        float toHead = (height - 0.93) / 0.07;
        float chest = exp(-toChest * toChest);
        float head = exp(-toHead * toHead);
        float axis = exp(-(vModel.x * vModel.x) / 0.02);
        float glow = clamp((chest + 0.8 * head) * axis + 0.15 * height, 0.0, 1.0);
        // Luz de piel (humano 6, 2026-11-09). Una luz principal arriba a la izquierda y otra de
        // relleno a la derecha, fijas respecto a la cámara (la normal está en el espacio de la
        // vista), para que la forma se lea de frente, de espalda y de lado. Antes la principal iba
        // al cuadrado y con poco «wrap»: el paso de luz a sombra era corto y duro, y cada músculo
        // salía como un cable recortado. La piel deja pasar la luz y la reparte bajo la superficie,
        // así que su sombra es ancha y no llega a negro: «wrap» amplio y lineal, y una dispersión
        // subsuperficial falsa —una franja templada en la línea de sombra, hacia el tono del
        // contorno— que redondea los volúmenes como en la piel de verdad.
        vec3 key = normalize(vec3(-0.45, 0.55, 0.7));
        vec3 fill = normalize(vec3(0.6, -0.1, 0.8));
        float keyLight = dot(normal, key);
        float wrapKey = clamp((keyLight + 0.6) / 1.6, 0.0, 1.0);
        float wrapFill = clamp((dot(normal, fill) + 0.7) / 1.7, 0.0, 1.0);
        float shade = 0.36 + 0.56 * wrapKey + 0.16 * wrapFill;
        float subsurface = exp(-keyLight * keyLight / 0.12) * 0.1;
        // Brillo especular ancho y suave: la piel brilla en mancha, no en una raya por cresta.
        vec3 halfway = normalize(key + normalize(vView));
        float sheen = pow(clamp(dot(normal, halfway), 0.0, 1.0), 10.0);
        // Surcos como oclusión suave: como mucho un 28 % más oscuro, con una curva que deja casi
        // sin tocar los surcos poco hondos. Con un 60 % y una curva empinada los surcos salían como
        // rayas pintadas y el cuerpo parecía despellejado. Las crestas, un toque del contorno.
        float groove = relief * smoothstep(0.0, 1.0, max(vCavity, 0.0));
        float crest = relief * max(-vCavity, 0.0);
        // Líneas de barrido solo en el contorno: sobre todo el cuerpo hacían bandas horizontales
        // que se leían como vendas. En el borde dicen «holograma» sin cruzar la piel: solo donde la
        // superficie se ve ya casi de canto, y tenues, para que el perfil no salga punteado.
        float scanRow = mod(floor(gl_FragCoord.y), scanPeriod) < scanPeriod / 3.0 ? 1.0 : 0.0;
        float scan = 1.0 - 0.3 * scanRow * smoothstep(0.3, 0.75, fresnel);
        vec3 body = mix(deep, core, glow) * shade + mix(core, rim, 0.5) * subsurface;
        if (thermalMix > 0.0) {
          vec3 facing = normalize(vFacing);
          // Lo que mira arriba o abajo (la cara de encima de hombros y trapecio, la coronilla, bajo
          // la barbilla, las plantas). Las dos proyecciones son de frente y de espalda: en una
          // superficie horizontal toda una franja de fondo recibe la misma fila de la imagen, y
          // arriba esa fila es la línea clara del contorno. Desde arriba salían rayas y
          // rectángulos, como un corte (Ellande, 2026-11-11: «desde arriba se sigue viendo
          // cortado»). Ahí se toma el color unos centímetros hacia dentro del cuerpo, por debajo
          // del contorno, y de la copia borrosa: piel continua en vez de la raya estirada.
          float level = smoothstep(0.35, 0.85, abs(facing.y));
          vec2 sampleAt = vModel.xy - vec2(0.0, sign(facing.y) * 0.07 * level);
          vec2 uv = clamp(projection.xz + projection.yw * sampleAt, 0.0, 1.0);
          // Cuánto mira hacia atrás: 0 de frente y de canto (también lo que mira arriba o abajo,
          // como el hombro, la coronilla o las plantas, con z = 0), 1 ya en la espalda. El paso es
          // ancho (de z = 0 a −0,4) para que el frente y la espalda se fundan sin costura.
          float back = smoothstep(0.0, -0.4, facing.z) * backMix;
          // De lado y en la franja donde se funde con la espalda, la copia borrosa del frente: sin
          // las rayas que deja la proyección frontal estirada. Sin textura trasera (aún no lista),
          // también detrás, para no dibujar allí el corazón, los abdominales y las rótulas.
          float soft = max(max(smoothstep(0.45, 0.9, abs(facing.x)), smoothstep(0.1, -0.5, facing.z)), level);
          vec3 heat = mix(texture2D(thermal, uv).rgb, texture2D(thermalSoft, uv).rgb, soft);
          // Con la misma viveza que de frente (Ellande, 2026-11-10: «los colores de la espalda no
          // tienen la viveza de los de enfrente, tienen que ser iguales»): la saturación que el
          // desenfoque pierde al promediar colores vecinos se devuelve.
          float heatLuma = dot(heat, vec3(0.2126, 0.7152, 0.0722));
          heat = max(mix(vec3(heatLuma), heat, 1.0 + 0.45 * soft), 0.0);
          // Detrás, su propio render dibujado a mano (backSkin.ts, backAnatomy/): el calor de
          // espalda y los trazos claros de sus músculos y huesos, como el dibujo del frente (Ellande:
          // «falta darle detalle [a la espalda] como en frente»). Sustituye a las líneas que se
          // sacaban de la cavidad del relieve (961cc3e): seguían la forma, no la anatomía.
          vec2 backAt = vRest.xy - vec2(0.0, sign(facing.y) * 0.07 * level);
          vec2 backUv = clamp(backProjection.xz + backProjection.yw * backAt, 0.0, 1.0);
          heat = mix(heat, texture2D(thermalBack, backUv).rgb, back);
          // Luz más suave que en el azul (de 0,62 a 1,1): los colores salen vivos y aún se lee la forma.
          vec3 painted = heat * (0.3 + 0.75 * shade) + heat * subsurface;
          body = mix(body, painted, thermalMix);
        }
        vec3 edge = rim * (fresnel * 1.6 * scan + 0.22 * sheen);
        vec3 color = (body + edge) * (1.0 - 0.28 * groove);
        // El resto del cuerpo con una zona marcada: sin sus colores y a media luz, en el azul de la
        // paleta, para que sus verdes y amarillos de adorno no se confundan con el verde liso de la
        // marcada. En azul y no en gris: un cuerpo gris se leería «no disponible» (F.5-1). También
        // con el holograma azul de respaldo, para que la marcada se lea igual mientras llegan los
        // colores. Antes del aclarado del puntero, para que la zona bajo el puntero se siga aclarando.
        vec3 lumaWeights = vec3(0.2126, 0.7152, 0.0722);
        vec3 tinted = dot(color, lumaWeights) * dimTint / dot(dimTint, lumaWeights);
        color = mix(color, tinted, 0.9 * dim) * (1.0 - 0.5 * dim);
        color += rim * (lift + 0.08 * crest);
        gl_FragColor = vec4(color, 1.0);
        #include <colorspace_fragment>
      }
    `,
    polygonOffset: true,
    polygonOffsetFactor: 1,
    polygonOffsetUnits: 1,
  });
}
