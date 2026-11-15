import { Mark } from "../components/Mark";
import type { EvidenceGrade } from "../lib/api";
import { gradeMark } from "./sourceMarks";
import { tr } from "../lib/i18n";

/**
 * Nivel de evidencia de una fuente, tal como lo calcula el backend desde el registro de PubMed
 * (`app/evidence/tier.py`, portado de Polaris). La interfaz no lo redacta ni lo reinterpreta.
 * Si la fuente no tiene registro y el nivel se leyo de su texto, la etiqueta del backend ya lo
 * dice ("desde el texto de la cita, no del registro"): aqui no se pone ni se recorta nada.
 *
 * Preclinico en amarillo: es la advertencia de alcance (un estudio en animales no respalda lo
 * mismo que uno en personas), igual que el "Alcance" de la evidencia de las recomendaciones.
 * "Desconocido" en gris: no disponible, que es lo que significa ese color en la tabla F.5-1.
 * El dibujo es el del diseno del estudio (`sourceMarks.ts`), junto a la palabra y nunca solo.
 */
export function SourceGrade({ grade }: { grade: EvidenceGrade }) {
  const look = gradeMark(grade);
  return (
    <Mark
      pictogram={look.pictogram}
      color={look.color}
      className={look.color === null ? "secondary" : undefined}
      title={grade.reason}
    >
      {tr("Nivel:", "Level:")} {grade.label}
    </Mark>
  );
}
