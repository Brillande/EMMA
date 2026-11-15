import { useState } from "react";

import { CyclePanel } from "./CyclePanel";
import { SexForm } from "./SexForm";

/**
 * El sexo declarado y el panel del ciclo, juntos en la consola (lote «ciclo», integración).
 *
 * Por qué existe: tras firmar una declaración del sexo, el panel del ciclo tiene que volver a leer
 * (de «no aplica» a lo registrado), y el estado de la consola no cambia por eso. Este envoltorio
 * guarda solo ese contador, para no meter estado del ciclo en las consolas.
 *
 * `phaseBaseline` es la frase del backend (`cycle_phase.reason` de `/api/status`), tal cual.
 * En Tierra, `until` y `ground`: lo llegado hasta el corte del retardo, de solo lectura.
 */
export function CycleSection({
  subject,
  refreshKey,
  until,
  ground = false,
  phaseBaseline,
}: {
  subject: string;
  refreshKey: string;
  until?: Date | undefined;
  ground?: boolean;
  phaseBaseline?: string | null | undefined;
}) {
  const [declarations, setDeclarations] = useState(0);
  const key = `${refreshKey}|${declarations}`;
  return (
    <>
      <SexForm
        subject={subject}
        refreshKey={key}
        until={until}
        readOnly={ground}
        onDeclared={() => setDeclarations((n) => n + 1)}
      />
      <CyclePanel
        subject={subject}
        refreshKey={key}
        until={until}
        ground={ground}
        phaseBaseline={phaseBaseline}
      />
    </>
  );
}
