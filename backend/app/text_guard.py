# SPDX-License-Identifier: AGPL-3.0-or-later
"""Linter de lenguaje: lo que EMMA no puede decir a una tripulación.

Por qué existe: la invariante 7 —apoyo a la decisión, no prescripción— era hasta ahora una
regla escrita. Mientras todo el texto clínico eran frases fijas revisadas a mano, bastaba. Con
un modelo de lenguaje redactando borradores deja de bastar: un modelo puede escribir "administre
10 mg" o "confirma un SANS" con total soltura. Este módulo convierte la regla en código.

Dos niveles (decisión del usuario, 2026-09-29: "evitar que se bloquee manteniéndolo todo"):
  * **Bloquean** las reglas de EMMA de abajo y la parte clínica de las listas de Polaris que
    EMMA ya usaba: absolutos (`imposible`, `nunca`, `cero riesgo`, `demostrado`…), acciones
    terapéuticas (cambiar dosis, suspender o empezar un tratamiento, biopsia, cirugía, punción,
    drenaje) y deliberación afirmada (`debería`, `conviene`, `es razonable`…).
  * **Avisan sin bloquear** todas las demás entradas de las listas completas de Polaris, leídas
    tal cual de la copia (`honestidad_lint.py::_TRIGGERS`, `decision_alto_riesgo.py::_ACCION` y
    `_DELIBERA_FUERTE`, por `app.polaris`). Incluyen disparadores de software y términos de su
    caso oncológico que en un borrador de EMMA dan falsos bloqueos ("no tiene", "y si", "qué
    lesión", "telemetría"). Se comprueban todas y se enseñan a quien firma (`advisories`), pero
    no impiden mostrar el borrador. Ninguna se quita ni se toca en la copia.

Licencia y origen (AGPL §5a): código de Polaris (AGPL-3.0-or-later, © 2026 la autora de Polaris,
«Beyond the Protocol»), de dos formas. LLAMA a `polaris/tools/honestidad_lint.py` y
`polaris/tools/decision_alto_riesgo.py` de la copia literal, sin modificarla (commit en
`polaris/ADOPTADO.txt`; se cargan con `app.polaris.load`): las listas completas, que avisan.
ADAPTADO a mano de `tools/honestidad_lint.py` y `tools/decision_alto_riesgo.py` @ 7bf47257
(github.com/BeyondTheProtocol/polaris, el commit que se copió primero): las listas que bloquean.
Cambios: `_OVERCLAIM` son los absolutos de `_TRIGGERS`, sin sus disparadores de software y sin
tildes; `_ACTION` es `_TTO` y `_ACCION` sin lo propio de su caso oncológico (fármacos, líneas de
tratamiento, ensayo, radioterapia) ni las formas de primera persona, más punción y drenaje;
`_DELIBERATE` son las formas de `_DELIBERA_FUERTE` que, escritas por el sistema, recomiendan, más
"es recomendable" y "se recomienda".

Reglas de EMMA, añadidas a las de Polaris (no son cambios del original): las categorías
`dosing`, `diagnosis`, `certainty` y `order` de abajo, punción y drenaje como acción, y "es
recomendable" / "se recomienda" como deliberación.

Qué caza, por categoría:
  dosing       fármacos, dosis y vías de administración: EMMA no administra terapia.
  diagnosis    afirmar o descartar un diagnóstico: EMMA no diagnostica.
  certainty    certezas que ningún dato de a bordo sostiene ("sin duda", "100 %").
  order        órdenes clínicas en imperativo ("debe tratarse", "inicie tratamiento"), acciones
               terapéuticas y recomendaciones ("conviene", "es razonable").
  overclaim    afirmaciones absolutas ("nunca", "siempre", "cero riesgo", "demostrado").

LÍMITE, dicho para no dar falsa confianza: es un filtro de patrones. Caza una clase de frase,
no toda frase peligrosa; una prescripción redactada en tono suave y sin palabras gatillo se le
escapa. Por eso no es la única barrera: el borrador además exige que toda cifra salga de los
hechos y, sobre todo, la firma de una persona antes de valer nada.

DOS IDIOMAS (decisión del usuario, 2026-11-15: castellano e inglés con selector). Con la salida en
inglés, un filtro de patrones castellanos lo dejaría pasar todo sin decir nada. Cada comprobación
pública acepta `lang` (`None` = el idioma de la petición, `i18n.current()`):
  * `"es"`: lo de siempre, sin un solo cambio en lo que caza ni en su orden.
  * `"en"`: los grupos ingleses de abajo (`_EN_*`), gemelos uno a uno de los castellanos y con las
    mismas categorías, **y además** los castellanos. El idioma de la consola no decide en qué
    idioma escribe un modelo, una persona de Tierra o un fichero de datos: una barrera que se
    salta cambiando de idioma no es una barrera. Los patrones castellanos no cazan nada en una
    frase inglesa corriente; un mismo tramo cazado por los dos no se repite.
Lo que el inglés no tiene igual, dicho aquí para que nadie lo busque:
  * **Las listas de Polaris son solo castellanas** (copia literal, no se edita): en inglés bloquean
    solo los grupos propios de EMMA, y `advisories` sigue pasando las de Polaris, que en un texto
    inglés no encuentran nada.
  * **No hay pronombres pegados** («suspéndala»): `ATTACHED_PRONOUNS` no tiene gemelo.
  * **El imperativo inglés es igual que el infinitivo** («Start the measurement» es un paso de
    medida): los imperativos sueltos de `order` («inicie», «reduzca») no tienen gemelo; la orden
    se caza por su objeto (`_EN_ACTION`: empezar, parar o seguir un tratamiento) y por la
    obligación («must be treated»). Por lo mismo solo cuentan las formas en tercera persona de
    «confirms/rules out»: «Confirm the probe position» es un paso, no un veredicto.
  * **No hay «¿»**: la pregunta abierta inglesa es la frase que empieza por un auxiliar invertido
    («Is it…?», «Should we…?») y acaba en «?», sin cruzar un fin de frase. Lo demás (la coletilla
    tras una coma) vale igual que en castellano. Se le escapa la condicional invertida («Should
    the pain return, …?»), que no es pregunta y lo parece.
  * **Solo el presente afirma un veredicto**, como en castellano («confirma», no «confirmó»):
    «The CMO confirmed the reading» es un hecho del registro. Un borrador que diagnostique en
    pasado («the scan confirmed the thrombosis») pasa este filtro; no pasa la firma.
  * **Palabras de nave que no son de botiquín**: «capsule» y «tablet» solo cuentan con su cuenta,
    su pauta o su toma («two tablets», «capsules daily»), «injection» no tras «lunar/orbital…»,
    «radiation dose» y «dose rate» son la magnitud medida (en castellano se escribe «radiación»;
    es la única holgura que el inglés tiene y el castellano no), y «never» / «always» no cuentan
    ante un verbo de dato («the reading never arrived»).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app import polaris
from app.core import i18n

_HONESTY = polaris.load("honestidad_lint")
_HIGH_RISK = polaris.load("decision_alto_riesgo")

# Hasta dos pronombres pegados a un imperativo («suspéndala», «adminístreselo»): sin ellos, la orden
# se cuela por un patrón que solo conoce el verbo desnudo. También los usa `core/ground_notes.py`.
ATTACHED_PRONOUNS = r"(?:(?:se|me|te|nos|le|les)(?:la|lo|las|los)?|la|lo|las|los)?"

_PATTERNS: dict[str, tuple[str, ...]] = {
    "dosing": (
        r"\b\d+(?:[.,]\d+)?\s*(?:mg|mcg|µg|ug|g|ml|ui|mEq)\b",
        r"\bdosis\b",
        r"\badministr(?:ad|acion)\b",
        r"\badministr(?:ar|e|en)" + ATTACHED_PRONOUNS + r"\b",
        r"\b(?:comprimidos?|capsulas?|inyecci[oó]n|intravenos[oa]|intramuscular|subcutane[oa])\b",
        r"\b(?:farmaco|medicamento|medicacion|prescrib\w*|receta\w*)\b",
        r"\b(?:sondaje|sondar|cateteri\w*)\b",
    ),
    "diagnosis": (
        r"\bdiagnostic\w*\b",
        r"\b(?:padece|sufre de|tiene un[a]? (?:sindrome|trombosis|retencion|neumotorax))\b",
        # "confirma la trombosis"; no "para confirmar" ni "descartar artefacto", que son pasos
        # de medida y no diagnósticos. "Descarta que…" se trata abajo (`_STATED_DIAGNOSIS`).
        r"\b(?:confirma|descarta|excluye)n? (?:el|la|los|las|un|una)\b",
        r"\bes (?:un[a]? )?(?:sans|trombosis|neumotorax|hemorragia)\b",
        # Insinuar un diagnóstico también es diagnosticar.
        r"\b(?:compatible con|sugestiv\w* de|sugiere|indicativ\w* de)\b",
    ),
    "certainty": (
        r"\bsin (?:ninguna )?duda\b",
        r"\bcon (?:total )?certeza\b",
        r"\bdefinitivamente\b",
        r"\bgarantiz\w*\b",
        r"\b100\s*%",
        r"\b(?:seguro que|es seguro)\b",
    ),
    "order": (
        r"\b(?:inicie|comience|suspenda|aumente|reduzca)n?" + ATTACHED_PRONOUNS + r"\b",
        r"\bdebe(?:n)? (?:tratar|tomar|recibir|evacuar)\w*\b",
        r"\btratamiento (?:inmediato|urgente)\b",
    ),
}

# Lo que bloquea de `honestidad_lint.py::_TRIGGERS`: los absolutos clínicos. Sin tildes: se
# busca sobre el texto normalizado.
_OVERCLAIM: tuple[str, ...] = (
    r"\bimposible\b", r"\bnunca\b", r"\bsiempre\b", r"\bjamas\b",
    r"\bcero\s+(?:riesgo|fallos?|errores?)\b",
    r"\bdemostrad", r"\bprobad[oa]\s+que\b",
    r"\b(?:es|son)\s+(?:falso|falsos|falsa|falsas)\b",
    r"\bno\s+hay\s+(?:forma|manera)\b",
)

# Acciones clínicas de EMMA que no están en `_ACCION` (también las usa `decision_risk.py`).
EMMA_ACTIONS: tuple[str, ...] = (r"\bpuncion\b", r"\bdrena(?:je|r)\b")
# Lo que bloquea de `decision_alto_riesgo.py::_TTO` y `_ACCION`: las acciones terapéuticas, sin
# los fármacos de su caso, más las de EMMA.
_TREATMENT = r"tratamiento|terapia|medicacion|farmaco|pastillas?|pauta"
_ACTION: tuple[str, ...] = (
    r"(?:duplic|dobl|subi|suba|baj|aument|reduc|escal|desescal|ajust|cambi|modific)\w*"
    r"(?:\s+\w+){0,2}\s+(?:la\s+|de\s+)?dosis",
    r"dosis\s+(?:doble|mas alta|mas baja|de carga|maxima)",
    r"(?:suspend\w*|interrump\w*|\bpar(?:ar|amos|o|e|emos|en|as|arlo|arla)\b|dej\w*|abandon\w*|"
    r"retir\w*|discontinu\w*)(?:\s+\w+){0,3}?\s+(?:" + _TREATMENT + r")",
    # «seguimiento del tratamiento» no es seguir con él.
    r"(?:continu\w*|segui(?!miento)\w*|mant[ei]n\w*)(?:\s+\w+){0,3}?\s+(?:" + _TREATMENT + r")",
    r"(?:empez|inici|comenz|arranc)\w*(?:\s+\w+){0,3}?\s+(?:" + _TREATMENT + r")",
    r"\bre-?biopsi\w*", r"\bbiopsi\w*",
    r"\bopera(?:r|rle|rla)\b", r"\bcirugia\b", r"\breseca\w*|\breseccion\b", r"\bablacion\b",
    *EMMA_ACTIONS,
)

# Lo que bloquea de `decision_alto_riesgo.py::_DELIBERA_FUERTE`: las formas que, escritas por el
# sistema, recomiendan (las de primera persona no las escribe un borrador), más las de EMMA.
_DELIBERATE: tuple[str, ...] = (
    r"\bdeberi\w+\b", r"\bconviene\b", r"\bmerece la pena\b", r"\bvale la pena\b",
    r"\bes razonable\b", r"\bvalorar si\b", r"\bes recomendable\b", r"\bse recomienda\b",
)

_PATTERNS["overclaim"] = _OVERCLAIM
_PATTERNS["order"] = (*_PATTERNS["order"], *_ACTION)

# Las listas completas de Polaris, tal cual: todo lo que cazan y no bloquea arriba, avisa.
_POLARIS_FULL: dict[str, tuple[re.Pattern[str], ...]] = {
    "overclaim": tuple(re.compile(pattern) for pattern in _HONESTY._TRIGGERS),
    "order": tuple(_HIGH_RISK._ACCION),
}

# La deliberación solo bloquea afirmada. Formulada como pregunta al médico ("¿conviene repetir la
# medida?") es justo lo que la sección de preguntas del borrador tiene que contener: la decisión
# queda en quien la lee. En Polaris esas mismas palabras son, precisamente, preguntas.
_DELIBERATE_COMPILED: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern) for pattern in _DELIBERATE
)
# "Confirma que…" / "descarta que…" afirmado es un veredicto; como pregunta al médico ("¿se
# confirma que la imagen es suficiente?") es una duda de procedimiento. Visto con el modelo real
# el 2026-09-25. "Confirma la trombosis" nombra lo confirmado y bloquea siempre, arriba. Es también
# la forma de un imperativo («Descarta que haya sangrado?»), así que solo lo exime una pregunta
# abierta con «¿»: un «?» al final no vuelve pregunta una orden.
_STATED_DIAGNOSIS = (re.compile(r"\b(?:confirma|descarta|excluye)n? que\b"),)

# Qué es una pregunta: una sola regla, aquí, para este filtro y para las notas de Tierra. Nació en
# ellas (revisión de código, 2026-10-26) y pasó aquí por decisión del usuario (2026-10-31): antes
# una pregunta iba del final de la frase anterior al «?», así que en «Conviene repetir la medida,
# ¿vale?» la coletilla volvía pregunta la frase entera.
#   * Abierta: de «¿» a «?», con sus comas dentro, sin cruzar un fin de frase; un «¿» suelto al
#     principio taparía todo lo que le sigue.
#   * Sin «¿»: desde el último corte de frase o de cláusula («.», «,», «;», «:», y también
#     paréntesis, raya o guion, que hacen de coma en «repita la medida — vale?») hasta el «?».
_OPENED_QUESTION = re.compile(r"¿[^?¿.!\n]*\?")
_BARE_QUESTION = re.compile(r"[^.!?\n,;:¿(—–-]*\?")

_COMPILED = {
    category: tuple(re.compile(pattern) for pattern in patterns)
    for category, patterns in _PATTERNS.items()
}

# --- Inglés: un grupo por cada grupo castellano de arriba, con su misma categoría -----------------
# Se busca sobre el texto normalizado (minúsculas; «µ» llega como la mu griega, U+03BC).
_EN_DOSING: tuple[str, ...] = (
    r"\b\d+(?:[.,]\d+)?\s*(?:mg|mcg|μg|ug|g|ml|iu|meq)\b",
    r"\b\d+(?:[.,]\d+)?\s*(?:(?:milli|micro)?gram(?:me)?s?|millilit(?:er|re)s?)\b",
    r"\b\d+(?:[.,]\d+)?\s*(?:international\s+)?units?\s+of\b",
    # «Radiation dose» y «dose rate» son la magnitud que EMMA mide, no una pauta. El castellano
    # lo esquiva escribiendo «radiación»; en inglés no hay otra palabra.
    r"(?<!radiation )(?<!absorbed )(?<!effective )(?<!equivalent )\bdoses?\b"
    r"(?!\s+(?:rates?|equivalents?|limits?)\b)",
    r"\bdos(?:ed|ing|ages?)\b",
    r"\badminister(?:s|ed|ing)?\b",
    # «National Aeronautics and Space Administration» no administra nada a nadie.
    r"\badministration\s+of\b|\broutes?\s+of\s+administration\b",
    r"\bpills?\b",
    # «Tablet» es también la pantalla y «capsule» la nave: cuentan con su cuenta, su pauta o
    # su toma, no solas («two capsules are docked», «record it on the tablet»).
    r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|half)\s+(?:an?\s+)?tablets?\b",
    r"\btablets?\s+(?:of|per|every|daily|twice|orally|with\s+(?:water|food|meals?))\b",
    r"\bcapsules?\s+(?:per|every|daily|twice|orally|by\s+mouth|with\s+(?:water|food|meals?))\b",
    r"\b(?:take|takes|taking|swallow\w*)\s+(?:\w+\s+){0,2}(?:tablets|capsules)\b",
    r"(?<!lunar )(?<!mars )(?<!earth )(?<!orbit )(?<!orbital )(?<!fault )\binjections?\b",
    r"\b(?:intravenous\w*|intramuscular\w*|subcutaneous\w*)\b",
    # Como en castellano («prescrib», no «prescripción»): «not a prescription» es de EMMA.
    r"\b(?:drugs?|medications?|prescrib\w*)\b",
    r"\bcatheter\w*\b",
)
_EN_MODIFIERS = (
    r"(?:(?!(?:for|of|to|on|about|with|in|by|from|as|at|than|against)\b)\w+\s+){0,2}"
)
_EN_DIAGNOSIS: tuple[str, ...] = (
    r"\bdiagnos\w*\b",
    r"\b(?:suffers?|suffering)\s+from\b",
    # En inglés el adjetivo va delante («a deep vein thrombosis»): hasta dos palabras entre el
    # artículo y el nombre, que no sean la preposición de otra frase («has a protocol for…»).
    r"\bhas\s+(?:an?\s+)?" + _EN_MODIFIERS
    + r"(?:syndrome|thrombosis|urinary\s+retention|pneumothorax)\b",
    r"\b(?:confirms|rules\s+out)\s+(?:the|an?)\b",
    r"\bis\s+(?:an?\s+)?" + _EN_MODIFIERS + r"(?:sans|thrombosis|pneumothorax|ha?emorrhage)\b"
    r"(?!\s+(?:risk|indicator|marker|sign|screen\w*|measure\w*|monitor\w*|protocol|study|check\w*|"
    r"evidence|data|research))",
    # «Consistent with your baseline» compara con la línea base, no insinúa un diagnóstico.
    r"\bconsistent\s+with\b(?!\s+(?:(?:the|your|their|his|her|its|an?)\s+)?"
    r"(?:personal\s+|own\s+|individual\s+)?"
    r"(?:baseline|previous|earlier|prior|protocol|standard|expected|reference))",
    r"\bcompatible\s+with\b",
    r"\b(?:suggestive|indicative)\s+of\b|\bsuggests?\b",
)
_EN_CERTAINTY: tuple[str, ...] = (
    r"\b(?:without|beyond)\s+(?:any\s+|a\s+|all\s+)?doubt\b|\bno\s+doubt\b|\bundoubtedly\b",
    r"\bwith\s+(?:total\s+|complete\s+|absolute\s+|full\s+)?certainty\b|\bcertainly\b",
    r"\bdefinitely\b",
    r"\bguarantee\w*\b",
    r"\b100\s*%",
    r"\b(?:for\s+sure|surely|it(?:\s+is|['’]s)\s+(?:certain|safe))\b",
    # «Make sure that the probe…» es un paso de medida, no una certeza.
    r"(?<!make )(?<!makes )(?<!making )(?<!be )\bsure\s+that\b",
)
_EN_ORDER: tuple[str, ...] = (
    r"\b(?:must|shall|has\s+to|have\s+to|needs?\s+to)\s+(?:be\s+)?"
    r"(?:treat(?:ed)?|take|taken|receive|given|evacuated?)\b",
    r"\b(?:immediate|urgent)\s+(?:treatment|therapy)\b",
    r"\b(?:treatment|therapy)\s+(?:immediately|urgently)\b",
)
_EN_OVERCLAIM: tuple[str, ...] = (
    r"\bimpossible\b",
    # Un absoluto sobre el dato («never arrived», «always signed») es un hecho del registro.
    r"\b(?:never|always)\b(?!\s+(?:arrived?|arrives|received|recorded|logged|stored|saved|signed|"
    r"sent|transmitted|uploaded|synced|synchroni[sz]ed|connected|paired|enters?|leaves?)\b)",
    r"\bzero[\s-]+(?:risk|failures?|errors?)\b|\brisk[- ]free\b",
    r"\bproven\b|\b(?:proves|proved|demonstrates|demonstrated)\s+that\b",
    r"\b(?:is|are)\s+(?:false|untrue)\b(?!\s+(?:alarms?|positives?|negatives?))",
    r"\bno\s+way\b",
)

# Gemelas de `EMMA_ACTIONS`. «Battery drain» no es un drenaje, ni «suit puncture» una punción.
EMMA_ACTIONS_EN: tuple[str, ...] = (
    r"(?<!suit )(?<!hull )(?<!glove )\bpunctures?\b",
    r"\bdrainage\b",
    r"\bdrain(?:s|ed|ing)?\s+(?:the\s+|an?\s+)?"
    r"(?:effusion|fluid|abscess|bladder|collection|ha?ematoma)\b",
)
_EN_TREATMENT = r"treatments?|therap(?:y|ies)|medications?|meds|drugs?|pills?|regimens?"
_EN_GAP = r"(?:\s+\w+){0,3}?\s+(?:"
_EN_ACTION: tuple[str, ...] = (
    r"\b(?:doubl|rais|lower|increas|decreas|reduc|escalat|de-?escalat|adjust|chang|modif|titrat)\w*"
    r"(?:\s+(?!radiation\b)\w+){0,2}\s+(?:dose|dosage)\b",
    r"\b(?:double|higher|lower|loading|maximum)\s+(?:dose|dosage)\b",
    r"\b(?:stop\w*|discontinu\w*|suspend\w*|interrupt\w*|halt\w*|ceas\w*|abandon\w*|"
    r"withdr[ae]w\w*|withhold\w*)" + _EN_GAP + _EN_TREATMENT + r")\b",
    # «Treatment follow-up» no es seguir con él: no hay «follow» aquí.
    r"\b(?:continu\w*|maintain\w*|resum\w*)" + _EN_GAP + _EN_TREATMENT + r")\b",
    r"\b(?:start\w*|begin\w*|began|begun|initiat\w*|commenc\w*)" + _EN_GAP + _EN_TREATMENT + r")\b",
    r"\bbiops\w*",
    # «Operating on battery» es del sensor.
    r"\boperat(?:e|es|ed|ing)\s+on\s+(?:the\s+)?(?:patient|crew\w*|him|her|them)\b",
    r"\bsurger(?:y|ies)\b", r"\bresect\w*", r"(?<!shield )\bablation\b",
    *EMMA_ACTIONS_EN,
)
# Gemelas de `_DELIBERATE`: bloquean afirmadas, no como pregunta. «Consider resting» no recomienda
# más que «considerar»; «recommendation» y «recommended action» son nombres, como en castellano.
_EN_IS = r"(?:\b(?:is|are|be)\s+|['’]s\s+)"  # «is», «are», «be» y la contracción «it's»
_EN_DELIBERATE: tuple[str, ...] = (
    r"\bshould(?:n['’]t)?\b", r"\bought\s+to\b",
    _EN_IS + r"advisable\b", r"\bit(?:\s+is|['’]s)\s+best\s+to\b", r"(?:\bhad|['’]d)\s+better\b",
    # «Three days' worth of data» es una cantidad.
    r"(?<!['’] )(?<!['’]s )\bworth\b|\bworthwhile\b",
    _EN_IS + r"reasonable\b",
    r"\b(?:consider|assess|evaluate|weigh)\s+(?:whether|if)\b",
    _EN_IS + r"recommended\b",
)
_EN_PATTERNS: dict[str, tuple[str, ...]] = {
    "dosing": _EN_DOSING,
    "diagnosis": _EN_DIAGNOSIS,
    "certainty": _EN_CERTAINTY,
    "order": (*_EN_ORDER, *_EN_ACTION),
    "overclaim": _EN_OVERCLAIM,
}
_EN_COMPILED = {
    category: tuple(re.compile(pattern) for pattern in patterns)
    for category, patterns in _EN_PATTERNS.items()
}
_EN_DELIBERATE_COMPILED: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern) for pattern in _EN_DELIBERATE
)
# Gemela de `_STATED_DIAGNOSIS`. «Confirm that the image is sharp» es un paso: solo las formas que
# afirman.
_EN_STATED_DIAGNOSIS = (
    re.compile(r"\b(?:confirms|rules\s+out|is\s+confirmed|is\s+ruled\s+out)\s+that\b"),
)
# La pregunta abierta inglesa, que no tiene «¿»: empieza la frase un auxiliar invertido y la
# cierra «?», con sus comas dentro y sin cruzar un fin de frase. Delante solo puede ir lo que abre
# un renglón (viñeta, comilla, paréntesis). Los interrogativos («when», «what»…) no abren: son
# también la conjunción de una afirmación («When the pain returns, the crew should rest?»), y la
# pregunta que empiezan sin coma ya la exime la regla de siempre.
_EN_OPENED_QUESTION = re.compile(
    r"(?:^|(?<=[.!?\n]))[\s\"“'‘(*•–—-]*(?:is|are|was|were|am|do|does|did|has|have|had|can|could|"
    r"should|would|will|shall|may|might|must)\b[^?¿.!\n]*\?"
)


@dataclass(frozen=True)
class Finding:
    category: str
    match: str
    start: int = -1
    end: int = -1

    def to_dict(self) -> dict[str, str]:
        return {"category": self.category, "match": self.match}


def normalize(text: str) -> str:
    """Minúsculas, sin tildes y sin caracteres invisibles.

    Sin esto, "Administré", "ADMINISTRE" o "admi​nistre" se colaban por un patrón escrito
    en minúsculas y sin tilde.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    visible = "".join(
        char for char in decomposed
        if not unicodedata.combining(char) and unicodedata.category(char) != "Cf"
    )
    return visible.lower()


