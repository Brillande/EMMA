"""El alimento de una valoración de la comida: qué se escribe, con qué regla y por qué así.

POR QUÉ EXISTE
--------------
La conversación de ideación del equipo pide guardar qué se elige y qué se rechaza, la repetición
del menú y los cambios de preferencia (`docs/contexto/conversacion-ideacion-v1.md`: «Food
selected / Food rejected / … Menu fatigue», y que un déficit puede venir de «un patrón
longitudinal de selección»). EMMA tenía la ingesta, el apetito, la fracción rechazada y la
aceptabilidad, pero ninguna lectura decía DE QUÉ alimento era: una valoración de 4 no se podía
poner al lado de la anterior del mismo plato, y sin eso no hay repetición que contar.

Decisión del usuario (2026-10-26): la valoración de aceptabilidad lleva el alimento. Lo leído
dice que la valoración es de un alimento, no de la comida en general: los astronautas «rated each
food or beverage» (`instruments_read.json`, `hedonic-anchors-crew`), y la norma habla de «A NASA
food item» (`v2-7002-acceptable-6`).

POR QUÉ TEXTO LIBRE
-------------------
Se buscó un vocabulario cerrado en una fuente ya leída y no lo hay: `instruments_read.json` no
nombra ningún alimento, categoría ni menú, y de lo registrado como leído del informe de evidencia
del HRP sobre el sistema de alimentos (ficha `hrp-food-system-evidence-report`: portada, resumen,
huecos y las páginas sobre radiación) tampoco consta una lista. Inventar categorías sería
atribuirles una fuente. Por eso es TEXTO LIBRE, con una regla que es una decisión de diseño de
EMMA, sin validar, y se dice así en cada respuesta que la lleva (`describe`).

LA REGLA (decisión de diseño de EMMA)
-------------------------------------
- Se normaliza antes de firmar: forma Unicode NFC, sin espacios al principio ni al final y con
  los de dentro reducidos a uno. Lo firmado es ya la forma normalizada.
- De 1 a `MAX_LENGTH` caracteres, con al menos una letra (un número solo no nombra un plato).
- Solo letras (de cualquier alfabeto), cifras, espacios y `ALLOWED_PUNCTUATION`: nada de
  caracteres de control, comillas, `<`, `>`, `:` ni emojis. Es el nombre de un plato, no una nota.
- Pasa el filtro de lenguaje de EMMA (`text_guard.check`): un nombre que escriba una dosis, un
  fármaco o una orden no se firma. Tiene un coste declarado: «arroz 100 g» se rechaza (el filtro
  ve una cantidad con unidad), y el nombre va sin la ración.
- Dos lecturas son del MISMO plato si su nombre coincide sin distinguir mayúsculas
  (`group_key`). EMMA no reconoce sinónimos ni erratas: «arroz con pollo» y «arroz pollo» son dos.

La regla se aplica en las rutas que firman (`accept`: el registro diario, la ingesta genérica y
la enmienda); el modelo (`VitalObservation`) solo exige lo estructural, para que un cambio futuro
de la regla no deje sin leer lo ya firmado.

DESDE LA DECIMONOVENA RONDA (2026-10-31): EL PLATO TAMBIÉN EN LA FRACCIÓN RECHAZADA Y EN LA INGESTA
GENÉRICA
-------------------------------------------------------------------------------------------------
La fracción de la ración que se deja sin comer («Food rejected» en la conversación de ideación)
puede ser de la comida en general o de un plato: lleva el alimento como OPCIONAL (`KEYS` menos
`REQUIRED`), y con él la ruta de nutrición la enseña junto a las valoraciones de ese plato. Y la
ingesta genérica (`POST /api/observations`) y la enmienda admiten `food_item`: hasta entonces lo
que entraba por ahí se contaba «sin alimento declarado» sin remedio. La regla es la misma en las
tres rutas y vive aquí (`accept`), para que no haya dos.
"""

from __future__ import annotations

import unicodedata
from typing import Any

# Los indicadores que pueden llevar alimento: la valoración (de un alimento) y la fracción que se
# deja sin comer (de la comida en general o de un plato).
KEYS = frozenset({"food-acceptability", "food-rejected-fraction"})
# Donde es obligatorio: solo la valoración, que es siempre de un alimento. La fracción rechazada
# puede ser de la comida entera, y sin plato se firma igual.
REQUIRED = frozenset({"food-acceptability"})

MAX_LENGTH = 64
# El tope del campo en los esquemas de entrada (`DiaryEntryIn.food`, `ObservationIn.food_item`):
# solo evita leer un texto enorme antes de aplicar la regla, que es la que rechaza con su motivo.
FIELD_MAX_LENGTH = 1024
# Signos de puntuación que puede llevar el nombre de un plato («crema de cacahuete, 2.º», «té
# verde/menta», «pan d’Avila»). Lo demás no.
ALLOWED_PUNCTUATION = frozenset("-'’,.()/&+º")

