import type { Recommendation } from "../lib/api";
import { RecommendationCard, ResourceClarificationNote } from "./RecommendationCard";

/**
 * Las recomendaciones de un sitio (la consola, una region del modo anatomico), una tarjeta por
 * cada una, con la aclaracion de los recursos de a bordo dicha UNA vez en la cabecera.
 *
 * Por que existe: cada tarjeta repetia entera la misma aclaracion —lo declara una persona, EMMA
 * no lleva inventario, sin declarar no es disponible—. Quitarla de las tarjetas sin mas la habria
 * hecho depender de que cada pantalla se acordara de ponerla; aqui la lista la pone y avisa a sus
 * tarjetas de que ya esta dicha, y una tarjeta usada fuera de una lista la sigue llevando.
 */
export function RecommendationList({
  items,
  operator = "",
  following,
  onAdopt,
  onDecline,
  past = false,
}: {
  items: readonly Recommendation[];
  operator?: string;
  /** Las contramedidas con un seguimiento abierto. */
  following: ReadonlySet<string>;
  onAdopt?: (countermeasureId: string, by: string) => Promise<void>;
  onDecline?: (countermeasureId: string, by: string, reason: string) => Promise<void>;
  /** Las de un momento pasado: cada tarjeta, con su forma y sin su color (`RecommendationCard`). */
  past?: boolean;
}) {
  return (
    <>
      <ResourceClarificationNote items={items} />
      {items.map((item) => (
        <RecommendationCard
          key={`${item.domain}:${item.action}`}
          item={item}
          operator={operator}
          adopted={item.countermeasure !== null && following.has(item.countermeasure.id)}
          {...(onAdopt === undefined ? {} : { onAdopt })}
          {...(onDecline === undefined ? {} : { onDecline })}
          resourcesClarified
          past={past}
        />
      ))}
    </>
  );
}
