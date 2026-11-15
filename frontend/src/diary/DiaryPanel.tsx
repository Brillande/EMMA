import { type FormEvent, Fragment, type ReactNode, useCallback, useEffect, useRef, useState } from "react";

import { BoardDetail } from "../components/BoardDetail";
import { BoardOnly, useLook } from "../components/BoardOnly";
import { Command } from "../components/Command";
import { FieldLabel } from "../components/FieldLabel";
import { Fold } from "../components/Fold";
import { IndicatorName } from "../components/IndicatorName";
import { Mark, MarkOf } from "../components/Mark";
import { ObservationTypeBadge } from "../components/ObservationTypeBadge";
import { PanelTitle } from "../components/PanelTitle";
import { StatTile } from "../components/StatTile";
import { Th } from "../components/Th";
import { Loading, Unavailable } from "../components/Unavailable";
import { DAY_SECONDS, type Reading, Sparkline } from "../dashboard/HomeCharts";
import {
  type DiaryCatalog,
  type DiaryEntry,
  type DiaryIndicator,
  diaryApi,
} from "../lib/api";
import { formatNumber, formatUtc } from "../lib/format";
import { hasIndicatorFamily, indicatorFamily } from "../lib/indicatorFamily";
import { EMPTY_MARK, LOADING_MARK, OK_MARK, UNKNOWN_PICTOGRAM, recordedByMark, REFUSED_MARK, type RequestOutcome, requestOutcome } from "../lib/marks";
import { useOperator } from "../lib/operator";
import { type Sign, uiPictogram } from "../lib/uiMarks";
import { cited } from "../pvt/published";
import {
  type Draft,
  type Items,
  type Outcome,
  afterSubmit,
  canSubmit,
  check,
  itemProblem,
  prepare,
  submitAll,
} from "./entry";
import { designAnchors, diaryInstrument, scaleLabels } from "./labels";
import { positionMark } from "./position";

/**
 * Las anclas de una escala propia de la misión: las decidió EMMA y no se leyeron en ninguna
 * fuente. Se pintan aparte de los rótulos leídos, con la marca del backend delante («decisión
 * de diseño, sin validar») y su porqué, y sin cita: no hay instrumento publicado que citar.
 * Cada extremo lleva un cursor en su lado de la pista (`labels.ts`): posición, no instrumento.
 */
function DesignAnchorsView({ indicator }: { indicator: DiaryIndicator }) {
  const decided = designAnchors(indicator);
  if (decided === null) return null;
  return (
    <div className="secondary" data-diary-anchors={indicator.key}>
      Anclas ({decided.mark}):{" "}
      {decided.anchors.map((anchor, index) => (
        <span key={anchor.key}>
          {index > 0 && " · "}
          <Mark pictogram={anchor.pictogram}>
            <span className="num">{anchor.point}</span> = {anchor.label}
          </Mark>
        </span>
      ))}
      . {decided.between}
      <Fold data-ui="diary-design-anchors" concept="whyEmma" label="Por qué son de EMMA">
        <p>{decided.why}</p>
        <p>{decided.reference}</p>
      </Fold>
    </div>
  );
}

/**
 * Lo leído del instrumento publicado de un indicador descriptivo: si su fuente da categorías
 * con palabras, cada una tal cual con el número que le da EMMA (y la nota que lo dice), y las
 * frases en el idioma de la fuente. No son rótulos de la escala y no se pintan como tales.
 */
function InstrumentView({ indicator }: { indicator: DiaryIndicator }) {
  const view = diaryInstrument(indicator);
  if (view === null) return null;
  return (
    <div className="secondary" data-diary-instrument={indicator.key}>
      {view.categories.length > 0 && (
        <>
          <Mark pictogram={uiPictogram("sourceText")}>Categorías de la fuente:</Mark>{" "}
          {view.categories.map((item, index) => (
            <span key={item.key}>
              {index > 0 && " · "}
              <span className="num">{item.point}</span> ={" "}
              <span lang={view.language}>{item.literal}</span>
            </span>
          ))}
          {view.numbering !== null && <p>{view.numbering}</p>}
        </>
      )}
      <Fold data-ui="diary-instrument-source" concept="sourceText" label={<>Fuente del instrumento: {view.name}</>}>
        <p>{view.scope}</p>
        <ul className="evidence">
          {view.quotes.map((item) => (
            <li key={item.id}>
              {item.label}
              <div>
                <q lang={view.language}>{item.quote}</q>
              </div>
              <div>
                <span lang={view.language}>{item.origin}</span>
                {item.url !== null && <span className="num url"> · {item.url}</span>}
              </div>
            </li>
          ))}
          {view.notFound.map((line) => (
            <li key={line}>Buscado y no encontrado: {line}</li>
          ))}
        </ul>
      </Fold>
    </div>
  );
}

