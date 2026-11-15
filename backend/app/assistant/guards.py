"""Las barreras de cada respuesta del modelo del asistente: si una falla, habla el backend.

Por qué existe: el asistente habla, y lo que dice en voz alta no pasa por los ojos de nadie antes
de oírse. El borrador de interpretación tiene firma humana detrás; una respuesta hablada, no. Así
que cada respuesta del modelo pasa, entera, por cuatro barreras deterministas, y basta que falle
una para que no se diga:

  * **text_guard**: el linter de lenguaje de EMMA (`app/text_guard.py`): dosis, diagnósticos,
    certezas, órdenes y acciones terapéuticas.
  * **numbers**: toda cifra de la respuesta está en el contexto que se le dio o en lo que dijo la
    persona (`interpret.draft.unsupported_numbers`, la misma regla de redondeo). También las cifras
    escritas con letras: «setenta y cuatro» cuenta como 74 y se coteja igual; una que no se sabe
    leer («mil doscientos») no pasa. Y de quién son: una respuesta que hable de otro tripulante
    no pasa, porque el contexto es solo del de la consola (`companion_ok`, 2026-11-04).
  * **no_prescription**: no recetar. Nombres de fármacos y formas («pastilla», «comprimido»),
    dosis y unidades, «tome», «tómese», «debes tomar», «te receto»… Más estricta que el linter a
    propósito: aquí no hay quien revise antes de oírlo, y una negativa del modelo que nombre una
    pastilla también cae (entonces se dice la negativa fija del backend, que es la misma idea).
  * **schema**: el JSON del modelo es un objeto con una intención del catálogo y argumentos que
    cumplen su esquema (`catalog.validate_args`); lo comprueba `turn.py`.

EN INGLÉS, LAS DOS A LA VEZ (2026-11-15). Con la consola en inglés el modelo contesta en inglés,
pero nada le impide soltar una frase en castellano: cada barrera de palabras (no recetar, de quién
son los datos, lo clínico en una respuesta general) aplica entonces sus patrones ingleses Y los
castellanos de siempre. Más estricta, nunca menos. En castellano no cambia nada: los patrones
ingleses ni se miran.
"""

from __future__ import annotations

import re

from app.core import i18n
from app.interpret.draft import unsupported_numbers
from app.text_guard import check, normalize

_PRESCRIPTION: tuple[re.Pattern[str], ...] = tuple(re.compile(pattern) for pattern in (
    # Imperativos y obligaciones de tomar algo. «Tomar la tensión» no es un imperativo, y
    # «tómate» no está porque sin tilde es «tomate», un alimento que el diario valora: lo que se
    # toma lo cazan las formas y los fármacos de abajo.
    r"\btom(?:e|es|en|ese|enlo|elo|ela|atelo|atela|aos)\b",
    r"\b(?:debe|debes|deben|deberia\w*|tiene que|tienes que|hay que|puede|puedes|podrias)"
    r"\s+tomar\w*",
    # Formas farmacéuticas y grupos de fármacos.
    r"\b(?:pastillas?|pildoras?|comprimidos?|capsulas?|jarabes?|supositorios?|inyecci\w+|"
    r"ampollas?|parches? de|pomadas?|colirios?)\b",
    r"\b(?:analgesic|antiinflamatori|antibiotic|antihistaminic|ansiolitic|antidepresiv|"
    r"somnifer|hipnotic|antiemetic|antipiretic|sedant|corticoid|opioid|opiace)\w*",
    # Fármacos que un tripulante podría nombrar a bordo (botiquín de la ISS y de uso común).
    r"\b(?:ibuprofeno|paracetamol|acetaminofeno?|aspirina|naproxeno|diclofenaco|metamizol|"
    r"melatonina|zolpidem|zaleplon|modafinilo|prometazina|escopolamina|meclizina|ondansetron|"
    r"loratadina|cetirizina|omeprazol|loperamida|amoxicilina|ciprofloxacino|diazepam|"
    r"lorazepam|tramadol|morfina|codeina)\b",
    # Dosis, cantidades y recetar.
    # «Dosis» de un fármaco; la de radiación es un dato del estado y se puede preguntar por ella
    # (en la respuesta del modelo la sigue parando el linter, que no distingue).
    r"\bdosis\b(?!\s+(?:de\s+)?(?:radiacion|equivalente|efectiva|absorbida|acumulada))",
    # `normalize` (NFKD) vuelve el signo micro «µ» la letra griega «μ»: van las dos.
    r"\b\d+(?:[.,]\d+)?\s*(?:mg|mcg|µg|μg|ug|ml|ui|gotas)\b",
    r"\bmiligram\w*", r"\b(?:te|le|os|les) recet\w*", r"\brecet\w*", r"\bprescri\w*",
    r"\b(?:medicamento|medicacion|farmaco|medicina)s?\b",
))

