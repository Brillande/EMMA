import { useEffect, useState } from "react";

import { Fold } from "../components/Fold";
import { Mark } from "../components/Mark";
import { type PainOnSubjectSkeleton, type SubjectSkeleton, skeletonApi } from "../lib/api";
import { formatNumber } from "../lib/format";
import { tr } from "../lib/i18n";
import { MISSING_MARK } from "../lib/marks";
import { anatomy, palette } from "../lib/palette";
import { NO_STATE } from "./chain";
import { noticeTone, painIsOnThisFigure, skeletonImageUrl, sourceTone } from "./skeleton";

/**
 * Esqueleto de la region "huesos", vista anterior, con un punto en el centroide de cada hueso.
 * Sale del TAC que el tripulante tiene en su registro cuando hay una segmentacion del esqueleto
 * vigente (backend `volumes/skeleton_view.py`, con `proyecta_anterior` de Polaris); si no, es el
 * de referencia de BodyParts3D (CC BY 4.0, DBCLS). Cual de los dos se ve, de que asiento sale,
 * que huesos no trae y por que no se ve el propio lo dice la respuesta, y aqui se muestra tal
 * cual: la interfaz no redacta ese texto. Los puntos dicen donde esta cada hueso, no que le pasa
 * (el estado lo da el detalle de la region, al lado).
 *
 * Accesible: la imagen lleva el texto alternativo del backend y los huesos tambien se listan,
 * plegados. El color de los puntos es contenido de imagen anatomica (`anatomy.bone` con borde
 * `anatomy.canvas`), no una señal de la tabla F.5-1; un hueso cortado por el borde del estudio se
 * distingue por la forma (punto hueco), no por otro color.
 */
