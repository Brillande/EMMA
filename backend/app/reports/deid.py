# SPDX-License-Identifier: AGPL-3.0-or-later
"""Des-identificación del texto de un informe escaneado, con revalidación que falla cerrada.

Por qué existe: el texto del OCR se muestra en la consola y viaja a Tierra con el resto del
registro. Un informe en papel lleva nombre, DNI, número de historia, teléfono y fecha de
nacimiento. Los DICOM ya se des-identifican antes de guardarse (perfil PS3.15); el texto de los
informes no lo estaba (`risk-management-file.md`, H17).

Adaptador sobre `de_identificar_verificado()` de `polaris/tools/deid.py`, de la copia literal de
Polaris (commit en `polaris/ADOPTADO.txt`; AGPL-3.0-or-later, © 2026 la autora de Polaris,
«Beyond the Protocol»; se carga con `app.polaris.load`). El único cambio a ese fichero es el
declarado en `polaris/CAMBIOS.json`. Hace todo el trabajo: correo, teléfono, DNI/NIE, número de
historia, fechas, campos de filiación etiquetados ("Paciente:", "Nombre:", "Fecha de
nacimiento:"), el normalizador contra homoglifos y caracteres invisibles, y la **revalidación**:
si tras enmascarar el detector aún ve algo, el texto no se usa.

Hasta el commit 7bf4725 EMMA usaba una versión adaptada, porque el original dejaba a la vista
"Paciente: <nombre>". El commit e3b588d lo corrige, y el usuario decidió pasar al original
(2026-10-01). Con él, lo visible cambia como lo hace Polaris: el texto sale sin tildes, se
enmascaran también las fechas de la analítica y dos líneas enmascaradas seguidas se funden.

Regla de EMMA, añadida encima (no es un cambio del original): un nombre con su tratamiento en
mitad de una frase ("revisado por la Dra. Ana López") se enmascara. El original lo deja a la
vista y lo da por verificado; lo demuestra `tests/test_reports.py`.

Otra regla de EMMA encima (2026-10-07): el familiar nombrado ("acude con su hermana Lucía
Fernández"). Era lo único del corpus que salía entero, porque no lleva etiqueta ni tratamiento y
ningún patrón del original lo ve. Se tapa el nombre y se queda el parentesco, que es dato clínico
(los antecedentes familiares se escriben con él). Lo que va detrás de un parentesco no siempre es
un nombre ("Madre: Diabetes", "abuelo Parkinson"), así que la regla pide indicios y tiene una
lista de lo que no es un nombre: ver `_mask_relatives`. Lo que deja pasar está en su docstring.
Desde el 2026-10-20 mira también el nombre delante del parentesco ("con Rosa Beltrán, su
cuñada"), que era lo único del corpus que seguía saliendo entero: ver `_name_before_kin`.

LÍMITE, como dice el propio Polaris: una des-identificación por patrones siempre es porosa, y
revalidar con el mismo detector que enmascara caza restos, no demuestra anonimato. Por eso el
original escaneado se guarda aparte, en local, y se puede redactar.

Capa NER (`deid_ner.py` de Polaris, decisión del usuario 2026-10-01): se usa (`ner=True`) solo si
`scripts/install_deid_ner.py` dejó la marca de pesos comprobados en `backend/.venv-deid` (o en
`BTP_VENV_DEID`). Con el entorno pero sin el modelo, cada informe se retendría entero; sin la marca
la capa no se pide. Si se pide y falla, el original devuelve "no verificado" y el texto se retiene.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, NamedTuple

from app import polaris

MARK = "[REDACTADO]"

# Nombre con tratamiento: "Dra. Ana López", "Sr. Pérez". Sin tildes también: el original las
# quita antes de que esta regla mire el texto.
_NAME_WORD = r"[A-ZÁÉÍÓÚÑ][a-záéíóúüñ]+(?:-[A-ZÁÉÍÓÚÑ][a-záéíóúüñ]+)?"
_HONORIFIC = r"(?:Sr|Sra|Srta|D|D[ñn]a|Dr|Dra)\.\s*"
_HONORIFIC_NAME = re.compile(rf"\b{_HONORIFIC}{_NAME_WORD}(?:\s+{_NAME_WORD}){{0,3}}")

# Identificadores que el original deja pasar como "verificados" (medido el 2026-10-01). Van ANTES
# del original, sobre el texto tal cual: sus patrones de teléfono o DNI partirían un IBAN o una
# tarjeta en trozos y dejarían el resto a la vista.
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,3})?\b", re.I)
_CARD = re.compile(r"(?<![\d-])\d(?:[ -]?\d){12,18}(?![\d-])")
_PASSPORT = re.compile(
    r"(\b(?:n[º°o]\.?\s*de\s+)?(?:pasaporte|passport|ppte\.?)\s*(?:n[º°o]\.?\s*)?[:#]?\s*)"
    r"([A-Z]{1,3}\d{5,9}|\d{6,9}[A-Z]?)\b",
    re.I,
)
# Campos de filiación con etiqueta que el original no conoce (medido con el corpus de
# `tests/data/deid_corpus/`, decisión del usuario 2026-10-01): el titular de la póliza o de la
# tarjeta, y el código de la tarjeta sanitaria (TSI, CIP autonómico). Se tapa el valor hasta el fin
# de línea; la etiqueta se queda para que se sepa qué había.
_LABELLED = re.compile(
    r"^([ \t]*(?:titular|tarjeta\s+sanitaria(?:\s+individual)?|tsi|c[oó]digo\s+cip|cip)"
    r"[ \t]*[:#][ \t]*)(\S[^\n]*)$",
    re.I | re.M,
)
_ISO_DATETIME = re.compile(
    r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?"
)

# --- Familiar nombrado: parentesco + nombre propio ------------------------------------------
#
# Va DESPUÉS del original, como la regla del tratamiento: el texto ya llega sin caracteres
# invisibles ni homoglifos, y sin tildes ("tio", "cunado"); se aceptan las dos grafías por si el
# original dejara de quitarlas.
_KIN = (
    r"(?:ex[- ]?)?(?:madre|padre|mam[aá]|pap[aá]|madrastra|padrastro|herman(?:astr)?[oa]"
    r"|hij(?:astr)?[oa]|espos[oa]|marido|mujer|pareja|novi[oa]|c[oó]nyuge|t[ií][oa]"
    r"|bisabuel[oa]|abuel[oa]|niet[oa]|prim[oa]|sobrin[oa]|cu[ñn]ad[oa]|suegr[oa]|yerno|nuera)s?"
)
# "su hermana mayor Lucía", "el abuelo materno Tomás".
_KIN_QUALIFIER = (
    r"(?:mayor|menor|matern[oa]|patern[oa]|adoptiv[oa]|biol[oó]gic[oa]|gemel[oa]|melliz[oa]"
    r"|pol[ií]tic[oa]|peque[ñn][oa])"
)
_KIN_DETERMINER = r"(?:sus?|mis?|tus?|nuestr[oa]s?|el|la|los|las|del|al|una?)"
_INITIAL = r"[A-ZÁÉÍÓÚÑ]\."
_NAME_TOKEN = rf"(?:{_NAME_WORD}|{_INITIAL}|{re.escape(MARK)})"
# Entre dos palabras del nombre: espacio (con partícula o sin ella) o guion. El guion, también
# pegado a una marca: Polaris tapa "Pérez" en "Pérez-Gómez" y deja "[REDACTADO]-Gomez".
_NAME_JOIN = r"(?:[ \t]+(?:(?:de(?:[ \t]+l[ao]s?)?|del|y|e)[ \t]+)?|-)"
_KIN_NAME = re.compile(
    rf"(?P<lead>(?:\b(?P<det>(?i:{_KIN_DETERMINER}))[ \t]+)?"
    rf"\b(?P<kin>(?i:{_KIN}))\b(?:[ \t]+(?i:{_KIN_QUALIFIER})\b)?"
    # Solo espacios de la misma línea: tras un punto o un salto empieza otra frase, y su
    # mayúscula no es un nombre ("Acude con su madre. Paracetamol 1 g").
    rf"(?:[ \t]*[,:][ \t]*|[ \t]+)(?:(?i:llamad[oa]|de[ \t]+nombre)[ \t]+)?\(?)"
    rf"(?P<names>{_NAME_WORD}(?:{_NAME_JOIN}{_NAME_TOKEN})"
    # Lo que acaba en dos puntos es la etiqueta del campo siguiente, no un apellido ("Sexo:
    # Mujer   Grupo Sanguineo: A+", "su madre Carmen Telefono: …").
    r"{0,7})(?!\w)(?![ \t]*:)"
)
_NAME_TOKEN_RE = re.compile(_NAME_TOKEN)
# "Hospital Madre Teresa", "Residencia de las Hermanas Hospitalarias", "Calle Padre Damián": el
# parentesco con mayúscula tras el nombre de un centro o de una vía es parte de ese nombre.
_PLACE_BEFORE = re.compile(
    r"(?i:\b(?:hospital|cl[ií]nica|centro|residencia|fundaci[oó]n|instituto|colegio|sanatorio"
    r"|parroquia|asilo|calle|avenida|avda\.?|plaza|paseo)\b|\bc/)"
    r"(?:[ \t]+(?:de|del|la|las|los|el|[A-ZÁÉÍÓÚÑ][\wáéíóúüñ]*))*[ \t]*$"
)


def _words(*lines: str) -> frozenset[str]:
    return frozenset(" ".join(lines).split())


# Lo que va con mayúscula detrás de un parentesco y NO es un nombre. Es una lista, y por tanto
# incompleta: una palabra clínica que falte aquí, escrita con mayúscula justo detrás de "su
# madre", se taparía. Por eso además se piden indicios (ver `_relative_name`).
_CLINICAL = _words(
    # Enfermedades y hallazgos frecuentes en antecedentes familiares.
    "diabetes mellitus hipertension infarto ictus cancer tumor neoplasia asma epilepsia demencia",
    "depresion ansiedad gota lupus psoriasis celiaquia cataratas migrana obesidad dislipemia",
    "colesterol embolia aneurisma angina arritmia fibrilacion insuficiencia neumonia covid",
    "alergia enfermedad sindrome trastorno tiroides bocio fractura ulcera calculos sordera",
    "ceguera miopia muerte accidente cardiopata esquizofrenia tuberculosis hematuria",
    # Epónimos (se dejan fuera los que también son nombre de pila: Gilbert, Wilson, Bell).
    "parkinson alzheimer crohn hodgkin cushing addison graves basedow raynaud sjogren behcet",
    "marfan huntington paget meniere guillain kawasaki hashimoto duchenne klinefelter tourette",
    "asperger brugada chagas lyme ehlers kaposi burkitt ewing wilms charcot dupuytren barrett",
    "whipple takayasu wegener horton down",
    # Fármacos.
    "paracetamol ibuprofeno aspirina metformina insulina heparina warfarina sintrom",
    "acenocumarol levotiroxina salbutamol prednisona morfina tramadol nolotil adiro digoxina",
    "furosemida amlodipino clopidogrel dexametasona ventolin",
)
# Sufijos de término médico o de fármaco. `-uria` y `-ina` no están: Nuria, Cristina. Como los
# estados, solo se miran en la primera palabra: hay apellidos que acaban así (Coloma, Poma).
_CLINICAL_SUFFIXES = (
    "itis", "osis", "iasis", "emia", "patia", "algia", "tomia", "plastia", "scopia", "grafia",
    "ismo", "penia", "rragia", "plejia", "trofia", "megalia", "plasia", "oma", "pril", "sartan",
    "statina", "azol", "cilina", "micina", "zepam", "olol", "mab",
)
_NAMES_WITH_A_CLINICAL_SUFFIX = frozenset({"paloma", "eufemia"})
# Solo para la PRIMERA palabra: estados y verbos que siguen al parentesco ("Padre Fallecido").
# Detrás de un nombre de pila no se miran, porque varios son apellidos (Mayor, Sano, Vivo).
_NOT_A_FIRST_NAME = _words(
    "fallecido fallecida vivo viva sano sana sin con no si niega refiere presenta padece tiene",
    "tuvo murio fallecio vive antecedentes diagnosticado diagnosticada operado operada",
    "intervenido intervenida ingresado ingresada tratado tratada fumador fumadora hipertenso",
    "hipertensa diabetico diabetica asmatico asmatica epileptico epileptica alergico alergica",
    "obeso obesa desconocido desconocida portador portadora afecto afecta mayor menor materno",
    "materna paterno paterna tambien igual edad anos unico unica derecho derecha izquierdo",
    "izquierda bilateral uno dos tres cuatro varios varias ninguno ninguna ambos ambas",
)
_FOLD = str.maketrans("áéíóúüñ", "aeiouun")


def _not_a_first_name(folded: str) -> bool:
    """Estado (también en plural: "sus padres Fallecidos") o palabra con sufijo médico."""
    if folded in _NAMES_WITH_A_CLINICAL_SUFFIX:
        return False
    return (
        folded in _NOT_A_FIRST_NAME
        or folded.removesuffix("s") in _NOT_A_FIRST_NAME
        or folded.endswith(_CLINICAL_SUFFIXES)
    )


def _relative_name(match: re.Match[str], line_before: str) -> int:
    """Cuántos caracteres de `names` son el nombre del familiar; 0 si no hay indicios de nombre.

    Indicios: con determinante delante ("su hermana Lucía", "la tía Carmen") basta un nombre de
    pila; sin él ("Madre: …", "Hermano …") hacen falta nombre y apellido, porque así es como se
    escriben los antecedentes ("Madre: Asma. Padre: Gota") y una lista de enfermedades nunca
    está completa. El nombre se corta en la primera palabra de la lista clínica.
    """
    if match.group("kin")[0].isupper() and _PLACE_BEFORE.search(line_before):
        return 0
    # "Mujer" es antes el sexo de la paciente que un parentesco, y "mama" (ya sin tilde) y
    # "papa", antes otra cosa ("ecografía de la Mama Derecha"): solo cuentan con posesivo.
    kin = match.group("kin").lower().translate(_FOLD)
    possessive = (match.group("det") or "").lower().startswith(("su", "mi", "tu", "nuestr"))
    if any(word in kin for word in ("mujer", "mama", "papa")) and not possessive:
        return 0
    words = evidence = end = 0
    for token in _NAME_TOKEN_RE.finditer(match.group("names")):
        value = token.group(0)
        if value != MARK and not value.endswith("."):
            folded = value.lower().translate(_FOLD)
            if folded in _CLINICAL or (not words and _not_a_first_name(folded)):
                break
            words += 1
        # Una marca del original tras el nombre de pila es el apellido que ya tapó él.
        evidence += 1
        end = token.end()
    if not words or (evidence < 2 and not match.group("det")):
        return 0
    return end


# --- Familiar nombrado delante del parentesco: "con Rosa Beltrán, su cuñada" -------------------
#
# Por qué existe (2026-10-20, decimotercera ronda): era el único familiar del corpus que salía
# entero (`informe11`), porque `_KIN_NAME` solo mira detrás del parentesco. Mirar hacia atrás es
# más arriesgado: la mayúscula de antes de la coma es a menudo lo clínico ("Diabetes, su madre
# también") o el principio de la frase ("Además, su madre…"). Por eso la regla exige que el
# parentesco esté anclado a la persona —posesivo ("su cuñada", "mi hermano") o "del paciente"
# detrás ("cuñada del paciente")— y, para el nombre, los mismos indicios que la otra regla más
# los propios de esta posición: ver `_name_before_kin`.
_POSSESSIVE = r"(?:sus?|mis?|tus?|nuestr[oa]s?)"
_OF_THE_PATIENT = (
    r"(?:de[ \t]+la|del)[ \t]+(?:paciente|enferm[oa]|usuari[oa]|tripulante|astronauta)"
)
_NAME_KIN = re.compile(
    # Puede empezar por la marca de lo que ya tapó Polaris: "con [REDACTADO]-Gomez, su madre".
    rf"(?<![\w-])(?P<names>(?:{re.escape(MARK)}{_NAME_JOIN})?{_NAME_WORD}"
    rf"(?:{_NAME_JOIN}{_NAME_TOKEN}){{0,7}})"
    # Aposición con coma ("Rosa Beltrán, su cuñada") o entre paréntesis ("Rosa (su madre)").
    rf"(?P<sep>[ \t]*[,(][ \t]*)"
    rf"(?:(?P<poss>(?i:{_POSSESSIVE}))[ \t]+|(?i:el|la|los|las)[ \t]+)?"
    rf"(?P<kin>(?i:{_KIN}))\b(?:[ \t]+(?i:{_KIN_QUALIFIER})\b)?"
    rf"(?P<patient>[ \t]+(?i:{_OF_THE_PATIENT})\b)?"
)
# Primeras palabras con mayúscula que abren la frase y no son un nombre ("Hoy Rosa Beltrán, su
# cuñada…", "Además Rosa, su cuñada"): se quitan por la izquierda antes de contar el nombre. Sin
# los meses y días que también son nombres de pila (Abril, Julio, Domingo): quitarlos dejaría el
# nombre a la vista ("Julio Pérez, su padre"). Una palabra que abra la frase y no esté aquí se
# tapa con el nombre ("Revisado Rosa Beltrán, su cuñada" → "[REDACTADO], su cuñada").
_SENTENCE_OPENERS = _words(
    "hoy ayer manana actualmente posteriormente previamente finalmente ademas asimismo tambien",
    "entonces luego despues antes durante segun aunque pero como cuando donde mientras tras",
    "desde hasta hacia sobre ante bajo para por con sin en de a y e o",
    "el la los las lo un una unos unas su sus mi mis tu tus este esta ese esa aquel aquella",
    "lunes martes miercoles jueves viernes sabado enero febrero marzo mayo junio agosto",
    "septiembre setiembre octubre noviembre diciembre",
    "paciente acude acuden acompanado acompanada acompanados acompanadas viene vienen llama",
    "llamada visita revision consulta control seguimiento ingreso alta cita motivo plan juicio",
    "evolucion exploracion tratamiento diagnostico observaciones informe historia nota",
)
# Primera palabra que nombra un centro, un servicio o una vía: "Hospital Clínico, su centro…",
# "Centro de Salud Las Rozas, su madre…". Con ella no hay nombre de persona.
_PLACE_WORDS = _words(
    "hospital clinica centro residencia fundacion instituto colegio sanatorio parroquia asilo",
    "calle avenida avda plaza paseo ambulatorio consultorio servicio unidad planta urgencias uci",
    "area hogar universidad ayuntamiento",
)
# Lo que puede ir justo delante de un nombre de pila suelto: "con Rosa", "a Rosa", "por Rosa",
# "acompañado de Rosa… y de Tomás". No "en" ni "desde" (lugares) ni "de" a secas (epónimos:
# "fractura de Colles, su madre…").
_PERSON_LEAD = re.compile(
    r"(?i:(?<!\w)(?:con|a|por|(?:y|e)(?:[ \t]+de)?|seg[uú]n|entre"
    r"|acompa[ñn]ad[oa]s?[ \t]+(?:de|por))[ \t]+$)"
)


def _name_before_kin(match: re.Match[str], line_before: str) -> int:
    """Desde qué carácter de `names` empieza el nombre del familiar; -1 si no hay indicios.

    Indicios: el parentesco con posesivo ("su cuñada") o con "del paciente" detrás. Ninguna
    palabra del nombre en la lista clínica, y la primera, ni estado ni sufijo médico ni un centro
    o una vía. Nombre y apellido (o nombre y la marca de un apellido que ya tapó Polaris) bastan;
    un nombre de pila suelto, solo en mitad de la frase y tras "con", "a", "por"… ("acude con Rosa,
    su cuñada"): al principio de la frase o tras dos puntos, una mayúscula sola no es indicio.

    Lo que decide son listas finitas (`_CLINICAL`, `_NOT_A_FIRST_NAME`, `_SENTENCE_OPENERS`,
    `_PLACE_WORDS`): dos palabras con mayúscula que no estén en ninguna pasan por un nombre, y un
    nombre junto a una palabra de la lista clínica no se tapa entero ("Ana Graves, su madre", o
    "Parkinson y Rosa Beltrán, su cuñada": una palabra clínica descarta todo el tramo, porque las
    enfermedades se escriben con varias palabras y cortar ahí taparía "Arterial Severa").
    """
    if not (match.group("poss") or match.group("patient")):
        return -1
    if _PLACE_BEFORE.search(line_before):
        return -1
    names = match.group("names")
    tokens = list(_NAME_TOKEN_RE.finditer(names))
    while tokens and tokens[0].group(0).lower().translate(_FOLD) in _SENTENCE_OPENERS:
        tokens.pop(0)
    words = [
        token.group(0).lower().translate(_FOLD)
        for token in tokens
        if token.group(0) != MARK and not token.group(0).endswith(".")
    ]
    if not words:
        return -1
    if words[0] in _PLACE_WORDS or _not_a_first_name(words[0]):
        return -1
    if any(word in _CLINICAL for word in words):
        return -1
    # Lo que va delante del nombre incluye las palabras quitadas: "Acompañada de Lucía".
    if len(tokens) < 2 and not _PERSON_LEAD.search(line_before + names[: tokens[0].start()]):
        return -1
    return tokens[0].start()


def _mask_relatives(text: str) -> tuple[str, int]:
    """Tapa el nombre de un familiar y deja el parentesco: "su hermana [REDACTADO]".

    Dos pasadas: el nombre detrás del parentesco (`_KIN_NAME`) y delante, en aposición
    (`_NAME_KIN`: "con [REDACTADO], su cuñada").

    Qué NO ve, para no leerla de más: un nombre de pila suelto delante del parentesco al principio
    de la frase ("Lucía, su hermana, acude": la mayúscula puede ser "Además, su madre…"), un
    parentesco en aposición sin posesivo ni "del paciente" ("Rosa Beltrán, cuñada"), un nombre de
    pila suelto sin determinante detrás ("Hermano Juan operado"), nombres en mayúsculas sostenidas
    ("MADRE: CARMEN RUIZ": ahí van también HTA, IAM, EPOC), "mujer", "mamá" y "papá" sin
    posesivo, parentescos que no están en `_KIN`, profesiones ("Ana López, su médica": el
    personal sanitario solo se tapa con su tratamiento, "Dra. Ana López") y un nombre junto a una
    palabra de la lista clínica delante del parentesco ("Ana Graves, su madre").
    La revalidación que retiene el texto usa esta misma función: caza restos, no lo que la regla
    no ve.
    De más: un lugar tras "a" ("trasladado a Bilbao, su hermano…") o dos palabras con mayúscula que
    no estén en las listas ("Plan Terapéutico, su madre…") se taparían.
    """
    count = 0

    def after(match: re.Match[str]) -> str:
        nonlocal count
        line_start = text.rfind("\n", 0, match.start()) + 1
        length = _relative_name(match, text[line_start : match.start("kin")])
        if not length:
            return match.group(0)
        count += 1
        return match.group("lead") + MARK + match.group("names")[length:]

    text = _KIN_NAME.sub(after, text)

    def before(match: re.Match[str]) -> str:
        nonlocal count
        line_start = text.rfind("\n", 0, match.start()) + 1
        start = _name_before_kin(match, text[line_start : match.start()])
        if start < 0:
            return match.group(0)
        count += 1
        tail = match.group(0)[match.end("names") - match.start() :]
        return match.group("names")[:start] + MARK + tail

    return _NAME_KIN.sub(before, text), count


def _iban_ok(candidate: str) -> bool:
    """Dígito de control ISO 13616 (mod-97 == 1): no se tapa cualquier ristra de letras y cifras."""
    compact = candidate.replace(" ", "").upper()
    if not 15 <= len(compact) <= 34:
        return False
    moved = compact[4:] + compact[:4]
    digits = "".join(str(int(char, 36)) for char in moved)
    return int(digits) % 97 == 1


def _luhn_ok(candidate: str) -> bool:
    """Algoritmo de Luhn: un número de tarjeta, no una cifra clínica larga cualquiera."""
    digits = [int(char) for char in candidate if char.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for position, digit in enumerate(reversed(digits)):
        if position % 2 == 1:
            digit = digit * 2 - 9 if digit > 4 else digit * 2
        total += digit
    return total % 10 == 0


def _emma_identifiers(text: str) -> tuple[str, int]:
    """IBAN, tarjeta, pasaporte, fecha ISO con hora y titular o tarjeta sanitaria con etiqueta."""
    count = 0

    def checked(valid: Callable[[str], bool]) -> Callable[[re.Match[str]], str]:
        def replace(match: re.Match[str]) -> str:
            nonlocal count
            if not valid(match.group(0)):
                return match.group(0)
            count += 1
            return MARK
        return replace

    text = _IBAN.sub(checked(_iban_ok), text)
    text = _CARD.sub(checked(_luhn_ok), text)
    text, passports = _PASSPORT.subn(lambda match: match.group(1) + MARK, text)
    text, dates = _ISO_DATETIME.subn(MARK, text)
    text, labelled = _LABELLED.subn(lambda match: match.group(1) + MARK, text)
    return text, count + passports + dates + labelled


@cache
def _original() -> Any:
    return polaris.load("deid")


def _ner_venv() -> Path:
    configured = os.environ.get("BTP_VENV_DEID")
    return Path(configured) if configured else Path(__file__).resolve().parents[2] / ".venv-deid"


def ner_ready() -> bool:
    """¿Está instalada la capa NER con sus pesos comprobados? (`scripts/install_deid_ner.py`)."""
    venv = _ner_venv()
    if not (venv / "ner-ok.json").is_file():
        return False
    # Lo que leen `deid._python_ner()` (el entorno) y `deid_ner.py` (la caché del modelo).
    os.environ["BTP_VENV_DEID"] = str(venv)
    os.environ.setdefault("HF_HOME", str(venv / "hf"))
    return True


@dataclass(frozen=True)
class Deidentified:
    text: str
    redactions: int
    # False: tras enmascarar, el detector aún veía algo; el texto se retiene.
    verified: bool
    remaining: tuple[str, ...]


def _pipeline(text: str) -> tuple[Deidentified, tuple[str, ...]]:
    """El resultado y el texto tras cada capa (EMMA antes, Polaris, tratamiento, parentesco).

    Las capas intermedias solo sirven para medir qué tapa cada una (`masked_spans`); de un texto
    retenido solo hay la primera.
    """
    emma_masked, emma_count = _emma_identifiers(text)
    masked, count, verified, reason = _original().de_identificar_verificado(
        emma_masked, ner=ner_ready()
    )
    if not verified or masked is None:
        withheld = Deidentified("", int(count) + emma_count, False, (str(reason),))
        return withheld, (emma_masked,)
    named, extra = _HONORIFIC_NAME.subn(MARK, str(masked))
    related, relatives = _mask_relatives(named)
    total = int(count) + emma_count + extra + relatives
    # Falla cerrado, como el original: si tras tapar la regla aún ve un familiar nombrado, el
    # texto no sale. Con el mismo detector que tapa, caza restos; no demuestra anonimato.
    if _mask_relatives(related)[1]:
        withheld = Deidentified("", total, False, ("queda un familiar nombrado",))
        return withheld, (emma_masked,)
    result = Deidentified(related, total, True, ())
    return result, (emma_masked, str(masked), named, related)


def deidentify(text: str) -> Deidentified:
    """Texto sin los identificadores que se reconocen, o retenido si no se verifica."""
    return _pipeline(text)[0]


# --- Tramos tapados, para medir el recall por tipo de entidad --------------------------------
#
# Por qué existe: `deid_eval.puntuar` de Polaris puntúa por entidad a partir de tramos
# (inicio, fin, capa) sobre el texto original, y la des-identificación de EMMA solo devuelve el
# texto ya tapado. `deid.detectar` de Polaris da tramos, pero de otra cosa: la unión de lo que
# cada patrón ve en el texto sin tapar, sin las reglas de EMMA y sin el efecto de tapar en cadena.
#
# Aquí los tramos se DERIVAN comparando el texto antes y después de cada capa, que es lo que de
# verdad sale. Precisión de esa derivación, para no leerla de más:
#   * Cada capa solo cambia trozos por `MARK` (y Polaris, antes, quita tildes y caracteres
#     invisibles: se deshace con su `_mapa_normalizado`). Lo que queda entre dos marcas es texto
#     literal del original; se busca en orden, lo más a la izquierda posible, y lo que queda entre
#     medias es el tramo tapado. Si no encaja entero se lanza `SpanAlignmentError`: no se
#     inventan tramos.
#   * Con una sola marca el tramo es exacto. Con varias, un literal corto que se repite (un salto
#     de línea, dos puntos) puede casar antes de su sitio, y la frontera entre dos tramos vecinos
#     se corre: uno sale corto y el siguiente largo. Lo tapado en total sigue cuadrando con la
#     salida.
#   * Polaris funde marcas seguidas en una; el tramo fundido incluye el espacio de en medio.
#     `puntuar` no cuenta los espacios, ni en la cobertura ni en la precisión.
#   * La capa de cada tramo es la etapa que lo tapó, no el patrón concreto.
#   * `deid_eval.offsets_cuadran` NO comprueba estos tramos: solo que las anotaciones del corpus
#     coinciden con su texto. Estos los comprueba `tests/test_deid_corpus.py`, que rehace la
#     salida a partir de ellos y la compara con la real.

LAYER_EMMA_BEFORE = "emma:identificadores"  # IBAN, tarjeta, pasaporte, fecha ISO, etiquetas
LAYER_POLARIS = "polaris:patrones"
LAYER_EMMA_TITLE = "emma:tratamiento"
LAYER_EMMA_KIN = "emma:parentesco"
LAYER_WITHHELD = "retenido"  # el texto no verificó: no sale nada de él
_LAYERS = (LAYER_EMMA_BEFORE, LAYER_POLARIS, LAYER_EMMA_TITLE, LAYER_EMMA_KIN)


class Span(NamedTuple):
    """Tramo [start, end) del texto ORIGINAL que no sale, y la capa que lo tapó."""

    start: int
    end: int
    layer: str


class SpanAlignmentError(RuntimeError):
    """El texto tapado no se explica como el de entrada con trozos cambiados por la marca."""


def _gaps(source: str, target: str) -> list[tuple[int, int]]:
    """Trozos de `source` que en `target` son una marca, en orden (uno por marca de `target`)."""
    literals = target.split(MARK)
    if not source.startswith(literals[0]):
        raise SpanAlignmentError("el principio del texto tapado no es el del original")
    if len(literals) == 1:
        if source != target:
            raise SpanAlignmentError("el texto cambió sin que haya ninguna marca")
        return []
    gaps = []
    cursor = len(literals[0])
    for literal in literals[1:-1]:
        # Un tramo tapado nunca está vacío: el literal siguiente empieza al menos un carácter
        # después.
        found = source.find(literal, cursor + 1)
        if found < 0:
            raise SpanAlignmentError("un trozo sin tapar no aparece en el original")
        gaps.append((cursor, found))
        cursor = found + len(literal)
    last = len(source) - len(literals[-1])
    if last <= cursor or not source.endswith(literals[-1]):
        raise SpanAlignmentError("el final del texto tapado no es el del original")
    gaps.append((cursor, last))
    return gaps


def masked_spans(text: str, *, emma_rules: bool = True) -> tuple[Span, ...]:
    """Qué tramos del texto original tapa la des-identificación, para `deid_eval.puntuar`.

    Solo para medir: `deidentify` no la usa. `emma_rules=False` mide los patrones de Polaris sin
    las reglas de EMMA, para comparar. Un texto retenido es un único tramo `LAYER_WITHHELD` que lo
    cubre entero: quien mide tiene que contarlo aparte, porque daría un recall perfecto.
    """
    stages: tuple[str, ...]
    layers: tuple[str, ...]
    if emma_rules:
        result, stages = _pipeline(text)
        layers = _LAYERS
    else:
        masked, _count, verified, _reason = _original().de_identificar_verificado(text, ner=False)
        result = Deidentified("", 0, bool(verified) and masked is not None, ())
        stages, layers = (str(masked),), (LAYER_POLARIS,)
    if not result.verified:
        return (Span(0, len(text), LAYER_WITHHELD),)

    spans: list[Span] = []
    current = text
    # Para cada carácter del texto de la etapa, de qué tramo [inicio, fin) del original sale.
    origin = [(index, index + 1) for index in range(len(text))]
    for layer, after in zip(layers, stages, strict=True):
        if layer == LAYER_POLARIS and current.strip():
            # Polaris tapa sobre el texto normalizado; su mapa dice de qué carácter sale cada uno.
            # (Un texto en blanco lo devuelve tal cual, sin normalizar.)
            source, back = _original()._mapa_normalizado(current)
            origin = [origin[index] for index in back]
        else:
            source = current
        next_origin: list[tuple[int, int]] = []
        cursor = 0
        for start, end in _gaps(source, after):
            next_origin.extend(origin[cursor:start])
            covered = (origin[start][0], origin[end - 1][1])
            # Una marca que ya puso una capa anterior no es un tramo nuevo de esta.
            if source[start:end] != MARK:
                spans.append(Span(covered[0], covered[1], layer))
            next_origin.extend([covered] * len(MARK))
            cursor = end
        next_origin.extend(origin[cursor:])
        current, origin = after, next_origin
    return tuple(spans)
