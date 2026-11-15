// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * El último volumen segmentado, dibujado en 3D en pequeño con el render de «ilustración médica» de
 * Polaris: el hígado rojo y translúcido por Fresnel (bordes opacos que dan forma, centro claro que
 * deja ver dentro), vasos con barniz, luz de estudio y tono ACES. Por qué existe: la maqueta de la
 * ISS (lote «reservas», 2026-11-14) pone ese hígado en «Diagnóstico integrado», y el visor completo
 * (NiiVue, cortes y TAC) pesa demasiado para una tarjeta. La primera versión usó los colores del
 * visor de cortes (hígado crema al 22 %) y el usuario lo vio: «se le han ido los colores al hígado,
 * ¿seguro que es el render?». No lo era; ahora sí.
 *
 * Incorpora código de Polaris (github.com/BeyondTheProtocol/polaris @ 7bf47257, AGPL-3.0-or-later,
 * (c) 2026 la autora de Polaris, «Beyond the Protocol»), de `tools/visor3d_web/render.js`: los
 * materiales (`fresnel`, `higadoMat`, `vaso`, vesícula), las tres luces, el entorno `RoomEnvironment`,
 * el tono ACES, el paso de RAS a three.js, el hígado en dos pasadas (caras de detrás y de delante) y
 * el encuadre por la caja del hígado con su inclinación de 9°.
 * Cambios respecto al original (AGPL §5a):
 *   * Colores como tokens `anatomy` de `palette.ts` (los mismos valores), salvo el brillo del hígado,
 *     oscurecido porque el de Polaris se parecía al rojo de alarma.
 *   * Sin lesiones, dianas, textos, leyenda, barra de escala ni vídeo: en la tarjeta, solo el órgano;
 *     las lesiones candidatas, con su estado, están en el visor completo.
 *   * Fondo berenjena liso (`anatomy.canvas`) en vez del degradado.
 *   * La vuelta de su vídeo (`__fotograma`: 360° en horizontal y cabeceo de 9° ± 4°) va en vivo, una
 *     cada `TURN_MS`, con un mando que la para (WCAG 2.2.2) y parada de partida si el sistema pide
 *     menos movimiento; no gira escondida ni con la pestaña detrás (pedido por el usuario,
 *     2026-11-14: «que el hígado gire 360 grados en horizontal sobre sí mismo»).
 *   * Mallas de la API de EMMA (`segmentationFileUrl`, el binario firmado) y no de una carpeta.
 *   * Presets que no son el hígado (ojos, esqueleto): los colores del visor completo (`looks.ts`).
 *
 * Lo que no es: un diagnóstico a bordo (hoy no vuela ningún TAC). Es imagen de referencia, de una
 * segmentación automática sin validar; la tarjeta lo dice. Sin WebGL, o si una malla no llega, el
 * lienzo no se enseña y queda el resto de la tarjeta.
 */
import { useEffect, useRef, useState } from "react";
import {
  ACESFilmicToneMapping,
  BackSide,
  Box3,
  type BufferGeometry,
  Color,
  DirectionalLight,
  DoubleSide,
  FrontSide,
  Group,
  MathUtils,
  Matrix4,
  Mesh,
  MeshPhysicalMaterial,
  MeshStandardMaterial,
  PMREMGenerator,
  PerspectiveCamera,
  SRGBColorSpace,
  Scene,
  type Side,
  Vector3,
  WebGLRenderer,
} from "three";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { PLYLoader } from "three/addons/loaders/PLYLoader.js";

import { Command } from "../components/Command";
import { type VolumeSegmentation, segmentationFileUrl } from "../lib/api";
import { tr } from "../lib/i18n";
import { anatomy } from "../lib/palette";
import { look } from "./looks";

/** De Polaris: translucidez por Fresnel, opaca en los bordes (`max`) y clara de frente (`min`). */
function fresnel<T extends MeshPhysicalMaterial>(material: T, min: number, max: number, power: number): T {
  material.onBeforeCompile = (shader) => {
    shader.uniforms.uMin = { value: min };
    shader.uniforms.uMax = { value: max };
    shader.uniforms.uPot = { value: power };
    shader.fragmentShader =
      "uniform float uMin; uniform float uMax; uniform float uPot;\n" +
      shader.fragmentShader.replace(
        "#include <opaque_fragment>",
        "float fr = pow(1.0 - abs(dot(normal, normalize(vViewPosition))), uPot);\n" +
          "diffuseColor.a = mix(uMin, uMax, fr);\n#include <opaque_fragment>",
      );
  };
  return material;
}

const liver = (side: Side) =>
  fresnel(
    new MeshPhysicalMaterial({
      color: new Color(anatomy.liverRender),
      roughness: 0.38,
      clearcoat: 0.8,
      clearcoatRoughness: 0.22,
      sheen: 0.5,
      sheenRoughness: 0.5,
      sheenColor: new Color(anatomy.liverSheen),
      transparent: true,
      depthWrite: false,
      side,
    }),
    0.1,
    0.92,
    2.4,
  );