/**
 * El alimento valorado, en la aceptabilidad de la comida (decisión del usuario, 2026-10-26). Va
 * junto a la valoración: es de un alimento. La regla, su marca de decisión de diseño de EMMA y
 * por qué es texto libre son del backend, tal cual; las frases leídas, con su cita.
 */
function FoodItemField({
  indicator,
  value,
  invalid,
  onChange,
  board = false,
}: {
  indicator: DiaryIndicator;
  value: string;
  invalid: boolean;
  onChange: (value: string) => void;
  /** En el tablero, la regla y su porqué van al detalle común (`FoodItemRule`); queda si es obligatorio. */
  board?: boolean;
}) {
  const rule = indicator.food_item;
  if (rule === null || rule === undefined) return null;
  const id = `diary-${indicator.key}-food`;
  if (board) {
    return (
      <div data-diary-food={indicator.key}>
        <label htmlFor={id}>{rule.label}</label>{" "}
        <input
          id={id}
          type="text"
          autoComplete="off"
          maxLength={rule.max_length * 2}
          value={value}
          aria-describedby={rule.requirement_note === undefined ? `${id}-rule-notes` : `${id}-rule ${id}-rule-notes`}
          aria-invalid={invalid}
          onChange={(event) => onChange(event.target.value)}
        />
        {/* Si es obligatorio u opcional: en una línea (`shell/log.css`, quinta ronda; recortado con
            «…»); entero en `title` y en la descripción de la entrada (`aria-describedby`), que lee
            el texto del DOM. */}
        {rule.requirement_note !== undefined && (
          <p className="secondary diary-food-rule" id={`${id}-rule`} title={rule.requirement_note}>
            <span data-diary-food-requirement>{rule.requirement_note}</span>
          </p>
        )}
      </div>
    );
  }
  return (
    <div data-diary-food={indicator.key}>
      <label htmlFor={id}>{rule.label}</label>{" "}
      <input
        id={id}
        type="text"
        autoComplete="off"
        maxLength={rule.max_length * 2}
        value={value}
        aria-describedby={`${id}-rule`}
        aria-invalid={invalid}
        onChange={(event) => onChange(event.target.value)}
      />
      <p className="secondary" id={`${id}-rule`}>
        {/* Obligatorio u opcional lo dice el backend, con sus palabras (desde el 2026-10-31). */}
        {rule.requirement_note !== undefined && <span data-diary-food-requirement>{rule.requirement_note} </span>}
        {rule.rule} ({rule.status_display})
      </p>
      <Fold data-ui="diary-free-text" concept="whyEmma" label="Por qué es texto libre">
        <p>{rule.why_free_text}</p>
        <p>{rule.grouping}</p>
        <ul className="evidence">
          {rule.basis.map(cited).map((item) => (
            <li key={item.id}>
              {item.label}
              <div>
                <q lang="en">{item.quote}</q>
              </div>
              <div>
                <span lang="en">{item.origin}</span>
                {item.url !== null && <span className="num url"> · {item.url}</span>}
              </div>
            </li>
          ))}
        </ul>
      </Fold>
    </div>
  );
}

/** La regla del alimento valorado y por qué es texto libre, en el detalle común del tablero. */
function FoodItemRule({ indicator }: { indicator: DiaryIndicator }) {
  const rule = indicator.food_item;
  if (rule === null || rule === undefined) return null;
  return (
    <div className="secondary" id={`diary-${indicator.key}-food-rule-notes`}>
      <p>
        {rule.label}: {rule.rule} ({rule.status_display})
      </p>
      {/* Junto a la entrada va recortado a dos líneas (`.diary-food-rule`); aquí, entero, para quien
          no puede pasar el ratón por encima (tableta, teclado). */}
      {rule.requirement_note !== undefined && <p>{rule.requirement_note}</p>}
      <Fold data-ui="diary-free-text" concept="whyEmma" label="Por qué es texto libre">
        <p>{rule.why_free_text}</p>
        <p>{rule.grouping}</p>
        <ul className="evidence">
          {rule.basis.map(cited).map((item) => (
            <li key={item.id}>
              {item.label}
              <div>
                <q lang="en">{item.quote}</q>
              </div>
              <div>
                <span lang="en">{item.origin}</span>
                {item.url !== null && <span className="num url"> · {item.url}</span>}
              </div>
            </li>
          ))}
        </ul>
      </Fold>
    </div>
  );
}

/**
 * Los rótulos de una escala que se leyeron en su fuente, con la frase que los sostiene.
 * Van en el idioma de la fuente, marcado en el HTML; aquí no se traducen ni se completan.
 * Una escala sin rótulos leídos no pinta nada: su nota, del backend, ya dice por qué. El
 * rótulo lleva la escalera (escala graduada con peldaños rotulados); el número de puntos y
 * cada rótulo son palabras del backend.
 */