export function SkeletonFigure({ subject }: { subject: string }) {
  const [skeleton, setSkeleton] = useState<SubjectSkeleton | null>(null);
  const [pain, setPain] = useState<PainOnSubjectSkeleton | null>(null);
  useEffect(() => {
    skeletonApi
      .own(subject)
      .then(setSkeleton)
      .catch(() => setSkeleton(null));
    // Dolor referido, colocado con el ajuste de Polaris: azul de aviso (F.5-1 "Advisory"), no
    // ambar (precaucion). Dice donde se refirio, no que tiene el hueso.
    skeletonApi
      .pain(subject)
      .then(setPain)
      .catch(() => setPain(null));
  }, [subject]);
  if (skeleton === null) return null;
  const bones = Object.entries(skeleton.bones);
  const source = sourceTone(skeleton);
  // Las marcas se colocaron sobre UNA figura: si no es la que se esta viendo, no se pintan.
  const placed = pain !== null && painIsOnThisFigure(skeleton, pain) ? pain : null;
  const own = skeleton.source === "own-ct";
  const spineTone = noticeTone(skeleton.spine?.nivel ?? "");
  return (
    <figure className="skeleton-figure">
      <p role="status" aria-label={tr("Origen de la figura del esqueleto", "Source of the skeleton figure")}>
        <Mark pictogram={source.pictogram} color={source.color}>
          {source.word}
        </Mark>{" "}
        · {skeleton.label}
      </p>
      {skeleton.fallback_reason !== null && (
        <p>
          <Mark pictogram={source.pictogram} color={source.color}>
            {skeleton.fallback_reason}
          </Mark>
        </p>
      )}
      <div
        className="skeleton-image"
        style={{ aspectRatio: `${skeleton.width} / ${skeleton.height}` }}
      >
        <img src={skeletonImageUrl(skeleton)} alt={skeleton.alt} />
        {bones.map(([name, point]) => (
          <span
            key={name}
            className="skeleton-point"
            title={point.truncated ? tr(`${point.display} (cortado por el borde del estudio)`, `${point.display} (cut off by the edge of the study)`) : point.display}
            aria-hidden="true"
            style={{
              left: `${point.u * 100}%`,
              top: `${point.v * 100}%`,
              background: point.truncated ? "transparent" : anatomy.bone,
              borderColor: point.truncated ? anatomy.bone : anatomy.canvas,
            }}
          />
        ))}
        {placed?.marks.map((mark) => (
          <span
            key={mark.zone}
            className="skeleton-point pain-mark"
            title={tr(`${mark.display}: dolor referido`, `${mark.display}: reported pain`)}
            aria-hidden="true"
            style={{
              left: `${mark.u * 100}%`,
              top: `${mark.v * 100}%`,
              background: palette.blue,
              borderColor: anatomy.canvas,
            }}
          />
        ))}
      </div>
      {placed !== null && !placed.superposable && placed.reason !== null && (
        <p className="c-gray">
          <Mark pictogram="cross">{placed.reason}</Mark>
          {placed.error_px !== null && (
            <>
              {" "}
              {tr("Error medio", "Mean error")} <span className="num">{formatNumber(placed.error_px.mean)}</span> px;{" "}
              {tr("umbral", "threshold")} <span className="num">{formatNumber(placed.error_px.threshold)}</span> px.
            </>
          )}
        </p>
      )}
      {placed !== null && placed.superposable && placed.marks.length > 0 && (
        <ul className="drivers">
          {placed.marks.map((mark) => (
            <li key={mark.zone}>
              {/* La chincheta dice que la zona se coloco sobre la figura, en el azul de aviso. */}
              <Mark pictogram="pin" color="blue">
                {mark.display}
              </Mark>
              {mark.intensity !== null && (
                <>
                  {" "}
                  · {tr("intensidad", "intensity")} <span className="num">{formatNumber(mark.intensity)}</span>
                </>
              )}{" "}
              <span className="secondary">
                ({formatNumber(mark.reports)} {mark.reports === 1 ? tr("informe", "report") : tr("informes", "reports")} {tr("en", "in")}{" "}
                <span className="num">{formatNumber(placed.window_days)}</span> {tr("días", "days")})
              </span>
            </li>
          ))}
        </ul>
      )}
      {placed !== null && placed.outside_study.length > 0 && (
        <ul className="drivers" aria-label={tr("Dolor referido fuera del estudio", "Reported pain outside the study")}>
          {placed.outside_study.map((item) => (
            <li key={item.zone} className="c-cyan">
              <Mark pictogram={NO_STATE.pictogram}>{item.display}</Mark>
              {item.intensity !== null && (
                <>
                  {" "}
                  · {tr("intensidad", "intensity")} <span className="num">{formatNumber(item.intensity)}</span>
                </>
              )}
              . {item.reason}
            </li>
          ))}
        </ul>
      )}
      <figcaption className="secondary">
        {/* El triangulo amarillo acompana al pie de figura del TAC propio: la imagen es de
            referencia y no un diagnostico, y lo dice el texto del backend. */}
        {own ? (
          <Mark pictogram="shape-triangle" color="yellow">
            <span className="secondary">{skeleton.caption}</span>
          </Mark>
        ) : (
          skeleton.caption
        )}
        {own && skeleton.attribution !== null && <> {skeleton.attribution}.</>}
      </figcaption>
      {skeleton.spine !== null && skeleton.spine.nivel === "atencion" && skeleton.spine.aviso !== null && (
        <div role="status" aria-label={tr("Control de la cadena vertebral", "Spinal chain check")}>
          <p>
            <Mark pictogram={spineTone.pictogram} color={spineTone.color}>
              {skeleton.spine.aviso}
            </Mark>
          </p>
          <ul>
            {skeleton.spine.listas
              .filter((list) => list.nivel === "atencion")
              .map((list) => {
                const tone = noticeTone(list.nivel);
                return (
                  <li key={list.titulo}>
                    <Mark pictogram={tone.pictogram} color={tone.color}>
                      {list.titulo}: {list.elementos.join(", ")}
                    </Mark>
                  </li>
                );
              })}
          </ul>
        </div>
      )}
      {skeleton.notes.map((note) => (
        <p key={note}>
          <Mark pictogram={NO_STATE.pictogram} color={NO_STATE.color}>
            {note}
          </Mark>
        </p>
      ))}
      {/* Los dos plegables de lo que falta llevan como signo la marca de F.5-1 (el anillo
          punteado del dato ausente): el cian va solo en el dibujo, no en el rótulo entero, y el
          triángulo de abrir sigue en el color de cualquier plegable (`Fold mark`, §5.33.12). */}
      {skeleton.absent_bones.length > 0 && (
        <Fold data-ui="skeleton-no-voxels"
          mark={MISSING_MARK}
          label={
            <>
              {tr("Huesos sin vóxeles", "Bones with no voxels")} (<span className="num">{formatNumber(skeleton.absent_bones.length)}</span>)
            </>
          }
        >
          <ul className="drivers">
            {skeleton.absent_bones.map((bone) => (
              <li key={bone.name}>{bone.display}</li>
            ))}
          </ul>
        </Fold>
      )}
      {skeleton.truncated_bones.length > 0 && (
        <Fold data-ui="skeleton-cut-bones"
          mark={MISSING_MARK}
          label={
            <>
              {tr("Huesos cortados por el borde del estudio", "Bones cut off by the edge of the study")} (
              <span className="num">{formatNumber(skeleton.truncated_bones.length)}</span>)
            </>
          }
        >
          <ul className="drivers">
            {skeleton.truncated_bones.map((bone) => (
              <li key={bone.name}>{bone.display}</li>
            ))}
          </ul>
        </Fold>
      )}
      <Fold data-ui="skeleton-marked-bones"
        concept="markedBones"
        summaryClassName="secondary"
        label={
          <>
            {tr("Huesos señalados", "Marked bones")} (<span className="num">{formatNumber(bones.length)}</span>)
          </>
        }
      >
        <ul className="drivers">
          {bones.map(([name, point]) => (
            <li key={name}>{point.display}</li>
          ))}
        </ul>
      </Fold>
    </figure>
  );
}