const vessel = (color: string) =>
  new MeshPhysicalMaterial({ color: new Color(color), roughness: 0.28, clearcoat: 0.9, clearcoatRoughness: 0.15 });

/** Material y orden de pintado de cada estructura del preset del hígado, como en Polaris. */
const RENDER: Record<string, { make: () => MeshPhysicalMaterial; order: number }> = {
  porta: { make: () => vessel(anatomy.portalRender), order: 1 },
  vasos: { make: () => vessel(anatomy.vesselsRender), order: 1 },
  vci: { make: () => vessel(anatomy.cavaRender), order: 1 },
  vesicula: {
    make: () =>
      fresnel(
        new MeshPhysicalMaterial({
          color: new Color(anatomy.gallbladder),
          roughness: 0.25,
          clearcoat: 1,
          transparent: true,
          depthWrite: false,
        }),
        0.35,
        0.95,
        2.0,
      ),
    order: 2,
  },
};

/** De RAS (milímetros del paciente) a three.js: la derecha del sujeto a la izquierda, la cabeza arriba. */
const RAS_TO_THREE = new Matrix4().set(-1, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 0, 1);

/** Una vuelta entera, en milisegundos: lenta, para que se lea la forma y no distraiga. */
export const TURN_MS = 24_000;

/**
 * El giro en el instante `elapsed`: la vuelta sobre su eje vertical y el cabeceo de Polaris
 * (9° ± 4°, una oscilación por vuelta, como su `__fotograma`).
 */
export function spinAt(elapsed: number): { y: number; x: number } {
  const turn = (elapsed % TURN_MS) / TURN_MS;
  return { y: 2 * Math.PI * turn, x: MathUtils.degToRad(9 + 4 * Math.sin(2 * Math.PI * turn)) };
}