function ScaleLabelsView({ indicator }: { indicator: DiaryIndicator }) {
  const labels = scaleLabels(indicator);
  if (labels === null) return null;
  return (
    <div className="secondary" data-diary-labels={indicator.key}>
      <Mark pictogram="stairs">Rótulos leídos en la fuente:</Mark>{" "}
      {labels.anchors.map((anchor, index) => (
        <span key={anchor.key}>
          {index > 0 && " · "}
          <span className="num">{anchor.point}</span> ={" "}
          <span lang={labels.language}>{anchor.label}</span>
        </span>
      ))}
      <Fold data-ui="diary-scale-labels" concept="sourceText" label="Fuente de los rótulos">
        <ul className="evidence">
          {labels.quotes.map((item) => (
            <li key={item.id}>
              {item.label}
              <div>
                <q lang={labels.language}>{item.quote}</q>
              </div>
              <div>
                <span lang={labels.language}>{item.origin}</span>
                {item.url !== null && <span className="num url"> · {item.url}</span>}
              </div>
            </li>
          ))}
          {labels.sources.map((source) => (
            <li key={source.key}>
              <span lang={labels.language}>{source.text}</span>
            </li>
          ))}
          {labels.notFound.map((line) => (
            <li key={line}>Buscado y no encontrado: {line}</li>
          ))}
        </ul>
      </Fold>
    </div>
  );
}

/** Una semana: el suelo de la ventana de la curva de las anotaciones. */
const WEEK_MS = 7 * DAY_SECONDS * 1000;

/** El dibujo de la familia de un indicador, o el de «desconocido» si el catálogo trae uno nuevo (como `IndicatorName`). */
function familyPictogram(key: string) {
  return hasIndicatorFamily(key) ? indicatorFamily(key) : UNKNOWN_PICTOGRAM;
}

/**
 * Las últimas anotaciones como fichas del tablero (decisión del usuario, 2026-11-07): por cada
 * indicador que aparece en la tabla, la última cifra tal como la escribió el backend
 * (`value_text`, sin tocarla) y, si hay dos o más anotaciones suyas, la curva de todas las que
 * trae la lista (`value`, por `effective`). Ninguna cifra nueva: la tabla de abajo es la que se lee;
 * esto solo la resume de un vistazo. La ventana de la curva es la de la propia serie (de la más
 * antigua a la más reciente de la lista, con una semana de suelo para que dos anotaciones del
 * mismo día no se estiren a todo el ancho) y es la misma para todos los indicadores, así las curvas
 * comparten el eje del tiempo. El orden es el del catálogo; lo que la lista trae y el catálogo ya
 * no nombra va al final. No se cuenta cuántas anotaciones hay: la lista trae solo las últimas.
 */
interface EntrySeries {
  key: string;
  /** La última anotada, por su hora firmada; sin hora legible, la primera de la lista. */
  last: DiaryEntry;
  readings: Reading[];
}

/** Las anotaciones por indicador, con la ventana común de sus curvas (ver `EntryTiles`). */
function entrySeries(entries: readonly DiaryEntry[], order: readonly string[]) {
  const byKey = new Map<string, DiaryEntry[]>();
  for (const key of order) byKey.set(key, []);
  for (const entry of entries) {
    const bucket = byKey.get(entry.key);
    if (bucket === undefined) byKey.set(entry.key, [entry]);
    else bucket.push(entry);
  }
  const series: EntrySeries[] = [...byKey.entries()]
    .filter(([, items]) => items.length > 0)
    .map(([key, items]) => {
      const readings: Reading[] = items
        .map((item) => ({ at: new Date(item.effective).getTime(), value: item.value }))
        .filter((item) => Number.isFinite(item.at))
        .sort((a, b) => a.at - b.at);
      const last = items.reduce((best, item) =>
        new Date(item.effective).getTime() > new Date(best.effective).getTime() ? item : best,
      );
      return { key, last, readings };
    });
  const times = series.flatMap((item) => item.readings.map((reading) => reading.at));
  if (times.length === 0) return null;
  const until = Math.max(...times);
  const windowMs = Math.max(until - Math.min(...times), WEEK_MS);
  return { series, until, windowMs };
}

type SeriesView = NonNullable<ReturnType<typeof entrySeries>>;