# Lo que pregunta la persona, para darle la negativa fija sin esperar a ver qué dice el modelo.
# La «dosis» suelta va aparte (`_DOSE_WORD`): en una pregunta se lee también la de radiación.
_DOSE_WORD = re.compile(r"\bdosis\b")
# El imperativo «tome/tomes» tampoco: en lo que dice la persona es casi siempre otra cosa («no
# hace falta que tomes la iniciativa»; medido el 2026-11-04). Lo que pregunta qué tomar va abajo.
_ASKS_MEDICATION: tuple[re.Pattern[str], ...] = (
    *(pattern for pattern in _PRESCRIPTION
      if not pattern.pattern.startswith((r"\bdosis\b", r"\btom(?:e|"))),
    re.compile(r"\bque (?:me )?(?:tomo|tomare|puedo tomar|deberia tomar)\b"),
    re.compile(r"\b(?:me )?tomo algo\b"),
    re.compile(r"\btomarme algo\b"),
)
# Cuándo «dosis» en lo que dice la persona es la de radiación o la de un panel, no la de un
# fármaco: con palabras de radiación, de acumular (la dosis de carrera se lleva, se acumula) o de
# pantalla. Medido el 2026-11-04: «léeme lo que pone en este panel de la dosis» recibía la negativa
# de no recetar. Un fármaco nombrado sigue cayendo por su propio patrón, diga lo que diga al lado.
_RADIATION_DOSE = re.compile(
    r"\b(?:radiac\w*|radiad\w*|msv|usv|sievert\w*|gray|mgy|dosimetr\w*|carrera|acumulad\w*|"
    r"acumul\w*|llevo|llevamos|lleva|recibid\w*|absorbid\w*|equivalente|efectiva|solar\w*|"
    r"panel|pestana|pantalla|apartado|recuadro|barra|medidor|limite)\b"
)

# --------------------------------------------------------------------------- #
# No recetar, en inglés
# --------------------------------------------------------------------------- #
#
# Al menos tan estricta como la castellana, patrón por patrón. Sobre texto de `normalize`: en
# minúsculas, sin tildes y CON su puntuación («don't» sigue siendo «don't»).

