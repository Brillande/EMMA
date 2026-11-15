# Decisión D16: línea base de familia

*Preparado el 2026-11-05 para que el usuario decida. No se ha fusionado nada.*

## Qué hay que decidir

Dos ramas guardan la corrección del respaldo de familia de la línea base. Las dos dejan una prueba
`-m external` en rojo **a propósito**: nadie ha tocado los techos ni los suelos. Hay que elegir qué
se fusiona y qué se hace con esa prueba.

## Las ramas

`worktree-agent-a13145213e51ba902` **contiene entera** a `worktree-agent-ae01a12ddd89a0f0e`: la
fusiona en `85a34cf` y le añade dos commits. Basta con decidir sobre la segunda.

| Commit | Rama | Qué cambia, en palabras llanas |
|---|---|---|
| `f5830dd` | las dos | **El error.** Cuando un estado (reposo, trabajo, comida) no tiene lecturas suficientes para su base, `Context.family` dice que se compara «contra el grupo al que pertenece». El código no lo hacía: la familia del reposo eran trabajo y comida, **sin el propio reposo**. Ahora la base de respaldo son las lecturas del estado más las de su familia (`baseline.FAMILY_FALLBACK`). El perfil de línea base nombra solo los estados que aportaron lecturas. |
| `26e5da0` | las dos | **La puerta de cobertura** (lo pidió el usuario tras la primera medición). La familia solo se junta si sus lecturas incluyen al menos 5 (`MIN_SAMPLES/24`) a menos de 30 min de la hora del reloj de la lectura juzgada (`family_covers`). Si no las tiene, se usa el rango poblacional, como antes. |
| `18043d1` | solo a131 | **La literatura.** Nueve fuentes y tres conjuntos de datos de varias semanas, leídos el 2026-10-23, con ficha en `evidence_refs.json`. La hora de la cobertura se lee en UTC (`FAMILY_COVERAGE_CLOCK`). Con marcas en UTC no cambia ninguna cifra. Añade el hallazgo 29 (Wilson, McNemar y variante C). |
| `b4cd0a0` | solo a131 | **Revisión de código y cifras finales.** Una zona horaria se escribe por su desfase. Una marca de tiempo sin zona es un error. La hora de cada lectura se lee una vez. Mutantes `baseline_family` 17/17 y `rules_version` 4/4. Suite: 3793 pasan y 1 falla, ajena al cambio y ya corregida en main. |

La huella cambia en cada paso: `reglas@faf6e60fc2fd3f12` → `52650e59…` → `dfce3ccf…` → `ef06e009be80877f`.

## Evidencia citada

- **El contrato del propio código**: `Context.family` describe la familia, y el código hacía otra
  cosa. No hay fuente que respalde quedarse como está.
- **La comparación a la misma hora y en la misma condición.** La respaldan la norma, las
  recomendaciones de método y dos detectores publicados (Mishra 2020, entre otros). Las fichas
  están en `evidence_refs.json` de la rama y se citan desde `baseline.FAMILY_COVERAGE_SOURCES`.
- **Conjuntos de varias semanas con licencia leída** (para medir la variante C): LifeSnaps y RELAX
  (CC BY 4.0), y PMData en parte. No se ha descargado ninguno.

## Invariante 5: las dos métricas, medidas en MMASH por la rama

| | main (antes) | solo `f5830dd` (variante A) | con cobertura (variante B, la rama a131) |
|---|---|---|---|
| Falsa alarma por lectura | 0,1842 % | 0,2329 % | **0,1625 %** (30 de 18 460) |
| Falsa alarma en reposo | 0,1472 % | 0,2103 % | 0,1472 % |
| Episodios por tripulante-semana | 3,63 | 4,31 | **3,18** |
| Sanos marcados | 1/22 | 1/22 | 1/22 |
| Colapso de HRV detectado | 13,6 % (3/22) | 18,2 % | **9,1 % (2/22)** |
| Taquicardias y episodio agudo | — | iguales | iguales |
| Veredicto (36 casos) | — | idéntico | idéntico |

Con B, `test_sensitivity_does_not_regress` falla: el colapso de HRV da 9,1 % y su suelo es 10 %
(`MIN_SUBJECT_DETECTION["colapso de HRV (-30 ms SDNN)"] = 0.10`). Las pruebas de falsa alarma
pasan. Con A, en cambio, fallan las dos pruebas de falsa alarma.

El análisis de la rama: 2/22 y 3/22 no se distinguen estadísticamente (Wilson y McNemar), y la
detección que se pierde viene de comparar una lectura de primera hora con una base de la otra
mitad del día. Es un cruce de fase, el mismo tipo de comparación que las fuentes desaconsejan.

## Riesgo de fusión contra el main actual

`git merge-tree --write-tree main <rama>` (en seco, sin tocar nada):

- **a131 (completa)**: hay conflictos en 9 ficheros: `analysis/baseline.py`,
  `analysis/baseline_profile.py`, `data/evidence_refs.json`, `validation/mmash.py`,
  `tests/mutants/rules_version.json`, `tests/test_baseline_profile.py`,
  `tests/test_evidence_registry.py`, `compliance/external-validation.md` y
  `compliance/hmi-state-of-the-art.md`.
- **ae01 (solo A+B)**: hay conflictos en 5 ficheros, un subconjunto de los anteriores.

La base común es `a9f4376`. Desde entonces main ha tocado `baseline.py` en «U1: solo lo medido
decide en el motor», en «U11: los cortes del perfil» y en el renombrado HALO → EMMA, entre otros.
**El riesgo es medio-alto.** Los conflictos no son solo de texto: U1 y U11 cambian el motor sobre
el que se midió. Después de resolverlos hay que **volver a medir las dos métricas** sobre main
(`pytest -m external`), porque las cifras de arriba son de la base vieja. También hay que
recalcular la huella `rules_version`.

## Opciones

1. **No adoptar.** El motor sigue contradiciendo su propio contrato.
2. **A con los techos de falsa alarma re-anclados.** Sube la falsa alarma y la rama la descarta.
3. **B (rama a131) con el suelo del colapso de HRV revisado.** Hay dos maneras: re-anclarlo a lo
   medido (2/22, 0,09) con un comentario de por qué, como se hizo en el hallazgo 17, o declararlo
   no validable con MMASH, como la deriva lenta en `MIN_ESCALATION`.
4. **C** (llevar la regla de la misma hora a toda base personal). No se puede evaluar con MMASH;
   hay que medirla antes con LifeSnaps o RELAX.

## Recomendación

**Opción 3: fusionar `worktree-agent-a13145213e51ba902`** (no la ae01, que se queda atrás).
Hay que hacerlo en una unidad dedicada, en este orden:

1. resolver los conflictos contra main;
2. volver a medir con `-m external`;
3. solo si las cifras siguen en la línea de la tabla, re-anclar el suelo del colapso de HRV al
   valor medido, con su justificación en el comentario.

La variante C se deja como trabajo aparte, con LifeSnaps o RELAX.

Lo que decide el usuario es esto: **¿se acepta bajar el suelo del colapso de HRV a cambio de menos
falsas alarmas y de un motor que cumple su contrato?**