function EntryTiles({ view, only, stale }: { view: SeriesView; only: (key: string) => boolean; stale: boolean }) {
  const shown = view.series.filter((item) => only(item.key));
  if (shown.length === 0) return null;
  return (
    <div className="board-stats diary-board" role="group" aria-label="Última anotación de cada indicador">
      {shown.map(({ key, last, readings }) => (
        <StatTile key={key} pictogram={familyPictogram(key)} label={last.display_es} value={last.value_text} stale={stale}>
          {readings.length >= 2 && <Sparkline readings={readings} until={view.until} windowMs={view.windowMs} />}
        </StatTile>
      ))}
    </div>
  );
}

/**
 * La última cifra de un campo junto a su entrada (2026-11-08, «Signos vitales» de la muestra: cada
 * fila, su nombre, su cifra y su curva): `value_text` tal cual y la curva de sus anotaciones con la
 * ventana común. Sin anotaciones de ese indicador no pinta nada: el campo está para anotar.
 */
function FieldLast({ item, view, stale }: { item: EntrySeries; view: SeriesView; stale: boolean }) {
  return (
    <div className="diary-last" role="group" aria-label={`Última anotación: ${item.last.display_es}`}>
      <span className="secondary">Última</span>{" "}
      <span className={stale ? "num stale" : "num"}>{item.last.value_text}</span>
      {item.readings.length >= 2 && <Sparkline readings={item.readings} until={view.until} windowMs={view.windowMs} />}
    </div>
  );
}

/**
 * Lo que dos líneas de una baldosa del tablero enseñan seguro de un nombre (unos 33 caracteres por
 * línea a 0,875 rem en una baldosa de cuatro por fila), menos el «…» y algo de holgura.
 */
const CLAMP_VISIBLE_CHARS = 50;

/**
 * Si el nombre de un campo se puede recortar a dos líneas sin confundirlo con otro: lo que lo
 * distingue de cada otro nombre del catálogo tiene que caer dentro de lo que se ve. Los tres de
 * cohesión del equipo comparten más de setenta caracteres y solo difieren en la frase del final:
 * recortados serían el mismo campo, así que van enteros.
 */
export function clampable(name: string, names: readonly string[]): boolean {
  return names.every((other) => {
    if (other === name) return true;
    let shared = 0;
    while (shared < name.length && shared < other.length && name[shared] === other[shared]) shared += 1;
    return shared < CLAMP_VISIBLE_CHARS;
  });
}

/**
 * Lo que distingue un nombre que no se puede recortar por el final (`clampable`): el trozo del
 * propio nombre del backend desde la última comilla «, o la última palabra, antes de donde se separa
 * del otro nombre más parecido. Quinta ronda (2026-11-08): los tres de cohesión del equipo iban
 * enteros, en cuatro líneas, y doblaban el alto de su fila; a la vista va solo su frase («Our team…»),
 * sin una palabra nueva (se corta, no se redacta), y el nombre entero sigue en `title`, para el
 * lector de pantalla y en el detalle de escalas. `null` si el nombre se puede recortar.
 */
export function distinctTail(name: string, names: readonly string[]): string | null {
  if (clampable(name, names)) return null;
  let shared = 0;
  for (const other of names) {
    if (other === name) continue;
    let length = 0;
    while (length < name.length && length < other.length && name[length] === other[length]) length += 1;
    shared = Math.max(shared, length);
  }
  const quote = name.lastIndexOf("«", shared);
  const cut = quote > 0 ? quote : name.lastIndexOf(" ", shared) + 1;
  return cut > 0 ? name.slice(cut) : null;
}

/** La regla, el equipo y la nota de escala de un campo, del backend tal cual (con « · » delante de cada una). */
function ScaleNote({ indicator }: { indicator: DiaryIndicator }) {
  return (
    <>
      {indicator.equipment !== null && <> · {indicator.equipment}</>}
      {indicator.scale !== null && (
        <>
          {indicator.scale.described_as !== null && <> · {indicator.scale.described_as}</>}
          {" · "}
          {indicator.scale.labels_note}
          {indicator.scale.concerning_note !== null && <> · {indicator.scale.concerning_note}</>}
        </>
      )}
    </>
  );
}