# Lo que sí se «toma» sin ser un fármaco: una medida, un descanso, un tiempo. Todo lo demás que
# siga a «take» en una respuesta del modelo se trata como tomar algo.
_NOT_A_DRUG = (
    r"(?:(?:a|an|the|your|my|another|some|one|more)\s+)?"
    r"(?:look|note|notes|break|rest|nap|breath|reading|readings|measurement|measurements|"
    r"sample|samples|photo|picture|temperature|blood pressure|pulse|weight|time|care|place|"
    r"part|action|priority|effect|shape|into account|over|off|longer|about|around|roughly|"
    r"approximately|nearly|almost|up to|less than|more than|between|"
    r"a while|(?:the\s+)?(?:pvt|test|initiative)|you\b|me\b|us\b|"
    r"a long time|some time|long\b|"
    r"(?:\d+(?:[.,]\d+)?|a few|several|many|a couple of|some)\s+"
    r"(?:seconds?|minutes?|hours?|days?|weeks?|months?|years?))"
)
_PRESCRIPTION_EN: tuple[re.Pattern[str], ...] = tuple(re.compile(pattern) for pattern in (
    # Imperativos y obligaciones de tomar algo. En inglés el imperativo y el infinitivo son la
    # misma palabra, así que cae todo «take» que no sea de la lista de arriba («take your
    # temperature» pasa; «take one», «take it», «take something for it», no).
    rf"\btak(?:e|es|ing)\b(?!\s+{_NOT_A_DRUG})",
    r"\b(?:should|must|ought to|need to|needs to|have to|has to|had better|can|could|may|"
    r"might|want to|try to|going to)\s+(?:\w+\s+)?take\b(?!\s+" + _NOT_A_DRUG + ")",
    # Formas farmacéuticas y grupos de fármacos. «Tablet» también es una pantalla: en lo que DICE
    # el modelo cae igual (se oye la frase del backend, que es lo seguro); en lo que pregunta la
    # persona, no (`_ASKS_MEDICATION_EN`).
    r"\b(?:pills?|tablets?|caplets?|capsules?|lozenges?|syrups?|suppositor(?:y|ies)|"
    r"injections?|ampoules?|ampules?|ointments?|salves?|eye ?drops|ear ?drops|nasal sprays?|"
    r"inhalers?|(?:skin|transdermal|medicated|nicotine|pain) patch(?:es)?)\b",
    r"\b(?:analgesi|painkill|pain reliev|pain med|anti-?inflammator|antibiotic|antihistamin|"
    r"anxiolytic|antidepress|sleeping (?:pill|aid|tablet)|sleep aid|hypnotic|antiemetic|"
    r"antipyretic|sedati|corticosteroid|steroid|opioid|opiate|nsaid|decongestant|laxative|"
    r"antacid|tranquilli?z)\w*",
    # Fármacos que un tripulante podría nombrar a bordo, por su nombre genérico y de marca.
    r"\b(?:acetaminophen|paracetamol|tylenol|ibuprofen|advil|motrin|aspirin|naproxen|aleve|"
    r"diclofenac|metamizole|dipyrone|melatonin|zolpidem|ambien|zaleplon|modafinil|provigil|"
    r"promethazine|phenergan|scopolamine|meclizine|ondansetron|zofran|loratadine|claritin|"
    r"cetirizine|zyrtec|diphenhydramine|benadryl|pseudoephedrine|sudafed|omeprazole|"
    r"loperamide|imodium|amoxicillin|ciprofloxacin|cipro|diazepam|valium|lorazepam|ativan|"
    r"tramadol|morphine|codeine)\b",
    # Dosis, cantidades y recetar. La dosis de radiación es un dato del estado: en inglés el
    # adjetivo va delante («radiation dose», «career dose») o detrás con «of».
    r"(?<!radiation )(?<!career )(?<!effective )(?<!equivalent )(?<!absorbed )"
    r"(?<!cumulative )(?<!accumulated )(?<!skin )(?<!organ )"
    r"\bdos(?:e|es|age|ages|ing)\b(?!\s+(?:of\s+)?(?:radiation|equivalent|rate|limits?))",
    r"\b\d+(?:[.,]\d+)?\s*(?:mg|mcg|µg|μg|ug|ml|cc|iu|drops)\b",
    r"\bmilligram\w*", r"\bmicrogram\w*", r"\bmillilit\w*", r"\bprescri\w*", r"\badminister\w*",
    r"\b(?:medications?|medicines?|medicament\w*|drugs?|meds|pharmaceuticals?|remed(?:y|ies))\b",
))
_DOSE_WORD_EN = re.compile(r"\bdos(?:e|es|age|ages|ing)\b")
# Lo que pregunta la persona. Sin el «take» suelto («how long does it take to reach Mars?» no
# pide un fármaco), sin la dosis suelta (va aparte, como en castellano) y sin «tablet» (la
# pantalla); lo que pregunta qué tomar va abajo.
_ASKS_MEDICATION_EN: tuple[re.Pattern[str], ...] = (
    *(pattern for pattern in _PRESCRIPTION_EN
      if not pattern.pattern.startswith((r"\btak(?:e|", r"(?<!radiation )", r"\b(?:should|",
                                         r"\b(?:pills?|"))),
    re.compile(r"\b(?:pills?|caplets?|capsules?|lozenges?|syrups?|suppositor(?:y|ies)|"
               r"injections?|ampoules?|ampules?|ointments?|salves?|eye ?drops|ear ?drops|"
               r"nasal sprays?|inhalers?|(?:skin|transdermal|medicated|nicotine|pain) "
               r"patch(?:es)?|(?:one|two|three|some|any|\d+) tablets?)\b"),
    re.compile(r"\bwhat (?:can|should|could|do|shall|may|would|must) (?:i|we) take\b"),
    re.compile(r"\b(?:can|should|could|may|shall|must|do) (?:i|we) (?:need to )?take "
               r"(?:something|anything|one|some|it|them|more|another)\b"
               r"(?!\s+(?:off|out|down|apart|away|over|look|break|reading|measurement))"),
    re.compile(r"\btak(?:e|ing) (?:something|anything) (?:for|to)\b"),
    re.compile(r"\b(?:something|anything) (?:i can take |to take )?for (?:the |my |this |a )?"
               r"(?:pain|headache|nausea|fever|sleep|insomnia|cough|allergy|stress|anxiety)\b"),
)
_RADIATION_DOSE_EN = re.compile(
    r"\b(?:radiation|irradiat\w*|msv|usv|sievert\w*|gray|mgy|dosimet\w*|career|cumulative|"
    r"accumulat\w*|so far|received|absorbed|equivalent|effective|solar\w*|panel|tab|screen|"
    r"section|box|bar|meter|gauge|limits?|rate)\b"
)