DECIDED_ON = "2026-10-26"
STATUS = "design"
STATUS_DISPLAY = "decisión de diseño de EMMA, sin validar"
LABEL = "Alimento valorado"
# En la fracción rechazada el alimento no se valora: es el plato del que se deja la fracción
# (decimonovena ronda, 2026-10-31). Un rótulo por indicador que lo lleva.
REJECTED_LABEL = "Alimento del que se deja la fracción"
LABELS = {"food-acceptability": LABEL, "food-rejected-fraction": REJECTED_LABEL}
RULE = (
    f"Texto libre, de 1 a {MAX_LENGTH} caracteres, con al menos una letra: letras, cifras, "
    "espacios y los signos - ' ’ , . ( ) / & + º. Los espacios de más se quitan. Pasa el filtro "
    "de lenguaje de EMMA, el mismo que revisa los borradores: lo que el filtro rechace no se "
    "firma, también una ración escrita con su cantidad y su unidad. Se escribe solo el nombre "
    "del plato."
)
WHY_FREE_TEXT = (
    "Ninguna fuente leída da un vocabulario cerrado de alimentos, categorías o menú: ni lo leído "
    "de los instrumentos ni lo registrado como leído del informe de evidencia del HRP sobre el "
    "sistema de alimentos. Por eso es texto libre, y la regla es de EMMA."
)
GROUPING = (
    "Dos lecturas son del mismo plato si su nombre coincide sin distinguir mayúsculas. EMMA "
    "no reconoce sinónimos ni erratas: dos nombres distintos son dos platos."
)
# Las frases leídas que dicen que la valoración es de un alimento: el porqué del campo, no de
# la regla (la regla no tiene fuente).
BASIS = ("hedonic-anchors-crew", "v2-7002-acceptable-6")
# Solo la valoración: esas frases no dicen nada de la fracción que se deja sin comer, y citarlas
# ahí sería un respaldo que no respalda. En la fracción, el plato no tiene fuente leída.
BASIS_BY_KEY: dict[str, tuple[str, ...]] = {"food-acceptability": BASIS}

MISSING = "Falta el alimento valorado: la valoración es de un alimento."
NOT_ALLOWED_HERE = "Solo la aceptabilidad de la comida y la fracción rechazada llevan alimento."
# Qué exige cada indicador que lo lleva, con palabras de pantalla (la consola no las redacta).
REQUIRED_NOTE = "Obligatorio: la valoración es de un alimento."
OPTIONAL_NOTE = (
    "Opcional: la fracción que se deja puede ser de la comida en general o de un plato; con el "
    "plato, se enseña junto a sus valoraciones."
)


def normalize(text: str) -> str:
    """NFC, sin espacios en los bordes y con los de dentro reducidos a uno."""
    return " ".join(unicodedata.normalize("NFC", text).split())


def _allowed(char: str) -> bool:
    category = unicodedata.category(char)
    return (
        category[0] in {"L", "M"} or category == "Nd" or char == " "
        or char in ALLOWED_PUNCTUATION
    )


def problem(text: str) -> str | None:
    """Por qué este nombre no se puede firmar, o `None` si cumple la regla.

    Se mira el texto YA normalizado: es el que se firmaría.
    """
    from app.text_guard import check  # el filtro carga las listas de Polaris al importarse

    name = normalize(text)
    if not name:
        return "El alimento valorado está vacío."
    if len(name) > MAX_LENGTH:
        return f"El alimento valorado pasa de {MAX_LENGTH} caracteres."
    # «º» es una letra para Unicode (categoría Lo) y está entre los signos admitidos: «º.» no
    # nombra un plato. La letra que cuenta es una que no sea de esos signos.
    if not any(char.isalpha() and char not in ALLOWED_PUNCTUATION for char in name):
        return "El alimento valorado tiene que llevar al menos una letra."
    refused = sorted({char for char in name if not _allowed(char)})
    if refused:
        shown = " ".join(f"U+{ord(char):04X}" for char in refused[:5])
        return f"El alimento valorado lleva caracteres que la regla no admite ({shown})."
    found = check(name)
    if found:
        words = ", ".join(f"«{item.match}»" for item in found[:3])
        return (
            f"El alimento valorado escribe {words}, que el filtro de lenguaje de EMMA no deja "
            "firmar. Se escribe el nombre del plato, sin cantidades ni unidades."
        )
    return None


def accept(key: str, food: str | None, *, require: bool) -> str | None:
    """El alimento normalizado que se firmará con una lectura de `key`, o `ValueError` y por qué.

    La regla entera, en un solo sitio para las tres rutas que firman. En un indicador que no lo
    admite, un alimento es un error (si no, una anotación de ánimo podría llevar un plato que nadie
    leería). `require` es si la ruta exige el alimento donde es obligatorio (el registro diario lo
    exige en la valoración; la ingesta genérica no, porque por ella entra también lo que no lo
    conoce). En la fracción rechazada nunca es obligatorio.
    """
    if key not in KEYS:
        if food is not None:
            raise ValueError(NOT_ALLOWED_HERE)
        return None
    if food is None:
        if require and key in REQUIRED:
            raise ValueError(MISSING)
        return None
    refused = problem(food)
    if refused is not None:
        raise ValueError(refused)
    return normalize(food)


def group_key(food: str) -> str:
    """La clave con que se agrupan las valoraciones de un mismo plato."""
    return normalize(food).casefold()


def describe(key: str) -> dict[str, Any]:
    """La regla del campo en el indicador `key`, para que la consola la enseñe tal cual.

    `KeyError` si el indicador no lleva alimento: quien describe pregunta antes (`KEYS`).
    """
    # Aquí y no arriba: `ingest/fhir.py` importa este módulo, y lo leído importa el catálogo.
    from app.evidence import instruments_read

    if key not in KEYS:
        raise KeyError(f"{key!r} no lleva alimento")
    required = key in REQUIRED
    return {
        "label": LABELS[key],
        "required": required,
        "requirement_note": REQUIRED_NOTE if required else OPTIONAL_NOTE,
        "max_length": MAX_LENGTH,
        "status": STATUS,
        "status_display": STATUS_DISPLAY,
        "decided_on": DECIDED_ON,
        "rule": RULE,
        "why_free_text": WHY_FREE_TEXT,
        "grouping": GROUPING,
        "basis": [instruments_read.statement(item) for item in BASIS_BY_KEY.get(key, ())],
    }
