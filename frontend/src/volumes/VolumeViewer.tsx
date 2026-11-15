// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Visor 3D de un volumen segmentado, solo para los presets que el visor web de Polaris no cubre
 * (los ojos: Polaris no tiene ese preset). El higado lo abre `PolarisViewer`, la copia literal.
 *
 * Incorpora codigo de Polaris (github.com/BeyondTheProtocol/polaris @ 7bf47257, AGPL-3.0-or-later,
 * (c) 2026 la autora de Polaris, «Beyond the Protocol»), de `tools/visor3d_web/main.js`: dos
 * instancias de NiiVue (BSD-2-Clause) —cortes multiplanares con regla y ventana, y render 3D con
 * mallas—, enlazadas entre si; la tabla de etiquetas (organo, estructuras, lesiones 10+id); el
 * organo cargado el ultimo con opacidad 0,22 para que la transparencia se ordene bien; y la tabla
 * de lesiones que, al pulsar una fila, lleva el cursor a su centro y la resalta en cortes y 3D.
 * Cambios respecto al original (AGPL §5a):
 *   * React y TypeScript en vez de manipular el DOM; datos de la API de EMMA, no de carpetas.
 *   * Dirigido por datos: las estructuras las da el resumen (`estructuras`), no el higado fijo.
 *   * Colores: la anatomia con los tonos de Polaris (higado crema translucido, porta azul, vasos
 *     azul grisaceo, fondo berenjena), ahora tokens `anatomy` de `palette.ts` que una prueba
 *     separa de los colores con significado. La lesion candidata en amarillo ("requiere
 *     atencion", F.5-1) y la seleccionada en verde vivo (cursor, F.5-2), no en el coral de Polaris.
 *     En la primera version portada todo era gris de interfaz y la escena no tenia forma.
 *   * Sin PET, marcas del radiologo, comparacion de fechas en tabla ni carga tumoral: eran del caso
 *     de su autora. Las cifras las da el backend y se formatean con `format.ts`.
 *   * Cabeceras de tabla y rotulo de la vista con el signo de EMMA (2026-10-21, §5.33.9), y el
 *     error de carga con su marca de fallo (cruz en rojo junto al motivo), no con el rojo solo.
 */
import { MULTIPLANAR_TYPE, Niivue, SHOW_RENDER, SLICE_TYPE } from "@niivue/niivue";
import { useEffect, useRef, useState } from "react";

import { FieldLabel } from "../components/FieldLabel";
import { Mark, MarkOf } from "../components/Mark";
import { Th } from "../components/Th";
import { type VolumeSegmentation, segmentationFileUrl } from "../lib/api";
import { formatNumber } from "../lib/format";
import { FAILURE_MARK } from "../lib/marks";
import { anatomy, palette } from "../lib/palette";
import { look, rgb } from "./looks";

type View = "mpr" | "axial" | "coronal" | "sagittal";

const VIEWS: Record<View, { label: string; type: number }> = {
  mpr: { label: "Tres planos", type: SLICE_TYPE.MULTIPLANAR },
  axial: { label: "Axial", type: SLICE_TYPE.AXIAL },
  coronal: { label: "Coronal", type: SLICE_TYPE.CORONAL },
  sagittal: { label: "Sagital", type: SLICE_TYPE.SAGITTAL },
};

// Los tipos de NiiVue 0.69 declaran el id de malla como numero, pero es un texto (uuid): el
// original de Polaris, en JS, lo pasa tal cual. Se convierte aqui, en un solo sitio.
const meshId = (id: unknown): number => id as number;
const LESION = rgb(palette.yellow);
const SELECTED = rgb(palette.green);
const BACKGROUND = rgb(anatomy.canvas).map((c) => c / 255);

function labelTable(summary: VolumeSegmentation, selected: number | null) {
  const R = [0];
  const G = [0];
  const B = [0];
  const A = [0];
  const I = [0];
  const labels = [""];
  summary.estructuras.forEach((structure) => {
    const { color, sliceAlpha } = look(structure.key);
    const [r, g, b] = color;
    const alpha = sliceAlpha;
    R.push(r);
    G.push(g);
    B.push(b);
    A.push(alpha);
    I.push(structure.etiqueta);
    labels.push(structure.nombre);
  });
  for (const lesion of summary.lesiones) {
    const [r, g, b] = lesion.id === selected ? SELECTED : LESION;
    R.push(r);
    G.push(g);
    B.push(b);
    A.push(255);
    I.push(10 + lesion.id);
    labels.push(`L${lesion.id}`);
  }
  return { R, G, B, A, I, labels };
}

export function VolumeViewer({ segmentation }: { segmentation: VolumeSegmentation }) {
  const slices = useRef<HTMLCanvasElement>(null);
  const render = useRef<HTMLCanvasElement>(null);
  const viewers = useRef<{ nv2: Niivue; nv3: Niivue } | null>(null);
  const [view, setView] = useState<View>("mpr");
  const [selected, setSelected] = useState<number | null>(null);
  const [cursor, setCursor] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (slices.current === null || render.current === null) return;
    const background = [...BACKGROUND, 1];
    const nv2 = new Niivue({
      backColor: background,
      crosshairColor: [...rgb(palette.green).map((c) => c / 255), 1],
      crosshairWidth: 1,
      isRadiologicalConvention: true,
      isOrientationTextVisible: true,
      isColorbar: false,
      isRuler: true,
      multiplanarShowRender: SHOW_RENDER.NEVER,
      dragMode: 1, // contraste: arrastrar cambia la ventana
    });
    const nv3 = new Niivue({
      backColor: background,
      show3Dcrosshair: true,
      isOrientCube: true,
      crosshairColor: [...rgb(palette.green).map((c) => c / 255), 1],
    });
    viewers.current = { nv2, nv3 };
    // Inspeccion local desde la consola del navegador, como en Polaris (`window.__visor`).
    (window as unknown as { __visor?: unknown }).__visor = { nv2, nv3 };
    let cancelled = false;
    const url = (name: string) => segmentationFileUrl(segmentation.ledger_index, name);
    (async () => {
      await nv2.attachToCanvas(slices.current as HTMLCanvasElement);
      await nv3.attachToCanvas(render.current as HTMLCanvasElement);
      nv2.setSliceType(SLICE_TYPE.MULTIPLANAR);
      nv2.opts.multiplanarLayout = MULTIPLANAR_TYPE.AUTO;
      // El lienzo 3D no tiene volumen: su extension es 0, NiiVue pide log10(0) decimales y
      // `toFixed` lanza en cada sincronizacion. Ese lienzo no informa del cursor; lo hace nv2.
      nv3.createOnLocationChange = () => undefined;
      nv2.broadcastTo(nv3, { "2d": true, "3d": false });
      nv3.broadcastTo(nv2, { "2d": true, "3d": false });
      nv2.onLocationChange = (data: unknown) => setCursor(String((data as { string?: string }).string ?? ""));
      const [low, high] = segmentation.ventana_hu;
      await nv2.loadVolumes([
        { url: url("ct.nii.gz"), colormap: "gray", cal_min: low, cal_max: high },
        { url: url("etiquetas.nii.gz"), opacity: 0.55 },
      ]);
      if (cancelled) return;
      nv2.volumes[1]?.setColormapLabel(labelTable(segmentation, null));
      nv2.updateGLVolume();
      // 3D: solo mallas; las etiquetas, invisibles, como espacio comun.
      await nv3.loadVolumes([{ url: url("etiquetas.nii.gz"), opacity: 0 }]);
      const meshes: { url: string; rgba255: number[]; name: string }[] = [];
      for (const lesion of segmentation.lesiones) {
        if (lesion.malla) meshes.push({ url: url(lesion.malla), rgba255: [...LESION, 255], name: `L${lesion.id}.ply` });
      }
      // Opacas primero, translucidas al final y de mas a menos opacas: NiiVue pinta la
      // transparencia en el orden de carga (Polaris cargaba el higado el ultimo por esto).
      const withMesh = segmentation.estructuras.filter((s) => s.malla);
      const ordered = [...withMesh].sort((a, b) => look(b.key).opacity - look(a.key).opacity);
      for (const structure of ordered) {
        const { color } = look(structure.key);
        meshes.push({ url: url(structure.malla as string), rgba255: [...color, 255], name: structure.malla as string });
      }
      await nv3.loadMeshes(meshes);
      if (cancelled) return;
      for (const mesh of nv3.meshes) {
        nv3.setMeshShader(meshId(mesh.id), "Phong");
        const structure = withMesh.find((s) => s.malla === mesh.name);
        const opacity = structure ? look(structure.key).opacity : 1;
        if (opacity < 1) nv3.setMeshProperty(meshId(mesh.id), "opacity", opacity);
      }
      nv3.setSliceType(SLICE_TYPE.RENDER);
      nv3.setRenderAzimuthElevation(210, 20);
    })().catch((reason: unknown) => setError(String(reason)));
    return () => {
      cancelled = true;
      viewers.current = null;
    };
  }, [segmentation]);

  useEffect(() => {
    viewers.current?.nv2.setSliceType(VIEWS[view].type);
  }, [view]);

  const select = (id: number) => {
    const current = viewers.current;
    const lesion = segmentation.lesiones.find((item) => item.id === id);
    if (current === null || lesion === undefined) return;
    setSelected(id);
    const { nv2, nv3 } = current;
    const ct = nv2.volumes[0];
    if (ct) nv2.scene.crosshairPos = nv2.vox2frac(ct.mm2vox(lesion.centro_mm) as Parameters<Niivue["vox2frac"]>[0]);
    nv2.volumes[1]?.setColormapLabel(labelTable(segmentation, id));
    nv2.updateGLVolume();
    for (const mesh of nv3.meshes) {
      if (mesh.name?.startsWith("L")) {
        nv3.setMeshProperty(meshId(mesh.id), "rgba255", mesh.name === `L${id}.ply` ? [...SELECTED, 255] : [...LESION, 255]);
      }
    }
    nv2.drawScene();
    nv3.drawScene();
  };

  return (
    <div className="volume-viewer">
      <p>
        <Mark pictogram="shape-triangle" color="yellow">
          {segmentation.estado} ({segmentation.segmentador ?? "segmentador local"}): lo que marca el
          modelo son candidatos a revisar por una persona, no hallazgos.
        </Mark>
      </p>
      {error !== null && (
        <p>
          <MarkOf mark={FAILURE_MARK}>{error}</MarkOf>
        </p>
      )}
      <div className="measure-actions">
        <FieldLabel concept="switchView">
          Vista{" "}
          <select value={view} onChange={(event) => setView(event.target.value as View)}>
            {(Object.keys(VIEWS) as View[]).map((key) => (
              <option key={key} value={key}>
                {VIEWS[key].label}
              </option>
            ))}
          </select>
        </FieldLabel>
        <span className="secondary num">{cursor}</span>
      </div>
      <div className="volume-canvases">
        <canvas ref={slices} aria-label="Cortes del volumen" />
        <canvas ref={render} aria-label="Superficies en 3D" />
      </div>
      <div className="quality-table">
      <table className="ledger" aria-label="Estructuras segmentadas">
        <thead>
          <tr>
            <Th concept="body">Estructura</Th>
            <Th concept="measure">Volumen (ml)</Th>
          </tr>
        </thead>
        <tbody>
          {segmentation.estructuras.map((structure) => (
            <tr key={structure.key}>
              <td>{structure.nombre}</td>
              <td className="num">{formatNumber(structure.volumen_ml, 1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
      {segmentation.lesiones.length > 0 && (
        <div className="quality-table">
        <table className="ledger" aria-label="Lesiones candidatas">
          <thead>
            <tr>
              <Th pictogram="blob">Lesión</Th>
              <Th concept="zone">Región</Th>
              <Th concept="measure">Diámetro axial (mm)</Th>
              <Th concept="measure">Volumen (ml)</Th>
              <Th concept="confidence">Acuerdo 2.º modelo</Th>
            </tr>
          </thead>
          <tbody>
            {segmentation.lesiones.map((lesion) => (
              <tr
                key={lesion.id}
                tabIndex={0}
                aria-selected={lesion.id === selected}
                onClick={() => select(lesion.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    select(lesion.id);
                  }
                }}
              >
                <th scope="row">L{lesion.id}</th>
                <td className="num">{lesion.region ?? "—"}</td>
                <td>
                  <span className="num">{formatNumber(lesion.diametro_mm, 1)}</span>
                  {lesion.pequena && (
                    <>
                      {" "}
                      <Mark pictogram="shape-triangle" color="yellow">
                        menos de 10 mm, fiabilidad baja
                      </Mark>
                    </>
                  )}
                </td>
                <td className="num">{formatNumber(lesion.volumen_ml, 2)}</td>
                <td className="num">
                  {lesion.acuerdo_2o_modelo === null ? "—" : `${formatNumber(lesion.acuerdo_2o_modelo * 100, 0)} %`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}
    </div>
  );
}
