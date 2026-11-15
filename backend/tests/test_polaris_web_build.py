# SPDX-License-Identifier: AGPL-3.0-or-later
"""El visor que EMMA sirve es el de la copia de Polaris que hay en `polaris/`.

Por qué existe: el visor web se compila aparte (`frontend/scripts/build-polaris.mjs`, que corre
con `npm run build`) y su resultado está en git, en `app/data/polaris_web/`. Nada obligaba a
recompilar después de poner la copia al día, ni impedía retocar a mano lo servido: el backend
habría seguido sirviendo el visor de un commit de Polaris mientras `polaris/ADOPTADO.txt`, el
manifiesto y el `NOTICE` declaran otro (auditoría del 2026-10-09).

Qué se comprueba y qué no. Las dos páginas (`index.html`, `render.html`) el guion las copia tal
cual, así que tienen que ser byte a byte las de `polaris/tools/visor3d_web/` **como están en
disco**, es decir, con los cambios decididos de `polaris/CAMBIOS.json` ya aplicados (los colores y
textos de EMMA en `index.html`). Los dos paquetes (`bundle.js`, `render.bundle.js`) **no se
pueden comparar sin compilar** —salen de `main.js` y `render.js` con el `npm ci` y el esbuild de
Polaris, que la suite no tiene ni debe pedir a la red—: de ellos solo se comprueba que existen,
que no están vacíos y que son los que cada página carga. Que un paquete corresponda al `main.js`
de la copia queda **sin comprobar** aquí; se comprueba recompilando.

Licencia y origen (AGPL §5a): este fichero no contiene código de Polaris; compara ficheros de la
copia literal (`polaris/ADOPTADO.txt`) con lo compilado a partir de ella.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.volumes import polaris_web

BACKEND = Path(__file__).resolve().parents[1]
COPY = BACKEND.parent / "polaris" / "tools" / "visor3d_web"
SERVED = BACKEND / "app" / "data" / "polaris_web"

# Cada página y el paquete que carga (lo que `build-polaris.mjs` compila y copia).
PAGES = {"index.html": "bundle.js", "render.html": "render.bundle.js"}


def test_the_served_folder_is_the_one_under_test() -> None:
    assert polaris_web.WEB_DIR == SERVED


@pytest.mark.parametrize("page", sorted(PAGES))
def test_a_served_page_is_byte_for_byte_the_one_in_the_copy(page: str) -> None:
    assert (SERVED / page).read_bytes() == (COPY / page).read_bytes(), (
        f"{page} servido no es el de polaris/: recompila con `npm run build` en frontend/ "
        "(scripts/build-polaris.mjs); lo servido no se edita a mano"
    )


@pytest.mark.parametrize(("page", "bundle"), sorted(PAGES.items()))
def test_each_page_loads_a_compiled_bundle_that_exists(page: str, bundle: str) -> None:
    scripts = re.findall(r'<script[^>]*\bsrc="([^"]+)"', (SERVED / page).read_text("utf-8"))

    assert scripts == [bundle]
    assert (SERVED / bundle).is_file()
    assert (SERVED / bundle).stat().st_size > 0


def test_everything_served_is_there_and_nothing_else() -> None:
    # Lo que el backend sirve de esta carpeta es justo lo que el guion deja en ella.
    expected = {*PAGES, *PAGES.values()}

    assert set(polaris_web.STATIC) == expected
    assert {path.name for path in SERVED.iterdir()} == expected
