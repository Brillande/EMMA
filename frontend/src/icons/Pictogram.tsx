import type { PictogramElement } from "./types";
import { type PictogramName, pictogram } from "./registry";

/**
 * Un pictograma como SVG en línea, del tamaño de la letra y del color del texto que lo rodea.
 *
 * Es el único sitio de la interfaz que escribe `<svg>` con trazos (la excepción declarada es el
 * calibre de la ecografía, que dibuja medidas sobre la imagen, no pictogramas). Va oculto al
 * lector de pantalla y sin `<title>`: la palabra de al lado es el texto accesible, y un segundo
 * texto la contradiría o la repetiría. `data-pictogram` lleva el nombre para las pruebas.
 */
export function Pictogram({ name, className }: { name: PictogramName; className?: string | undefined }) {
  const def = pictogram(name);
  return (
    <svg
      className={className === undefined ? "pictogram" : `pictogram ${className}`}
      viewBox="0 0 24 24"
      width="1em"
      height="1em"
      aria-hidden="true"
      focusable="false"
      fill="none"
      stroke="currentColor"
      strokeWidth={def.strokeWidth ?? 2}
      strokeLinecap="round"
      strokeLinejoin="round"
      data-pictogram={name}
    >
      {def.elements.map((element, index) => (
        <Element key={index} element={element} />
      ))}
    </svg>
  );
}

/**
 * Tramos de 4,19: doce sobre un anillo de r = 8 (perímetro 50,27), que cierran sin tramo roto.
 * Con extremos rectos, no redondeados: un extremo redondeado alarga cada tramo una unidad por
 * lado y a 12 px se come el hueco.
 */
const DASH_ARRAY = "4.19 4.19";

function Element({ element }: { element: PictogramElement }) {
  const fill = "fill" in element && element.fill === true ? "currentColor" : undefined;
  const dashed = "dashed" in element && element.dashed === true;
  const stroke = dashed ? { strokeDasharray: DASH_ARRAY, strokeLinecap: "butt" as const } : {};
  switch (element.kind) {
    case "path":
      return <path d={element.d} fill={fill} {...stroke} />;
    case "circle":
      return <circle cx={element.cx} cy={element.cy} r={element.r} fill={fill} {...stroke} />;
    case "rect":
      return (
        <rect x={element.x} y={element.y} width={element.width} height={element.height} fill={fill} />
      );
    case "line":
      return <line x1={element.x1} y1={element.y1} x2={element.x2} y2={element.y2} />;
    case "polygon":
      return <polygon points={element.points} fill={fill} />;
    case "polyline":
      return <polyline points={element.points} />;
  }
}
