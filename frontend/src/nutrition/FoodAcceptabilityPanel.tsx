import { useEffect, useState } from "react";

import { BoardDetail } from "../components/BoardDetail";
import { BoardOnly, useLook } from "../components/BoardOnly";
import { Fold } from "../components/Fold";
import { IndicatorName } from "../components/IndicatorName";
import { Mark, MarkOf } from "../components/Mark";
import { Meter } from "../components/Meter";
import { ObservationTypeBadge } from "../components/ObservationTypeBadge";
import { StatTile } from "../components/StatTile";
import { Th } from "../components/Th";
import { Loading, Unavailable } from "../components/Unavailable";
import { type FoodAcceptability, nutritionApi } from "../lib/api";
import { formatNumber } from "../lib/format";
import { EMPTY_MARK, NO_MARK, type RequestOutcome, requestOutcome, UNAVAILABLE_MARK } from "../lib/marks";
import { foodView } from "./foodAcceptability";

/**
 * La comida frente a su criterio de aceptable, valoración a valoración.
 *
 * Cada valoración por debajo de 6,0 lleva la marca del backend, con la frase de NASA-STD-3001
 * Vol. 2 [V2 7002] y su página al lado (decisión del usuario del 2026-10-15). Es una marca
 * sobre la comida, no sobre la persona: no es una alerta y no lleva color de aviso. Aquí no se
 * redacta nada: el recuento, la regla, su alcance y la cifra de cada valoración son del backend.
 *
 * Dibujos (§5.32.7): el título con los cubiertos de la familia del indicador, la regla del
 * criterio con la escalera (escala graduada; sus nueve puntos los dice el texto), y la
 * valoración por debajo con el triángulo común, en el color del texto.
 *
 * Segunda pasada (§5.33.7): el libro abierto en «La frase de la norma» (lo leído en la fuente),
 * la escalera también en «Valoraciones, la última primero» (las valoraciones son puntos de esa
 * misma escala: un concepto, un dibujo), y el vocabulario común en las cabeceras: el reloj, la
 * almohadilla del valor, el tope del criterio y el sello de la procedencia.
 *
 * Plato a plato (§5.38.2, decisión del usuario del 2026-10-26): cada valoración lleva su alimento,
 * y «Por plato» enseña, del backend, cuántas veces se valoró cada uno, en cuántos días y cada
 * valoración en el tiempo. Descriptivo: sin umbral, sin veredicto y sin color; la marca sigue
 * siendo solo la del criterio. El plato lleva los cubiertos de la familia del indicador; las
 * valoraciones en el tiempo, la escalera de la escala (un concepto, un dibujo).
 *
 * De la primera a la última, y la fracción rechazada (§5.39.15, 2026-10-31): bajo el nombre del
 * plato, la frase del backend con la fracción rechazada anotada con ese nombre (o sus palabras
 * para «sin declarar»); sobre su serie, la frase que compara la primera y la última valoración.
 * Texto secundario, sin dibujo nuevo, sin color y sin flecha: dos cifras no son un veredicto.
 *
 * Tablero (decisión del usuario, 2026-11-07): bajo la concha de la maqueta, dos fichas con cifra
 * junto al recuento del backend (`FoodTiles`): cuántas valoraciones hay (`rated`) y cuántas quedan
 * por debajo del criterio (`below`), esta con el medidor neutro de una sobre la otra. La escala del
 * medidor es la propia serie (las valoradas), ninguna otra; sin criterio leído el backend no da
 * `below`, y la ficha lo dice con la marca de «no disponible» en vez de pintar un cero. Sin ninguna
 * valoración no hay fichas: la frase del backend con su marca de registro vacío ya lo dice, y un
 * «0» grande la repetiría.
 */

/** El indicador de este panel: su API es la de la aceptabilidad de la comida, y solo esa. */
const INDICATOR = "food-acceptability";

function Title() {
  return (
    <h2>
      <IndicatorName indicatorKey={INDICATOR} displayEs="Aceptabilidad de la comida" />
    </h2>
  );
}

/** Las dos fichas del tablero: valoradas, y por debajo del criterio sobre las valoradas. */
function FoodTiles({ data, stale }: { data: FoodAcceptability; stale: boolean }) {
  if (data.rated <= 0) return null;
  const below = data.below;
  return (
    <div className="board-stats food-board" role="group" aria-label="Valoraciones frente al criterio">
      <StatTile concept="value" label="Valoradas" value={data.rated} stale={stale} />
      {below === null ? (
        <StatTile
          concept="limits"
          label="Por debajo del criterio"
          value={null}
          status={{ mark: UNAVAILABLE_MARK, word: "sin criterio leído" }}
          stale={stale}
        />
      ) : (
        <StatTile concept="limits" label="Por debajo del criterio" value={below} unit={`de ${formatNumber(data.rated)}`} stale={stale}>
          {/* Un `below` negativo o mayor que `rated` sería un dato incoherente del backend: la cifra escrita lo
              diría y el medidor, que lanzaría, no se monta. */}
          {below >= 0 && below <= data.rated && (
            <Meter value={below} max={data.rated} label="Valoraciones por debajo del criterio sobre las valoradas" stale={stale} />
          )}
        </StatTile>
      )}
    </div>
  );
}

