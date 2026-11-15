# Decisión: tres worktrees viejos con cambios sin commit

*Preparado el 2026-11-05. No se ha tocado ninguna de las tres carpetas.* Las tres están en el
commit `3efe771` (2026-10-22, fusión de la decimoquinta ronda), anterior al renombrado
HALO → EMMA. El aislamiento de esta sesión no deja ejecutar `git -C` sobre otro worktree, así que
cada fichero de la carpeta se ha comparado con su blob en `3efe771` (sha1 de git, sin tener en
cuenta los CRLF). El resultado equivale a `git status` y `git diff`.

## `.claude/worktrees/agent-a40a5752d4b93ce54` (D20: derivas del simulador) — **descartar**

**Qué hay:**

- `ingest/simulator.py`: la deriva de FC en reposo pasa de 0,4 a 0 lpm/semana, marcada
  `established`, y la del cortisol salival de 0,0145 a 0, marcada `contested`. Añade el campo
  `refs` a `DriftParameter` (Hughson 2012, Xu 2013, Fraser 2012, Mehta 2017, Vorobiev 1995).
- `test_simulator_evidence.py`: huellas de las series recalculadas.
- `test_evidence_registry.py`: la ficha de Vorobiev 1995.
- `clinical-decision-rationale.md`: un párrafo.
- Dos ficheros nuevos sin seguimiento: `tests/test_simulator_flight_direction.py` y
  `tests/mutants/simulator_flight_direction.json`.

**¿Lo supera main? Sí.** El main actual tiene las dos derivas a 0.0 y marcadas `contested`, con
«decisión del usuario, 2026-10-31» (`simulator.py`, líneas 323 y 447). También tiene ya `refs` en
`DriftParameter` y la prueba `test_flight_direction.py`. La decisión del 31 calificó la FC como
`contested`, no como `established`, que es lo que hace este worktree. Commitearlo reintroduciría
una calificación que el usuario ya corrigió.

## `.claude/worktrees/agent-a5f45df84d8587682` (D22: tiempo de tripulación de Biolab) — **descartar, y anotar la pista**

**Qué hay:** solo pruebas.

- `test_facilities.py`: una prueba nueva. Comprueba que la lección del «crew time» de Biolab se lee
  en dos artículos del ESA Bulletin (`esa-bulletin-90-mfc-programme`, de 1997-05, y
  `esa-bulletin-122-columbus-payloads`, de 2005-05) como afirmación de diseño, sin cifra.
- `test_evidence_registry.py`: añade esas dos fichas a `CUT_REVIEWED`.

**¿Lo supera main? No, pero está incompleto.** Ni ese worktree ni main tienen las fichas en
`evidence_refs.json`, ni las frases en `facilities_read.json`. Main sigue diciendo que la página
de Biolab no menciona el «crew time». Las pruebas fallarían, y la lectura (URL, frases) se perdió:
solo queda su descripción en la prueba. No hay nada que se pueda commitear tal cual.

**Lo que sí vale:** la pista. La frase empieza por «By implementing such a high level of
automation» y está en ESA Bulletin 90 y 122 (`https://www.esa.int/esapub/bulletin/`). Si el
usuario sigue queriendo cerrar ese hueco, conviene una unidad nueva que lea esos dos artículos y
cree las fichas sobre el main actual.

## `.claude/worktrees/agent-ae8b3e64d7e788dc0` (§5.35.21: «lo que ya no es lo revisado» en rojo) — **conservar: rehacerlo sobre main**

**Qué hay:**

- En el backend, `main.py` añade `NOT_AS_REVIEWED`, un único manejador que contesta con un 409
  `{"detail", "integrity_ok": false}`. Lo usa para cuatro casos: la ecografía de ejemplo
  cambiada, el TAC de ejemplo cambiado, el CSV de Inspiration4 cambiado y la calibración firmada
  ilegible (nueva excepción `UnreadableCalibration` en `api/imaging.py`). Las rutas `imaging`,
  `volumes` y `replay` dejan de convertir cada caso por su cuenta.
- En el frontend, `lib/marks.ts` deja de reconocer la calibración por su texto
  (`UNREADABLE_CALIBRATION`) y decide solo por `integrity_ok`. Hay pruebas en `marks.test.ts` y
  `panels.test.ts`.
- Ficheros nuevos sin seguimiento: `tests/test_not_as_reviewed.py` (124 líneas) y
  `tests/mutants/not_as_reviewed.json`.
- Los comentarios citan la decisión del usuario «Sí, también rojo» (2026-10-22).

**¿Lo supera main? No.** Main no tiene `NOT_AS_REVIEWED` ni `UnreadableCalibration`. `marks.ts`
sigue reconociendo la calibración por su texto exacto (líneas 87 y 101). Un fichero del paquete
cambiado sigue saliendo en amarillo, como un rechazo. Tampoco hay §5.35.21 en
`hmi-state-of-the-art.md`: falta la documentación.

**Recomendación:** no lo commitees en su rama tal cual. Está sobre `3efe771`, con «HALO» en los
comentarios, y chocaría con el renombrado y con lo que ha cambiado desde entonces. Es mejor
**rehacerlo sobre main** en una unidad corta, usando ese diff como guía:

1. portar el diff;
2. renombrar HALO → EMMA;
3. escribir §5.35.21;
4. correr `test_not_as_reviewed.py`, la campaña de mutantes y `vitest` de `marks`.

Después se puede descartar la carpeta. Si prefieres no perderlo mientras tanto, la alternativa
segura es un commit WIP en su propia rama `worktree-agent-ae8b3e64d7e788dc0`, hecho por quien
tenga ese worktree.
