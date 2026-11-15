import {
  Fragment,
  type ReactNode,
  type RefObject,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";

import { OFF, type WakeState, microphoneOpen, wakeLabel } from "../assistant/wake/machine";
import { useWakeWord } from "../assistant/wake/useWakeWord";
import { type LiveMessage, appendMessages } from "../lib/announce";
import type { FaceUnavailable } from "../lib/faceCamera";
import {
  type CompanyEvent,
  NO_COMPANY,
  PROPOSAL_TEXT,
  type PresenceNotice,
  companyStep,
  presenceNotice,
  presenceText,
} from "../lib/faceCompany";
import { type FaceStatus, cameraIsOn, faceHoldsView, faceRotation, faceStatusOf } from "../lib/faceOrientation";
import { formatNumber, formatUtc } from "../lib/format";
import { LANGUAGES, type Language, chooseLanguage, language, tr } from "../lib/i18n";
import { LOADING_MARK, UNAVAILABLE_MARK, mark } from "../lib/marks";
import { PRIVATE_NAME_HIGHLIGHT, nameRangesIn, namesMaskable } from "../lib/privacyNames";
import {
  type OrientationReading,
  type SensorSource,
  type SensorStatus,
  type UpReference,
  followQuadrant,
  requestOrientationPermission,
  upReference,
  viewAngle,
  watchOrientation,
} from "../lib/orientation";
import { uiPictogram } from "../lib/uiMarks";
import { setUpAngle, upArrowDegrees, useUpAngle } from "../lib/upAngle";
import { Pictogram } from "../icons";
import { Chosen } from "./Chosen";
import {
  DEFAULT_MODES,
  type DisplayModes,
  ROTATIONS,
  type Rotation,
  browserStore,
  readDisplayOpen,
  readModes,
  writeDisplayOpen,
  writeModes,
} from "./displayModes";
import { Fold } from "./Fold";
import { Mark, MarkOf } from "./Mark";
import { ProactiveControls, useSilence } from "../assistant/ProactiveControls";
import { VoiceUnavailable, useVoiceAvailability } from "./ReadAloud";

/**
 * La cámara encendida, en el borde de arriba mientras lo está: azul, «aviso» de la tabla F.5-1
 * (*advisory*). No es una alerta ni un fallo (rojo, amarillo), ni un dato ausente (cian) ni algo
 * no disponible (gris): es algo que la persona tiene que saber en todo momento.
 */
export const CAMERA_ON_MARK = mark(uiPictogram("cameraOn"), "blue");

/**
 * El micrófono abierto por el modo «Escuchar "EMMA"», en el mismo sitio y color que la cámara: el
 * mismo micrófono del aviso «Micrófono abierto» de pulsar y hablar (`assistant/`).
 */
export const MICROPHONE_ON_MARK = mark(uiPictogram("microphone"), "blue");

/**
 * Los mandos de la pantalla (§5.40): baja visión, esencial, girar (a mano, siguiendo el
 * giroscopio, `lib/orientation.ts`, o siguiendo la cara, `lib/faceOrientation.ts`), privacidad y voz. Son de las dos
 * consolas y de la carcasa, así que viajan por contexto desde `App.tsx`, no por cada panel.
 *
 * Cada mando dice su estado con `aria-pressed`, con el anillo con punto de «elegido» y con la
 * negrita y el borde de `button.command[aria-pressed="true"]`: nunca solo con el color (F.5.10 e).
 * Los rótulos son de navegación, no clínicos.
 */

export interface DisplayModesValue {
  modes: DisplayModes;
  update: (patch: Partial<DisplayModes>) => void;
  /** Cómo va el sensor de giro; sin él (pruebas, contexto de partida), apagado. */
  sensor?: SensorStatus;
  /** De dónde salen las lecturas y desde cuándo vale el «arriba» de ahora (hora del equipo). */
  sensorSource?: SensorSource | null;
  upSince?: Date | null;
  /**
   * «Esto es arriba»: la vista con el giro `base` (el de ahora si no se da) queda como derecha
   * para la posición de la tableta en este momento.
   */
  markUp?: (base?: Rotation) => void;
  /** Cómo va el seguimiento de la cara; sin él, apagado. */
  face?: FaceStatus;
  /** Por qué no hay cámara, si no la hay. */
  faceProblem?: FaceUnavailable | null;
  /**
   * Si la privacidad sabe tapar solo los nombres dentro de las frases (`lib/privacyNames.ts`).
   * Sin la API de resaltado (`false`), la privacidad tapa también las secciones de estado general.
   * Ausente cuenta como que sí: lo fija `App.tsx` según el navegador.
   */
  namesMasked?: boolean;
  /** Cómo va la escucha de la palabra «EMMA» (`assistant/wake/`); sin él, apagada. */
  wake?: WakeState;
  /** El aviso de otra persona delante (`lib/faceCompany.ts`, demostración); sin él, ninguno. */
  presence?: PresenceNotice;
  /** Lo que el lector de pantalla tiene que decir de ese aviso, en su región viva. */
  presenceMessages?: readonly LiveMessage[];
  /** La respuesta a la propuesta: `true` pone la privacidad, `false` la deja como está. */
  answerPresence?: (accept: boolean) => void;
}

/**
 * Tapa en `root` cada aparición exacta de `names` mientras `active` (§5.40): un resaltado de CSS
 * por encima del texto, sin tocar el DOM que pinta React. Se rehace cuando cambia el contenido
 * (llega un estado, se abre una pestaña), una vez por fotograma como mucho.
 */
export function usePrivateNameMask(root: RefObject<HTMLElement | null>, active: boolean, names: () => string[]) {
  const latest = useRef(names);
  latest.current = names;
  useEffect(() => {
    const element = root.current;
    if (!active || element === null || !namesMaskable()) return;
    let frame: number | null = null;
    const paint = () => {
      frame = null;
      CSS.highlights.set(PRIVATE_NAME_HIGHLIGHT, new Highlight(...nameRangesIn(element, latest.current())));
    };
    paint();
    const observer = new MutationObserver(() => {
      if (frame === null) frame = requestAnimationFrame(paint);
    });
    observer.observe(element, { childList: true, subtree: true, characterData: true });
    return () => {
      observer.disconnect();
      if (frame !== null) cancelAnimationFrame(frame);
      CSS.highlights.delete(PRIVATE_NAME_HIGHLIGHT);
    };
  }, [root, active]);
}

export const DisplayModesContext = createContext<DisplayModesValue>({
  modes: DEFAULT_MODES,
  update: () => undefined,
});

/** El estado de los modos, leído del equipo y guardado en él con cada cambio. */
export function useStoredDisplayModes(): DisplayModesValue {
  // La cámara no se enciende sola al arrancar, aunque se cerrara con el modo puesto: delante puede
  // estar otra persona. «Seguir la cara» se guarda como los demás modos, pero cada sesión empieza
  // con él apagado y lo enciende un gesto de quien mira.
  // El micrófono, igual: cada sesión empieza sin escuchar la palabra «EMMA».
  // Y la privacidad automática con otra cara, que va con la cámara: la enciende quien mira.
  const [modes, setModes] = useState<DisplayModes>(() => ({
    ...readModes(browserStore()),
    followFace: false,
    wakeWord: false,
    autoPrivacy: false,
  }));
  const update = useCallback((patch: Partial<DisplayModes>) => {
    setModes((current) => {
      const next = { ...current, ...patch };
      // Poner la privacidad apaga la cámara, y no se enciende mientras esté puesta.
      if (next.privacy) next.followFace = false;
      // Y el micrófono: con la privacidad puesta no se escucha.
      if (next.privacy) next.wakeWord = false;
      writeModes(browserStore(), next);
      return next;
    });
  }, []);
  // Mientras la cara manda (`faceHoldsView`), el giroscopio no gira la vista.
  const faceHolds = useRef(false);
  const { sensor, sensorSource, upSince, markUp, anchor } = useSensorRotation(
    modes.followSensor,
    modes.rotation,
    update,
    faceHolds,
  );
  const { presence, presenceMessages, answerPresence, company } = usePresence(modes, update);
  const { face, faceProblem } = useFaceRotation(
    modes.followFace && !modes.privacy,
    modes.rotation,
    update,
    faceHolds,
    anchor,
    company,
  );
  const switchWakeOff = useCallback(() => update({ wakeWord: false }), [update]);
  const wake = useWakeWord(modes, switchWakeOff);
  return {
    modes,
    update,
    sensor,
    sensorSource,
    upSince,
    markUp,
    face,
    faceProblem,
    wake,
    presence,
    presenceMessages,
    answerPresence,
  };
}

/** Lo que la búsqueda de caras le cuenta a `usePresence`. */
type CompanySignal = Exclude<CompanyEvent, null> | "cameraOff";

/**
 * Otra persona delante (`lib/faceCompany.ts`, demostración): el aviso de la franja, lo que oye el
 * lector de pantalla (una región viva, `lib/announce.ts`) y la privacidad. Al llegar alguien, con
 * «Privacidad automática con otra cara» se pone la privacidad, que apaga la cámara (la regla de
 * `update`); sin él, solo se propone. Lo decide la persona: la privacidad puesta sola se queda
 * hasta que ella la quite, y la cámara no se vuelve a encender sola.
 */
function usePresence(
  modes: DisplayModes,
  update: (patch: Partial<DisplayModes>) => void,
): {
  presence: PresenceNotice;
  presenceMessages: readonly LiveMessage[];
  answerPresence: (accept: boolean) => void;
  company: (signal: CompanySignal) => void;
} {
  const [presence, setPresence] = useState<PresenceNotice>(null);
  const [presenceMessages, setPresenceMessages] = useState<LiveMessage[]>([]);
  const nextId = useRef(0);
  // Lo de ahora, leído cuando llega alguien: la búsqueda de caras no se rehace por cambiarlo.
  const auto = useRef(modes.autoPrivacy);
  auto.current = modes.autoPrivacy;

  const company = useCallback(
    (signal: CompanySignal) => {
      if (signal !== "arrived") {
        setPresence((current) => presenceNotice(current, { kind: signal }));
        return;
      }
      const protect = auto.current;
      setPresence((current) => presenceNotice(current, { kind: "arrived", auto: protect }));
      const id = nextId.current;
      nextId.current += 1;
      setPresenceMessages((current) => appendMessages(current, [presenceText(protect ? "protected" : "proposed")], id));
      if (protect) update({ privacy: true });
    },
    [update],
  );

  const answerPresence = useCallback(
    (accept: boolean) => {
      setPresence((current) => presenceNotice(current, { kind: accept ? "accepted" : "dismissed" }));
      if (accept) update({ privacy: true });
    },
    [update],
  );

  // Quitar la privacidad, por el mando, el asistente o como sea, quita el aviso de «puesta sola».
  useEffect(() => {
    if (!modes.privacy) setPresence((current) => presenceNotice(current, { kind: "privacyOff" }));
  }, [modes.privacy]);

  return { presence, presenceMessages, answerPresence, company };
}

/** Si la ventana se ve: oculta (otra pestaña, minimizada, pantalla apagada), la cámara se apaga. */
function usePageVisible(): boolean {
  const [visible, setVisible] = useState(() => typeof document === "undefined" || document.visibilityState !== "hidden");
  useEffect(() => {
    const changed = () => setVisible(document.visibilityState !== "hidden");
    document.addEventListener("visibilitychange", changed);
    return () => document.removeEventListener("visibilitychange", changed);
  }, []);
  return visible;
}

/**
 * El giro que sigue la cara (`lib/faceOrientation.ts`, demostración). La cámara solo está
 * encendida mientras el modo lo está, la privacidad no y la ventana se ve; el módulo de la cámara y
 * el detector se cargan al encenderlo por primera vez. Como con el sensor, solo escribe el giro
 * cuando cambia de cuadrante, y el estado solo cuando cambia.
 */
function useFaceRotation(
  active: boolean,
  rotation: Rotation,
  update: (patch: Partial<DisplayModes>) => void,
  holds: RefObject<boolean>,
  anchor: (base: Rotation, angle?: number) => void,
  company: (signal: CompanySignal) => void,
): { face: FaceStatus; faceProblem: FaceUnavailable | null } {
  const [face, setFace] = useState<FaceStatus>("off");
  const [faceProblem, setFaceProblem] = useState<FaceUnavailable | null>(null);
  const visible = usePageVisible();
  const current = useRef<Rotation>(rotation);
  const on = active && visible;

  useEffect(() => {
    current.current = rotation;
  }, [rotation]);

  useEffect(() => {
    holds.current = false;
    setFaceProblem(null);
    setUpAngle("face", null);
    if (!on) {
      setFace("off");
      return undefined;
    }
    setFace("starting");
    let cancelled = false;
    // Cuántas caras, de una búsqueda a la siguiente; cada vez que se enciende la cámara, de cero.
    let others = NO_COMPANY;
    let stop = (): void => undefined;
    const unavailable = (why: FaceUnavailable) => {
      holds.current = false;
      setUpAngle("face", null);
      setFaceProblem(why);
      setFace("unavailable");
    };
    import("../lib/faceCamera").then(
      ({ watchFace }) => {
        if (cancelled) return;
        stop = watchFace({
          started: () => setFace("noFace"),
          reading: (reading) => {
            const status = faceStatusOf(reading);
            setFace(status);
            holds.current = faceHoldsView(status);
            // La flecha de «arriba» sigue el ángulo de la cara grado a grado, no el cuadrante.
            setUpAngle("face", reading.kind === "one" ? reading.angle : null);
            const next = faceRotation(current.current, reading);
            if (next !== current.current) {
              current.current = next;
              update({ rotation: next });
            }
            // La cara fija el «arriba» del giroscopio en cada búsqueda: si deja de verse, sigue él
            // desde aquí sin salto.
            if (holds.current) anchor(current.current, reading.kind === "one" ? reading.angle : undefined);
            // Solo cuántas caras: si hay otra persona delante un rato, o si se ha ido.
            const step = companyStep(others, reading, performance.now());
            others = step.state;
            if (step.event !== null) company(step.event);
          },
          unavailable,
        });
      },
      () => {
        if (!cancelled) unavailable("sin modelo");
      },
    );
    return () => {
      cancelled = true;
      stop();
      holds.current = false;
      setUpAngle("face", null);
      // Con la cámara apagada ya no se sabe quién hay delante: una propuesta pendiente se va.
      company("cameraOff");
    };
  }, [on, update, holds, anchor, company]);

  return { face, faceProblem };
}

/**
 * El giro que sigue al sensor (`lib/orientation.ts`). Vive una sola vez, con el estado de los
 * modos, aunque los mandos se pinten en dos sitios. Solo escribe el giro cuando cambia de
 * cuadrante, no con cada lectura. Mientras `faceHolds` (la cara manda), lee pero no gira; la cara
 * le fija el «arriba» con `anchor`.
 */
function useSensorRotation(
  follow: boolean,
  rotation: Rotation,
  update: (patch: Partial<DisplayModes>) => void,
  faceHolds: RefObject<boolean>,
): {
  sensor: SensorStatus;
  sensorSource: SensorSource | null;
  upSince: Date | null;
  markUp: (base?: Rotation) => void;
  anchor: (base: Rotation, angle?: number) => void;
} {
  const [sensor, setSensor] = useState<SensorStatus>("off");
  const [sensorSource, setSensorSource] = useState<SensorSource | null>(null);
  const [upSince, setUpSince] = useState<Date | null>(null);
  const current = useRef<Rotation>(rotation);
  const reference = useRef<UpReference | null>(null);
  const pendingBase = useRef<Rotation>(rotation);
  const last = useRef<OrientationReading | null>(null);

  useEffect(() => {
    current.current = rotation;
  }, [rotation]);

  useEffect(() => {
    reference.current = null;
    last.current = null;
    setUpSince(null);
    setSensorSource(null);
    setUpAngle("sensor", null);
    if (!follow) {
      setSensor("off");
      return undefined;
    }
    setSensor("waiting");
    pendingBase.current = current.current;
    const stop = watchOrientation({
      reading: (reading) => {
        last.current = reading;
        // La primera lectura fija la referencia con la vista como está: encender no la gira.
        if (reference.current === null) {
          reference.current = upReference(pendingBase.current, reading);
          setUpSince(new Date());
        }
        setSensor("reading");
        setSensorSource(reading.source);
        const angle = viewAngle(reference.current, reading);
        // La flecha de «arriba» va grado a grado; si la cara se ve, manda ella (`upAngle.ts`).
        setUpAngle("sensor", angle);
        if (faceHolds.current) return;
        const next = followQuadrant(current.current, angle);
        if (next !== current.current) {
          current.current = next;
          update({ rotation: next });
        }
      },
      unavailable: () => {
        setUpAngle("sensor", null);
        setSensor("unavailable");
      },
    });
    return () => {
      stop();
      setUpAngle("sensor", null);
    };
  }, [follow, update, faceHolds]);

  // La referencia pasa a ser la vista `base` con la tableta como está ahora; sin tocar el estado,
  // porque la cara la llama cuatro veces por segundo.
  // `angle`, si se da, es el ángulo real (el de la cara): la referencia parte de él y no del
  // cuadrante, para que al pasar al giroscopio no arrastre la diferencia.
  const anchor = useCallback((base: Rotation, angle?: number) => {
    current.current = base;
    pendingBase.current = base;
    reference.current = last.current === null ? null : upReference(angle ?? base, last.current);
  }, []);

  const markUp = useCallback(
    (base?: Rotation) => {
      anchor(base ?? current.current);
      if (last.current !== null) setUpSince(new Date());
    },
    [anchor],
  );

  return { sensor, sensorSource, upSince, markUp, anchor };
}

export function useDisplayModes(): DisplayModesValue {
  return useContext(DisplayModesContext);
}

/**
 * Los mandos de pantalla en un plegable, «Pantalla», al pie del carril (§5.40): el carril queda
 * para las pestañas, y los mandos, cuando se abren, en dos columnas que no se cortan. Abierto o
 * cerrado se guarda en el equipo (`emma.display.open`). Cerrado no apaga nada ni esconde un aviso:
 * «Cámara encendida» y «Micrófono escuchando» van en la franja (`ScreenTop`), y el asistente cambia
 * los modos con `update`, sin pulsar estos mandos.
 *
 * `folded` solo lo pide el carril. En la página sin consola (cargando, o sin backend) no hay
 * carril ni nada más que pulsar: allí los mandos van a la vista, sin plegar, como antes.
 */
export function DisplayControls({ folded = false }: { folded?: boolean }) {
  if (!folded) {
    return (
      <div className="display-controls" role="group" aria-label={tr("Pantalla", "Display")}>
        <div className="display-body">
          <DisplayModeButtons />
        </div>
      </div>
    );
  }
  return <FoldedDisplayControls />;
}

function FoldedDisplayControls() {
  const { modes } = useDisplayModes();
  const voiceReady = useVoiceAvailability() === "ready";
  const [open, setOpen] = useState(() => readDisplayOpen(browserStore()));
  const body = useRef<HTMLDivElement>(null);
  // Si lo abrió la persona tocando el rótulo (y no el asistente, que ya lo lleva a la vista él).
  const byHand = useRef(false);
  const active = activeModes(modes, voiceReady);
  return (
    <Fold data-ui="display-controls"
      concept="displayModes"
      className="display-controls"
      summaryClassName="display-toggle"
      label={
        <>
          {tr("Pantalla", "Display")}
          {/* Plegado, el rótulo dice qué modos están puestos: cerrar el plegable no los esconde. */}
          {active.length > 0 && (
            <span className="display-summary secondary">
              {active.map((item, index) => (
                <Fragment key={index}>
                  {index > 0 && " · "}
                  {item}
                </Fragment>
              ))}
            </span>
          )}
        </>
      }
      open={open}
      onClick={(event) => {
        // Pulsar el rótulo (también con Intro o espacio, que dan un clic) es abrirlo a mano.
        if ((event.target as Element).closest("summary") !== null) byHand.current = true;
      }}
      onToggle={(event) => {
        const hand = byHand.current;
        byHand.current = false;
        // También llega cuando React pone `open` al montar: solo cuenta lo que cambia.
        const now = event.currentTarget.open;
        if (now === open) return;
        setOpen(now);
        writeDisplayOpen(browserStore(), now);
        // Al pie de un carril que se desplaza, lo recién abierto puede quedar fuera de la vista.
        if (now && hand) body.current?.scrollIntoView({ block: "nearest" });
      }}
    >
      {/* El `<details>` ya agrupa con el nombre de su rótulo: sin otro «Pantalla» para el lector. */}
      <div ref={body} className="display-body">
        <DisplayModeButtons />
      </div>
    </Fold>
  );
}

/**
 * Los modos puestos, para el rótulo del plegable: rótulos de navegación, en el orden de los mandos.
 * Sin ninguno, nada. Solo lo que de verdad funciona: con la privacidad, la cámara y el micrófono
 * no se abren aunque el modo quedara guardado; sin voz local, ni la voz ni la iniciativa hablan.
 */
export function activeModes(modes: DisplayModes, voiceReady: boolean): ReactNode[] {
  const items: ReactNode[] = [];
  if (modes.lowVision) items.push(tr("baja visión", "low vision"));
  if (modes.highContrast) items.push(tr("alto contraste", "high contrast"));
  if (modes.essential) items.push(tr("esencial", "essential"));
  if (modes.rotation !== 0)
    items.push(
      <>
        {tr("giro", "rotation")} <span className="num">{formatNumber(modes.rotation)}</span> °
      </>,
    );
  if (modes.followSensor) items.push("sensor");
  if (modes.followFace && !modes.privacy) items.push(tr("cara", "face"));
  if (modes.privacy) items.push(tr("privacidad", "privacy"));
  // Solo hace algo con la cámara mirando.
  if (modes.autoPrivacy && modes.followFace && !modes.privacy) items.push(tr("privacidad automática", "automatic privacy"));
  if (modes.voice && voiceReady) items.push(tr("voz", "voice"));
  if (modes.wakeWord && !modes.privacy) items.push(tr("«EMMA»", "“EMMA”"));
  if (modes.proactive && voiceReady) items.push(tr("iniciativa", "initiative"));
  return items;
}

/** Los mandos de dentro del plegable, en una rejilla de dos columnas (`styles.css`). */
/** Cómo se llama cada idioma en el suyo: quien no lee el de ahora reconoce el propio. */
const LANGUAGE_NAMES: Record<Language, string> = { es: "Español", en: "English" };

/**
 * El idioma de la interfaz (`lib/i18n.ts`). No es un modo de pantalla: elegir otro recarga la
 * página, porque casi todo el texto lo redacta el backend y hay que volver a pedirlo.
 */
function LanguageChoice() {
  return (
    <div className="rotation" role="group" aria-label={tr("Idioma", "Language")}>
      <span className="secondary">{tr("Idioma", "Language")}</span>
      <span className="rotation-options">
        {LANGUAGES.map((option) => (
          <button
            key={option}
            type="button"
            className="command"
            lang={option}
            aria-pressed={language() === option}
            onClick={() => chooseLanguage(option)}
          >
            {/* El elegido se dice también con el anillo, no solo con el color (como el giro). */}
            <Chosen chosen={language() === option}>{LANGUAGE_NAMES[option]}</Chosen>
          </button>
        ))}
      </span>
    </div>
  );
}

function DisplayModeButtons() {
  const {
    modes,
    update,
    sensor = "off",
    sensorSource = null,
    upSince = null,
    markUp,
    face = "off",
    faceProblem = null,
    wake = OFF,
  } = useDisplayModes();
  const silenced = useSilence();
  return (
    <>
      <LanguageChoice />
      <Toggle on={modes.lowVision} onChange={(on) => update({ lowVision: on })}>
        <Mark pictogram={uiPictogram("lowVision")}>{tr("Baja visión", "Low vision")}</Mark>
      </Toggle>
      <Toggle on={modes.highContrast} onChange={(on) => update({ highContrast: on })}>
        <Mark pictogram={uiPictogram("highContrast")}>{tr("Alto contraste", "High contrast")}</Mark>
      </Toggle>
      <Toggle on={modes.essential} onChange={(on) => update({ essential: on })}>
        <Mark pictogram={uiPictogram("essential")}>{tr("Modo esencial", "Essential mode")}</Mark>
      </Toggle>
      <div className="rotation" role="group" aria-label={tr("Girar la pantalla", "Rotate the screen")}>
        <Mark pictogram={uiPictogram("orientation")} className="secondary">
          {tr("Girar", "Rotate")}
        </Mark>
        <span className="rotation-options">
          {ROTATIONS.map((rotation) => (
            <button
              key={rotation}
              type="button"
              className="command"
              aria-pressed={modes.rotation === rotation}
              onClick={() => {
                update({ rotation });
                // Siguiendo el sensor, el giro elegido a mano pasa a ser el «arriba» de ahora.
                if (modes.followSensor) markUp?.(rotation);
              }}
            >
              <Chosen chosen={modes.rotation === rotation}>
                <span className="num">{formatNumber(rotation)}</span> °
              </Chosen>
            </button>
          ))}
        </span>
        <span className="rotation-sensor">
          <Toggle
            on={modes.followSensor}
            onChange={(on) => {
              // iOS solo da el permiso desde un gesto: se pide al pulsar, no al arrancar la escucha.
              if (on) requestOrientationPermission();
              update({ followSensor: on });
            }}
          >
            <Mark pictogram={uiPictogram("followSensor")}>{tr("Seguir el sensor", "Follow the sensor")}</Mark>
          </Toggle>
          {modes.followSensor && (
            <SensorState status={sensor} source={sensorSource} since={upSince} onUp={() => markUp?.()} />
          )}
        </span>
        <span className="rotation-sensor">
          {/* Con la privacidad puesta no se puede encender: la cámara no mira a nadie entonces. */}
          <Toggle on={modes.followFace} disabled={modes.privacy} onChange={(on) => update({ followFace: on })}>
            <Mark pictogram={uiPictogram("followFace")}>{tr("Seguir la cara (demo)", "Follow the face (demo)")}</Mark>
          </Toggle>
          {modes.privacy ? (
            <span className="secondary">
              {tr("Con la privacidad puesta, la cámara no se enciende", "With privacy on, the camera does not turn on")}
            </span>
          ) : (
            modes.followFace && <FaceState status={face} problem={faceProblem} sensor={modes.followSensor} />
          )}
        </span>
      </div>
      {/* Poner la privacidad es un clic; quitarla, otro, sobre un mando que dice lo que hace. No
          pide confirmación: no pierde ni borra nada (F.4.3.2 c es para lo irreversible). */}
      <Toggle on={modes.privacy} onChange={(on) => update({ privacy: on })}>
        <Mark pictogram={uiPictogram("privacy")}>
          {modes.privacy ? tr("Quitar privacidad", "Turn privacy off") : tr("Privacidad", "Privacy")}
        </Mark>
      </Toggle>
      <span className="rotation-sensor">
        {/* Sin él, con otra cara delante EMMA propone la privacidad; con él, la pone sola. */}
        <Toggle on={modes.autoPrivacy} onChange={(on) => update({ autoPrivacy: on })}>
          <Mark pictogram={uiPictogram("privacy")}>
            {tr("Privacidad automática con otra cara", "Automatic privacy with another face")}
          </Mark>
        </Toggle>
        <span className="secondary">
          {modes.followFace && !modes.privacy
            ? modes.autoPrivacy
              ? tr(
                  "Si la cámara ve otra cara un momento, EMMA pone la privacidad sola y lo dice.",
                  "If the camera sees another face for a moment, EMMA turns privacy on by itself and says so.",
                )
              : tr(
                  "Si la cámara ve otra cara un momento, EMMA propone la privacidad.",
                  "If the camera sees another face for a moment, EMMA proposes privacy.",
                )
            : tr("Funciona con «Seguir la cara (demo)» encendido.", "It works with “Follow the face (demo)” turned on.")}{" "}
          {tr(
            "Es una demostración sin validar, y solo cuenta caras.",
            "This is an unproven demonstration, and it only counts faces.",
          )}
        </span>
      </span>
      <VoiceToggle on={modes.voice} onChange={(on) => update({ voice: on })} />
      <span className="rotation-sensor">
        {/* Como la cámara: con la privacidad puesta el micrófono no se abre. */}
        <Toggle on={modes.wakeWord} disabled={modes.privacy} onChange={(on) => update({ wakeWord: on })}>
          <Mark pictogram={uiPictogram("wakeWord")}>{tr("Escuchar «EMMA»", "Listen for “EMMA”")}</Mark>
        </Toggle>
        {modes.privacy ? (
          <span className="secondary">
            {tr("Con la privacidad puesta, el micrófono no se abre", "With privacy on, the microphone does not open")}
          </span>
        ) : (
          modes.wakeWord && <WakeWordState state={wake} />
        )}
      </span>
      <ProactiveControls on={modes.proactive} onChange={(on) => update({ proactive: on })} silenced={silenced} />
    </>
  );
}

/**
 * Cómo va el sensor de giro, en una región de estado para que el lector de pantalla diga cuándo
 * deja de estar disponible. Leyendo, el mando «Esto es arriba» (fuera de la región: un mando no se
 * anuncia como estado) fija la referencia.
 */
function SensorState({
  status,
  source,
  since,
  onUp,
}: {
  status: SensorStatus;
  source: SensorSource | null;
  since: Date | null;
  onUp: () => void;
}) {
  return (
    <>
      <span role="status" className="sensor-state">
        {status === "unavailable" ? (
          <MarkOf mark={UNAVAILABLE_MARK}>{tr("Sensor de giro no disponible", "Rotation sensor not available")}</MarkOf>
        ) : status !== "reading" ? (
          <MarkOf mark={LOADING_MARK}>{tr("Esperando al sensor de giro", "Waiting for the rotation sensor")}</MarkOf>
        ) : (
          <>
            {/* La orientación del navegador funde el acelerómetro: en caída libre no vale. */}
            {source === "earth" && (
              <span className="secondary">
                {tr("Orientación del navegador: solo vale en Tierra", "Browser orientation: only valid on Earth")}
              </span>
            )}
          </>
        )}
      </span>
      {status === "reading" && (
        <>
          {/* El giroscopio deriva: se dice desde cuándo vale el «arriba», para saber cuándo volver a fijarlo. */}
          {since !== null && (
            <span className="secondary">
              {tr("Arriba fijado:", "Up set:")} {formatUtc(since)}
            </span>
          )}
          <button type="button" className="command" onClick={onUp}>
            <Mark pictogram={uiPictogram("screenTop")}>{tr("Esto es arriba", "This is up")}</Mark>
          </button>
        </>
      )}
    </>
  );
}

/**
 * El modo voz (`lib/speech.ts`): con él, cada alerta nueva se lee una vez. Sin síntesis de voz o
 * sin voz local no hay mando que encender: en su sitio, la marca gris de «no disponible» con el
 * motivo (tabla F.5-1), aunque lo guardado la tenga puesta.
 */
export function VoiceToggle({ on, onChange }: { on: boolean; onChange: (on: boolean) => void }) {
  const availability = useVoiceAvailability();
  if (availability !== "ready") return <VoiceUnavailable availability={availability} />;
  return (
    <Toggle on={on} onChange={onChange}>
      <Mark pictogram={uiPictogram("voice")}>{tr("Voz: leer cada alerta nueva", "Voice: read each new alert")}</Mark>
    </Toggle>
  );
}

/** Por qué no hay cámara, con palabras: la clave es la de `lib/faceCamera.ts` y no se traduce. */
const FACE_PROBLEMS: Record<FaceUnavailable, string> = {
  "sin cámara": tr("sin cámara", "no camera"),
  "sin permiso": tr("sin permiso", "no permission"),
  "sin modelo": tr("sin modelo", "no model"),
};

/**
 * Cómo va el seguimiento de la cara, en una región de estado como la del sensor. Siempre dice que
 * es una demostración sin validar y qué se hace con la imagen: nada más que el ángulo. El aviso de
 * «Cámara encendida» no va aquí sino en el borde de arriba (`ScreenTop`), que se ve siempre.
 */
function FaceState({
  status,
  problem,
  sensor,
}: {
  status: FaceStatus;
  problem: FaceUnavailable | null;
  sensor: boolean;
}) {
  return (
    <>
      <span role="status" className="sensor-state">
        {status === "unavailable" ? (
          <MarkOf mark={UNAVAILABLE_MARK}>
            {tr("Cámara no disponible", "Camera not available")}
            {problem === null ? "" : `: ${FACE_PROBLEMS[problem]}`}
          </MarkOf>
        ) : status === "off" || status === "starting" ? (
          <MarkOf mark={LOADING_MARK}>{tr("Preparando la cámara", "Preparing the camera")}</MarkOf>
        ) : status === "several" ? (
          <span>{tr("Hay más de una cara: la vista no gira", "There is more than one face: the view does not rotate")}</span>
        ) : status === "noFace" ? (
          <span className="secondary">
            {sensor
              ? tr("No se ve ninguna cara: sigue el sensor de giro", "No face in view: following the rotation sensor")
              : tr("No se ve ninguna cara: la vista se queda como está", "No face in view: the view stays as it is")}
          </span>
        ) : (
          <span className="secondary">{tr("Siguiendo la cara", "Following the face")}</span>
        )}
      </span>
      <span className="secondary">
        {tr(
          "Demostración, sin validar. Solo se usa el giro de la cara: ningún fotograma se ve, se guarda ni sale del equipo.",
          "Demonstration, unproven. Only the rotation of the face is used: no frame is viewed, stored or sent off the device.",
        )}
      </span>
    </>
  );
}

/**
 * Cómo va la escucha de «EMMA», en una región de estado: el lector de pantalla dice «Te escucho»
 * al abrirse la grabación, la señal de que lo que siga se manda al asistente. Siempre dice qué se
 * graba y qué no. Rótulos de navegación, no clínicos.
 */
export function WakeWordState({ state }: { state: WakeState }) {
  return (
    <>
      <span role="status" className="sensor-state">
        {state.kind === "unavailable" ? (
          <MarkOf mark={UNAVAILABLE_MARK}>{wakeLabel(state)}</MarkOf>
        ) : state.kind === "off" ? null : state.kind === "loading" ? (
          <MarkOf mark={LOADING_MARK}>{wakeLabel(state)}</MarkOf>
        ) : state.kind === "recording" ? (
          <MarkOf mark={MICROPHONE_ON_MARK}>{wakeLabel(state)}</MarkOf>
        ) : (
          <span className="secondary">{wakeLabel(state)}</span>
        )}
      </span>
      <span className="secondary">
        {tr(
          "Sin probar con personas. Solo se graba lo que se dice después de «EMMA», hasta el silencio; lo de antes no se guarda, y el audio no sale del equipo.",
          "Not tested with people. Only what is said after “EMMA” is recorded, until silence; what came before is not kept, and the audio does not leave the device.",
        )}
      </span>
    </>
  );
}

/** El mando de encender y apagar un modo de pantalla; también lo usa `assistant/ProactiveControls`. */
export function Toggle({
  on,
  onChange,
  disabled = false,
  children,
}: {
  on: boolean;
  onChange: (on: boolean) => void;
  disabled?: boolean;
  children: ReactNode;
}) {
  return (
    <button type="button" className="command" aria-pressed={on} disabled={disabled} onClick={() => onChange(!on)}>
      <Chosen chosen={on}>{children}</Chosen>
    </button>
  );
}

/**
 * La referencia de «arriba» de la pantalla: el borde de arriba, con su dibujo y su palabra. Con la
 * cara o el giroscopio midiendo, el dibujo se gira grado a grado para señalar el arriba real de
 * quien mira, aunque la vista solo gire de 90 en 90 (`lib/upAngle.ts`); sin medida, señala el borde
 * de arriba de la vista.
 */
export function ScreenTop() {
  const { modes, face = "off", wake = OFF, presence = null, presenceMessages = [], answerPresence } = useDisplayModes();
  const measured = useUpAngle();
  const arrow = upArrowDegrees(measured, modes.rotation);
  return (
    <span className="screen-top">
      {/* Mientras la cámara está encendida, se dice siempre aquí, en la franja fija. */}
      {cameraIsOn(face) && (
        <MarkOf mark={CAMERA_ON_MARK} className="camera-on">
          {tr("Cámara encendida", "Camera on")}
        </MarkOf>
      )}
      {/* Igual con el micrófono del modo «Escuchar "EMMA"», mientras está abierto. */}
      {microphoneOpen(wake) && (
        <MarkOf mark={MICROPHONE_ON_MARK} className="microphone-on">
          {wake.kind === "recording"
            ? tr("Micrófono escuchando · te escucho", "Microphone listening · I'm listening")
            : tr("Micrófono escuchando", "Microphone listening")}
        </MarkOf>
      )}
      <PresenceStrip notice={presence} privacy={modes.privacy} answer={answerPresence} />
      {/* Siempre en la página, vacía hasta que hay algo que decir: un lector no anuncia una región
          que nace con el texto dentro (`AlertAnnouncer.tsx`). */}
      <span className="sr-only" role="status" aria-atomic="false">
        {presenceMessages.map((message) => (
          <span key={message.id}>{message.text}</span>
        ))}
      </span>
      <span className="mark secondary up-reference" data-up-arrow={measured === null ? undefined : String(arrow)}>
        {/* El giro va en línea: es un ángulo medido, no un estilo; sin animación (WCAG 2.3.1). */}
        <span className="up-arrow" style={arrow === 0 ? undefined : { transform: `rotate(${arrow}deg)` }}>
          <Pictogram name={uiPictogram("screenTop")} />
        </span>
        {measured !== null ? tr("Arriba real", "True up") : tr("Arriba", "Up")}
        {modes.rotation !== 0 && (
          <>
            {" "}
            · {tr("vista girada", "view rotated")} <span className="num">{formatNumber(modes.rotation)}</span> °
          </>
        )}
      </span>
    </span>
  );
}

/**
 * El aviso de otra persona delante, en la fila fija de arriba (se ve con el plegable «Pantalla»
 * cerrado): la pregunta con sus dos mandos, o por qué la privacidad se ha puesto sola. Rótulos de
 * navegación, no clínicos. Los mandos van fuera de la región viva (un mando no se anuncia como
 * estado); la frase la oye el lector por la región de `ScreenTop`.
 */
export function PresenceStrip({
  notice,
  privacy,
  answer,
}: {
  notice: PresenceNotice;
  privacy: boolean;
  answer: ((accept: boolean) => void) | undefined;
}) {
  if (notice === "proposed" && !privacy) {
    return (
      <span className="presence-notice">
        <Mark pictogram={uiPictogram("privacy")}>{PROPOSAL_TEXT}</Mark>
        <button type="button" className="command" onClick={() => answer?.(true)}>
          {tr("Activar la privacidad", "Turn privacy on")}
        </button>
        <button type="button" className="command" onClick={() => answer?.(false)}>
          {tr("No, seguir así", "No, carry on like this")}
        </button>
        <span className="secondary">
          {tr("Demostración, sin validar: solo se cuentan caras.", "Demonstration, unproven: only faces are counted.")}
        </span>
      </span>
    );
  }
  if (notice === "protected" && privacy) {
    return (
      <span className="presence-notice">
        <Mark pictogram={uiPictogram("privacy")}>
          {tr(
            "Privacidad puesta sola: había otra persona delante",
            "Privacy turned on by itself: someone else was in front of the screen",
          )}
        </Mark>
        <span className="secondary">
          {tr("La cámara está apagada. Demostración, sin validar.", "The camera is off. Demonstration, unproven.")}
        </span>
      </span>
    );
  }
  return null;
}