def _found(category: str, pattern: re.Pattern[str], text: str) -> list[Finding]:
    return [
        Finding(category, match.group(0), match.start(), match.end())
        for match in pattern.finditer(text)
    ]


def _blanked(question: re.Pattern[str], plain: str) -> str:
    """Tapa con espacios de su longitud lo que caza `question`: las posiciones siguen valiendo."""
    return question.sub(lambda match: " " * len(match.group(0)), plain)


def outside_opened_questions(plain: str, lang: i18n.Lang | None = None) -> str:
    """El texto normalizado sin las preguntas con «¿»: lo único que exime a un imperativo.

    En inglés, además, sin las que abre un auxiliar o un interrogativo (`_EN_OPENED_QUESTION`).
    """
    # `lang` se fija como idioma en curso y se vuelve a entrar, aquí y en las otras tres funciones
    # públicas, en vez de pasarlo hacia abajo: las líneas de siempre (`stated(plain)`,
    # `check(text)`) no cambian, y son las que mutan las campañas del castellano.
    if lang is not None:
        with i18n.use(lang):
            return outside_opened_questions(plain)
    if i18n.current() == "en":
        plain = _blanked(_EN_OPENED_QUESTION, plain)
    return _blanked(_OPENED_QUESTION, plain)


def stated(plain: str, lang: i18n.Lang | None = None) -> str:
    """El texto normalizado sin ninguna de sus preguntas, con «¿» o sin él."""
    if lang is not None:
        with i18n.use(lang):
            return stated(plain)
    return _blanked(_BARE_QUESTION, outside_opened_questions(plain))