function prefersStill(): boolean {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

/** Lo que no es del hígado (ojos, esqueleto): los colores del visor completo. */
function plain(key: string): MeshStandardMaterial {
  const { color, opacity } = look(key);
  return new MeshStandardMaterial({
    color: new Color(color[0] / 255, color[1] / 255, color[2] / 255),
    transparent: opacity < 1,
    opacity: Math.max(opacity, 0.6),
    depthWrite: opacity >= 1,
    side: DoubleSide,
    roughness: 0.55,
  });
}

export function SegmentationPreview({
  segmentation,
  label,
  open,
}: {
  segmentation: VolumeSegmentation;
  label: string;
  /** El mando que lleva al visor completo, sobre la esquina de abajo del render (como en la maqueta). */
  open?: { label: string; onClick: () => void } | undefined;
}) {
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const [failed, setFailed] = useState(false);
  // Gira solo si quien mira no ha pedido menos movimiento; el mando lo para y lo reanuda (WCAG 2.2.2).
  const [spinning, setSpinning] = useState(() => !prefersStill());
  const spin = useRef(spinning);
  spin.current = spinning;
  const structures = segmentation.estructuras.filter((item) => item.malla !== null);
  const files = structures.map((item) => `${item.key}:${item.malla ?? ""}`).join("|");

  useEffect(() => {
    const element = canvas.current;
    if (element === null || structures.length === 0) return;
    let renderer: WebGLRenderer;
    try {
      renderer = new WebGLRenderer({ canvas: element, antialias: true });
    } catch {
      setFailed(true);
      return;
    }
    renderer.outputColorSpace = SRGBColorSpace;
    renderer.toneMapping = ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.0;
    let cancelled = false;
    const scene = new Scene();
    // El fondo berenjena de Polaris: el hígado es translúcido de frente (alfa 0,1) y, sin fondo
    // opaco detrás, su centro se perdería contra la tarjeta (se probó: se veía medio hígado).
    scene.background = new Color(anatomy.canvas);
    const pmrem = new PMREMGenerator(renderer);
    const environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environment = environment;
    scene.environmentIntensity = 0.9;
    const light = (color: number, intensity: number, x: number, y: number, z: number) => {
      const item = new DirectionalLight(color, intensity);
      item.position.set(x, y, z);
      scene.add(item);
    };
    light(0xfff0dc, 1.7, 2.5, 3, 4); // clave cálida
    light(0xb8c8ff, 0.6, -4, 0.5, 2); // relleno frío
    light(0xffd9f0, 2.2, -1, 2, -5); // contraluz: silueta
    const camera = new PerspectiveCamera(26, 1, 1, 5000);
    const group = new Group();
    scene.add(group);
    const loader = new PLYLoader();
    const extent = new Vector3(1, 1, 1);
    const geometries: BufferGeometry[] = [];
    // Para la vuelta (abajo): hasta que llegan las mallas no hay nada que girar.
    let ready = false;
    let frame = 0;
    let turned = 0;
    let last: number | null = null;

    const draw = () => {
      const width = element.clientWidth;
      const height = element.clientHeight;
      if (width === 0 || height === 0) return;
      renderer.setPixelRatio(window.devicePixelRatio || 1);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      // Encuadre de Polaris: el alto del hígado con un 12 % de margen y, de ancho, su diagonal en planta
      // (lo que ocupa en cualquier punto de la vuelta); la cámara se aparta además media diagonal,
      // porque al girar lo de delante viene hacia ella y en perspectiva se ve más grande.
      const half = Math.tan(MathUtils.degToRad(camera.fov / 2));
      const wide = Math.hypot(extent.x, extent.z);
      const distance = Math.max((extent.y * 1.12) / 2 / half, wide / 2 / (half * camera.aspect), 1) + wide / 2;
      camera.position.set(0, 0, distance);
      camera.lookAt(0, 0, 0);
      camera.near = distance / 50;
      camera.far = distance * 4;
      camera.updateProjectionMatrix();
      renderer.render(scene, camera);
    };

    (async () => {
      const loaded = await Promise.all(
        structures.map(async (item) => {
          const geometry = await loader.loadAsync(segmentationFileUrl(segmentation.ledger_index, item.malla ?? ""));
          geometry.applyMatrix4(RAS_TO_THREE);
          geometry.computeVertexNormals();
          geometries.push(geometry);
          return { key: item.key, geometry };
        }),
      );
      if (cancelled) return;
      let organ: Mesh | null = null;
      for (const { key, geometry } of loaded) {
        if (segmentation.preset === "higado" && key === "higado") {
          // Caras de detrás primero y las de delante encima (la transparencia se ordena bien).
          const back = new Mesh(geometry, liver(BackSide));
          back.renderOrder = 3;
          group.add(back);
          organ = new Mesh(geometry, liver(FrontSide));
          organ.renderOrder = 4;
          group.add(organ);
        } else {
          const render = segmentation.preset === "higado" ? RENDER[key] : undefined;
          const mesh = new Mesh(geometry, render === undefined ? plain(key) : render.make());
          mesh.renderOrder = render?.order ?? 1;
          group.add(mesh);
        }
      }
      // La caja se mide sin la inclinación (el grupo puede venir ya girado de un dibujo anterior,
      // y entonces la caja saldría en otro espacio): primero se centra y después se inclina 9°.
      group.rotation.x = 0;
      group.updateMatrixWorld(true);
      const box = new Box3().setFromObject(organ ?? group);
      const center = box.getCenter(new Vector3());
      for (const child of group.children) child.position.sub(center);
      group.rotation.x = MathUtils.degToRad(9);
      extent.copy(box.getSize(new Vector3()));
      ready = true;
      draw();
    })().catch(() => {
      if (!cancelled) setFailed(true);
    });

    // La vuelta: un fotograma por refresco mientras gira, se ve y la pestaña está delante. Parado,
    // se queda donde estaba (el tiempo girado se guarda, y al reanudar sigue desde ahí).
    const tick = (now: number) => {
      frame = window.requestAnimationFrame(tick);
      const visible = !document.hidden && element.offsetParent !== null;
      if (!ready || !spin.current || !visible) {
        last = null;
        return;
      }
      turned += last === null ? 0 : now - last;
      last = now;
      const { y, x } = spinAt(turned);
      group.rotation.set(x, y, 0);
      renderer.render(scene, camera);
    };
    frame = window.requestAnimationFrame(tick);

    const observer = new ResizeObserver(draw);
    observer.observe(element);
    return () => {
      cancelled = true;
      window.cancelAnimationFrame(frame);
      observer.disconnect();
      group.traverse((node) => {
        if (node instanceof Mesh) (node.material as MeshStandardMaterial).dispose();
      });
      for (const geometry of geometries) geometry.dispose();
      environment.dispose();
      pmrem.dispose();
      renderer.dispose();
    };
    // `files` resume las mallas: el efecto no se repite por una lista nueva con lo mismo.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [segmentation.ledger_index, segmentation.preset, files]);

  if (failed || structures.length === 0) return null;
  return (
    <div className="dx-render-frame">
      <canvas ref={canvas} className="dx-render" role="img" aria-label={label} />
      {open !== undefined && (
        <Command pictogram="layers-stack" type="button" className="dx-render-open" aria-label={open.label} onClick={open.onClick}>
          <span>{tr("Abrir visor", "Open viewer")}</span>
        </Command>
      )}
      <Command
        concept="displayModes"
        type="button"
        className="dx-render-spin"
        aria-pressed={spinning}
        onClick={() => setSpinning(!spinning)}
      >
        <span>{spinning ? tr("Parar giro", "Stop rotation") : tr("Girar", "Rotate")}</span>
      </Command>
    </div>
  );
}