_UNITS = {
    "cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
}
_TEENS = {
    "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
    "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19, "veinte": 20,
    "veintiuno": 21, "veintiuna": 21, "veintidos": 22, "veintitres": 23, "veinticuatro": 24,
    "veinticinco": 25, "veintiseis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29,
    "cien": 100,
}
_TENS = {
    "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80,
    "noventa": 90,
}
# Lo que no se sabe leer como una cifra sola: no se deja pasar.
# Las centenas van pegadas («doscientos», «trescientas»): sin `\b` delante.
_UNREADABLE = re.compile(r"(?:cient(?:o|os|as)|quinient(?:os|as)|setecient(?:os|as)|"
                         r"novecient(?:os|as))\b|\b(?:mil|miles|millon\w*)\b")
_WORD = re.compile(r"[a-z]+")

# Las cifras con letras en inglés. «A», «an» y «one» solos no cuentan, como «un» y «uno»: son
# casi siempre artículo o pronombre («the one on the left»). «Twenty one» sí es 21.
_UNITS_EN = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9,
}
_TEENS_EN = {
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS_EN = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90,
}
# Lo que no se sabe leer como una cifra sola. «A hundred» y «one hundred» a secas son 100 (como
# «cien»); «one hundred and twenty» o «two hundred», como «ciento veinte», no se dejan pasar.
_UNREADABLE_EN = re.compile(r"\b(?:thousands?|millions?|billions?|dozens?)\b")
_COUNTS_EN = frozenset({*_UNITS_EN, *_TEENS_EN, *_TENS_EN})


def language_ok(reply: str) -> bool:
    """El linter de lenguaje de EMMA no caza nada."""
    return not check(reply)


def _spelled_in_english(plain: str) -> tuple[list[float], bool]:
    """`spelled_numbers` para el inglés: «seventy-four» y «seventy four» son 74."""
    words = _WORD.findall(plain)
    found: list[float] = []
    unreadable = bool(_UNREADABLE_EN.search(plain))
    index = 0
    while index < len(words):
        word = words[index]
        following = words[index + 1] if index + 1 < len(words) else ""
        if word in _TENS_EN:
            value = _TENS_EN[word]
            if following in _UNITS_EN and following != "zero":
                value += _UNITS_EN[following]
                index += 1
            found.append(float(value))
        elif word in _TEENS_EN:
            found.append(float(_TEENS_EN[word]))
        elif word == "hundred":
            before = words[index - 1] if index else ""
            if before in ("a", "one") and following != "and" and following not in _COUNTS_EN:
                found.append(100.0)
            else:
                unreadable = True
        elif word in _UNITS_EN and word != "one":
            if following == "hundred":
                unreadable = True  # «two hundred»: ni 2 ni 100
            else:
                found.append(float(_UNITS_EN[word]))
        index += 1
    return found, unreadable