/**
 * Registro diario del tripulante en la consola.
 *
 * Los autoinformes del catálogo (ánimo, síntomas, apetito, comida, ingesta) solo llegaban del
 * simulador: ninguna pantalla los pedía. Qué se puede anotar, con qué rango y con qué
 * procedencia lo dice el backend (`GET /api/diary`); cada valor se envía a la ruta del diario,
 * que lo firma como una observación más con su fuente propia, y lo que se enseña después es
 * lo que el registro firmado devuelve, no lo tecleado.
 *
 * Con cada valor va quién lo teclea (el operador de la consola, que puede no ser el
 * tripulante del dato): sin nombre no se envía nada. De cada anotación ya registrada se
 * enseña con qué fuente entró y quién la anotó, con las palabras del backend; de una
 * anterior a este campo, que no consta.
 *
 * Aquí no se interpreta nada de lo anotado, y una escala solo lleva los rótulos que el backend
 * entrega con la frase de su fuente: una sin rótulos leídos no se rotula. Las escalas propias
 * de la misión enseñan, aparte, las anclas que el backend da como decisión de diseño de EMMA
 * sin validar, con esa marca: no son rótulos leídos y no se pintan como si lo fueran.
 *
 * Signos (§5.33.7): el cuaderno en el título, la pluma en «Últimas anotaciones» y en
 * «Registrar», el libro abierto en todo lo leído en una fuente (sus plegables y «Categorías de
 * la fuente»), el lápiz en «Por qué son de EMMA» y el vocabulario común en las cabeceras. Las
 * anclas no llevan signo propio: no hay concepto para ellas, y ya llevan su cursor cada una.
 *
 * Una pantalla por sección (2026-11-08, «Notas / Bitácora» y «Signos vitales» de la muestra): en el
 * tablero cada campo es una baldosa baja con su nombre, su unidad, su entrada, su rango (que nunca
 * se pliega) y su última cifra con su curva; la regla de cada escala, sus rótulos, anclas, fuentes y
 * con qué se firma van en un «Ver detalle» común al pie, y la tabla de anotaciones en otro. En la
 * segunda ronda (mismo día), cuatro baldosas por fila con el nombre arriba en dos líneas como mucho
 * (`clampable`) y la unidad y el rango junto a la entrada.
 */
export function DiaryPanel({ subject }: { subject: string }) {
  const [catalog, setCatalog] = useState<DiaryCatalog | null>(null);
  const [entries, setEntries] = useState<DiaryEntry[] | null>(null);
  const [draft, setDraft] = useState<Draft>({});
  const [items, setItems] = useState<Items>({});
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [unavailable, setUnavailable] = useState<RequestOutcome | null>(null);
  const [busy, setBusy] = useState(false);
  const [operator, setOperator] = useOperator();

  // El tripulante en pantalla: una respuesta que llega tarde para el anterior se descarta, para
  // que sus anotaciones no aparezcan como las de este.
  const shown = useRef(subject);
  useEffect(() => {
    shown.current = subject;
  }, [subject]);
  const load = useCallback(() => {
    const asked = subject;
    Promise.all([diaryApi.catalog(), diaryApi.entries(subject)])
      .then(([offered, recorded]) => {
        if (shown.current !== asked) return;
        setCatalog(offered);
        setEntries(recorded.entries);
        setUnavailable(null);
      })
      .catch((reason: unknown) => {
        if (shown.current === asked) setUnavailable(requestOutcome(reason));
      });
  }, [subject]);
  // Lo tecleado era para el tripulante que estaba en pantalla: no se arrastra a otro, y sus
  // anotaciones tampoco: hasta que llegan las de este, la tabla dice «Cargando…» (§5.33.7), en
  // vez de enseñar las del anterior como si fueran suyas (o como suyas caducadas si falla).
  useEffect(() => {
    setDraft({});
    setItems({});
    setOutcome(null);
    setEntries(null);
    setUnavailable(null);
  }, [subject]);
  useEffect(load, [load]);

  const submit = async () => {
    if (catalog === null) return;
    const prepared = prepare(catalog, subject, draft, operator, items);
    if (!canSubmit(prepared)) return;
    setBusy(true);
    setOutcome(null);
    try {
      const result = await submitAll(prepared.bodies, diaryApi.record);
      setOutcome(result);
      setDraft((current) => afterSubmit(current, result));
      setItems((current) => afterSubmit(current, result));
      load();
    } finally {
      setBusy(false);
    }
  };

  return (
    <DiaryView
      catalog={catalog}
      entries={entries}
      draft={draft}
      items={items}
      outcome={outcome}
      unavailable={unavailable}
      busy={busy}
      operator={operator}
      onOperator={setOperator}
      onChange={(key, value) => setDraft((current) => ({ ...current, [key]: value }))}
      onItem={(key, value) => setItems((current) => ({ ...current, [key]: value }))}
      onSubmit={() => void submit()}
    />
  );
}