export function FoodAcceptabilityPanel({
  subject,
  refreshKey,
}: {
  subject: string;
  /** Cambia cuando cambian los datos del estado: entonces se vuelve a leer. */
  refreshKey: string;
}) {
  const [data, setData] = useState<FoodAcceptability | null>(null);
  const [unavailable, setUnavailable] = useState<RequestOutcome | null>(null);

  // Otro tripulante: lo pintado era del anterior. Hasta que llega lo suyo, «Cargando…», no las
  // valoraciones del otro como si fueran suyas (ni, si falla, como suyas caducadas).
  useEffect(() => {
    setData(null);
    setUnavailable(null);
  }, [subject]);

  useEffect(() => {
    let alive = true;
    nutritionApi
      .foodAcceptability(subject)
      .then((body) => {
        if (!alive) return;
        setData(body);
        setUnavailable(null);
      })
      .catch((reason: unknown) => {
        if (alive) setUnavailable(requestOutcome(reason));
      });
    return () => {
      alive = false;
    };
  }, [subject, refreshKey]);

  return <FoodAcceptabilityView data={data} unavailable={unavailable} />;
}

/** Solo pinta. Separado de la carga para poder probar lo que se lee en pantalla. */
export function FoodAcceptabilityView({
  data,
  unavailable,
}: {
  data: FoodAcceptability | null;
  unavailable: RequestOutcome | null;
}) {
  // En el tablero (2026-11-08, una pantalla por sección): el recuento, las fichas y la regla
  // arriba; su alcance, la frase de la norma y las tablas, en un «Ver detalle».
  const board = useLook() === "reference";
  if (data === null) {
    return (
      <section data-ui="food-acceptability" className="panel" aria-label="Aceptabilidad de la comida">
        <Title />
        {unavailable !== null ? (
          <Unavailable outcome={unavailable} />
        ) : (
          <Loading />
        )}
      </section>
    );
  }
  const view = foodView(data);
  // Si la última lectura falló, lo que queda es la de antes: caducado. Además del «Sin datos» con
  // la marca de la petición, la cursiva en sus cifras (la tercera señal, §5.33).
  const stale = unavailable !== null;
  const numClass = stale ? "num stale" : "num";
  const criterion = view.criterion;
  const rule = criterion !== null && (
    <p className="secondary">
      <Mark pictogram="stairs">{criterion.rule}</Mark>
    </p>
  );
  // Lo que se lee: el alcance de la regla y su frase, lo que no se mide, y las valoraciones
  // por plato y una a una (sus pliegues de siempre).
  const reading = (
    <>
      {view.criterion !== null && (
        <>
          <p className="secondary">{view.criterion.scope}</p>
          <Fold data-ui="food-standard" concept="sourceText" label="La frase de la norma">
            <ul className="evidence">
              <li>
                {view.criterion.quote.label}
                <div>
                  <q lang={view.criterion.language}>{view.criterion.quote.quote}</q>
                </div>
                <div>
                  {view.criterion.quote.origin}
                  {view.criterion.quote.url !== null && (
                    <span className="num url"> · {view.criterion.quote.url}</span>
                  )}
                </div>
              </li>
            </ul>
            <p className="secondary">{view.criterion.appliesTo}</p>
          </Fold>
        </>
      )}
      {view.notMeasured !== null && <p className="secondary">{view.notMeasured}</p>}
    </>
  );
  const tables = (
    <>
      {view.dishes !== null && view.dishes.rows.length > 0 && (
        <Fold data-ui="food-dishes" concept="ratings" label="Por plato" data-food-dishes>
          <p className={stale ? "secondary stale" : "secondary"}>{view.dishes.statement}</p>
          <p className="secondary">{view.dishes.repetition}</p>
          {view.dishes.changeNote !== null && <p className="secondary">{view.dishes.changeNote}</p>}
          {view.dishes.rejectedNote !== null && <p className="secondary">{view.dishes.rejectedNote}</p>}
          <p className="secondary">{view.dishes.grouping}</p>
          {view.dishes.withoutFood !== null && <p className="secondary">{view.dishes.withoutFood}</p>}
          <div className="quality-table">
            <table className="ledger">
              <thead>
                <tr>
                  <Th pictogram="fork-knife">Plato</Th>
                  <Th concept="value">Veces</Th>
                  <Th concept="date">Días distintos</Th>
                  <Th concept="ratings">Valoraciones en el tiempo</Th>
                </tr>
              </thead>
              <tbody>
                {view.dishes.rows.map((dish) => (
                  <tr key={dish.key} data-food-dish={dish.food}>
                    <th scope="row">
                      {dish.food}
                      <div className="secondary">{dish.statement}</div>
                      {/* La fracción rechazada anotada con este plato, o las palabras del backend
                          para «sin declarar». Sin color: no es una marca sobre nadie. */}
                      {dish.rejected !== null && (
                        <div className={stale ? "secondary stale" : "secondary"} data-food-rejected>
                          {dish.rejected}
                        </div>
                      )}
                    </th>
                    <td className={numClass}>{dish.times}</td>
                    <td className={numClass}>{dish.days}</td>
                    <td>
                      {/* De la primera a la última, con las palabras del backend: ni flecha ni
                          color, porque dos cifras no son un veredicto. */}
                      {dish.change !== null && (
                        <p className={stale ? "secondary stale" : "secondary"} data-food-change>
                          {dish.change}
                        </p>
                      )}
                      <ol className="food-series">
                        {dish.series.map((point) => (
                          <li key={point.key}>
                            <span className={numClass}>{point.when}</span>{" "}
                            <span className={numClass}>{point.value}</span>
                            {point.mark !== null && (
                              <>
                                {" "}
                                <Mark pictogram={point.mark.mark.pictogram} color={point.mark.mark.color}>
                                  {point.mark.text}
                                </Mark>
                              </>
                            )}
                          </li>
                        ))}
                      </ol>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Fold>
      )}
      {view.dishes !== null && view.dishes.rows.length === 0 && view.dishes.withoutFood !== null && (
        <p className="secondary">
          {view.dishes.statement} {view.dishes.withoutFood}
        </p>
      )}
      {view.rows.length > 0 && (
        <Fold data-ui="food-ratings" concept="ratings" label="Valoraciones, la última primero">
          {view.shown !== null && <p className={stale ? "secondary stale" : "secondary"}>{view.shown}</p>}
          <div className="quality-table">
            <table className="ledger">
              <thead>
                <tr>
                  <Th concept="time">Hora</Th>
                  <Th pictogram="fork-knife">Alimento</Th>
                  <Th concept="value">Valoración</Th>
                  <Th concept="limits">Frente al criterio</Th>
                  <Th concept="provenance">Procedencia</Th>
                </tr>
              </thead>
              <tbody>
                {view.rows.map((row) => (
                  <tr key={row.key} data-food-below={row.mark !== null ? "yes" : "no"}>
                    <td className={numClass}>{row.when}</td>
                    {/* El alimento firmado; sin él, la palabra del backend con «no disponible». */}
                    <td data-food-item={row.hasFood ? "named" : "missing"}>
                      <MarkOf mark={row.hasFood ? NO_MARK : UNAVAILABLE_MARK}>{row.food}</MarkOf>
                    </td>
                    <td className={numClass}>{row.value}</td>
                    {/* Sin color de aviso: marcar la comida no es avisar de nada sobre la persona. */}
                    <td>
                      {row.mark !== null && (
                        <Mark pictogram={row.mark.mark.pictogram} color={row.mark.mark.color}>
                          {row.mark.text}
                        </Mark>
                      )}
                    </td>
                    <td>
                      <ObservationTypeBadge
                        type={row.observationType}
                        context={row.evidenceContext}
                      />{" "}
                      · {row.source}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Fold>
      )}
    </>
  );
  return (
    <section data-ui="food-acceptability" className="panel" aria-label="Aceptabilidad de la comida" data-food-acceptability>
      <Title />
      {view.empty ? (
        // Sin valoraciones: el recuento del backend con la marca de registro vacío (§5.34.14), la
        // del diario: no falta un dato que debiera estar, es que aún no se ha anotado ninguna.
        <p>
          <MarkOf mark={EMPTY_MARK} stale={stale}>
            {view.statement}
          </MarkOf>
        </p>
      ) : (
        <p className={stale ? "stale" : undefined}>{view.statement}</p>
      )}
      <BoardOnly>
        <FoodTiles data={data} stale={stale} />
      </BoardOnly>
      {rule}
      {board ? (
        <>
          {unavailable !== null && <Unavailable outcome={unavailable} />}
          {/* Sin nada que leer (ni regla, ni nota, ni valoraciones) no hay mando vacío. */}
          {(criterion !== null || view.notMeasured !== null || view.dishes !== null || view.rows.length > 0) && (
            <BoardDetail label="la regla, su fuente y las valoraciones">
              {reading}
              {tables}
            </BoardDetail>
          )}
        </>
      ) : (
        <>
          {reading}
          {unavailable !== null && <Unavailable outcome={unavailable} />}
          {tables}
        </>
      )}
    </section>
  );
}