def spelled_numbers(text: str) -> tuple[list[float], bool]:
    """Las cifras escritas con letras, y si hay alguna que no se sabe leer.

    «Un» y «una» son artículos casi siempre: no se cuentan como cifra si van solos.
    """
    plain = normalize(text)
    if i18n.current() == "en":
        # Las dos lecturas: una respuesta en inglés puede traer una cifra en castellano. Salvo
        # «once» y «miles», que en inglés son «una vez» y «millas», no el 11 ni «miles de».
        english, unreadable = _spelled_in_english(plain)
        spanish, also = _spelled_in_spanish(_FALSE_FRIENDS.sub(" ", plain))
        return english + spanish, unreadable or also
    return _spelled_in_spanish(plain)


_FALSE_FRIENDS = re.compile(r"\b(?:once|miles)\b")


def _spelled_in_spanish(plain: str) -> tuple[list[float], bool]:
    words = _WORD.findall(plain)
    found: list[float] = []
    index = 0
    while index < len(words):
        word = words[index]
        if word in _TENS:
            value = _TENS[word]
            if index + 2 < len(words) and words[index + 1] == "y" and words[index + 2] in _UNITS:
                value += _UNITS[words[index + 2]]
                index += 2
            found.append(float(value))
        elif word in _TEENS:
            found.append(float(_TEENS[word]))
        elif word in _UNITS and word not in ("un", "una", "uno"):
            found.append(float(_UNITS[word]))
        index += 1
    return found, bool(_UNREADABLE.search(plain))


def numbers_ok(reply: str, known: str) -> bool:
    """Toda cifra de la respuesta, en dígitos o en letras, sale de `known`."""
    if unsupported_numbers(reply, known):
        return False
    spelled, unreadable = spelled_numbers(reply)
    if unreadable:
        return False
    return not any(unsupported_numbers(f"{value:g}", known) for value in spelled)


def no_prescription(reply: str) -> bool:
    """La respuesta no receta: ni fármacos, ni formas, ni dosis, ni «tome»."""
    plain = normalize(reply)
    if i18n.current() == "en" and any(item.search(plain) for item in _PRESCRIPTION_EN):
        return False
    return not any(pattern.search(plain) for pattern in _PRESCRIPTION)


def _asks_in_english(plain: str) -> bool:
    """`asks_for_medication` con las palabras inglesas: qué tomar, un fármaco o una dosis que no
    es la de radiación."""
    if any(item.search(plain) for item in _ASKS_MEDICATION_EN):
        return True
    return bool(_DOSE_WORD_EN.search(plain) and not _RADIATION_DOSE_EN.search(plain))


def asks_for_medication(text: str) -> bool:
    """¿Pregunta la persona qué tomar? Entonces la respuesta es la negativa fija."""
    plain = normalize(text)
    if i18n.current() == "en" and _asks_in_english(plain):
        return True
    if any(pattern.search(plain) for pattern in _ASKS_MEDICATION):
        return True
    return bool(_DOSE_WORD.search(plain)) and not _RADIATION_DOSE.search(plain)


# --------------------------------------------------------------------------- #
# De quién son los datos (dentro de la barrera «numbers»)
# --------------------------------------------------------------------------- #
#
# El contexto del modelo es el de UN tripulante (el de la consola). Medido el 2026-11-04:
# «¿qué tal está mi compañero?» se contestaba con los datos de crew-01 como si fueran del
# compañero. Las preguntas por otra persona las contesta el backend con el estado de esa persona
# (`turn.py`); y una respuesta del modelo que hable de otro tripulante, en un turno que no es sobre
# él, no se dice: lo único que podría contar de él son datos que no son suyos.

