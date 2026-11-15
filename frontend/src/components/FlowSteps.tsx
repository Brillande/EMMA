import { stepMark } from "../habitat/flow";
import type { HypothesisStep } from "../lib/api";
import { MarkOf } from "./Mark";

/**
 * Los pasos de un flujo con su estado: nombre, marca del estado y frase, los tres del backend.
 *
 * Por qué existe: los pasos de una hipótesis de cabina (`analysis/context.py`, §7) y los de una
 * alerta (`analysis/alert_flow.py`, base de conocimiento §10, §5.34.6) siguen la misma convención
 * —mismos estados, mismas palabras, misma marca (`stepMark`)—, y dos copias de esta lista la
 * dejarían derivar. Aquí no se deduce ningún estado: uno desconocido sale con su palabra y sin
 * significado propio.
 */
export function FlowSteps({ steps }: { steps: readonly HypothesisStep[] }) {
  return (
    <ol>
      {steps.map((step) => (
        <li key={step.key}>
          <strong>{step.name}</strong> <MarkOf mark={stepMark(step.state)}>{step.state_display}</MarkOf>
          <span className="secondary"> · {step.detail}</span>
        </li>
      ))}
    </ol>
  );
}