def _english(plain: str, said: str, unopened: str) -> list[Finding]:
    """Lo que cazan los grupos ingleses, en el orden de `check`: grupos, deliberación, veredicto."""
    return [
        *(found for category, patterns in _EN_COMPILED.items()
          for compiled in patterns for found in _found(category, compiled, plain)),
        *(found for compiled in _EN_DELIBERATE_COMPILED
          for found in _found("order", compiled, said)),
        *(found for compiled in _EN_STATED_DIAGNOSIS
          for found in _found("diagnosis", compiled, unopened)),
    ]


def _merged(*groups: list[Finding]) -> list[Finding]:
    """Los hallazgos en su orden, sin repetir el mismo tramo de la misma categoría."""
    unique: dict[tuple[str, int, int], Finding] = {}
    for group in groups:
        for finding in group:
            unique.setdefault((finding.category, finding.start, finding.end), finding)
    return list(unique.values())


def check(text: str, lang: i18n.Lang | None = None) -> list[Finding]:
    """Todo lo que el texto dice y EMMA no puede decir: bloquea. Lista vacía = pasa.

    `lang`: el idioma cuyos patrones se aplican; `None`, el de la petición. En inglés van primero
    los hallazgos ingleses y después los castellanos que no repitan tramo.
    """
    if lang is not None:
        with i18n.use(lang):
            return check(text)
    plain = normalize(text)
    findings: list[Finding] = []
    for category, patterns in _COMPILED.items():
        for pattern in patterns:
            findings.extend(_found(category, pattern, plain))
    said = stated(plain)
    for pattern in _DELIBERATE_COMPILED:
        findings.extend(_found("order", pattern, said))
    unopened = outside_opened_questions(plain)
    for pattern in _STATED_DIAGNOSIS:
        findings.extend(_found("diagnosis", pattern, unopened))
    if i18n.current() == "en":
        return _merged(_english(plain, said, unopened), findings)
    return findings


def advisories(text: str, lang: i18n.Lang | None = None) -> list[Finding]:
    """Lo que las listas completas de Polaris cazan y EMMA no bloquea: se enseña, no bloquea.

    Un aviso que cae sobre un tramo que ya bloquea no se repite. Las listas de Polaris son
    castellanas en los dos idiomas; `lang` decide qué bloquea ya y, por tanto, qué no se repite.
    """
    if lang is not None:
        with i18n.use(lang):
            return advisories(text)
    plain = normalize(text)
    blocked = [(finding.start, finding.end) for finding in check(text)]
    found = [
        *(finding for category, patterns in _POLARIS_FULL.items()
          for pattern in patterns for finding in _found(category, pattern, plain)),
        *_found("order", _HIGH_RISK._DELIBERA_FUERTE, stated(plain)),
    ]
    unique: dict[tuple[int, int], Finding] = {}
    for finding in found:
        if not any(start < finding.end and finding.start < end for start, end in blocked):
            unique.setdefault((finding.start, finding.end), finding)
    return list(unique.values())
