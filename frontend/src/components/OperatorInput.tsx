import { tr } from "../lib/i18n";

/**
 * El campo de quien firma en consola, el que queda a la vista con la privacidad puesta (§5.41).
 *
 * Por qué existe: con la privacidad, el nombre de quien firma va difuminado en pantalla, pero un
 * difuminado es CSS y el lector de pantalla lee el valor del campo igual, en voz alta, delante de
 * quien la privacidad quería dejar fuera. Los demás campos de firma están en paneles que la
 * privacidad tapa con `inert`; este no, porque está junto a las alertas, que se dejan a la vista.
 * Así que con la privacidad el campo también es `inert`: fuera del foco y del lector, como lo
 * tapado. El nombre ya escrito sigue firmando (se guarda en el equipo, `lib/operator.ts`), así que
 * se puede reconocer una alerta con la privacidad puesta; escribir otro nombre pide quitarla.
 *
 * No se usa un campo de contraseña: el navegador ofrecería guardar o rellenar una contraseña con
 * el nombre del tripulante, y lo rellenado acabaría firmado en el registro.
 */
export function OperatorInput({
  value,
  onChange,
  privacy,
}: {
  value: string;
  onChange: (value: string) => void;
  privacy: boolean;
}) {
  return (
    <input
      value={value}
      maxLength={64}
      inert={privacy}
      onChange={(event) => onChange(event.target.value)}
      placeholder={tr("nombre o indicativo", "name or call sign")}
    />
  );
}