/** Solo pinta. Separado del estado para poder probar lo que se lee en pantalla. */
export function DiaryView({
  catalog,
  entries,
  draft,
  items = {},
  outcome,
  unavailable,
  busy,
  operator,
  onOperator,
  onChange,
  onItem = () => undefined,
  onSubmit,
}: {
  catalog: DiaryCatalog | null;
  /** Las anotaciones del tripulante en pantalla; `null` mientras no han llegado las suyas. */
  entries: DiaryEntry[] | null;
  draft: Draft;
  /** El alimento tecleado junto a la valoración de la comida, por indicador. */
  items?: Items;
  outcome: Outcome | null;
  unavailable: RequestOutcome | null;
  busy: boolean;
  /** Quién está en la consola: se firma con cada valor. */
  operator: string;
  onOperator: (value: string) => void;
  onChange: (key: string, value: string) => void;
  onItem?: (key: string, value: string) => void;
  onSubmit: () => void;
}) {
  // En el tablero (la concha de la maqueta) cada campo es una baldosa baja y lo que se lee para
  // anotar va a un detalle; en la clásica, todo como siempre.
  const board = useLook() === "reference";
  if (catalog === null) {
    return (
      <section data-ui="diary" className="panel" aria-label="Registro diario">
        <PanelTitle concept="diary">Registro diario</PanelTitle>
        {unavailable !== null ? (
          <Unavailable outcome={unavailable} />
        ) : (
          <Loading />
        )}
      </section>
    );
  }

  const prepared = prepare(catalog, "", draft, operator, items);
  const names = Object.fromEntries(catalog.indicators.map((item) => [item.key, item.display_es]));
  // El nombre del indicador con el dibujo de su familia; la clave si el catálogo ya no lo trae.
  const named = (key: string) => <IndicatorName indicatorKey={key} displayEs={names[key] ?? key} />;
  const send = (event: FormEvent) => {
    event.preventDefault();
    onSubmit();
  };
  // Mientras se envía, el mando enseña la marca de «cargando» con su palabra de siempre; el
  // dibujo cambia, el botón es el mismo (no se desmonta ni pierde su sitio).
  const submitSign: Sign =
    busy && LOADING_MARK.pictogram !== null ? { pictogram: LOADING_MARK.pictogram } : { concept: "register" };
  // Si la última lectura falló, lo que queda en la tabla es la de antes: caducado. Además del
  // «Sin datos» en cian, la cursiva en sus cifras (la tercera señal, §5.33).
  const numClass = unavailable !== null ? "num stale" : "num";
  const stale = unavailable !== null;
  // Las anotaciones por indicador: en el tablero, la última de cada campo va junto a su entrada.
  const order = catalog.indicators.map((item) => item.key);
  const seriesView = entries === null ? null : entrySeries(entries, order);
  const lastOf = new Map((seriesView?.series ?? []).map((item) => [item.key, item]));
  const offered = new Set(order);
  const otherNames = catalog.indicators.map((item) => item.display_es);

  // Lo que se lee antes de anotar (qué es el registro y con qué procedencia se firma): en la
  // clásica, arriba y bajo los campos, como siempre; en el tablero, en el detalle del pie.
  const intro = (
    <p className="secondary">
      Lo que el tripulante anota por sí mismo. Rellene solo lo que quiera anotar: un campo
      vacío no se registra.
    </p>
  );
  const provenance = (
    <>
      <p className="secondary">
        Se firma como{" "}
        <ObservationTypeBadge
          type={catalog.provenance.observation_type}
          context={catalog.provenance.evidence_context}
        />{" "}
        · fuente: {catalog.provenance.source_display}
      </p>
      {catalog.notes.map((note) => (
        <p className="secondary" key={note}>
          {note}
        </p>
      ))}
    </>
  );
  const operatorNote = (
    <p className="secondary" id="diary-operator-note">
      {catalog.recorded_by.note}
    </p>
  );
  // El pie del formulario: en el tablero, el mando y el detalle común en una sola pieza; en la
  // clásica, solo el mando (el detalle es del tablero).
  const footer = (actions: ReactNode, notes: ReactNode) =>
    board ? (
      <div className="diary-foot">
        {actions}
        {notes}
      </div>
    ) : (
      actions
    );

  return (
    <section data-ui="diary" className="panel" aria-label="Registro diario">
      <PanelTitle concept="diary">Registro diario</PanelTitle>
      {!board && intro}

      {/* `diary-form`: en tableta vertical el rótulo va encima de su campo y en horizontal los
          campos van en dos columnas (styles.css, §5.40). En el tablero, cada campo en una baldosa
          baja: nombre y unidad, entrada, rango y la última cifra con su curva (`shell/log.css`). */}
      <form className="silence-form diary-form" onSubmit={send} noValidate>
        {catalog.indicators.map((indicator) => {
          const id = `diary-${indicator.key}`;
          const result = check(indicator, draft[indicator.key] ?? "");
          const invalid = result.state === "invalid";
          // El alimento que falta (o que sobra sin su valoración): el mismo «no» que el backend.
          const itemIssue = invalid
            ? null
            : itemProblem(indicator, result, items[indicator.key] ?? "");
          const last = lastOf.get(indicator.key);
          const tail = board ? distinctTail(indicator.display_es, otherNames) : null;
          return (
            <div key={indicator.key} className={board ? "field-block diary-field" : "field-block"}>
              <label htmlFor={id}>
                {board ? (
                  // Tablero: el nombre en dos líneas como mucho (recortado con «…», entero en
                  // `title` y en el texto que lee el lector de pantalla); si recortarlo lo confundiría
                  // con otro campo, a la vista solo lo que lo distingue (`distinctTail`) y entero
                  // para el lector de pantalla. La unidad va junto a la entrada.
                  <span
                    className="diary-field-name"
                    data-clamp={tail !== null || clampable(indicator.display_es, otherNames) ? "" : undefined}
                    title={indicator.display_es}
                  >
                    {tail === null ? (
                      <IndicatorName indicatorKey={indicator.key} displayEs={indicator.display_es} />
                    ) : (
                      <>
                        <span aria-hidden="true" data-diary-tail="">
                          <IndicatorName indicatorKey={indicator.key} displayEs={`…${tail}`} />
                        </span>
                        <span className="sr-only">{indicator.display_es}</span>
                      </>
                    )}
                  </span>
                ) : (
                  <IndicatorName indicatorKey={indicator.key} displayEs={indicator.display_es} />
                )}{" "}
                <span className="secondary diary-field-unit">({indicator.unit_display})</span>
              </label>{" "}
              <input
                id={id}
                type="text"
                inputMode="decimal"
                autoComplete="off"
                className="num"
                value={draft[indicator.key] ?? ""}
                aria-describedby={`${id}-hint${board ? ` ${id}-notes` : ""}${invalid ? ` ${id}-error` : ""}`}
                aria-invalid={invalid}
                onChange={(event) => onChange(indicator.key, event.target.value)}
              />
              {/* El rango no se pliega nunca: dice qué se puede escribir. La regla de la escala sí,
                  en el tablero, al detalle común del pie (`#diary-<clave>-notes`). */}
              <p className="secondary" id={`${id}-hint`}>
                Rango: <span className="num">{indicator.range_text}</span>
                {!board && <ScaleNote indicator={indicator} />}
              </p>
              {board && last !== undefined && seriesView !== null && (
                <FieldLast item={last} view={seriesView} stale={stale} />
              )}
              {!board && (
                <>
                  <ScaleLabelsView indicator={indicator} />
                  <DesignAnchorsView indicator={indicator} />
                  <InstrumentView indicator={indicator} />
                </>
              )}
              <FoodItemField
                indicator={indicator}
                value={items[indicator.key] ?? ""}
                invalid={itemIssue !== null}
                onChange={(value) => onItem(indicator.key, value)}
                board={board}
              />
              {/* Lo que aún falta del par valoración-alimento se dice sin interrumpir: aparece
                  mientras se rellena la otra mitad, y un `alert` lo anunciaría a cada tecla. */}
              {itemIssue !== null && (
                <p role="status">
                  <MarkOf mark={REFUSED_MARK}>{itemIssue}</MarkOf>
                </p>
              )}
              {/* Fuera de rango: el mismo «no» que daría el backend (un 4xx), adelantado para
                  ahorrar el viaje; lleva su marca, la de un rechazo (§5.34.14). */}
              {invalid && (
                <p id={`${id}-error`} role="alert">
                  <MarkOf mark={REFUSED_MARK}>{result.reason}</MarkOf>
                </p>
              )}
            </div>
          );
        })}

        {!board && provenance}

        <FieldLabel concept="person" className="operator">
          {catalog.recorded_by.label}{" "}
          <input
            value={operator}
            maxLength={64}
            autoComplete="off"
            aria-describedby="diary-operator-note"
            aria-invalid={prepared.unnamed}
            onChange={(event) => onOperator(event.target.value)}
          />
        </FieldLabel>
        {!board && operatorNote}

        {/* Tablero: el mando con sus avisos y el detalle común, juntos en el pie (`.diary-foot`, una
            sola pieza de la rejilla a la fila entera): sueltos, el empaquetado `dense` de los campos
            podía subir el detalle a un hueco por encima del mando. En la clásica, como siempre. */}
        {footer(
        <div className="measure-actions">
          <Command {...submitSign} type="submit" disabled={busy || !canSubmit(prepared)}>
            {busy ? "Registrando…" : "Registrar"}
          </Command>
          {prepared.problems.length > 0 && (
            <span className="secondary">
              Hay <span className="num">{formatNumber(prepared.problems.length)}</span> campos que
              no se pueden enviar: no se registra ninguno hasta corregirlos.
            </span>
          )}
          {prepared.unnamed && (
            <span className="secondary">
              Falta el nombre de quien anota: sin él no se registra nada.
            </span>
          )}
        </div>,

        /* Tablero: lo que se lee para anotar (la regla de cada escala, sus rótulos, anclas y
            fuentes, y con qué se firma) en un solo detalle al pie; el rango sigue en cada campo. */
          <BoardDetail label="escalas, anclas y fuentes de cada campo" className="diary-notes">
            {intro}
            {catalog.indicators.map((indicator) => (
              <div key={indicator.key} id={`diary-${indicator.key}-notes`} className="diary-field-notes">
                <p>
                  <IndicatorName indicatorKey={indicator.key} displayEs={indicator.display_es} />{" "}
                  <span className="secondary">
                    Rango: <span className="num">{indicator.range_text}</span>
                    <ScaleNote indicator={indicator} />
                  </span>
                </p>
                <ScaleLabelsView indicator={indicator} />
                <DesignAnchorsView indicator={indicator} />
                <InstrumentView indicator={indicator} />
                <FoodItemRule indicator={indicator} />
              </div>
            ))}
            {provenance}
            {operatorNote}
          </BoardDetail>,
        )}
      </form>

      <div role="status" aria-live="polite">
        {outcome !== null && outcome.saved.length > 0 && (
          <p className="secondary">
            <MarkOf mark={OK_MARK}>Registrado:</MarkOf>{" "}
            {outcome.saved.map((key, index) => (
              <Fragment key={key}>
                {index > 0 && ", "}
                {named(key)}
              </Fragment>
            ))}
            . Abajo, tal como quedó en el registro.
          </p>
        )}
        {outcome !== null && outcome.failed !== null && (
          <p role="alert">
            <MarkOf mark={outcome.failed.outcome.mark}>
              No se registró {named(outcome.failed.key)}: {outcome.failed.outcome.text}
            </MarkOf>
          </p>
        )}
        {unavailable !== null && <Unavailable outcome={unavailable} />}
      </div>

      <PanelTitle concept="notes" as="h3">
        Últimas anotaciones
      </PanelTitle>
      {entries === null ? (
        // Las de este tripulante aún no han llegado; si la lectura falló, ya lo dice «Sin datos».
        unavailable === null && (
          <Loading />
        )
      ) : entries.length === 0 ? (
        // Nada registrado todavía: la marca de registro vacío de toda la consola (`EMPTY_MARK`),
        // la misma que el dolor, la ecografía, los informes y la PVT (§5.33.12).
        <p className="secondary">
          <MarkOf mark={EMPTY_MARK}>Ninguna anotación a mano de este tripulante en el registro.</MarkOf>
        </p>
      ) : (
        <>
        {/* Tablero: la última cifra de cada indicador del catálogo ya va en su campo; aquí, en
            fichas, solo la de los que la lista trae y el catálogo ya no nombra. La tabla que las
            detalla, en su «Ver detalle». Solo en la concha de la maqueta. */}
        <BoardOnly>
          {seriesView !== null && (
            <EntryTiles view={seriesView} only={(key) => !offered.has(key)} stale={stale} />
          )}
        </BoardOnly>
        <BoardDetail label="tabla de anotaciones">
        <div className="quality-table">
        {entries.some((entry) => entry.recorded_by === null) && (
          <p className="secondary">{catalog.recorded_by.legacy_note}</p>
        )}
        <table className="ledger">
          <thead>
            <tr>
              <Th concept="indicator">Indicador</Th>
              <Th concept="value">Valor</Th>
              <Th concept="time">Hora</Th>
              <Th concept="provenance">Procedencia</Th>
              <Th concept="person">{catalog.recorded_by.label}</Th>
              <Th concept="state">En el estado</Th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={`${entry.key}|${entry.effective}|${entry.value}`}>
                <th scope="row">
                  <IndicatorName indicatorKey={entry.key} displayEs={entry.display_es} />
                  {/* El alimento firmado con la valoración, tal cual. */}
                  {entry.food !== null && entry.food !== undefined && (
                    <span className="secondary" data-diary-entry-food>
                      {" "}· {entry.food}
                    </span>
                  )}
                </th>
                <td className={numClass}>{entry.value_text}</td>
                <td className={numClass}>{formatUtc(new Date(entry.effective))}</td>
                <td>
                  <ObservationTypeBadge
                    type={entry.observation_type}
                    context={entry.evidence_context}
                  />{" "}
                  · {entry.source_display}
                </td>
                {/* El nombre firmado, o las palabras del backend para quien no consta, con la
                    marca de «no disponible» (`position.ts`). */}
                <td data-recorded-by={entry.recorded_by === null ? "missing" : "named"}>
                  <MarkOf mark={recordedByMark(entry.recorded_by)}>{entry.recorded_by_display}</MarkOf>
                </td>
                <td data-position={entry.position}>
                  <MarkOf mark={positionMark(entry.position)}>{entry.position_note}</MarkOf>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
        </BoardDetail>
        </>
      )}
    </section>
  );
}