_COMPANION = re.compile(
    r"\b(?:companer[oa]s?|colegas?|otr[oa]s? tripulantes?|los demas|las demas|"
    r"resto de la tripulacion|el resto del equipo)\b"
)
# Por todos a la vez: «¿cómo está la tripulación?», «¿y mis compañeros?».
_GROUP = re.compile(
    r"\b(?:companer[oa]s|colegas|otr[oa]s tripulantes|los demas|las demas|"
    r"resto de la tripulacion|el resto del equipo|toda la tripulacion|la tripulacion|"
    r"todos los tripulantes)\b"
)
# Lo mismo en inglés, sobre texto de `_plain` (sin puntuación).
_COMPANION_EN = re.compile(
    r"\b(?:crewmates?|crew mates?|colleagues?|teammates?|team mates?|companions?|"
    r"other crew members?|another crew member|the others|everyone else|everybody else|"
    r"rest of the crew|rest of the team)\b"
)
_GROUP_EN = re.compile(
    r"\b(?:crewmates|crew mates|colleagues|teammates|team mates|companions|other crew members|"
    r"the others|everyone else|everybody else|rest of the crew|rest of the team|"
    r"the whole crew|the entire crew|the crew|all crew members|all the crew)\b"
)


def asks_about_group(text: str) -> bool:
    """¿Pregunta por la tripulación entera o por «los demás», no por una persona?"""
    plain = _plain(text)
    if i18n.current() == "en" and _GROUP_EN.search(plain):
        return True
    return bool(_GROUP.search(plain))


def _others(subject: str, crew: list[str]) -> set[str]:
    return {_plain(name).strip() for name in crew if name != subject and name.strip()}


def names_companion(text: str, subject: str, crew: list[str]) -> bool:
    """¿Habla el texto de alguien de la tripulación que no es el tripulante de la consola?"""
    plain = _plain(text)
    if i18n.current() == "en" and _COMPANION_EN.search(plain):
        return True
    return bool(_COMPANION.search(plain)) or _names_any(text, _others(subject, crew))


def companion_ok(reply: str, subject: str, crew: list[str]) -> bool:
    """Una respuesta del modelo no atribuye nada a otro tripulante: ni lo nombra ni habla de «tu
    compañero». El contexto que se le dio es solo de `subject`."""
    return not names_companion(reply, subject, crew)


# --------------------------------------------------------------------------- #
# Conocimiento del modelo, sin fuente (`reply_source="general"`, decisión del usuario 2026-11-03)
# --------------------------------------------------------------------------- #
#
# El asistente puede contestar lo que NO es clínico ni del tripulante («¿cuánto tarda la luz del Sol
# a la Tierra?») con lo que el modelo sabe por su cuenta, rotulado aparte. Dos barreras:
#   * la pregunta: si toca la salud, el cuerpo, un indicador, un dominio, el glosario, un fármaco o
#     a un tripulante, o habla de sí misma («llevo», «mi…»), nunca es `general`: ahí solo vale el
#     contexto de EMMA;
#   * la respuesta: no nombra nada de eso, no da cifras con unidades clínicas, no receta y pasa el
#     linter de lenguaje. Si falla, se dice el texto fijo del backend.

# Cifras con unidades clínicas o de dosis: lpm, mSv, mmHg, °C, %…
_CLINICAL_FIGURE = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:lpm|bpm|ppm|rpm|msv|usv|μsv|µsv|sv|mgy|gy|mmhg|°\s*c|º\s*c|°|º|"
    r"grados|%|por ciento|mg|mcg|µg|μg|ug|ml|kg|kcal|mmol|g/dl|mg/dl|ms)(?!\w)"
)
_HEALTH_WORDS = re.compile(
    r"\b(?:salud|medic\w*|sintom\w*|enferm\w*|diagnost\w*|tratamient\w*|dolor\w*|duele|"
    r"lesion\w*|herida\w*|sangr\w*|mare\w*|fiebre|tension|pulso|corazon|cuerpo|dosis)\b"
)
# La persona habla de sí misma o de alguien de la tripulación.
_PERSONAL = re.compile(
    r"\b(?:mi|mis|estoy|tengo|llevo|noto|siento|nuestr\w*|tripulante\w*|"
    r"comandante|astronauta del equipo)\b"
)
# Lo mismo en inglés. Las unidades de `_CLINICAL_FIGURE` no tienen idioma; aquí van las que en
# inglés se dicen con palabra.
_CLINICAL_FIGURE_EN = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:degrees|percent|per cent|beats|breaths)(?!\w)"
)
_HEALTH_WORDS_EN = re.compile(
    r"\b(?:health\w*|medic\w*|symptom\w*|ill|illness\w*|sick\w*|disease\w*|diagnos\w*|"
    r"treatment\w*|therap\w*|pain\w*|hurt\w*|aches?|aching|injur\w*|wound\w*|blood|bleed\w*|"
    r"dizz\w*|nause\w*|fever\w*|blood pressure|pulse|heart|body|dose|doses|dosage)\b"
)
# «I'm» llega aquí como «i m» (`_plain` quita el apóstrofo).
_PERSONAL_EN = re.compile(
    r"\b(?:my|mine|myself|i am|i m|i have|i ve|i feel|i notice|our|ours|crew members?|"
    r"commander|astronaut on the team)\b"
)
MIN_TERM_CHARS = 4


def _plain(text: str) -> str:
    return " " + " ".join(re.sub(r"[^\w\s]", " ", normalize(text)).split()) + " "


@i18n.lang_cache
def clinical_terms() -> frozenset[str]:
    """Lo que nombra EMMA de la salud: indicadores, zonas del cuerpo, dominios y el glosario."""
    # Imports tardíos: el catálogo de indicadores y el glosario son grandes y no hacen falta para
    # las otras barreras.
    from app import guides
    from app.ingest import codes
    from app.ingest.names_es import name_es
    from app.pain.catalog import ZONES

    names: set[str] = set()
    for key, code in codes.CATALOG.items():
        names.add(code.display_es)
        names.add(name_es(key))
    names.update(zone.display for zone in ZONES.values())
    names.update(codes.domain_name(str(domain)) for domain in codes.Domain)
    names.update(str(term["term"]) for term in guides.glossary()["terms"])
    # «Saturación de oxígeno (SpO2)» se nombra sin el paréntesis, y también por lo que lleva dentro.
    parts = set()
    for name in names:
        parts.add(re.sub(r"\([^)]*\)", " ", name))
        parts.update(re.findall(r"\(([^)]*)\)", name))
    plain = {_plain(name).strip() for name in parts}
    # Los nombres largos se dicen por su comienzo: «saturación de oxígeno en sangre arterial» es
    # «saturación de oxígeno». Comienzos de dos y tres palabras que no acaban en una palabra vacía.
    for name in list(plain):
        words = name.split()
        for size in (2, 3):
            if len(words) > size and len(words[size - 1]) >= MIN_TERM_CHARS:
                plain.add(" ".join(words[:size]))
    return frozenset(name for name in plain if len(name) >= MIN_TERM_CHARS)


def _names_any(text: str, words: frozenset[str] | set[str]) -> bool:
    plain = _plain(text)
    return any(f" {word} " in plain for word in words if word)


def about_crew_or_health(text: str, crew: list[str]) -> bool:
    """¿Toca la pregunta la salud, el cuerpo o a alguien de la tripulación? Entonces no es
    general."""
    plain = _plain(text)
    people = {_plain(name).strip() for name in crew}
    if i18n.current() == "en" and (_HEALTH_WORDS_EN.search(plain) or _PERSONAL_EN.search(plain)):
        return True
    return bool(_HEALTH_WORDS.search(plain) or _PERSONAL.search(plain)
                or _names_any(text, clinical_terms()) or _names_any(text, people)
                or asks_for_medication(text))


def general_ok(reply: str, crew: list[str]) -> bool:
    """La respuesta de conocimiento general no toca nada clínico ni del tripulante."""
    people = {_plain(name).strip() for name in crew}
    if i18n.current() == "en" and (_CLINICAL_FIGURE_EN.search(normalize(reply))
                                   or _HEALTH_WORDS_EN.search(_plain(reply))):
        return False
    if _CLINICAL_FIGURE.search(normalize(reply)):
        return False
    if _HEALTH_WORDS.search(_plain(reply)):
        return False
    return not (_names_any(reply, clinical_terms()) or _names_any(reply, people))
