# Integridad y trazabilidad de registros de salud

**Estado:** implementado y verificado — `backend/app/core/ledger.py` y `backend/app/core/storage.py`.
Corregido tras seis revisiones adversarias (§7). Las cinco primeras encontraron afirmaciones de
este documento que el código no respaldaba; la sexta, ninguna —sus cinco hallazgos son de la
importación—, que es la primera vez que ocurre.
**Última revisión:** 2026-09-22

Documento de respaldo para la decisión de arquitectura: cómo EMMA garantiza que un registro de
salud no pueda alterarse sin dejar evidencia, en un entorno sin conexión fiable con la Tierra.

---

## 1. De dónde viene el requisito

Se citan a continuación los textos normativos aplicables. **Las citas entre comillas son textuales**;
el resto es paráfrasis marcada como tal.

### 1.1 FDA — 21 CFR Part 11 §11.10, *Controls for closed systems*

Fuente: [21 CFR §11.10 (Cornell LII)](https://www.law.cornell.edu/cfr/text/21/11.10)

> **(a)** "Validation of systems to ensure accuracy, reliability, consistent intended performance,
> and the ability to discern invalid or altered records."

> **(c)** "Protection of records to enable their accurate and ready retrieval throughout the records
> retention period."

> **(e)** "Use of secure, computer-generated, time-stamped audit trails to independently record the
> date and time of operator entries and actions that create, modify, or delete electronic records.
> Record changes shall not obscure previously recorded information. Such audit trail documentation
> shall be retained for a period at least as long as that required for the subject electronic records
> and shall be available for agency review and copying."

El inciso (a) —"*the ability to discern invalid or altered records*"— es literalmente un requisito de
**evidencia de manipulación**, que es lo que aporta una cadena de hashes. El inciso (e) exige que el
audit trail sea *generado por la computadora*, *con marca de tiempo* y que registre **de forma
independiente** las acciones: no vale que el propio registro editable sea su única prueba.

La segunda frase de (e) —*"Record changes shall not obscure previously recorded information"*— la
omitía la versión anterior de este documento, que cortaba la cita justo antes. Es la frase que
**choca con la redacción**: redactar suprime el contenido registrado. Por eso la corrección de un
dato equivocado ya no pasa por ahí: la vía normal es la **enmienda anexada** (§3.7), que deja la
versión anterior registrada y legible. La redacción queda para el dato que nunca debió existir, y
ahí el conflicto persiste y se declara en §3.6.

### 1.2 HIPAA Security Rule — 45 CFR §164.312, *Technical safeguards*

Fuente: [45 CFR §164.312 (eCFR)](https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C/part-164/subpart-C/section-164.312)

> **(b) Audit controls.** "Implement hardware, software, and/or procedural mechanisms that record and
> examine activity in information systems that contain or use electronic protected health information."

> **(c)(1) Integrity.** "Implement policies and procedures to protect electronic protected health
> information from improper alteration or destruction."

> **(c)(2)** "Implement electronic mechanisms to corroborate that electronic protected health
> information has not been altered or destroyed in an unauthorized manner."

**§164.312(c)(2) es la cita central de este diseño**: pide exactamente un mecanismo electrónico que
permita *corroborar* la no-alteración. Una cadena de hashes es la implementación canónica de eso.

La rectificación la regula otra sección, §164.526, *Amendment of protected health information*.
Fuente: [45 CFR §164.526 (Cornell LII)](https://www.law.cornell.edu/cfr/text/45/164.526). Al aceptar
una enmienda, según (c)(1):

> "[The covered entity] must make the appropriate amendment to the protected health information or
> record that is the subject of the request for amendment by, at a minimum, identifying the records
> in the designated record set that are affected by the amendment and appending or otherwise
> providing a link to the location of the amendment."

Se corrige **anexando o enlazando**, no borrando. Es lo que implementa `HashChainLedger.amend()`:
la versión buena se añade como asiento propio, atado por hash a la entrada que corrige, y esa
entrada permanece. Especificación en §3.7. La redacción, que sí borra, sigue existiendo para otra
cosa (§3.6).

### 1.3 ISO 27789:2021 — *Health informatics: Audit trails for electronic health records*

Fuente: [ISO 27789:2021](https://www.iso.org/standard/75313.html) ·
[borrador público en PDF](https://cdn.standards.iteh.ai/samples/75313/5ff648d7c6e047a1bb4c9a119a13345e/ISO-27789-2021.pdf)

*Paráfrasis del alcance publicado por ISO* (la norma completa es de pago): especifica un marco común
de audit trails para historias clínicas electrónicas, aplicable a sistemas que procesan información
personal de salud, creando un registro de auditoría seguro **cada vez que un usuario lee, crea,
actualiza o archiva** dicha información. Cada registro de auditoría identifica como mínimo: el
usuario, el sujeto de atención, la función realizada y la fecha y hora.

Nota de alcance: ISO 27789 cubre acciones sobre la historia clínica, **no** logs de sistema ni de
seguridad general (eso queda para normas de seguridad informática generales).

### 1.4 NASA-STD-3001 — qué aporta, y qué no

Los identificadores ya están verificados. [`nasa-std-3001-traceability.md`](nasa-std-3001-traceability.md)
recoge 15 requisitos del Vol. 1 Rev. C aplicables al software, extraídos el 2026-09-20 del PDF
oficial y de su *Appendix D Requirements Compliance Matrix*. Las citas que siguen salen de ese
documento.

**Ninguno de los 15 impone un mecanismo de integridad.** No hay entre ellos un equivalente a
§11.10(a) o a §164.312(c)(2): nada exige evidencia de manipulación, firma ni auditoría de los
registros. Lo que el estándar aporta aquí es la razón por la que los registros tienen que
conservarse y ser de fiar, no el cómo:

- **[V1 3004] h** — *"Assessing, recording, monitoring, and trending vital signs and additional
  physiological and behavioral health signs."* Registrar y seguir la tendencia: el ledger es la capa
  de registro sobre la que se calcula esa tendencia.
- **[V1 3018]** — *"Crewmembers returning from spaceflight shall be monitored longitudinally for
  health, behavioral health, and well-being parameters in a standardized manner."* Un seguimiento
  longitudinal tras el vuelo necesita registros que sigan siendo comparables y creíbles años
  después: formato estándar (FHIR R4) e integridad verificable.

El mecanismo de integridad se apoya, por tanto, en los textos de §1.1–1.3 (FDA, HIPAA, ISO 27789),
que el proyecto adopta como referencia. En los requisitos revisados de NASA-STD-3001 no aparece de
forma explícita.

**Alcance de esta afirmación.** La extracción buscaba los requisitos aplicables al software de
monitorización, no específicamente requisitos sobre datos médicos o sistemas de información. Que
ninguno de los 15 trate de integridad no demuestra que el estándar no contenga uno en otra sección
u otro volumen. Buscarlo es tarea pendiente.

> Regla del proyecto: no se cita un ID de requisito que no se haya leído en el documento fuente.

### 1.5 Corrección: IEC 62304 **no** es una fuente válida para esto

Una versión anterior de este razonamiento apelaba a "integridad de registros de IEC 62304". **Es
incorrecto.** El *audit trail* que exige IEC 62304 pertenece a la **gestión de configuración y control
de cambios del software** — trazar una modificación del código hasta su origen y sus aprobaciones. Es
un requisito sobre el ciclo de vida del software, no sobre los registros clínicos que el software
produce en operación.

IEC 62304 sigue siendo aplicable al proyecto (ver `software-safety-classification.md`), pero **no
como justificación del ledger**.

---

## 2. Por qué no blockchain

La necesidad es real; el mecanismo de una cadena de bloques distribuida con tokens no lo resuelve
aquí, por tres razones independientes y cada una suficiente:

**1. Colisiona con la privacidad médica.** Los datos de salud de tripulación son información
protegida. Un ledger público los expone de forma permanente, a cualquiera, y su inmutabilidad impide
retirar un dato que nunca debió registrarse —el de un tripulante atribuido a otro—. Corregir sí
cabría en una cadena inmutable, anexando una enmienda, que es lo que prescribe §164.526 (§1.2). La
versión anterior de esta razón atribuía a §164.312(c)(1) una capacidad de suprimir que el texto no
impone.

**2. El consenso distribuido es físicamente inviable en el escenario de diseño.** Todo el sistema
parte de operar con un retardo de ida y vuelta que el spike de Horizons midió en **22,03 minutos para
el 14 de noviembre de 2026** (1,324 UA de distancia Tierra-Marte). Un protocolo de consenso necesita
pares con los que acordar. En tránsito hay una sola nave. No es que el consenso sea lento: no hay
quórum.

**3. "Tokenizar" no aplica a datos de salud.** Un token representa un activo transferible. Una
observación clínica no se transfiere ni se intercambia. El término no añade función.

---

## 3. Diseño adoptado

Tres mecanismos, todos operativos sin red.

### 3.1 Log append-only encadenado por hash

Cada entrada del ledger contiene el hash criptográfico de la entrada anterior. La fórmula exacta:

```
cabecera[n]            = {index, recorded, entry_type, content_hash, prev_hash, signer, signer_public_key}
firma[n]               = Ed25519(JSON canónico de cabecera[n])
entrada[n+1].prev_hash = SHA-256(JSON canónico de cabecera[n] + {signature: firma[n]})
content_hash[n]        = SHA-256(JSON canónico del payload)
                         (el de una lectura lleva una sal aleatoria de 16 bytes; el de una lápida, no)
```

Alterar cualquier entrada pasada invalida todos los hashes posteriores. Esto satisface
§11.10(a) ("discern invalid or altered records") y §164.312(c)(2) ("corroborate that ePHI has not
been altered"), y funciona con cero conectividad.

**La cadena almacena hashes del contenido, no el contenido.** El payload no entra en la cabecera,
solo su `content_hash`. Esto resuelve la tensión entre inmutabilidad y derecho de rectificación: se
puede suprimir el dato clínico y la cadena sigue demostrando que el resto no se tocó (§3.6).

Tres precisiones que la revisión del 2026-09-21 obligó a hacer, porque la versión anterior de esta
sección prometía más de lo que el código hacía:

- **El hash encadenado cubre la firma.** Antes era solo el de la cabecera, así que ni la cadena ni
  la raíz de Merkle comprometían quién firmó. La fórmula que se publicaba aquí —"SHA-256 de la
  entrada serializada"— tampoco era la implementada.
- **JSON canónico estricto.** Se serializaba con `default=str`: `Decimal("1.5")` y `"1.5"`, o un
  `datetime` y su texto, producían el mismo hash. Ahora se rechaza todo lo que no sea JSON puro,
  además de NaN, infinito, claves no textuales y tuplas. Entre procesos Python basta; interoperar
  con otro lenguaje exigiría JCS (RFC 8785).
- **`recorded` lo pone el sistema**, en UTC y nunca hacia atrás. Lo ponía quien llamaba, y §11.10(e)
  exige audit trails *"computer-generated"*. El instante clínico del dato va en el payload.

La revisión del 2026-09-22 añadió tres más (§7.4):

- **Cada payload lleva una sal aleatoria** de 16 bytes que pone el ledger. Sin ella, el
  `content_hash` de una lectura clínica —con pocos valores posibles— se invertía probando
  candidatos, y la lápida de una redacción, que lo repite, permitía recuperar el dato redactado. La
  sal se borra con el contenido.
- **El JSON canónico rechaza además** el anidamiento de más de 32 niveles y el texto que no se puede
  codificar en UTF-8.
- **"Nunca hacia atrás" ya no hereda fechas falsas.** El reloj solo se iguala al asiento anterior si
  este verifica por sí solo. Una fecha 9999-12-31 en un asiento manipulado se heredaba en todas las
  escrituras siguientes, que quedaban firmadas con ella. **Protege en modo aprovisionado** (§3.2).
  En modo aprendido, quien dé de alta una identidad en la base puede añadir un asiento bien firmado
  con fecha futura, que verifica y arrastra el reloj; lo mismo con una clave comprometida. Y un
  reloj del sistema que estuvo adelantado arrastra, por diseño, hasta que el tiempo real lo alcanza.

### 3.2 Firma criptográfica de procedencia, contra un registro de claves

Cada entrada va firmada con Ed25519 por la identidad que la origina (dispositivo wearable,
tripulante, o el propio simulador en modo demo), y la firma se comprueba **contra la clave
registrada para esa identidad**, no contra la que declara la propia entrada.

Esa distinción es el hallazgo más grave de la revisión. `verify()` validaba cada firma con la clave
pública guardada en la entrada: la entrada se certificaba a sí misma. Generar una clave con el mismo
`identity_id`, reescribir la cadena entera y firmarla pasaba la verificación. La prueba que esta
sección citaba como evidencia (`test_signature_rejects_wrong_key`) cambiaba la firma pero conservaba
la clave original, y por eso no lo veía.

Diseño:

- **`KeyRegistry`** guarda la clave de confianza de cada identidad, fuera de las entradas.
  `append()` rechaza firmantes no registrados y `verify()` exige que cada entrada use la registrada.
- **Cada identidad queda fijada a su primera clave.** Registrar el mismo id con otra falla. Eso
  impide suplantar una fuente conocida; dar de alta una fuente nueva no suplanta a nadie.
- **El registro se persiste en su propia tabla, `trusted_keys`**, y nunca se deriva de los asientos:
  si se derivara, reescribir todos los asientos de una fuente reescribiría también su confianza. Se
  guarda en el mismo `commit` que el primer asiento de la identidad.
- **Las lápidas no las firma nadie del registro**, sino una autoridad de redacción aprovisionada
  aparte (§3.6). En la API se llama `emma-audit` y el nombre está reservado: si una fuente de datos
  pudiera llamarse así, fijaría otra clave con ese nombre y bloquearía las redacciones.
- **Los nombres de antes se leen; no se escriben.** Cuando HALO pasó a llamarse EMMA
  (2026-11-02) cambiaron también los identificadores que viajan dentro de lo firmado:
  `halo-audit` → `emma-audit`, `halo-forecast` → `emma-forecast` y `https://halo.mission/...` →
  `https://emma.mission/...` (sistema de códigos y extensiones FHIR). Lo escrito antes lleva el
  nombre viejo dentro del material firmado y no se reescribe. Por eso:
  - la autoridad de redacción reconoce como suyas las lápidas firmadas como `halo-audit` **solo si
    la clave es la suya** (`FORMER_AUTHORITY_IDS`, `RedactionAuthority.former_ids`); una lápida
    nueva se firma siempre como `emma-audit`, y con el nombre viejo no se firma ni una lápida ni
    un dato clínico;
  - al leer un recurso FHIR, `https://halo.mission/codes` se toma por el sistema de hoy
    (`FORMER_CODE_SYSTEMS`) y las extensiones bajo `https://halo.mission/fhir/` por las de hoy; al
    escribirlo, sale siempre con los URI de hoy;
  - `halo-audit` y `halo-forecast` siguen reservados: ninguna fuente puede firmar con ellos;
  - los asientos de `halo-forecast` siguen verificando por su clave en `trusted_keys`, como
    cualquier fuente.

  Lo comprueban `test_former_names.py` y los ledgers grabados antes del cambio
  (`test_contrast_phase.py`, `test_volume_redaction.py`), que no se han regrabado.

**Dos modos, y lo que protege cada uno.** El registro es tan fiable como el sitio de donde sale:

- **Aprendido**, el modo por defecto: cada identidad se fija en su primer uso (*trust on first use*)
  y se guarda en `trusted_keys`, en la misma base que la cadena. Quien pueda escribir en ella, sin
  ninguna clave del sistema, puede borrar la cola desde cualquier asiento y volver a encadenar lo que
  quiera con una identidad nueva, que el registro admite porque no suplanta a nadie. Así puede hacer
  desaparecer una lectura con la verificación en verde. La versión anterior de este documento
  afirmaba que nadie podía suprimir contenido "anclado o no"; era falso (§7.4), y una prueba fija
  ahora el límite.
- **Aprovisionado** (`trusted_sources`): el registro llega de fuera al abrir el almacén, como la
  autoridad de redacción, y no admite altas. Una fila de `trusted_keys` que no esté aprovisionada es
  un fallo de verificación. El reencadenado con una identidad nueva deja de funcionar; queda el
  truncado puro de la cola, que solo detecta un ancla (§3.3). Dar de alta una fuente nueva en una
  base existente añade su fila a `trusted_keys` —antes dejaba la verificación en rojo para siempre,
  una falsa alarma (§7.5)—. La lista aprovisionada tiene que conservar para siempre las claves de
  todas las fuentes que han escrito, y una identidad no puede cambiar de clave.

La API usa un almacén **en memoria**, que quien edita el disco no puede tocar, con el registro
aprendido. Un almacén en fichero debería abrirse con fuentes aprovisionadas. En ninguno de los dos
modos se puede justificar un contenido ausente sin la autoridad de redacción (§3.6), y la parte
anclada no se puede reescribir, porque la raíz de Merkle compromete la clave y la firma de cada
entrada (§3.3). En producción el
registro llegaría aprovisionado desde Tierra antes del lanzamiento, y las claves privadas vivirían
en un elemento seguro del dispositivo. Ni lo uno ni lo otro está implementado: hoy las claves
de la API se generan por proceso y solo en memoria.

El no-repudio que da la firma es, por tanto, relativo a ese registro.

Biblioteca: `cryptography` (ya en `pyproject.toml`).

### 3.3 Anclaje por raíz de Merkle

Las entradas se agrupan en un árbol de Merkle con la construcción de **RFC 6962** (Certificate
Transparency): prefijo `0x00` en las hojas, `0x01` en los nodos internos, y el nodo impar de cada
nivel sube sin duplicarse. Cuando existe ventana de comunicación con la Tierra, se transmite un
**ancla**: la raíz (32 bytes), el número de entradas que cubre y el identificador del algoritmo
(`rfc6962-sha256`). Control de Misión la sella con marca de tiempo y la devuelve firmada.

La versión anterior duplicaba el último nodo de cada nivel impar y no separaba hojas de nodos: es
CVE-2012-2459. `[a, b, c]` y `[a, b, c, c]` daban la misma raíz, una prueba de inclusión para una
hoja fantasma validaba contra el ancla, y un nodo interno podía presentarse como hoja. La
implementación actual se comprueba contra una implementación recursiva literal de la RFC, escrita
aparte en la suite, para árboles de 0 a 33 hojas.

Consecuencias:
- Un testigo externo e independiente de la integridad, que es el espíritu de "independently record"
  en §11.10(e).
- **Ningún dato médico sale de la nave** para conseguirlo.
- Unos 100 bytes por ventana: irrelevante frente al presupuesto de enlace profundo.
- Verificable a posteriori: cualquier entrada se prueba contra la raíz anclada con una prueba de
  Merkle de tamaño logarítmico.
- **La raíz compromete también la firma y la clave de cada entrada** (§3.1): el ancla atestigua
  procedencia, no solo contenido.

**Qué detecta el ancla que la cadena sola no puede.** `verify(anchor=...)` falla si la cadena es más
corta que el tamaño anclado o si su prefijo no reproduce la raíz. Eso cubre dos casos que ningún log
local puede detectar por sí mismo:

- **Truncar la cola.** Borrar las últimas entradas —justo las del incidente que se quiere ocultar—
  deja una cadena internamente coherente. Sin ancla no es detectable, y la suite lo documenta con
  una prueba que lo afirma, para que nadie sostenga lo contrario.
- **Reescribir con control total del almacén.** Quien pueda editar a la vez la cadena y el registro
  de claves puede fabricar una historia coherente (§3.2). No puede fabricar una que reproduzca una
  raíz que ya está en Tierra.

El ancla **no** cubre el payload —por eso sobrevive a una redacción—, así que por sí sola no
protege frente a la supresión de contenido. Eso lo cierra la autoridad de redacción (§3.6). La
versión anterior de este documento lo daba por cubierto, y no lo estaba (§7.2).

**Estado:** el ancla se calcula y se expone en `GET /api/audit`, y `verify_integrity(anchor=...)` la
comprueba. **La transmisión a Tierra y el sellado por Control de Misión no están implementados.**
Y como no se recibe ningún ancla, **ningún camino de la aplicación verifica contra una**:
`verify_integrity(anchor=...)` existe, pero nadie se la pasa. En la práctica, hoy nada está anclado.
Hasta que lo estén, el sistema tiene integridad interna frente a una edición parcial del almacén,
no frente a quien lo controle entero.

### 3.4 Escritura: un escritor a la vez, y cada lote entero o nada

La cadena de hashes solo prueba algo si el orden de los asientos es el orden real de escritura. El
almacén **no tenía ningún cerrojo**, y FastAPI atiende los endpoints síncronos en un pool de hilos.
`HashChainLedger.append` lee el índice y el hash anterior, firma, y solo entonces añade: dos
peticiones simultáneas podían coger el mismo índice.

Reproducido con 4 hilos y 800 escrituras: **163 asientos con índice duplicado**. La cadena quedaba
rota por pura concurrencia, y `verify_integrity()` lo habría denunciado como manipulación: un falso
positivo de alteración es tan dañino para 11.10(a) como un falso negativo, porque enseña a ignorar
la alarma. Con la base en memoria —la que usa la aplicación— la única conexión compartida acabó
reseteada y el almacén **perdió sus tablas**.

Diseño:

- **Un cerrojo reentrante en `ObservationStore`** serializa toda escritura y lectura. El orden de
  la cadena coincide con el de los `commit`, y la conexión compartida nunca la usan dos hilos.
- **Cada lote es una transacción.** `record_many` valida el lote entero contra el catálogo antes de
  escribir nada, y escribe todas sus filas con un solo `commit`. `record()` es un lote de uno.
- **El ledger en memoria nunca diverge de la base.** Los asientos se añaden en memoria antes del
  `commit` porque la fila necesita su hash y su firma. Si el `commit` falla, se retiran. No es
  reescribir historia: nunca llegaron a disco, y bajo el cerrojo nadie ha podido encadenar detrás.
  La redacción sigue la misma regla: si la base no llega a redactar, la memoria tampoco.

Efecto secundario: sembrar 21 120 observaciones bajó de 23,1 s a 7,6 s. El coste estaba en un
`commit` por fila; firmar y encadenar son menos de 1 s. Remedido el 2026-09-22 con el código actual:
2,3 s con la base en memoria y 2,4 s en fichero, con el proceso fijado a un núcleo de rendimiento.
Sin fijarlo, Windows puede llevarlo a núcleos de eficiencia, y todas las cifras de esta sección y de
la siguiente salen de 5 a 7 veces más lentas; en fichero se llegaron a medir 13 s así.

Tras la revisión del 2026-09-21, dos refuerzos:

- **El ledger tiene su propio cerrojo.** El del almacén protegía el camino de la API, pero
  `HashChainLedger` usado directamente reproducía la carrera: 8 hilos × 30 escrituras dejaban
  índices duplicados. La garantía vive ahora en el ledger, no en quien lo llama.
- **`HashChainLedger.transaction()`** agrupa todo lo que un lote o una redacción cambia en memoria
  —asientos, lápida, contenido suprimido y claves recién fijadas— y lo deshace entero si el `commit`
  falla. Antes el almacén retiraba los asientos a mano, y una clave nueva fijada dentro de un lote
  fallido se habría quedado en memoria sin estar en disco.

### 3.5 Se verifica el disco, y el motor solo analiza lo firmado

La base guarda cada lectura dos veces: en el asiento firmado (`ledger_entries.payload`) y en la
tabla `observations`, una copia de conveniencia que **no cubre ningún hash**. Dos fallos, uno por
cada copia, reproducidos con la aplicación en marcha:

- **El análisis leía la copia sin hash.** Editar en disco una lectura de 62 a 140 lpm hacía que el
  motor de detección **analizara los 140**.
- **`verify_integrity()` verificaba la memoria, no el disco**, aunque su docstring decía "tal y como
  está en disco". Respondía ok ante cualquier edición del fichero, y `/api/status` publicaba
  `integrity_ok: true` junto a un análisis hecho sobre el dato alterado. Solo se detectaba al
  reiniciar.

Diseño:

- **`query()` sirve cada lectura desde el `payload` de su asiento**, y comprueba que ese contenido
  sigue coincidiendo con el `content_hash` firmado antes de entregarla; si no, lanza
  `TamperedRecordError` en vez de devolverla. La tabla `observations` queda como índice para
  inspección por SQL.
- **`verify_integrity()` tiene dos partes.** (1) La cadena en memoria: encadenamiento y hash de
  contenido de todas las entradas, y firma Ed25519 solo de las que aún no se comprobaron —cubren
  campos de un dataclass congelado que no cambian una vez en memoria; lo que se carga de disco se
  verifica entero—. (2) El disco contra la cadena: cada asiento guardado y cada fila de
  `observations` deben coincidir con la cadena verificada. La memoria no la puede editar otro
  proceso; el fichero sí.

Detecta con la aplicación en marcha las cuatro manipulaciones probadas: editar una lectura, editar
un asiento, borrar una fila y añadir una fila sin asiento. Tras la revisión del 2026-09-21 compara
además las diez columnas de cada asiento —antes omitía `recorded`, `entry_type` y `signer`, y con
las lápidas `entry_type` decide qué asiento justifica una supresión— y el registro de claves en los
dos sentidos.

Coste, remedido el 2026-09-22 con 21 120 asientos, el código actual y el proceso en un núcleo de
rendimiento (§3.4): 1,9-2,0 s la primera verificación y 0,4-0,5 s las siguientes, igual con la base
en memoria que en fichero. `query()` tarda unos 40 ms consultando a uno de cuatro tripulantes
(5 280 lecturas), y 130-155 ms si las 21 120 son del mismo, porque vuelve a hashear cada lectura que
entrega, como defensa en profundidad. La medición anterior de esta sección (8,8 s / 1,7 s) es de
antes de estos cambios; no se ha investigado la diferencia. Desde el 2026-11-03 las verificaciones
siguientes a la primera repiten a fondo solo lo nuevo, y `query()` deja de rehashear mientras la
memoria no haya cambiado desde su comprobación (§3.5 bis).

Tras la segunda revisión (2026-09-22), tres correcciones más:

- **Las lecturas se guardan en UTC.** SQLite descartaba el desfase: una lectura en `+02:00` se releía
  como UTC, dos horas desplazada, y la verificación del disco la denunciaba como manipulación para
  siempre. Era una falsa alarma de integridad producida por una petición legítima.
- **Un disco incoherente es un fallo de verificación, no una excepción.** Una fila de
  `observations` que apuntara a una lápida, una fecha ilegible en un asiento o una lápida mal
  formada lanzaban una excepción y tumbaban `/api/status` o `/api/audit` con un 500. La primera
  corrección dejó fuera los valores de tipo inesperado —un BLOB donde iba texto, un índice
  decimal—, que seguían lanzando en caliente y al reabrir (§7.3). Ahora la cabecera de cada asiento
  se comprueba por tipos antes de hashearla, y todo el cotejo con el disco queda cubierto. Una base
  corrupta en reposo —fecha ilegible, JSON roto, clave no hexadecimal— ya no impide abrir el
  almacén: abre, y la verificación señala el asiento.
- **`query()` solo sirve datos de una cadena verificada.** Filtraba por tripulante y fecha antes de
  comprobar nada: mover en disco una lectura a otro tripulante la sacaba de la consulta sin error,
  y el motor emitía un veredicto sin ella. La primera corrección comparaba cada payload con su
  `content_hash`, pero ese hash venía del disco sin verificar su firma: recalcularlo —un SHA-256 no
  necesita clave— o cambiar `entry_type` bastaba para que `query()` omitiera la lectura o la
  entregara alterada (§7.3). Ahora lo que no se ha verificado en este proceso se verifica entero
  antes del primer uso —firma, firmante, encadenamiento, contenido y lápidas—, y cualquier fallo es
  un 409. Lo que escribe el propio proceso no necesita verificarse: lo construye el ledger. Coste
  con 21 120 asientos: 1,75-1,95 s la primera consulta tras abrir un almacén en fichero; las siguientes,
  lo de siempre. El almacén en memoria que usa la API no paga ese coste.

Sobre el atajo de firmas: se salta Ed25519 de lo ya verificado porque la memoria del ledger es
privada del proceso —toda salida pública es una copia—, no porque lo cubra el encadenamiento. Cambiar
la firma de una entrada rompe el enlace de la siguiente, pero la última no tiene siguiente. Una
versión anterior de este documento daba la razón equivocada; hay una prueba que fija el límite.

Tras la cuarta revisión (2026-09-22), la carga y el cotejo toleran también el texto que no es UTF-8,
el JSON anidado a miles de niveles, un NULL donde iba un instante y una identidad repetida en
`trusted_keys`. La afirmación anterior de que "todo el cotejo con el disco queda cubierto" era
prematura (§7.4), y la de esta misma sección, que decía "nunca en un 500", también: una lectura mal
formada firmada por una identidad dada de alta en la base (modo aprendido) seguía tumbando
`query()` y la verificación (§7.5). Ahora todo termina en un fallo de verificación, en un 409 o en un
almacén que abre y lo señala. Lo que sigue impidiendo abrirlo es un cambio de esquema —una columna o
una tabla borradas o renombradas—: sin esquema no hay nada que verificar.

### 3.5 bis Verificación incremental: a fondo, solo lo nuevo (2026-11-03)

**Problema medido.** Con el escenario `spe-event` de 40 días (~94 000 asientos), `GET /api/status`
tardaba 3,7-10 s según la carga de la máquina, y el 75 % era `verify_integrity()`: el hash de
contenido de cada asiento recalculado en memoria (serialización canónica, ~2,5 s) y la base entera
releída y cotejada (~2 s), en **cada** consulta. La consola pide el estado cada 30 s y el asistente
de voz en cada turno. Recalcular lo ya verificado solo sirve para descubrir que algo cambió; si
cada cambio deja rastro, eso se sabe sin releerlo.

**Diseño.** Cuando una `verify_integrity()` sale bien, el almacén anota hasta qué asiento llegó y
dos marcas. En la siguiente, si las dos marcas siguen iguales, se verifica **a fondo solo lo
añadido** desde entonces —firma, firmante, encadenamiento con el último ya verificado, contenido,
fila del asiento, fila de `observations` y binario— con el mismo código que la completa. Si
cualquiera de las dos ha cambiado, la verificación es la completa de siempre.

1. **Marca de memoria** (`HashChainLedger.memory_mark` / `unchanged_since`). La cabecera de cada
   asiento ya era un dataclass congelado; el payload no: es un `dict`, y mutarlo en sitio fue un
   fallo real (§3.5, las lecturas de analítica anotadas sobre el asiento). Ahora el payload
   guardado —lo escrito y lo cargado de disco— vive en contenedores vigilados (`_WatchedDict`,
   `_WatchedList`, a cualquier profundidad admitida) que **cuentan cada mutación en cuanto la hacen**
   —después, no antes: contada antes, una marca tomada entre la cuenta y el cambio ya lo daría por
   visto—, y lo que meten entra vigilado también. La lista de asientos cuenta toda operación que no sea
   añadir al final (`_EntryList.rewrites`: redactar, deshacer una transacción, sustituir un
   asiento a mano). La marca guarda además la identidad de la lista —una lista sustituida, o una
   que no es la vigilada, nunca se da por intacta—, la autoridad de redacción y el registro de
   claves (que gane claves no cambia lo ya verificado; que pierda o cambie una, sí). Copiar un
   payload (`copy`, `deepcopy`, `pickle`, `dict(...)`) da un `dict` normal: cambiar la copia no es
   cambiar el asiento, ni lo parece.
2. **Marca de disco** (`_DiskMark`), tres contadores de SQLite que no hace falta leer la base para
   consultar, más la identidad de la conexión a la que pertenecen:
   - `PRAGMA data_version`: según la documentación de SQLite, cambia si **otra** conexión —de este
     proceso o de otro, con cualquier cliente— confirmó un cambio en la base desde la última
     consulta de esta conexión.
   - `total_changes` de la conexión: filas insertadas, cambiadas o borradas por **esta** conexión,
     triggers incluidos. Cubre lo que el anterior no ve por definición: quien edite la base por la
     misma conexión del almacén, que con la base en memoria de la API es la única que existe.
   - `PRAGMA schema_version`: cambia con cualquier cambio de esquema (borrar o rehacer una tabla),
     que `total_changes` no cuenta.

   Las escrituras del propio almacén mueven `total_changes`. Para no confundirlas con una edición
   ajena: **antes** de escribir se comprueba que la marca sigue como se anotó (si no, se olvida la
   verificación anterior), y **después** se anota solo el nuevo `total_changes`, y solo si
   `data_version` y el esquema no se han movido. Una escritura fallida olvida la verificación.
3. **Lo que depende de un asiento anterior vuelve a la completa.** Si entre lo nuevo hay una lápida
   o una enmienda, se verifica todo: las dos se validan contra su diana —que esté redactada, que no
   tenga otra enmienda—, y redactar o enmendar es además lo único que toca filas antiguas en disco.
   Con `anchor`, también siempre completa: el ancla se comprueba sobre los hashes de todo el
   prefijo anclado.

La primera verificación tras arrancar o abrir un almacén es siempre completa, y `query()` y los
demás lectores dejan de recalcular el hash de cada lectura que entregan **solo** mientras la marca
de memoria de su última comprobación siga intacta: una mutación en sitio los devuelve a comprobar
asiento a asiento, como antes (`test_query_rechecks_readings_after_a_memory_mutation`).

**Por qué no debilita la detección.** `verify()` es una función de lo que hay en memoria (cabeceras,
payloads, lista, registro y autoridad) y `_verify_disk_matches_chain`, de eso y del disco. Si nada
de la memoria ya verificada ha cambiado y SQLite no ha visto ninguna escritura salvo las propias,
repetir la verificación sobre ese prefijo daría el mismo resultado que dio: saltarla no oculta
nada. Todo lo que puede cambiarlo —un payload mutado a cualquier profundidad, un asiento sustituido,
la lista cambiada por otra, una clave desfijada, otra autoridad, una fila editada por la misma
conexión o por otra, una tabla rehecha, una edición ajena justo antes de una escritura
propia, o durante ella desde otra conexión— mueve una marca, y entonces se repite entera. Cada una de esas vías tiene su prueba en
`backend/tests/test_incremental_verification.py`, que ejecuta el ataque entre dos verificaciones, y
cada comprobación de las marcas su mutante en `backend/tests/mutants/incremental_verification.json`
(19 de 19 cazados). Las respuestas de `/api/status` antes y después del cambio son idénticas campo a
campo en cinco escenarios del simulador, en la primera consulta y en las dos siguientes.

**Límites declarados.**

- **Bytes del fichero escritos sin pasar por SQLite** (un editor hexadecimal con la aplicación en
  marcha): no mueven ningún contador, y el camino incremental no los ve; los ve la siguiente
  verificación completa (al reabrir, tras cualquier escritura por SQLite, una lápida, una enmienda o
  un ancla). Tampoco antes eran una garantía: SQLite conserva su caché de páginas entre
  transacciones mientras no cambie el contador de cambios de la cabecera del fichero, así que una
  relectura completa solo veía esa edición en las páginas que no tuviera en caché. La API usa la
  base en memoria (`routes.new_store`): no hay fichero que editar.
- **Código dentro del proceso que esquiva la vigilancia a propósito**: `dict.__setitem__(payload,
  …)`, `object.__setattr__` sobre un asiento congelado, o las API de bajo nivel de la propia
  conexión (`blobopen`, `deserialize`, copia de seguridad), o escribir por la conexión del almacén
  desde otro hilo, sin su cerrojo, mientras el almacén escribe (esa subida de `total_changes` se
  confundiría con la propia). Quien ejecuta código en el proceso con
  intención de engañar puede igual de fácil sustituir el verificador; no es una amenaza que la
  verificación pueda cerrar, y lo mismo valía para el atajo de firmas de §3.5.
- **Las escrituras propias solo añaden filas de sus asientos nuevos.** Es una propiedad del código
  de `storage.py` (`_ledger_row`, `_observation_row`, el binario de su estudio), no una suposición
  sobre el disco: las dos vías que tocan filas antiguas, redactar y enmendar, fuerzan la completa.

**Coste**, medido el 2026-11-03 con 40 días de `spe-event` (94 084 asientos), base en memoria,
`TestClient` y la máquina cargada por otras sesiones (las cifras absolutas varían con la carga;
la comparación es la de dos ejecuciones seguidas): `verify_integrity()` en caliente pasa de
5,2 s a 10-16 ms, y `GET /api/status` en caliente de 7,1 s a 1,7 s con solo este cambio, y a
0,8 s junto con dos arreglos del mismo perfil que no cambian ningún resultado —`query()` y los
lectores de hábitat y acciones sin rehashear lo ya comprobado, y una ordenación menos por ventana
en `compute_baseline`—. La primera consulta tras sembrar sigue haciendo la verificación completa
(11-19 s con esa carga, sin cambios). Con la base en fichero, servida por uvicorn: 1,2-1,4 s en
caliente con la suite corriendo a la vez, y una edición de `observations` hecha desde otra
conexión de SQLite sale como `integrity_ok: false` en la petición siguiente.

### 3.6 Redacción: el contenido se va, la constancia se queda

Suprimir un dato que nunca debió registrarse —el de un tripulante atribuido a otro— es una
decisión de diseño; la rectificación que prescribe HIPAA es otra cosa, una enmienda anexada
(§164.526, §1.2). La versión anterior de este documento la atribuía a §164.312(c)(1). La
versión anterior del código implementaba la supresión vaciando el payload de la entrada y marcándola `redacted`, y nada
más. La revisión demostró que eso permitía **borrar una alerta clínica crítica y dejar la cadena en
verde, con la raíz anclada idéntica**: no quedaba asiento, ni motivo, ni autor, y la marca
`redacted` no estaba firmada, así que borrarla dejaba la entrada indistinguible de una que nunca
tuvo contenido. Chocaba con tres cosas que este documento declara cumplir: §164.312(c)(2) cita
*"altered **or destroyed**"*, §11.10(e) exige registrar las acciones que *"delete"*, e ISO 27789
pide un registro por cada acción.

Diseño:

- **Solo firma lápidas la autoridad de redacción**: una identidad cuya clave pública llega al ledger
  al construirlo, desde fuera del almacén, y nunca se lee de `trusted_keys`. `verify()` rechaza
  cualquier lápida firmada por otra clave, aunque esté en el registro, y la autoridad no puede
  firmar datos clínicos. Sin autoridad no hay redacciones: la API responde 503. La primera versión
  de esta sección dejaba firmar lápidas a cualquier clave registrada, y eso permitía borrar una
  lectura anclada sin ninguna clave privada del sistema (§7.2).
- **Redactar añade primero una lápida**: un asiento firmado (`entry_type: "redaction"`) con el
  índice de la entrada, su `entry_hash`, su `content_hash`, el motivo y quién lo pidió. Después se
  suprime el contenido. Lápida, supresión y borrado de la fila de `observations` van en un solo
  `commit`. Redactar un TAC arrastra en ese mismo `commit` las fases de contraste declaradas de
  él y sus segmentaciones, cada una con su lápida y, la segmentación, con su binario borrado
  (§3.13 bis).
- **`verify()` exige una lápida por cada contenido ausente**, que apunte exactamente a esa entrada.
  Vaciar un payload sin lápida, borrar la marca `redacted`, restaurar un contenido redactado
  dejando la lápida, redactar una lápida o redactar dos veces la misma entrada: todo falla. Borrar la
  lápida y restaurar el contenido a la vez es otra cosa: si la lápida es el último asiento, es un
  truncado de la cola más una restauración, y sin ancla no se detecta (§3.2). Lo que lo impide en la
  práctica es que el contenido ya no existe en ningún sitio del que restaurarlo (siguiente punto).
- **La lápida está atada a su entrada exacta** (`target_entry_hash` y `target_content_hash`).
  Todos los almacenes de la API comparten autoridad: sin esa atadura, la lápida legítima de uno,
  copiada en otro, suprimía allí una lectura para `redacted_indices()` (§7.3).
- **No se redacta sobre una cadena que no verifica.** La autoridad podía firmar una lápida para un
  asiento ya manipulado, y `verify()` pasaba a verde: la prueba de la alteración quedaba sustituida
  por una rectificación de apariencia legítima (§7.3). Ahora la redacción exige que la cadena
  verifique; si no, la API responde 409.
- **El tipo `redaction` está reservado**: `append()` no lo acepta; solo `redact()` lo escribe.
- **Borrar es borrar.** La redacción dejaba la lectura en el fichero —SQLite marca el espacio como
  libre sin sobrescribirlo—, y el `content_hash` de la lápida se invertía con un diccionario (§7.4).
  Ahora cada conexión activa `PRAGMA secure_delete`, que pone a cero lo borrado, y el hash cubre una
  sal aleatoria que desaparece con el contenido. Una copia de la base anterior a la redacción sigue
  teniendo el dato, y eso ya no está al alcance del software. **El journal sí lo está, y no se
  limpia:** en el momento del `commit`, `emma.db-journal` contiene la página anterior con el dato,
  y en modo DELETE ese fichero se desenlaza sin sobrescribirse, así que el dato queda en bloques
  libres del disco hasta que se reutilicen. Con `journal_mode=WAL`, el fichero `-wal` lo conserva
  mientras el proceso vive. Solo el cifrado del disco lo cierra, y no está implementado (§7.5).
- **Un ancla anterior a la redacción sigue verificando**, porque la hoja de Merkle no cubre el
  payload. La siguiente ancla incluye la lápida: la redacción queda registrada también en Tierra.

**Límite, declarado.** `POST /api/audit/redact/{índice}` exige motivo y solicitante, pero **no
autentica a nadie**: `requested_by` es lo que declara quien llama. La lápida la firma el sistema
(`emma-audit`), que da fe de que se redactó y de lo que se declaró, no de quién lo pidió.

**Conflicto con la norma, ahora acotado.** Redactar borra el contenido, y eso choca con dos textos
que este documento cita. 21 CFR 11.10(e) exige que *"record changes shall not obscure previously
recorded information"* (§1.1), y HIPAA §164.526 corrige anexando o enlazando la enmienda, no
borrando (§1.2). La lápida conserva la constancia de que el dato existió, su hash, el motivo y el
solicitante, pero no el dato. **La corrección de un valor erróneo ya no pasa por aquí**: para eso
está la enmienda anexada de §3.7, que no borra nada. Lo que queda en la redacción es el caso para el
que se diseñó —el dato que nunca debió registrarse, como el de un tripulante atribuido a otro—, y
ahí el choque con la segunda frase de (e) persiste: es deliberado, y se declara en vez de
disimularse.

Y en la demo la autoridad es efímera: su clave se genera al arrancar el proceso, igual que el
almacén vive en memoria. Un almacén en fichero exige una clave de redacción aprovisionada y la misma
entre reinicios. Con otra, las lápidas anteriores dejan de justificar sus supresiones y la
verificación falla; hay una prueba que lo afirma.

---

### 3.7 Enmienda anexada: la corrección que no borra

La vía normal para corregir un dato mal registrado. La implementa `HashChainLedger.amend()`, y
`ObservationStore.amend()` la lleva hasta lo que el motor analiza.

**Qué se escribe.** Un asiento propio, de tipo `amendment`, firmado como cualquier otro, con:

```
target_index          índice de la entrada que corrige
target_entry_hash     su entry_hash   ─┐ atadura a la entrada exacta
target_content_hash   su content_hash ─┘
reason                por qué se corrige
amended_by            quién la firma
replacement           la versión buena del dato
_salt                 16 bytes aleatorios
```

**La entrada corregida no se toca.** Sigue con su contenido, su firma y su hash; no se marca ni se
vacía. Eso es lo que la separa de una redacción, y lo que satisface la segunda frase de
21 CFR 11.10(e): el cambio **no oculta** lo registrado antes. La atadura por `target_entry_hash` y
`target_content_hash` es el *"appending or otherwise providing a link to the location of the
amendment"* de §164.526(c)(1).

**Qué versión está vigente.** `ledger.amendments()` responde a esa pregunta: una entrada que aparece
como clave está sustituida por la enmienda que la acompaña. Sobre eso, `query()` entrega la versión
corregida **y solo esa** — entregar las dos contaría dos veces el mismo dato en la línea base
personal, que es lo que decide todas las desviaciones. La versión anterior sigue en `/api/audit`.

**Reglas, y el ataque que cierra cada una:**

- **`append()` no puede escribir un asiento `amendment`.** Sin esa reserva, cualquier fuente de
  confianza declararía corregida —y fuera de las consultas— una lectura ajena que nunca examinó,
  con los campos que quisiera.
- **La firma una fuente del registro, nunca la autoridad de redacción.** El `replacement` es un dato
  clínico: una clave pensada para rectificar no puede fabricarlos.
- **Una enmienda por entrada.** Dos dejarían dos versiones vigentes del mismo dato sin forma de
  decidir cuál vale. Una corrección de una corrección enmienda la enmienda, y la cadena de eslabones
  queda atada hash a hash.
- **No se enmienda una lápida, ni una entrada redactada, ni una que no verifique por sí sola.** Lo
  último por la misma razón que no se redacta sobre ella: daría apariencia de dato revisado a un
  registro manipulado.
- **Una enmienda copiada de otro almacén no retira nada aquí**, porque no coincide con el
  `entry_hash` de ninguna entrada de esta cadena.
- **La corrección es del mismo indicador que la lectura que corrige** (2026-10-26).
  `ObservationStore.amend()` compara la clave de la corrección con la de la lectura vigente del
  asiento —la de una observación, o la corrección de una enmienda si se enmienda una enmienda— y,
  si no coincide, no escribe nada; la API responde 422 con el motivo en español, no 409, porque es
  un dato malo de quien llama y no un conflicto de estado. Un asiento que no es una lectura de un
  indicador (una lectura de cabina, un reconocimiento…) tampoco se enmienda con una: 422. Sin la
  regla, cambiar el indicador retiraba la lectura de una serie y ponía en otra un dato que nadie
  midió en su sitio. **El tripulante sí puede cambiar, a propósito:** reasignar una lectura mal
  atribuida es el control del peligro H3 (`risk-management-file.md`), y la redacción no lo sustituye
  porque borra. El pendiente de la decimosexta ronda pedía «mismo indicador y tripulante»; lo
  segundo chocaba con H3 y no se adoptó. La regla es de la escritura, no de `verify()`: un ledger
  ya escrito con una enmienda de otro indicador sigue verificando. Una entrada ya enmendada,
  redactada o que es una lápida sigue siendo un 409 sea cual sea el indicador: el conflicto de
  estado no se disfraza de dato malo. Se comprueba antes de verificar la cadena entera.
- **El orden al borrar: primero el original, después su corrección.** Redactar la enmienda antes que
  su objetivo devolvería a las consultas el valor que corrigió, y ese valor se sabe equivocado. El
  ledger lo rechaza con ese motivo.
- **Una enmienda anterior a una redacción sigue siendo válida después de ella**, porque ni
  `content_hash` ni `entry_hash` cambian al redactar: la corrección ocurrió, y eso no se deshace.

**Lo que cuesta.** Resolver qué versión está vigente es una pasada más sobre la cadena en cada
consulta: medido sobre 21 120 asientos, **0,6 ms sin ninguna enmienda y 4,4 ms con una** —ahí entra
verificar su firma y rehacer los dos hashes que la atan—, frente a los ~244 ms de la consulta
completa en esa misma máquina. Por debajo del 2 %. Las cifras absolutas de §3.4 y §3.5 no se tocan:
se midieron con el proceso fijado a un núcleo de rendimiento y esta medición no lo estaba.

**En la tabla espejo `observations`**, la fila de la lectura corregida se sustituye por la de la
versión buena. La tabla es el índice de lo vigente, no el registro: lo anterior sigue en la cadena.
El cotejo con el disco (§3.5) exige exactamente eso — una fila por lectura vigente, ni la corregida
de más ni la corrección de menos.

**Lo que esta vía no resuelve.** La API no autentica a quien llama (§3.6), así que `amended_by` vale
lo que valga la identidad firmante, y el motivo es lo que declare quien corrige. Y §164.526 regula
además el procedimiento —plazos, denegación motivada, notificación a terceros— que es organizativo y
queda fuera del software.

### 3.8 Reconocimiento de alertas: una acción que se registra

Reconocer una alerta detiene su parpadeo (NASA-STD-3001 Vol 2, F.5.11). Deja de reclamar
atención, y eso es una decisión: 21 CFR 11.10(e) pide registrar las acciones del operador, no solo
los datos. Hasta el 2026-09-23 el reconocimiento vivía en la sesión de la interfaz: no dejaba
rastro, no tenía autor y se perdía al recargar.

Ahora es un asiento de tipo **`alert-acknowledgement`** (`core/storage.py`), escrito por la vía
general `append()`. No hace falta cambiar `ledger.py`: el tipo no está reservado como la lápida o
la enmienda, porque no retira ni sustituye nada. Lo firma la identidad `crew-console`, una fuente
más del registro de confianza que, como todas, no puede firmar lápidas ni enmiendas (§3.2).

| Campo | Contenido |
|---|---|
| `subject` | Tripulante |
| `domain`, `level` | La alerta reconocida. Un cambio de nivel es una alerta distinta |
| `reference_time` | La última lectura del estado que vio quien reconoce: se reconoce **esa** alerta |
| `acknowledged_by` | Autor **declarado**; la API no autentica (§3.6) |
| `_salt` | La pone el ledger, como en todo asiento |

**No es un dato clínico.** No entra en `observations` ni en el análisis. El cotejo con el disco
(§3.5) solo exige fila para los asientos que ponen una lectura en circulación, así que este tipo no
la necesita. Se prueba que reconocer no cambia ni las lecturas analizadas ni los dominios.

**Qué cubre un reconocimiento.** El mismo dominio al mismo nivel, y solo mientras su
`reference_time` siga dentro de la ventana con que se calcula el estado (`CURRENT_WINDOW`, 2 días).
Si valiera para siempre, una recaída días después llegaría ya reconocida, sin parpadeo. Pasada la
ventana, las lecturas que motivaron la alerta reconocida han salido del cálculo: lo que siga
alertando se apoya en lecturas nuevas y hay que reconocerlo otra vez.

**Un reconocimiento manipulado no silencia nada.** Se entrega con las mismas garantías que una
lectura: si su contenido no coincide con el hash firmado, `/api/status` responde 409 en vez de dar
la alerta por reconocida (`test_a_tampered_acknowledgement_cannot_silence_an_alert`).

**Silenciar: `alert-annunciation`.** Suprimir, inhibir y volver a habilitar el anuncio de las
alertas de un dominio (F.6.4) es otro tipo de asiento, con la misma vía y la misma firma:

| Campo | Contenido |
|---|---|
| `action` | `suppress` (una alerta concreta), `inhibit` (el dominio hasta un nivel) o `enable` |
| `domain`, `level` | Lo silenciado. `level` vacío en `enable` |
| `reference_time` | El estado sobre el que se decidió |
| `until` | Hasta cuándo. Vacío en `enable` |
| `reason`, `requested_by` | Motivo **obligatorio** y autor declarado |

Para cada dominio vale el último cambio que ya existía en el instante del estado: la consola de
Tierra no ve silenciado lo que a bordo se silenció después. Los límites (duración, nada de inhibir
en crítico, una escalada rompe el silencio) los impone la API y están en el peligro H13 de
`risk-management-file.md`.

**Existencia, firmante y límites (2026-09-24).** Reconocer o suprimir exige que la alerta exista en
el estado de `reference_time` (409 si no). Al calcular el estado solo cuentan las acciones
firmadas por `crew-console` y, en el caso de los silencios, dentro de los límites que impone la API;
un silencio caduca con el reloj real, y la consola de Tierra solo tiene en cuenta acciones
registradas (`recorded`) antes de su corte. Cada acción expone ahora su firmante (`signer`).

### 3.9 Cambiar de escenario simulado: se sustituye el almacén, nunca un registro real

`POST /api/simulate?replace=true` construye un almacén nuevo con el escenario pedido y sustituye al
anterior. Es lo mismo que cerrar y abrir la aplicación, que ya descartaba el almacén en memoria, pero
sin cerrarla. **No es un endpoint de borrado**, y tiene tres condiciones:

- **Solo si todo lo registrado es simulado.** Si alguna lectura, enmienda, lectura redactada o
  estudio de imagen (§3.10) la firmó otra fuente que no sea el simulador, responde 409 y no toca
  nada. Se mira el firmante del
  asiento, que se conserva aunque se redacte el contenido: una lectura real redactada sigue siendo
  un registro real. Los reconocimientos y silencios de la consola sobre alertas simuladas no lo
  impiden, porque no son lecturas.
- **Atómico.** El almacén nuevo se siembra aparte y solo al final sustituye al viejo. Si algo falla,
  el anterior sigue intacto.
- **Sin carreras.** Sembrar lleva segundos. Si mientras tanto entra cualquier asiento en el almacén
  viejo, no se sustituye (409): podría ser una lectura real.

Pruebas: `test_replace_switches_the_scenario_without_mixing`,
`test_replace_never_discards_a_real_reading`, `test_a_study_is_not_lost_by_switching_scenario`.

### 3.10 Estudios de imagen: el binario fuera del asiento, dentro de la firma

Una ecografía es un registro clínico como una lectura, pero no cabe en un asiento: el ledger solo
admite JSON (§3.1), y un DICOM son megas de binario. Añadido el 2026-09-24 (`core/storage.py`,
`app/imaging/`, `app/api/imaging.py`).

**Diseño.** Un asiento **`imaging-study`**, escrito por la vía general `append()` —el tipo no está
reservado: no retira ni sustituye nada—, cuyo payload lleva el **SHA-256 y el tamaño** del binario.
El binario va en la tabla `imaging_blobs`, en la **misma base** y en el **mismo `commit`** que el
asiento. En la misma base y no en ficheros sueltos: no puede quedar un asiento que apunte a un
fichero que no llegó a escribirse, funciona igual con la base en memoria, y redactar borra el binario
con el mismo `secure_delete` que el resto (§3.6).

| Campo | Contenido |
|---|---|
| `subject`, `protocol` | Tripulante y protocolo ecográfico del registro (`imaging/protocols.py`) |
| `acquired` | Instante de adquisición en UTC. Del propio DICOM si fija la zona; si no, lo tiene que dar quien sube, con zona: adivinarla desplazaría el estudio horas en la tendencia |
| `source` | Fuente que firma (`ultrasound`) |
| `sha256`, `size_bytes` | Del binario **ya des-identificado**, que es el que se guarda |
| `frames`, `rows`, `columns` | Geometría |
| `calibration` | Regiones con escala física declarada por el equipo, en mm/píxel. Vacía = no se puede medir en mm |
| `burned_in_annotation` | Lo que declara el equipo sobre texto quemado en los píxeles |
| `_salt` | La pone el ledger, como en todo asiento |

**Antes de guardar se des-identifica** (perfil básico de DICOM PS3.15 con retención de fechas
completas, códigos DCM 113100 y 113106). **Desde el 2026-11-16 por lista de lo que se conserva**
(`imaging/dicom.py: _KEPT`), no de lo que se quita: en la raíz solo quedan la identidad del objeto,
el módulo de píxel, el cine, las fechas, la calibración de ecografía, la marca de texto quemado y
las secuencias de volumen y de referencias; todo lo demás se quita, se llame como se llame. Dentro
de una secuencia conservada se quita todo valor que pueda llevar texto (PN, LO, LT, SH, ST, UT, UC,
UR, AE, AS, OB, UN), las etiquetas privadas y los grupos 50xx/60xx. Todo UID que no sea del propio
estándar (`1.2.840.10008.`) se sustituye, coherente dentro del fichero, y la cabecera de fichero se
rehace sin su título AE de origen. La lista de prohibidos anterior dejaba pasar otros campos de la
tabla E.1-1, el texto de `ContentSequence`, las superposiciones y UID no listados bajo el mismo sello
(auditoría run-2, `emma:imaging:deid-profile-incomplete`). Lo que entra en la cadena no se borra sin
lápida, así que lo identificativo no debe entrar. **Límite declarado:** el texto quemado en los
píxeles no se quita leyendo cabeceras; se registra lo que declara el equipo.

**Qué se verifica.**

- Al escribir: que el `sha256` y el `size_bytes` del asiento son los del binario. Un asiento que
  firmara el hash de otros bytes sería la auditoría de algo que no se guardó.
- Al servir (`imaging_blob()`, `GET /api/imaging/studies/{i}/dicom` y cada fotograma en
  `GET /api/imaging/studies/{i}/frames/{n}`): se **recalcula** el hash del binario en cada entrega.
  El PNG de un fotograma se genera a partir de ese binario ya comprobado. Entre dos verificaciones periódicas, una imagen cambiada en disco ya se
  habría mostrado o medido.
- En `verify_integrity()` (§3.5): cada estudio vigente tiene exactamente un binario, la columna
  `sha256` coincide con el asiento y el SHA-256 **recalculado** del binario también. Comparar solo la
  columna no detectaría nada, porque se edita igual que el dato. Coste: leer y resumir todos los
  binarios en cada verificación, del orden de un segundo por gigabyte; se leen de uno en uno.

**Redacción y enmienda.** Redactar un estudio borra su binario en el mismo `commit` que la lápida:
el hash sin los bytes no revela nada, los bytes sí. Un estudio **no se enmienda**: la enmienda
sustituye un dato por otro del mismo tipo, y enmendar una imagen con una lectura escalar la
retiraría de la consola sin borrarla ni dejar lápida. Si no debió registrarse, se redacta.

**Medidas sobre un estudio.** Una medida escribe dos asientos en un solo `commit`: la lectura
(`vital-observation`, que entra en el análisis) y su procedencia (`imaging-measurement`: estudio y
su `sha256`, puntos, método, operador declarado), que cita la lectura por índice. El valor solo va
en la lectura, así que redactarla no deja una copia. Solo se mide sobre un estudio vigente cuyo
binario verifica, y del mismo tripulante. Una medida no se enmienda: se vuelve a medir.

**Signos anotados y lista de calidad** (`imaging-findings`, firmado por `crew-console`): para un
estudio vigente y citando su `sha256`, lo que el operador anotó en cada ventana (pulmón, FAST,
hígado) y si la adquisición cumplió cada punto de la lista de calidad del protocolo. El formulario
entra entero o no entra: cada signo lleva un valor, "no valorable" incluido. No es una lectura: no
entra en `observations` ni en el análisis (`tests/test_imaging_findings.py`).

**Borradores de interpretación** (`app/interpret/`). Dos tipos de asiento por la vía general
`append()`: `draft-interpretation`, firmado por `interpretation-local`, con el estado
(`unvalidated` o `blocked`), el modelo, el SHA-256 de los hechos que recibió y —solo si no se
bloqueó— el texto; y `draft-signoff`, firmado por `crew-console`, con la decisión (`accepted` o
`rejected`), quien firma (declarado, sin autenticar), un comentario y **`text_sha256`**: la huella
SHA-256 del texto que se leyó. Un borrador se firma una sola vez, y uno bloqueado no se firma.
Ninguno de los dos es una lectura: no entran en `observations` ni en el análisis. Se redactan como
cualquier asiento.

**La firma cita lo que se leyó** (desde el 2026-09-25; patrón de Polaris `tools/salida.py`, donde
un borrador solo se aprueba con el `nonce` que se entregó con él). La lista de borradores devuelve
`text_sha256`, calculada al leer desde el texto firmado; la petición de firma tiene que traerla, y
`sign_draft` la compara con la del borrador registrado antes de escribir: si no coincide, 409 y no
hay asiento. Así una consola con una vista caducada, o una petición que apunta a otro índice, no
puede firmar un texto distinto del que la persona tuvo delante. La huella queda en el asiento de
firma: la auditoría puede comprobar después qué texto exacto se aceptó
(`tests/test_interpret.py::test_a_clean_draft_is_stored_unvalidated_and_signed_once`).

**Cuenta como registro real** para §3.9: si no contara, cambiar de escenario simulado la borraría
junto con el almacén.

### 3.11 Informes de dolor: la cifra que se analiza, atada a lo que la explica

El tripulante marca en un mapa corporal dónde le duele, cuánto (0-10) y cómo. Añadido el 2026-09-25
(`core/storage.py`, `app/pain/`, `app/api/pain.py`).

**Diseño.** Igual que una medida ecográfica (§3.10): dos asientos en un solo `commit`. La lectura
`vital-observation` de `pain-intensity` (LOINC 72514-3) lleva la **intensidad máxima** del informe y
es lo único que entra en el análisis. El asiento **`pain-report`**, por la vía general `append()`,
lleva el informe y cita la lectura por `observation_index`. Ambos los firma la fuente `pain-report`,
reservada: la ingesta genérica no puede firmar así (`_is_reserved_source`).

| Campo | Contenido |
|---|---|
| `subject`, `effective` | Tripulante e instante del informe, en UTC |
| `reported_by` | Quién informa. **Declarado, sin autenticar**, como el resto de acciones de consola (§7.5) |
| `zones` | Lista de `{zone, intensity, characters}`: zona y tipo de listas cerradas (`app/pain/catalog.py`), intensidad entera de 1 a 10. Vacía = "sin dolor", que registra un 0 |
| `observation_index` | La lectura que lleva la intensidad máxima |
| `_salt` | La pone el ledger, como en todo asiento |

**Qué se impide.**

- Una intensidad **sin su informe**: `record_many` rechaza `pain-intensity`, así que ni `POST
  /api/observations` ni una importación la cuelan. Sin informe, la cifra no dice dónde duele.
- Una lectura que **no sea el máximo** del informe, o de otro tripulante: el almacén no la escribe.
  El análisis vería un dolor distinto del informado.
- **Enmendar** la intensidad: la separaría de las zonas de su informe. Se registra un informe nuevo
  y, si el erróneo no debió existir, se redacta (409, como una medida ecográfica).

**Redacción.** Redactar la lectura retira el informe entero de `pain_reports()`: no queda un dolor
sin cifra ni una cifra sin sitio. La lápida sigue en la auditoría.

**Cuenta como registro real** para §3.9, por la lectura que escribe.

### 3.12 Segunda firma de una decisión de alto riesgo, e informes escaneados (2026-09-25)

**Segunda firma** (`draft-countersign`, firmado por `crew-console`; patrón de Polaris
`tools/decision_alto_riesgo.py`). El asiento `draft-signoff` lleva ahora `high_risk`: el resultado
del disparador (`app/decision_risk.py`) sobre el comentario de quien firma. Si el comentario
registra una decisión clínica de alto riesgo —una acción terapéutica, o una decisión clínica
irreversible—, la firma queda **pendiente de una segunda, de otra persona**. `countersign_draft`
exige, bajo el cerrojo del almacén: que exista la primera firma y que registrara alto riesgo; que
quien firma no sea la misma persona (se compara sin mayúsculas ni espacios de más); que cite la
misma huella del texto (`text_sha256`); y que no haya ya una segunda firma. Si no, 409 y no hay
asiento. `drafts()` devuelve `countersign` y `record` —si hacía falta segunda firma, si está y si
las dos decisiones discrepan—: el acta. Un desacuerdo no se resuelve solo: queda a la vista.

**Regla más estricta desde el 2026-10-13** (decisión del usuario; `app/countersign_rule.py`,
detalle en §3.24). Si la segunda firma cita un informe guardado (`informe:<n>`), a las cuatro
condiciones de arriba se suman dos, también bajo el cerrojo del almacén: que la cita **se localice**
en el informe y que la firma **declare la frase que vio** (`seen_quote`). Si falta una, la ruta
responde **422** con el motivo y **no se escribe ningún asiento**. Los 409 de arriba, y el de una
bóveda que ya no da lo que se declaró haber visto, se conservan. Una segunda firma que cita otra
cosa, o nada, **no se puede cotejar** y no se rechazaba por ello. Las contrafirmas anteriores al
cambio no se tocan ni se invalidan.

**Cita obligatoria desde el 2026-10-15** (decisión del usuario; detalle en §3.24). Toda segunda
firma —que solo existe para una decisión de alto riesgo— tiene que citar un informe guardado,
con las dos condiciones de arriba: otra fuente, o ninguna, se rechaza también con **422** y sin
asiento, después de los 409. La primera firma no cambia. Las contrafirmas ya escritas sin
informe siguen verificando y se rotulan al leer.

**Informes escaneados** (`scanned-report`, firmado por `crew-console`; OCR de Polaris
`tools/ocr_informes.py`). Mismo diseño que un estudio de imagen (§3.10): el original, fuera del
asiento, en la tabla de binarios; el asiento lleva su SHA-256 y su tamaño, que se comprueban antes
de escribir, y los dos van en un solo `commit`. El asiento lleva además el tipo de documento (lista
cerrada), el formato, las páginas, quién lo registró y el texto del OCR por página con su confianza
y la marca de "poco fiable" por debajo de 60/100. El texto que se firma es el **des-identificado**
(`reports/deid.py`), con cuántos datos se enmascararon y si la revalidación pasó; si no pasó, el
texto va vacío (retenido) y se anota qué tipo de dato quedaba, nunca el dato. Los tipos de asiento con binario se declaran
juntos (`BLOB_ENTRY_TYPES`), y todo lo que valía para la imagen vale para el informe:
- `report_blob()` recalcula el hash del original en cada entrega; si no casa, 409.
- `_compare_blobs()` coteja todos los binarios de la cadena en cada verificación.
- Redactar el asiento borra el original; la lápida queda.
- No es una lectura: no entra en `observations`, ni en el análisis, ni en los hechos del borrador
  del modelo (es texto libre de un tercero: vía de inyección).
- **Cuenta como registro real** para §3.9: un cambio de escenario simulado no lo puede tirar.

Pruebas: `tests/test_decision_risk.py`, `tests/test_reports.py`; de las reglas del 2026-10-13 y
del 2026-10-15, `tests/test_countersign_strict.py`.

### 3.13 Volúmenes y su segmentación (2026-09-26)

**Estudio volumétrico** (`volume-study`, firmado por `crew-console`, o por `simulator` si es un
TAC de ejemplo de un dataset). El NIfTI entero es el binario, fuera del asiento; el asiento lleva
su SHA-256, tamaño, dimensiones, espaciado, modalidad y quién lo registró. Cuenta como registro
real para §3.9.

Desde el 2026-10-07 el asiento puede llevar un campo más, `cleaned`, y solo cuando el operador
pidió limpiar la cabecera al subirlo (`POST /api/volumes?clean=true`, `app/volumes/privacy.py`):
`fields` (nombres de los campos vaciados, nunca su contenido), `received_sha256` y
`received_size_bytes` (el fichero recibido, que no se conserva) y `note`. En ese caso el binario
firmado, y el `sha256` y `size_bytes` del asiento, son los del volumen limpio: la regla de que el
asiento describe el binario guardado no cambia. El campo es opcional y va dentro del contenido
firmado como cualquier otro: los asientos escritos antes, sin él, se verifican igual; uno que lo
lleva verifica (`tests/test_volumes.py`), y quitarlo o cambiarlo rompe su hash como con cualquier
otro campo del contenido.

**Segmentación** (`volume-segmentation`, firmado por `segmentation-local`, fuente reservada). Es
un asiento derivado: cita el estudio por índice y por `study_sha256`, y el almacén comprueba que
es el binario vigente antes de escribir. Su binario es un zip con lo que abre el visor (volumen
recortado a 2 mm, etiquetas, mallas PLY y `estudio.json`); el asiento lleva el resumen —estructuras
con su volumen, lesiones candidatas, ventana, `estado: segmentación automática sin validar`— y la
lista de ficheros. Sin SeriesInstanceUID: en Polaris, el resumen lo llevaba y llegaba a la web.

Los dos tipos están en `BLOB_ENTRY_TYPES`: cada fichero servido sale del binario recién comprobado,
`_compare_blobs()` los coteja en cada verificación y redactar el asiento borra el binario. Nada de
esto es una lectura (`tests/test_volumes.py`). Desde el 2026-10-15, redactar el estudio redacta
también sus segmentaciones, porque el binario de cada una lleva un volumen recortado de él
(§3.13 bis, «Redactar el estudio redacta sus segmentaciones»).

### 3.13 bis Fase de contraste declarada de un TAC (2026-10-13)

Tipo nuevo `volume-contrast-phase`, firmado por `crew-console` con el patrón de §3.8 (una acción
humana que se registra; `_actions` rechaza un asiento mal formado) y el modelo de §3.17 quater.
La densidad (HU) de una lesión candidata cambia con la fase de contraste del estudio, y un NIfTI
no la lleva: hasta aquí no había forma de decirla (decisión del usuario, 2026-10-13). **Es una
etiqueta declarada, no una medida**: no lleva código LOINC ni uno propio (invariante 1), no es
una observación del catálogo y **EMMA no la propone ni la comprueba con la imagen** (la `fase()`
de Polaris sigue sin llamarse: `docs/polaris-divergencias.md` §7.5). El asiento del estudio
(`volume-study`) **no se toca**: este es otro asiento que lo cita.

| Tipo | Campos | Regla (rechazo sin escribir nada) |
|---|---|---|
| `volume-contrast-phase` | `subject` (el del estudio, copiado de su asiento), `study_index` (entero: índice del asiento `volume-study`), `study_sha256` (la huella del volumen firmada en ese asiento), `phase` (código del vocabulario), `at` (cuándo se declara, con zona horaria), `note` (puede ir vacía), `declared_by` | 422: `phase` fuera del vocabulario o `undeclared`; `at` sin zona horaria; `declared_by` sin nombre; cualquier campo de más; estudio que no es un TAC (`modality` ≠ `CT`). 404: `study_index` sin un `volume-study` vigente (no existe, es otro tipo de asiento o está redactado) |

- **Una sola vía.** `POST /api/volumes/{estudio}/contrast-phase` → `record_contrast_phase` →
  `_record_action`: un asiento encadenado y firmado en un solo `commit` (invariante 4). El almacén
  lee el estudio con `_signed_entry` bajo cerrojo —vigente y con el contenido que firma su hash— y
  copia de él `subject` y `study_sha256`; las reglas de la tabla las impone también él si se le
  llama desde otro sitio (`volumes/contrast_phase.check`, `check_modality`).
- **Vocabulario cerrado** (`app/volumes/contrast_phase.py`, diseño de EMMA, sin fuente leída):
  `non-contrast` («sin contraste»), `arterial` («arterial»), `portal-venous` («portal (venosa
  portal)»), `delayed` («tardía») y `unknown` («no se sabe»). Sin subfases. **«No se sabe» se
  firma** —una persona miró y no lo sabe— y **«sin declarar» no**: es que nadie ha dicho nada, no
  hay asiento que lo diga y se enseña como dato ausente.
- **Qué vale.** La fase vigente de un estudio es la de su último asiento firmado por la consola
  que cite su índice **y** su huella y que la ruta habría firmado (`contrast_phase.history`). Los
  anteriores se conservan y se entregan como historial. **No hay borrado ni edición**: se corrige
  declarando de nuevo. `at` es lo que dice quien declara; no decide cuál manda.
- **Al leer.** `GET /api/volumes` da en cada estudio `contrast_phase` (si aplica, la vigente con
  su código, su texto, quién y cuándo, y el historial) y, en la densidad de cada segmentación,
  `fase_contraste` con esa misma declaración en lugar de la nota «el estudio no declara la fase».
  **Se pone al servir**: la densidad firmada al segmentar (§3.13) lleva `fase_contraste` vacía y
  no se reescribe, porque la declaración puede llegar después. `GET /api/volumes/compare` añade
  `fase_contraste` con las dos fases y uno de cuatro estados —`same`, `different`, `missing` (falta
  alguna o consta «no se sabe») y `not-applicable`— con su texto. `GET /api/volumes/contrast-phases`
  da el vocabulario.
- **Para qué sirve, y para qué no.** Solo acompaña a la densidad, que es descriptiva. **No
  clasifica** ninguna lesión ni convierte una densidad en un «realce»; **no bloquea la comparación,
  no añade una columna de cambio de densidad y no toca el estado de la evolución**, que sale solo
  del diámetro (Polaris `evolucion`). No entra en `observations`, en el análisis ni en una alerta,
  no mueve niveles ni umbrales (invariante 5) y no forma parte de `rules_version`. No cuenta como
  registro real a efectos de §3.9, como las demás acciones de la consola. El nombre de quien
  declara va firmado en el asiento y no se escribe en ningún log.
- **En la crónica** (2026-10-14). Cada declaración que cuenta (`contrast_phase.history`: de un
  estudio vigente, firmada por la consola, con su huella) sale en la crónica **del tripulante del
  estudio** como hecho firmado `contrast-phase-declared`, tipo `imagen`, clave `ledger:<asiento>`,
  en el instante `at` que declara y con `quien` = `declared_by`, como las demás declaraciones. La
  frase (`contrast_phase.sentence`) dice solo el asiento del estudio, la fase, la que constaba
  antes y el rótulo «declarada por una persona; EMMA no la propone ni la comprueba». **No lleva la
  nota** —texto libre sobre el estudio, que puede llevar datos personales— **ni nada del
  volumen**: la crónica se escribe en más sitios que la respuesta a quien la pide. Tierra (`until`)
  solo ve lo firmado antes de su corte, como en el resto de la crónica.
- **Redactar el estudio redacta sus declaraciones** (2026-10-14). `ObservationStore.redact` sobre
  un `volume-study` redacta también, **en el mismo `commit`**, cada `volume-contrast-phase` con
  contenido que cite su índice (por el índice, sin mirar huella ni firmante: lo que se protege es
  el nombre de quien habló de ese estudio), **cada una con su propia lápida** (§3.6) firmada por
  la autoridad, con el mismo solicitante y el motivo «redactado con el estudio del asiento N:
  <motivo>». Si una falla, no se escribe ninguna. `Redaction.dependents` las lleva y
  `POST /api/audit/redact/{i}` las devuelve en `dependent_redactions` (índice redactado y de su
  lápida). Redactar una declaración sola sigue siendo posible y no toca el estudio. **No cambia el
  formato de ningún asiento ni lo que `verify()` exige**: una cadena escrita antes, con la fase de
  un estudio ya redactado aún firmada, sigue verificando con sus hashes; esa declaración no se
  enseña en ninguna vista (todas parten de los estudios vigentes) y se redacta por su índice.
- **Redactar el estudio redacta sus segmentaciones** (2026-10-15, decisión del usuario). Hasta
  aquí este apartado declaraba lo contrario como límite: la segmentación (§3.13) se quedaba,
  firmada y servible por su índice, y su binario lleva un volumen recortado del estudio —sus
  píxeles—. Ahora `ObservationStore.redact` sobre un `volume-study` redacta también cada
  `volume-segmentation` con contenido que cite su índice, con la misma regla que las fases (por
  el índice, sin mirar `study_sha256` ni firmante), **en el mismo `commit`, cada una con su
  lápida**, el mismo solicitante y el motivo «redactado con el estudio del asiento N: <motivo>»,
  y **su binario se borra** de `imaging_blobs` como el del estudio (`secure_delete`, §3.6). Si
  una falla —también la última, con la segmentación ya redactada dentro de la transacción—, no
  se escribe ninguna y los binarios siguen. Fases y segmentaciones van juntas en `dependents` y
  en `dependent_redactions`, **en el orden de la cadena**. Redactar una segmentación sola sigue
  siendo posible y no toca el estudio. Ningún otro tipo de asiento que cite el índice del
  estudio se arrastra. **Tampoco cambia el formato de ningún asiento ni lo que `verify()`
  exige**: una cadena escrita antes, con la segmentación de un estudio ya redactado aún firmada
  y con su binario, sigue verificando con sus hashes; esa segmentación no se enseña en ninguna
  vista (todas parten de los estudios vigentes) y se redacta por su índice.
- **Límite declarado.** Las rutas de lectura de volúmenes no aplican el corte de Tierra
  (`until`), tampoco a esto.

Pruebas: `tests/test_contrast_phase.py` (el vocabulario cerrado, lo vigente y su historial, lo que
no cuenta, el asiento firmado y el del estudio intacto, los 422 y el 404, un asiento mal formado,
**un ledger escrito por el código anterior** —`tests/data/volumes_pre_contrast_phase.db`— que se
sigue verificando con sus hashes y admite una declaración, la densidad con las mismas cifras, **el
mismo estado de la evolución con y sin fases declaradas** y `/api/status` y `/api/anatomy/state`
idénticos con y sin declaración; la crónica, con su rótulo, sin la nota, del tripulante del
estudio, con el corte de Tierra y solo lo que la consola enseñaría; redactar el TAC redacta sus
declaraciones con una lápida cada una, todo o nada, y **un ledger escrito antes de esa regla**
—`tests/data/volumes_pre_phase_redaction.db`, con la fase de un TAC ya redactado— que sigue
verificando con sus hashes; la prueba que fijaba que la segmentación se quedaba se cambió a
propósito el 2026-10-15 y ahora la arrastra, y otro tipo de asiento que cite el estudio se
queda) y `tests/test_volume_redaction.py` (redactar el TAC redacta sus segmentaciones, una lápida
cada una y el binario borrado; lo de otro estudio no se toca; todo o nada, falle la segmentación
o la fase de después; una segmentación se redacta sola sin tocar el estudio; y **un ledger
escrito antes de esa regla** —`tests/data/volumes_pre_segmentation_redaction.db`, con un TAC, su
segmentación y su fase, y otro TAC ya redactado con su segmentación aún firmada— que sigue
verificando con sus hashes, ahora redacta en cascada y, reabierto, no guarda ningún binario ni,
en el fichero, las huellas, el nombre de quien declaró la fase ni los bytes de los volúmenes). Campañas:
`tests/mutants/contrast_phase*.json` y `tests/mutants/volume_redaction.json`.

---

### 3.14 Campos del asiento `vital-observation` (2026-09-26)

Hasta ahora el payload solo se describía en prosa; la definición es `_to_payload` en
`core/storage.py`. Con la especificación del equipo (`docs/contexto/`, §2 y §5) gana tres campos:

| Campo | Contenido | Asientos anteriores |
|---|---|---|
| `subject`, `key`, `value`, `effective`, `source` | Sujeto, indicador del catálogo, valor en la unidad del catálogo, instante con zona, fuente | — |
| `context`, `confidence` | Estado fisiológico (sueño, reposo…) y confianza 0-1 | `unknown`, `1.0` |
| `observation_type` | `measured`, `inferred` o `predicted` | `measured` (todo lo registrado antes era medida) |
| `evidence_context` | `iss`, `spaceflight`, `analog_bedrest`, `analog_isolation`, `ground` o `simulated` | se deduce de `source` (`evidence_context_for`) |
| `model_version` | Modelo que produjo el valor; **obligatorio** si no es `measured` | ausente |
| `device` | Identificador del dispositivo que envió la lectura, **solo si quien envía lo puso** (§3.14 bis) | ausente |
| `recorded_by` | Nombre declarado de quien tecleó el valor en la consola, **solo si lo anotó una persona** (§3.14 ter) | ausente |
| `food` | Alimento, **solo en la aceptabilidad de la comida y en la fracción rechazada, y solo si lo lleva** (§3.14 quinquies) | ausente |
| `_salt` | Sal del hash (§3.1) | — |

Los campos nuevos viven en el payload firmado, que es el registro; el espejo SQL `observations` no
los copia porque es el índice que usa `query()` y añadir columnas obligaría a migrar las bases en
disco. Un valor inferido o predicho sin `model_version` se rechaza al construirlo y la API responde
422. Pruebas: `tests/test_observation_provenance.py`.

La unidad no es un campo del asiento: la cifra está siempre en la unidad del catálogo, y una
unidad declarada distinta se rechaza antes de firmar (§3.14 quater).

### 3.14 bis El dispositivo que envió la lectura (2026-10-13)

Decisión del usuario (2026-10-13): el identificador del dispositivo se guarda en cada lectura
firmada, como campo **opcional**, para que el aviso de «sensor vinculado a otro tripulante»
(§3.17 ter) se pueda reconstruir después de la ingesta y se vea en el estado y en la consola.

- **Qué se firma.** `VitalObservation.device`: el identificador que puso quien envía, normalizado
  con la misma función que el de una declaración de vínculo (`ingest/bindings.device_key`). Las
  tres rutas de ingesta de wearables lo recibían ya; ahora lo ponen en cada lectura del lote
  justo antes de firmar (`ingest/fhir.from_device`). EMMA sigue sin leerlo de la trama ni del
  export. Un identificador vacío o que no es texto no se puede construir (`ValueError`).
- **Por qué no invalida lo firmado.** La clave `device` se escribe en el payload **solo cuando
  existe**. Una lectura sin dispositivo produce exactamente las mismas claves, en el mismo orden,
  y los mismos bytes canónicos que antes de existir el campo, así que su `content_hash` es el
  mismo; y al leer, un asiento sin la clave es una lectura sin dispositivo (`_from_payload`). No
  hay migración ni versión de formato: el campo es aditivo, como lo fue `model_version`.
- **Con qué se comprueba.** `backend/tests/data/readings_pre_device.db` es un ledger de tres
  lecturas escrito con el código anterior al campo (commit `7c44dc3`, exportado con
  `git archive` a una carpeta aparte para que no pudiera firmarlo el código nuevo), y
  `readings_pre_device.fhir.json` es el FHIR que aquel código serializaba de ellas. La prueba abre
  ese ledger con el código de ahora: verifica, los `content_hash` son los firmados entonces,
  `_to_payload` reproduce sus bytes canónicos bajo la misma sal, el FHIR sale carácter a carácter
  igual, y una lectura nueva (con y sin dispositivo) se encadena detrás y la cadena sigue
  verificando al reabrir.
- **En FHIR.** `Observation.device` es una `Reference(Device)` y EMMA no tiene recursos `Device`.
  Una referencia FHIR admite un identificador lógico (`Reference.identifier`) cuando no hay un
  recurso al que apuntar: el identificador va en `device.identifier.value`, junto al `display` de
  la fuente que ya había. **Sin `system`**: EMMA no sabe qué clase de identificador puso quien
  envía (una dirección MAC, una etiqueta), y declarar un sistema sería inventarlo. No se usa una
  extensión propia porque el estándar ya tiene el sitio. Sin dispositivo, `device` queda como
  estaba (`{"display": <fuente>}`).
- **El espejo SQL no lo copia.** Como los demás campos de §3.14: `query()` lee el payload
  firmado, y `observations` es solo el índice.
- **Privacidad.** Puede ser un dato personal. Consta en el asiento firmado y en el FHIR que
  entrega `GET /api/observations` a quien pide las lecturas; **no se escribe en el log**
  (`tests/test_logs_privacy.py` y la prueba de esta pieza); `/api/audit` no enseña payloads; y el
  estado lo enseña **abreviado** (§3.17 ter).
- **No entra en el análisis.** Ningún módulo que decide (`analysis/risk.py`, `baseline.py`,
  `trend.py`) lee `device`, y una prueba lo comprueba con `ast`. Niveles, alertas,
  recomendaciones, lecturas aceptadas y `rules_version` son idénticos con y sin dispositivo en
  las lecturas (invariante 5).
- **Límite declarado.** Una enmienda (§3.7) la escribe una persona y su versión corregida no
  lleva dispositivo: la lectura enmendada deja de contar para el aviso. La original, con su
  identificador, sigue firmada en la cadena.

Pruebas: `tests/test_device_in_reading.py`. Campañas: `tests/mutants/device_in_reading*.json`.

### 3.14 ter Quién anota: fuente propia y operador en el registro diario y en la PVT de consola (2026-10-13)

Decisión del usuario (2026-10-13): lo que una persona teclea en la consola —el registro diario y
la prueba PVT hecha en pantalla— se firma con una **fuente propia** en vez de «alta manual», y
queda escrito **quién teclea** (el operador de la consola), no solo de qué tripulante es el dato.

- **Dos fuentes nuevas, con su clave de firma.** `crew-diary` («registro diario») y `console-pvt`
  («test PVT en la consola»). Son fuentes de datos como `manual` o `pvt-test`
  (`identity_for(<fuente>)`, §3.2): **no** son la identidad `crew-console`, que firma decisiones del
  operador y sigue sin poder firmar una lectura.
- **La fuente la pone el backend, no el cliente.** Cada una tiene su ruta de escritura
  —`POST /api/diary/entries` (`api/diary.py`) y `POST /api/pvt/console` (`api/pvt_console.py`)—,
  que fija la fuente, pone la hora de recepción y rechaza con 422 cualquier campo de más (una
  fuente, una hora o un tipo enviados por el cliente no se ignoran: se rechazan). La ingesta
  genérica (`POST /api/observations`) las rechaza como **reservadas** (`_is_reserved_source`), igual
  que `pain-report` o `ultrasound`: si las aceptara, una lectura podría llevar la fuente del diario
  sin decir quién la anotó. Así, toda lectura con una de estas fuentes pasó por su ruta. Se eligió
  ruta propia y no «aceptar `crew-diary` de cualquiera» por eso: la garantía la impone el código, no
  el buen comportamiento del cliente. La ruta del diario solo admite los indicadores del diario.
- **Siguen siendo observaciones normales** (invariante 4): se construyen con el modelo canónico
  (`ingest/fhir.observation`, que rechaza lo que no es una medida) y se anexan con `store.record` /
  `store.record_many` como asientos `vital-observation`. No hay tipo de asiento nuevo. La PVT de
  consola usa la misma puntuación (`ingest/pvt.score`) y la misma conversión que `POST /api/pvt`.
- **Qué se firma de más.** `VitalObservation.recorded_by`: el nombre que declara quien teclea,
  recortado, de 1 a 64 caracteres y con al menos una letra o una cifra (la misma regla que
  `acknowledged_by` en §3.8). Las dos rutas lo **exigen** (422 si falta o está vacío); el resto de
  la ingesta no lo lleva, y `POST /api/observations` rechaza el campo. Como en §3.8, la API **no
  autentica**: es lo declarado, firmado por la fuente, y no demuestra identidad. Es distinto de
  `subject`: uno dice de quién es el dato y el otro quién lo escribió.
- **Por qué no invalida lo firmado.** Igual que `device` (§3.14 bis): la clave `recorded_by` se
  escribe en el payload **solo cuando existe**, detrás de las demás. Una lectura que no anotó una
  persona produce las mismas claves, en el mismo orden, y los mismos bytes canónicos que antes.
- **Con qué se comprueba.** `backend/tests/data/diary_pvt_pre_recorded_by.db` es un ledger con dos
  anotaciones del diario firmadas como `manual` y una PVT firmada como `pvt-test`, escrito con el
  código anterior al cambio (commit `82ea87d`, exportado con `git archive` a una carpeta aparte), y
  `diary_pvt_pre_recorded_by.fhir.json` es el FHIR que aquel código serializaba. La prueba lo abre
  con el código de ahora: verifica, los `content_hash` son los de entonces, `_to_payload` reproduce
  sus bytes bajo la misma sal, el FHIR sale carácter a carácter igual, y lo nuevo se encadena
  detrás.
- **Lo ya firmado se sigue enseñando.** `GET /api/diary/entries` cuenta lo firmado como
  `crew-diary` y lo firmado como `manual`; `GET /api/pvt/sessions`, lo firmado como `console-pvt` y
  como `pvt-test`. Cada entrada dice con qué fuente entró (`source`, `source_display`) y quién la
  anotó (`recorded_by`); una sin anotador dice **«no consta»** (`recorded_by_display`) y no se
  rellena con nadie. Dos pruebas del mismo instante con fuentes distintas son dos pruebas.
- **En FHIR.** `Observation.performer` («quién responde de la observación»), como
  `[{"display": <nombre>}]`. Una referencia FHIR admite llevar solo `display` cuando no hay un
  recurso al que apuntar: EMMA no tiene recursos `Practitioner` ni un sistema de identificadores de
  operadores, así que no lleva ni `reference` ni `identifier` (ponerlos sería inventarlos). No se
  usa una extensión propia porque el estándar ya tiene el sitio. **Límite declarado:** «quién
  tecleó» en sentido estricto es, en FHIR, un agente `enterer` de un recurso `Provenance`; EMMA no
  emite recursos `Provenance`, y `performer` es el sitio que el recurso `Observation` tiene para
  una persona. Sin anotador, la clave `performer` no existe y el recurso es el de antes.
- **Privacidad.** Es un dato personal. Consta en el asiento firmado, en las dos listas de arriba y
  en el FHIR de `GET /api/observations`; va en el cuerpo de la petición, nunca en la URL, y **no se
  escribe en el log** (`tests/test_logs_privacy.py` y la prueba de esta pieza, también por los
  caminos de rechazo). `/api/audit` no enseña payloads.
- **No entra en el análisis.** Ningún módulo de `analysis/` ni de `advisor/` lee `recorded_by` ni
  nombra estas fuentes, salvo la tabla de rótulos de `analysis/data_quality.py`, que solo las
  nombra para pintarlas; una prueba lo comprueba con `ast`. El mismo escenario con los mismos
  valores a las mismas horas da el mismo estado completo con `manual`/`pvt-test` que con
  `crew-diary`/`console-pvt`, salvo el nombre de la fuente (invariante 5).
- **Límite declarado.** Una enmienda (§3.7) entra por la ingesta genérica: la versión corregida de
  una anotación del diario la firma una fuente no reservada (p. ej. `manual`) y no lleva anotador.
  La original, con su fuente y su operador, sigue firmada en la cadena.

- **Una tercera fuente con la misma regla (2026-11-03): `console-cognition`** («batería Cognition
  en la consola»). Las puntuaciones de una sesión de la batería Cognition de NASA que da su
  programa (EMMA no pasa ni puntúa las pruebas) entran por `POST /api/cognition/console`
  (`api/cognition.py`), que fija la fuente y la hora de recepción, exige `recorded_by`, rechaza con
  422 cualquier campo de más, y solo admite las claves de `codes.COGNITION_CODES`, cada prueba con
  todas sus puntuaciones y cada cifra en su rango físico (`ingest/cognition.py`): o entra la sesión
  entera o no entra nada. Las observaciones se construyen con `ingest/fhir.observation` y se anexan
  con `store.record_many` bajo `identity_for("console-cognition")`; la ingesta genérica la rechaza
  como reservada. Son indicadores descriptivos (`codes.DESCRIPTIVE_ONLY`): ni el estado ni la
  huella de reglas los leen. `GET /api/cognition/sessions` enseña lo firmado con esta fuente y lo
  que llegó por la ingesta genérica, cada sesión con su fuente y su anotador o «no consta».

Pruebas: `tests/test_recorded_by.py`, y `tests/test_diary.py` y `tests/test_pvt_console.py` para lo
que ya había; `tests/test_cognition.py` para `console-cognition`. Campañas:
`tests/mutants/recorded_by*.json`, `diary.json`, `pvt_console.json`, `cognition.json`.

### 3.14 quater La unidad del alta manual, y el contrato de §5 en FHIR R4 (2026-10-23)

Decisión del plan aprobado de la decimosexta ronda: `POST /api/observations` gana un campo `unit`
(código UCUM) **opcional**. La especificación del equipo pide en §5 «un esquema canónico de
observación con unidades y procedencia explícitas», y la invariante 2 dice que la unidad sigue a la
propiedad LOINC. Hasta ahora la vía FHIR rechazaba una unidad distinta de la del catálogo, pero el
alta manual no tenía dónde decirla: una vitamina D en nmol/L entraba como si fuera ng/mL.

- **Si viene y no es la del catálogo**, 422 con el motivo en español, **antes** de construir la
  observación: no hay asiento en el ledger y **no se convierte**. La comparación es
  `ingest.fhir.require_catalog_unit`, la misma que usa `VitalObservation.from_fhir`; es literal
  sobre el código UCUM y distingue mayúsculas («ml» no es «mL», aunque UCUM acepte las dos grafías
  del litro: UCUM 2.2 §31, ficha `ucum-2-2`). La unidad recibida se repite recortada a 40
  caracteres en el error, con «…» si se cortó. Desde el 2026-10-26 la confirmación de una
  analítica escaneada (§3.21, `reports/labs.confirmed_value`) usa esa misma comparación: su motivo
  empieza por el de la ingesta y añade lo que puede hacer quien lee el papel (convertir el valor y
  declarar la unidad del catálogo). Ya no hay una segunda comparación.
- **Vacía o de más de 64 caracteres**, también 422 y sin asiento, con el motivo en español. Antes la
  rechazaba el esquema con la lista de errores de Pydantic. La vacía la rechaza ahora la comparación
  compartida, con el mismo motivo por todas las vías (también FHIR): no es una unidad ausente, y si
  no se conoce no se declara. El tope de 64 es de la API (`api.routes._unit_or_422`): pasado, la
  unidad ni se compara ni se repite.
- **Si falta**, se asume la del catálogo y la respuesta lo dice: `unit` (la del catálogo) y
  `unit_assumed: true`. Con la unidad declarada y correcta, `unit_assumed: false`.
- **La enmienda (§3.7)** lleva el mismo campo en su `correction` y la misma regla. Además firma
  ahora lo que la corrección declara de su procedencia (`observation_type`, `model_version`,
  `evidence_context`): antes los aceptaba y los perdía, y una corrección inferida se firmaba como
  medida y sin modelo. Sin entorno declarado vale el del despliegue (`EMMA_DEPLOYMENT_CONTEXT`),
  como en el alta: antes se deducía de la fuente, y corregir una errata en un despliegue `iss`
  pasaba la lectura a `ground`.
- **Lo firmado no cambia.** El asiento `vital-observation` (§3.14) no lleva la unidad: guarda la
  cifra, que solo puede estar en la unidad del catálogo, y la clave del indicador. Una lectura con
  unidad declarada produce los mismos bytes canónicos que la misma lectura sin ella.
- **La lectura de cabina manual** (`POST /api/habitat`, §3.16) lleva desde el 2026-10-26 el mismo
  campo opcional y la misma regla, contra la unidad del parámetro de `environment/habitat.py`: si
  no coincide, 422 sin asiento y sin conversión; si falta, se asume y la respuesta lo dice (`unit`,
  `unit_assumed`). El asiento `habitat-reading` ya llevaba la unidad del catálogo y la sigue
  llevando: una lectura con unidad declarada firma los mismos bytes que sin ella.
- **La categoría FHIR** (`category` del recurso `Observation`) de los analitos de una analítica
  (`LAB_REPORT_ONLY`) y del NTx es desde el 2026-10-26 `laboratory`, sea cual sea su dominio: antes
  tomaban la del dominio (el calcio del óseo, «activity»; el sodio del genitourinario, «imaging»; la
  hemoglobina, «vital-signs»). La categoría solo vive en el recurso que se sirve: no está en el
  asiento ni en la huella de las reglas (`rules_version` no cambia) y ningún asiento cambia.
- **El adaptador del contrato de §5** (`POST /api/import/observations`, desde el 2026-10-31; abajo)
  recibe la unidad con el nombre de §5 (`unit`) y le aplica, lectura a lectura, esta misma regla
  por la misma función que el alta manual (`_observation_or_422`): distinta, 422 sin asiento y
  sin conversión **para el lote entero**; ausente o nula, se asume la del catálogo y la respuesta
  lo cuenta por indicador (`units`: `declared`, `assumed`).

Con este campo, cada campo del JSON de §5 de la especificación tiene sitio en el recurso FHIR R4
`Observation` que sirve EMMA, y desde el 2026-10-31 también un nombre en la ingesta: la última
columna es la correspondencia que aplica el adaptador de §5. La tabla la compara con el código
`tests/test_observation_unit.py`: lee el JSON de §5 en `docs/contexto/especificacion-tecnica-v1.1.md`,
resuelve cada ruta de la segunda columna en el `to_fhir()` de una lectura y comprueba que da el
atributo de la tercera, que el campo de la cuarta está (o, con «—», no está) en el asiento firmado, y
que la quinta es, campo a campo, `api/spec5.FIELDS` —la fuente única de la correspondencia; la tabla
la copia— y nombra un campo de `ObservationIn`.

| Campo de §5 | Elemento FHIR R4 `Observation` | Atributo de `VitalObservation` | Campo del asiento firmado | Campo de la ingesta (`ObservationIn`) |
|---|---|---|---|---|
| `timestamp` | `effectiveDateTime` | `effective` | `effective` | `effective` |
| `subject_id` | `subject.reference` | `subject` | `subject` | `subject` |
| `variable_id` | `code.coding[0].code` | `code.code` | `key` | `key` |
| `value` | `valueQuantity.value` | `value` | `value` | `value` |
| `unit` | `valueQuantity.code` | `code.unit` | — | `unit` |
| `source` | `device.display` | `source` | `source` | `source` |
| `quality` | `extension('https://emma.mission/fhir/confidence').valueDecimal` | `confidence` | `confidence` | `confidence` |
| `evidence_context` | `extension('https://emma.mission/fhir/evidence-context').valueCode` | `evidence_context` | `evidence_context` | `evidence_context` |
| `observation_type` | `extension('https://emma.mission/fhir/observation-type').valueCode` | `observation_type` | `observation_type` | `observation_type` |
| `model_version` | `extension('https://emma.mission/fhir/model-version').valueString` | `model_version` | `model_version` | `model_version` |

Lecturas de la tabla:

- `subject.reference` lleva el prefijo `Patient/` delante del sujeto. `variable_id` es en EMMA la
  clave del catálogo (`key`, la que se firma), y FHIR lleva el código que le corresponde (LOINC o
  `https://emma.mission/codes`, con su `system` en `code.coding[0].system`).
- `unit` sale del catálogo (`code.unit`), también en `valueQuantity.unit`, con
  `valueQuantity.system` = `http://unitsofmeasure.org`. No se firma, por lo dicho arriba.
- La `quality` de §5 es en EMMA la confianza 0-1 de cada lectura. No es el informe de calidad de
  datos de `analysis/data_quality.py`, que describe series, no lecturas.
- Las extensiones son propias de EMMA (FHIR las admite con URL propia); no son de un perfil
  publicado.
- EMMA firma además campos que §5 no pide: `context` (estado fisiológico, extensión
  `https://emma.mission/fhir/context`), `device` (§3.14 bis), `recorded_by` (§3.14 ter) y, desde
  el 2026-10-26, `food` (§3.14 quinquies, en `Observation.focus`). No van en la tabla: la prueba
  exige en ella exactamente los campos de §5. Por el adaptador de §5 tampoco entran: son campos
  desconocidos para él (422).

**El adaptador del contrato de §5** (`POST /api/import/observations`, `api/spec5.py`, 2026-10-31,
decimonovena ronda, U10). La especificación pide en §13 adaptadores de «archivos/demo» y EMMA no
tenía ninguno que leyera un JSON con los nombres literales de §5: la correspondencia de arriba
estaba solo escrita. Es una vía de ingesta más, junto al alta manual (`POST /api/observations`), la
PVT (`/api/pvt`), la trama BLE (`/api/wearable/ble`), Apple Health (`/api/import/apple-health`) y
Google Fit (`/api/import/google-fit`), y entra por el ledger como todas:

- **Forma.** El cuerpo es una lista JSON de lecturas con los nombres de §5, tal cual (el fichero con
  `--data-binary`), como las otras dos importaciones reciben su fichero; no es `multipart`. Mismos
  topes (`MAX_IMPORT_BYTES`, `MAX_IMPORT_RECORDS` → 413, `MAX_CONCURRENT_IMPORTS`). Muestra con tres
  lecturas de una fuente en `app/data/samples/spec5_observations.json` (una constante con unidad,
  una sin ella, una analítica con unidad; `model_version: null` literal). Como no la lee nadie antes
  de firmar, rechaza con 422 lo que el alta manual no: un texto en blanco en sujeto, indicador, fuente
  o versión de modelo, una fuente de más de 128 caracteres y un instante pasado `MAX_CLOCK_SKEW`,
  como las otras dos importaciones. Pide la cabecera de consola (`console_post`).
- **Traducción.** Cada lectura pasa por `spec5.translate` (la tabla, y nada más) y por el esquema del
  alta manual (`ObservationIn`); el alias `ISS` → `iss` es el único (§5 lo escribe en mayúsculas;
  nada más se normaliza). Un opcional nulo es un opcional ausente. Son **obligatorios** `timestamp`,
  `subject_id`, `variable_id`, `value` y `source`: el alta manual supone «ahora», `crew-01` y
  `manual` cuando faltan, lo que tiene sentido delante de la consola y no en un fichero importado
  después. `quality` ausente es confianza plena, `evidence_context` ausente es el del despliegue y
  `observation_type` ausente es `measured`, como en el alta. `context` (estado fisiológico) no está
  en §5 y queda `unknown`. Por la misma razón, un `timestamp` **sin zona** es un 422, no UTC
  supuesto como en el alta: en un fichero serían horas de error firmadas.
- **Mismo camino.** Catálogo (`_catalog_or_422`), unidad y modelo canónico (`_observation_or_422`)
  son las funciones del alta manual, no una copia: una lectura importada firma los mismos bytes
  y con la misma identidad (la de su `source`) que la misma lectura por `POST /api/observations`
  (`test_the_same_reading_signs_the_same_bytes_as_the_manual_route`). El lote se firma con
  `record_many` (§3.4): **entero o nada**, también cuando quien rechaza es el ledger al firmar
  (una intensidad de dolor sin informe en medio del lote deja el ledger como estaba). Como esa
  transacción lleva una identidad, **un lote es una fuente**: dos `source` distintas son un 422 que
  las nombra, antes de firmar nada.
- **Rechazos**, todos 422 antes de cualquier asiento y con la lectura («lectura 2 de 3»), el campo con
  el nombre de §5 y el motivo en español: campo que §5 no tiene (también los de EMMA: `key`,
  `context`, `device`…), obligatorio ausente o nulo, `variable_id` fuera del catálogo, unidad distinta
  de la del catálogo (la comparación compartida, sin conversión), valor no medido sin
  `model_version`, `source` reservada, instante sin zona, que no tenga forma ISO-8601 (un texto
  numérico no es una fecha) o anterior al suelo de importación, campo repetido en una lectura
  (`json.loads` se quedaría con el último), indicador de otra vía (dolor y analitos, con su
  lectura; `record_many` lo sigue garantizando), cuerpo que no es
  una lista no vacía de objetos. **Los tipos son estrictos**, a diferencia del alta manual: `true`
  no es 1.0, `"64"` no es 64, un entero no es un instante y `MEASURED` no es `measured`; delante de
  la consola hay una persona que ve lo que entró, y un fichero importado después no lo lee nadie
  (un entero sí vale como número). El motivo de un tipo equivocado es el de Pydantic.
  Todo motivo se acota a `MAX_DETAIL_CHARS`: repite nombres que llegan del fichero.
- **Aviso de vínculo.** Sin `device` (§5 no lo tiene), el aviso se calcula por fuente y sujeto
  (§3.14 bis) y la respuesta lo trae en `binding_notices`, uno por sujeto; solo describe.
- **Lo que no hace.** No lleva `device`, ni `recorded_by`, ni `food`, ni detecta un lote ya
  importado: reenviar el fichero lo firma otra vez, como en las otras importaciones. No convierte unidades ni normaliza nombres de indicador: el
  `hrv_rmssd` del ejemplo de §5 es `hrv-rmssd` en el catálogo y llega como desconocido, con su
  motivo. `rules_version` no cambia: la ruta no toca el análisis.

Pruebas: `tests/test_observation_unit.py`, `tests/test_spec5_import.py`. Campañas:
`tests/mutants/manual_unit.json`, `tests/mutants/spec5_import.json`.

### 3.14 quinquies El alimento de una valoración de la comida (2026-10-26) y de una fracción rechazada (2026-10-31)

Decisión del usuario (2026-10-26, decimoctava ronda, U2): la valoración de aceptabilidad de la
comida lleva el **alimento valorado**, para poder contar plato a plato cuántas veces se valoró cada
uno y cómo fue su valoración en el tiempo (la repetición del menú de la conversación de ideación).
Lo leído dice que la valoración es de un alimento: los astronautas «rated each food or beverage»
(`instruments_read.json`, `hedonic-anchors-crew`) y la norma habla de «A NASA food item»
(`v2-7002-acceptable-6`).

- **Qué se firma.** `VitalObservation.food`: el nombre normalizado (NFC, sin espacios en los bordes
  y con los de dentro reducidos a uno). Pueden llevarlo la aceptabilidad (`food-acceptability`) y,
  desde el 2026-10-31 (decimonovena ronda, U15), la fracción de la ración que se deja sin comer
  (`food-rejected-fraction`), que puede ser de la comida en general o de un plato (`food_item.KEYS`);
  el modelo rechaza un alimento en otro indicador, uno vacío y uno con espacios en los bordes
  (`ValueError`). Es **texto libre**: ninguna fuente leída da un vocabulario cerrado de alimentos,
  categorías o menú (ni `instruments_read.json` ni lo registrado como leído del informe de evidencia
  del HRP sobre el sistema de alimentos, ficha `hrp-food-system-evidence-report`), y una lista
  inventada se atribuiría una fuente que no tiene.
- **La regla, decisión de diseño de EMMA sin validar** (`ingest/food_item.py`, y así lo dice
  `GET /api/diary` en `food_item`): de 1 a 64 caracteres, con al menos una letra; solo letras de
  cualquier alfabeto, cifras, espacios y `- ' ’ , . ( ) / & + º`; y pasa el filtro de lenguaje de
  EMMA (`text_guard.check`), así que una ración escrita con su cantidad y su unidad («arroz 100 g»)
  se rechaza. La aplican las **rutas que firman** (`food_item.accept`, una sola función para las
  tres), no el modelo: un cambio futuro de la regla no puede dejar sin leer lo ya firmado.
- **Por dónde entra.** Por `POST /api/diary/entries` (`food`), que lo **exige** en la aceptabilidad
  (422 «Falta el alimento valorado» sin asiento) y lo admite **opcional** en la fracción rechazada
  (`food_item.REQUIRED`; `GET /api/diary` dice cuál es cuál en `food_item.required` y
  `requirement_note`, con un rótulo por indicador); y, desde el 2026-10-31, por la ingesta genérica
  (`POST /api/observations`, campo `food_item`) y por la enmienda (`POST /api/audit/amend/{index}`,
  `correction.food_item`). Hasta entonces la genérica no tenía el campo y, con `extra="forbid"`,
  enviarlo era un 422: lo que entraba por ahí no podía decir de qué plato era. En la genérica el
  alimento es opcional **también en la aceptabilidad**: por ella entra lo que no lo conoce (el
  simulador, un cliente anterior al campo), que se sigue contando aparte como «sin alimento
  declarado». Las tres rutas aplican la misma regla con su motivo en español y sin asiento: 422 en
  cualquier otro indicador, vacío o sin letra, con caracteres fuera de la regla o rechazado por el
  filtro de lenguaje. Las tres devuelven el alimento tal como quedó firmado (`food`; `null` si la
  lectura no lo lleva).
- **Por qué no invalida lo firmado.** Igual que `device` (§3.14 bis) y `recorded_by` (§3.14 ter): la
  clave `food` se escribe en el payload **solo cuando existe**, detrás de las demás. Una lectura sin
  alimento produce las mismas claves, en el mismo orden, y los mismos bytes canónicos que antes.
- **Con qué se comprueba.** `backend/tests/data/food_pre_item.db` es un ledger con dos valoraciones
  del diario (`crew-diary`, con anotador) y una de alta manual, escrito con el código anterior al
  campo (commit `2972d93`, exportado con `git archive` a una carpeta aparte), y
  `food_pre_item.fhir.json` es el FHIR que aquel código serializaba. La prueba lo abre con el código
  de ahora: verifica, los `content_hash` son los de entonces, `_to_payload` reproduce sus bytes bajo
  la misma sal, el FHIR sale carácter a carácter igual, y una valoración con alimento se encadena
  detrás y la cadena sigue verificando al reabrir.
- **En FHIR.** `Observation.focus` («what the observation is about, when it is not about the subject
  of record»), como `[{"display": <alimento>}]`. FHIR R4B pone «the subject's diet» entre los
  ejemplos de ese elemento (ficha `hl7-fhir-r4b-observation`, leída el 2026-10-26); es una lista de
  referencias de cualquier recurso, y EMMA no tiene un recurso del alimento al que apuntar: solo
  `display`, sin `reference` ni `identifier` (serían inventados). No se usa una extensión propia
  porque el estándar ya tiene el sitio. Sin alimento, la clave `focus` no existe y el recurso es el de
  antes.
- **El espejo SQL no lo copia**, como los demás campos de §3.14.
- **Una enmienda (§3.7) conserva el alimento, o lo corrige.** Sin `food_item` en la corrección,
  `ObservationStore.amend` firma la versión corregida con el alimento de la lectura que corrige: la
  corrección es del valor, el instante o el tripulante, no del plato. Antes se perdía, y la versión
  corregida —la única que se lee— salía de su plato y se contaba como «sin alimento declarado» sin
  que nada lo dijera (revisión de código de la decimoctava ronda). Desde el 2026-10-31, con
  `food_item` en la corrección se corrige también el plato, con la misma regla (hasta entonces un
  plato mal escrito no se podía enmendar). Quitarle el alimento a una lectura no es una enmienda
  posible, tampoco en la fracción rechazada, donde es opcional: sin el campo se conserva y un texto
  vacío es un 422. Una fracción anotada con plato que era de la comida en general se redacta y se
  anota de nuevo; es una decisión deliberada, para que un `null` no borre un plato por omisión.
- **No entra en el análisis.** Ningún módulo de `analysis/` ni de `advisor/` lee `food` salvo
  `analysis/food_acceptability.py`, que lo usa para describir plato a plato en una ruta de solo
  lectura (`GET /api/nutrition/food-acceptability`); una prueba lo comprueba con `ast`. Los mismos
  valores a las mismas horas dan el mismo estado con alimento y sin él, y `rules_version` no cambia
  (`reglas@c89d7ebf4d5f4aa9` antes y después, medido con el código de `2972d93` y con el de esta
  pieza; y otra vez el 2026-10-31, con el de `6372fad` y con el de la decimonovena ronda, que toca
  `ingest/fhir.py` solo en un comentario y en el texto de un `ValueError`: la huella se calcula sobre
  valores, no sobre el código).

Pruebas: `tests/test_food_item.py`, y `tests/test_food_acceptability.py` y `tests/test_diary.py` para
lo que ya había. Campañas: `tests/mutants/food_item.json` y, para el plato en la fracción rechazada,
la ingesta genérica y la enmienda, `tests/mutants/food_in_ingest.json`.

### 3.15 Seguimiento de contramedidas (2026-09-26)

Tipo `countermeasure-followup`, firmado por `crew-console`, con el patrón de §3.8: es una
**decisión humana**, no un dato clínico, y no entra en `observations` ni en el análisis.

| Campo | Contenido |
|---|---|
| `action` | `adopted` o `closed` |
| `countermeasure_id`, `domain`, `level` | Contramedida de la biblioteca, su dominio y el nivel del dominio al adoptarla |
| `reference_time` | Instante del estado que vio quien decide (UTC) |
| `decided_by` | Operador declarado (la API no autentica operadores, §7.5) |
| `reason` | Motivo del cierre; vacío al adoptar |
| `adoption_index` | En un cierre, el asiento de la adopción que cierra; vacío al adoptar |

Reglas que aplica la API: adoptar exige que la contramedida estuviera **recomendada** en el estado
de `reference_time` (409 si no); cerrar exige una adopción abierta y no admite un segundo cierre.
Solo cuentan los asientos firmados por la consola y, para Tierra, los ya existentes en su corte.
El estado (en ventana, listo para revisar, cerrado) y la evaluación se derivan en cada consulta
(`advisor/followup.py`). Pruebas: `tests/test_countermeasures.py`.

### 3.15 bis Decidir no adoptar una contramedida (2026-10-09)

No es un tipo de asiento nuevo ni un campo nuevo: es un tercer valor de `action` en el asiento
`countermeasure-followup` de §3.15, `declined`, y recorre exactamente su camino —`POST
/api/countermeasures/decline`, `record_followup`, `_record_action`: un asiento encadenado y
firmado por `crew-console` en un solo `commit`—. No hay otra vía que escriba esa decisión
(invariante 4).

- **Los mismos campos.** Un asiento `declined` lleva los nueve campos de §3.15, como texto. Solo
  cambia cómo se usan dos: `reason` es el **motivo de no adoptar**, obligatorio (en `adopted` va
  vacío; en `closed` es el motivo del cierre), y `adoption_index` va vacío, porque no apunta a
  ninguna adopción. `level` es el nivel del dominio en el estado que vio quien decide.
- **Lo ya firmado no cambia.** Los asientos `adopted` y `closed` conservan su payload, su hash y
  su firma, y `_actions` los lee con la misma lista de campos. Prueba: un ledger escrito con el
  código anterior al cambio (`tests/data/followup_pre_decline.db`) se abre, se verifica, entrega
  sus dos decisiones con los hashes de contenido que firmó aquel código, admite después un
  `declined` y vuelve a verificarse.
- **Qué significa, y qué no.** Es el registro de una decisión humana, no una evaluación. No cierra
  la alerta, no la silencia (eso es §3.8 y tiene sus propias reglas), no baja ningún nivel y no
  retira la recomendación: si los datos la siguen sosteniendo vuelve a salir, y `/api/status` la
  entrega con `decision` al lado («Se decidió no adoptarla el … (quién): motivo», texto compuesto
  por el backend). No entra en `observations`, ni en el análisis, ni en la puntuación (invariante
  5): `advisor/followup.py` solo añade ese campo a recomendaciones ya calculadas.
- **Qué se rechaza, y dónde.** En la API, 422 con su texto si el motivo va vacío o en blanco, si
  la contramedida no está en la biblioteca, o si está **adoptada y con el seguimiento abierto**
  (decir «no» a lo que se está siguiendo sería un registro que se contradice; el seguimiento se
  puede cerrar con su motivo y entonces sí). 409, como al adoptar, si no estaba recomendada en el
  estado de `reference_time`. `record_followup` rechaza también un `declined` sin motivo o con
  `adoption_index` si se le llama desde otro sitio: no se escribe nada.
- **Cambiar de opinión.** Se puede adoptar después de un «no»: son dos asientos, los dos
  firmados, y ninguno se borra. El «no» deja entonces de estar en pie y la nota desaparece de la
  recomendación. Un «no» repetido sustituye al anterior: vale el último motivo.
- **Qué cuenta.** Solo los asientos firmados por la consola y, para Tierra, los ya existentes en
  su corte (`_counts`, como toda acción del operador).
- **Dónde se lee.** `decision` en cada recomendación de `/api/status`; `GET
  /api/countermeasures/decisions` (los asientos en orden y, por contramedida, el último «no» en
  pie); y la crónica (`timeline.py`), que lo cuenta como hecho `countermeasure-declined` con su
  motivo. El motivo es texto libre de una persona: vive en el asiento firmado y en esas
  respuestas, y no se escribe en ningún log.

Pruebas: `tests/test_countermeasure_decline.py` (el asiento y sus campos, el ledger anterior al
cambio, el veredicto del motor idéntico con y sin la decisión, los 422 y el 409, adoptar tras un
«no», la crónica y que el motivo no llega al log); campañas
`tests/mutants/countermeasure_decline*.json`.

### 3.15 ter El nivel, al cerrar una adopción (2026-10-13)

No es un tipo de asiento nuevo: el asiento `closed` de §3.15 gana **dos campos opcionales**. El
cierre no guardaba el nivel del dominio, así que de una adopción cerrada hace tiempo solo se podía
decir «cómo está hoy frente a entonces», que mezcla todo lo que pasó después del cierre. Recorre
el camino de siempre —`POST /api/countermeasures/close`, `record_followup`, `_record_action`: un
asiento encadenado y firmado por `crew-console` en un solo `commit`— (invariante 4).

| Campo | Contenido |
|---|---|
| `level_at_close` | Nivel del dominio de la adopción en el estado del instante en que se cerró |
| `closed_reference_time` | Instante de ese estado (su última lectura), en el tiempo de los datos, como `reference_time` |

- **Quién los pone.** El backend: la ruta de cierre los copia del mismo análisis que sirve
  `/api/status`, sin corte (`_level_at_close`). El cliente no los manda: el cuerpo de la petición
  no tiene esos campos y rechaza los que sobran (422). `level` sigue siendo el nivel **al
  adoptar**; el cierre no lo pisa.
- **Solo en un cierre, y los dos o ninguno.** `record_followup` rechaza un nivel sin su instante
  (o al revés) y cualquiera de los dos en un `adopted` o un `declined`: no se escribe nada. Si en
  el instante del cierre no hay estado que consultar, el cierre se firma **sin** ellos: cerrar es
  una decisión humana y no se bloquea porque falte una copia descriptiva.
- **Lo ya firmado no cambia y sigue verificándose.** Los campos son opcionales en la lectura
  (`_actions(..., optional=_FOLLOWUP_OPTIONAL)`): un cierre firmado antes no los lleva, conserva
  su payload, su hash y su firma, y se entrega con los nueve campos de §3.15. Un cierre nuevo sin
  la copia es, campo por campo, el de antes. Prueba: un ledger escrito con el código anterior al
  cambio (`tests/data/followup_pre_close_level.db`, generado con `main` en `7efaf69`) se abre, se
  verifica, entrega su adopción y su cierre con los hashes de contenido que firmó aquel código,
  admite después un cierre con el nivel y vuelve a verificarse.
- **De un cierre antiguo no se inventa nada.** Sin los campos, `level_at_close` y
  `evaluation_at_close` van a `None` y la respuesta previa lo dice con estas palabras: «Este
  cierre no guardó el nivel: se compara con el estado actual». Lo mismo si la copia no se entiende
  (un nivel desconocido, un instante sin zona horaria): se trata como no guardada y no tumba el
  estado.
- **Qué es, y qué no.** Una **copia** de lo que el motor ya había calculado en ese instante. No
  entra en `observations`, ni en el análisis, ni en la puntuación, y no decide ningún nivel,
  alerta ni recomendación (invariante 5): el mismo ledger, leído con el campo y sin él, da el
  mismo estado salvo los seguimientos y la respuesta previa. Tampoco es una valoración de la
  contramedida: lo que se deriva de él es la comparación de dos niveles —al adoptar y al cerrar—
  con la nota de siempre de que coincidir en el tiempo no demuestra una causa (invariante 7).
- **Dónde se lee.** `followups` en `/api/status` da, para una adopción cerrada, `closed_at` (el
  instante del estado del cierre, si se guardó), `closed_recorded_at` (cuándo se firmó el
  asiento; lo tiene todo cierre), `level_at_close` y `evaluation_at_close`, **al lado** de la
  `evaluation` de siempre (nivel al adoptar frente al estado que se mira), que no cambia.
  `prior_response` en cada recomendación de `/api/status` y de `/api/anatomy/state` usa la del
  cierre cuando existe y rotula con qué compara (`advisor/prior_response.py`). `GET
  /api/countermeasures/decisions` entrega el asiento tal y como está firmado.

Pruebas: `tests/test_close_level.py` (el asiento y sus campos, el ledger anterior al cambio, la
comparación al cierre junto a la de siempre, lo repetido contado hasta el cierre, el rótulo de un
cierre antiguo, el 422 si el cliente lo manda, el cierre sin estado y el veredicto del motor
idéntico con y sin el campo); campañas `tests/mutants/close_level*.json`.

### 3.16 Telemetría de cabina (2026-09-26)

Tipo `habitat-reading`, firmado por la fuente que mide (`habitat-telemetry` o `simulator`). La
invariante 4 se aplica también al hábitat: no hay vía para registrar una lectura de cabina sin
asiento firmado. Payload: `module`, `parameter` (catálogo de `environment/habitat.py`), `value`,
`unit` (la del catálogo; si no coincide, el asiento se rechaza al leerlo), `effective`, `source` y
`evidence_context`. Varias lecturas se escriben en un solo `commit`. No entra en `observations`
ni en el análisis fisiológico; `habitat_readings()` entrega solo lo que coincide con su hash.
Cuenta como registro real a efectos de §3.9: telemetría real impide sustituir el almacén por un
escenario. Pruebas: `tests/test_habitat.py`.

Desde el 2026-10-22 el catálogo incluye también lo que se muestra y no se evalúa: la luz de cabina,
el agua potable (`water-toc`, `water-silver`, `water-microbial`) y la microbiología del aire y las
superficies (`air-microbial`, `surface-microbial`). Van por este mismo asiento, con el mismo payload
—el formato no cambia—, firmados por la fuente que declara la muestra. Pruebas:
`tests/test_habitat_water.py`.

Desde el 2026-10-07, `module` es en la API un dato opcional de la lectura que solo admite un
módulo de la lista declarada (§3.17 bis): sin él, la lectura cae en el módulo por defecto; con uno
que no está en la lista, 422 y no se escribe nada. El formato del asiento no cambia.

Desde el 2026-10-26, `unit` es en la API un dato opcional con la regla del alta de una lectura
(§3.14 quater): distinta de la del parámetro, 422 sin asiento y sin conversión; ausente, se asume y
la respuesta lo dice. El asiento sigue llevando la unidad del catálogo. Pruebas:
`tests/test_observation_unit.py`.

### 3.16 bis Estado declarado de los sistemas del hábitat (2026-10-10)

Tipo nuevo `system-status`, firmado por `crew-console` con el patrón de §3.8 (una acción humana
que se registra; todos los campos como texto; `_actions` rechaza un asiento mal formado). Es el
campo `system_status` de `HabitatState` (especificación del equipo §3) en la única versión que
se puede afirmar: **EMMA no lee el estado de ningún sistema**; una persona lo declara en la
consola y la declaración queda firmada. No es telemetría, y por eso no es un `habitat-reading`
(§3.16) ni lo firma una fuente que mide.

| Tipo | Campos | Regla (rechazo con 422, sin escribir nada) |
|---|---|---|
| `system-status` | `subject` (= `habitat`), `system`, `state`, `at` (instante al que se refiere quien declara, en UTC), `note` (puede ir vacía), `declared_by`; y `module` solo si la declaración habla de un módulo | `system` y `state` fuera del vocabulario; `state` = `undeclared`; `module` fuera de la lista de §3.17 bis; `at` sin zona horaria; `declared_by` sin nombre |

- **Una sola vía.** `POST /api/habitat/systems/status` → `record_system_status` →
  `_record_action`: un asiento encadenado y firmado en un solo `commit`. No hay otra escritura
  de un estado de sistema (invariante 4). Las reglas de la tabla las impone también
  `record_system_status` si se le llama desde otro sitio (`environment/systems.check`).
- **Vocabulario cerrado y de diseño.** `system` y `state` son claves de
  `backend/app/data/habitat_systems.json`, que se valida al cargar y se rotula «vocabulario de
  diseño de EMMA»: no se ha leído de ninguna nave. No son códigos de indicador: no llevan LOINC
  ni entran en el catálogo. La relación de un sistema con un parámetro de cabina solo se declara
  cuando es de definición, y ningún análisis la usa.
- **«Sin declarar» no es un estado que se firme.** Es lo que hay cuando no existe ningún
  asiento de ese sistema, y la lectura lo entrega como dato ausente, no como «nominal». Por eso
  `undeclared` no se puede declarar.
- **Qué vale.** De cada sistema y módulo, el último asiento firmado por la consola (`_counts`,
  como toda acción del operador; para Tierra, además, los que ya existían en su corte y no se
  refieren a un instante posterior a él). Los anteriores se conservan y se entregan como
  historial. **No hay borrado ni edición**: una declaración equivocada se corrige declarando de
  nuevo. «Desde cuándo» es el `at` de la primera declaración seguida del estado vigente, y la
  lectura dice que es lo que declaró una persona, no el instante del fallo.
- **Al leer.** `GET /api/habitat/systems` rotula toda la respuesta «declarado por una persona,
  no telemetría». `_actions` entrega `module` solo si el asiento lo trae y exige que sea texto.
  Una declaración de un sistema que ya no está en el vocabulario se conserva en el historial con
  su clave y no tiene fila vigente.
- **Para qué sirve, y para qué no.** La leen tres sitios, y los tres solo la cuentan: la ruta de
  arriba, el contexto de una alerta (`analysis/alert_context.py`, una fuente más, rotulada
  «correlación temporal, no causa», que dice si había o no declaraciones) y la crónica
  (`app/timeline.py`, en el instante `at`). No entra en `observations`, en el análisis
  fisiológico ni en las excursiones del hábitat; no mueve niveles, umbrales ni alertas
  (invariante 5) y no forma parte de `rules_version`. No cuenta como registro real a efectos de
  §3.9, como las demás acciones de la consola.

Pruebas: `tests/test_system_status.py` (el asiento firmado y la verificación de integridad, lo
vigente y su historial, los 422 y el rechazo del almacén, lo que no firmó la consola, el corte
de Tierra, el contexto de la alerta, la crónica y los niveles, alertas y excursiones idénticos
con y sin declaraciones). Campañas: `tests/mutants/system_status*.json`.

### 3.17 Perfil, eventos de misión y revisión de hipótesis (2026-09-28)

Tres decisiones humanas firmadas por `crew-console`, con el patrón de §3.8 (todos los campos
como texto; `_actions` rechaza un asiento mal formado). Ninguna entra en `observations`.

| Tipo | Campos | Regla de la API |
|---|---|---|
| `crew-profile` | `subject`, `prior_missions`, `prior_career_dose_msv` (vacío = no se conoce), `declared_by` | Vale el último; nunca negativo. Alimenta la escala de carrera de la radiación |
| `mission-event` | `subject`, `kind` (`eva`, `workload`, `location`, `shift`), `start`, `end`, `label`, `declared_by`; y `module` solo si `kind` es `location` (§3.17 bis; `shift`, §3.17 sexies) | 422 si el tipo es desconocido o termina antes de empezar |
| `hypothesis-review` | `subject` = `tripulacion`, `decision` (`confirmed`, `discarded`), `parameter`, `excursion_start`, `reason`, `decided_by` | 409 si esa hipótesis no está en el estado actual |

Pruebas: `tests/test_context_round2.py`.

### 3.17 bis Ubicación declarada de un tripulante (2026-10-07)

No es un tipo de asiento nuevo: es un tercer valor de `kind` en el asiento `mission-event` de
§3.17, `location`, y recorre exactamente su camino —`POST /api/mission/events`,
`record_mission_event`, `_record_action`: un asiento encadenado y firmado por `crew-console` en un
solo `commit`—. La otra fuente, desde el 2026-11-10, son las anclas de módulo (abajo): dos tipos
de asiento propios, también por `_record_action`. Ninguna escribe una ubicación fuera del ledger
(invariante 4). El simulador **no** pone ubicaciones: lo hizo del 2026-11-09 al 2026-11-10 y se
quitó por decisión del usuario («no las queremos simuladas, las queremos reales»).

- **Campo añadido: `module`.** Lo lleva el asiento **solo** cuando `kind` es `location`, como
  texto, igual que los demás campos. Los asientos `eva` y `workload` no lo llevan, ni los firmados
  antes de este cambio: su payload, su hash y su firma son los de siempre.
- **Lista declarada.** `module` es una clave de `backend/app/data/habitat_modules.json`: una lista
  pequeña que es **parámetro de diseño sin respaldo bibliográfico** (EMMA no modela una nave
  concreta) y que el fichero y `GET /api/habitat/modules` rotulan así. No es un código de
  indicador: no lleva LOINC ni entra en el catálogo.
- **Qué se rechaza, y dónde.** Un módulo que no está en la lista, una ubicación sin módulo o un
  módulo en una `eva` o un `workload` son un 422 en la API, y `record_mission_event` los rechaza
  también si se le llama desde otro sitio: no se escribe nada. Un `label` vacío en una ubicación se
  sustituye por el nombre del módulo; en `eva` y `workload` sigue siendo obligatorio.
- **Al leer.** `_actions` entrega `module` solo si el asiento lo trae y exige que sea texto; un
  `module` que no lo sea es un asiento mal formado (409), como cualquier otro campo.
- **Quién firma qué (2026-11-10).**
  - `crew-console`: la ubicación declarada (`mission-event` con `kind` `location`) y la
    declaración de cada ancla (`location-anchor`). Regla de toda acción del operador (`_counts`).
  - `location-anchors`: los lotes de lo que oyó el receptor de un tripulante
    (`location-sightings`). Solo la ruta `POST /api/location/sightings` firma así; ninguna
    lectura pública puede (`routes._is_reserved_source`), y un lote firmado por otra identidad no
    se usa al estimar.
  - El simulador no firma ninguna ubicación ni ningún lote.

| Tipo | Campos | Regla (rechazo con 422, sin escribir nada) |
|---|---|---|
| `location-anchor` | `subject` (= `habitat`), `anchor_id` (minúsculas), `module`, `since` (UTC), `declared_by` | `anchor_id` sin forma de identificador (hasta 64 caracteres entre letras sin acento, cifras y `: . _ -`); `module` fuera de la lista; `since` sin zona horaria; `declared_by` sin nombre |
| `location-sightings` | `subject`, `sightings` (lista de `{anchor_id, rssi_dbm, at}`, 1 a 500), `device` solo si quien envía lo pone | lote vacío o de más de 500; `anchor_id` sin forma; `rssi_dbm` fuera de [-127, 20] dBm; `at` sin zona horaria o fuera de la ventana de una lectura de wearable (2000-01-01 … ahora + 10 min, `ingest/wearable.py`) |

  `POST /api/location/anchors` → `record_location_anchor`; `POST /api/location/sightings` →
  `record_location_sightings`: **un asiento por lote**, no uno por lectura. Las reglas de la tabla
  las impone también el almacén (`ingest/location_anchors.py`) si se le llama desde otro sitio.
  Al leer, `location_sightings` comprueba el hash de cada asiento como `_actions` y exige la
  forma de cada lectura: un lote alterado o mal formado es un 409, no una lectura menos. Un ancla
  que nadie ha declarado se guarda y la respuesta la nombra (`unknown_anchors`), pero no se usa.
  Un lote **cuenta como registro real** para §3.9: el simulador no lo firma nunca.
- **Qué cuenta.** Las ubicaciones firmadas por la consola y las anclas firmadas por la consola
  (para Tierra, las ya existentes en su corte y, en las anclas, con `since` ≤ corte); los lotes
  firmados por `location-anchors` (para Tierra, los firmados hasta su corte). Una lectura se juzga
  con el ancla que valía en SU instante (de las declaraciones con `since` ≤ `at`, la de asiento
  posterior). Con eso se **estima** el módulo (`analysis/location.estimate`, función pura: señal
  más fuerte por módulo en una ventana, con margen, histéresis, indeterminación y caducidad;
  parámetros sin respaldo en `data/location_sensing.json`). Si una declarada y una estimada se
  solapan **manda la de la consola, aunque sea anterior** (`context.prevailing`, la única regla
  de `_presence`, `_deciding`, `location_at` y `crew_whereabouts`); entre dos del mismo tipo, la
  de asiento posterior. Una ubicación en un módulo que ya no está en la lista no se usa.
- **Lo que se sirve.** `GET /api/status` → `mission.location` (`module`, `display`, `start`,
  `end`, `ledger_index`, `source` `console` o `anchors`, `last_seen` en una estimada),
  `location_state` (`declared`, `estimated`, `ambiguous`, `stale`, `missing`, `unavailable`),
  `location_missing_text` y `location_basis`; lo mismo en cada tripulante de `GET /api/crew` y de
  `GET /api/crew/radiation`. El estado solo lee los lotes que pueden decir algo de su instante
  (`Sensing.lookback`), y sin ninguna ancla declarada no los lee.
- **Para qué sirve, y para qué no.** La lee `analysis/context.py`, para ordenar las hipótesis
  de causa ambiental de `GET /api/crew`, y se muestra (la del instante de referencia) en
  `GET /api/status` → `mission.location`, en `GET /api/crew` y en `GET /api/crew/radiation`
  (`analysis/location.py`). No entra en `observations` ni en el análisis fisiológico, y no mueve
  niveles, umbrales ni alertas (invariante 5; `risk-management-file.md`, H21).

Pruebas: `tests/test_habitat.py` (el asiento firmado y la verificación de integridad, el orden de
las hipótesis, los niveles idénticos con y sin ubicación, la salida sin ubicación idéntica a la
anterior y los 422), `tests/test_location_status.py` (el simulador que no pone a nadie, los seis
estados en el estado y en las vistas de tripulación, la consola que manda sobre lecturas
posteriores, el corte de Tierra, los niveles idénticos con anclas, la lectura acotada y el lote
como registro real) y `tests/test_location_anchors.py` (los dos asientos firmados, los 422, el
ancla desconocida, el lote de otra firma, el lote mal formado y la estimación: margen,
histéresis, indeterminación, caducidad). Campañas de mutantes: `tests/mutants/location_api.json`
y `tests/mutants/location_anchors.json`.

### 3.17 ter Vínculo sensor-tripulante declarado (2026-10-10)

Tipo nuevo `sensor-binding`, firmado por `crew-console` con el patrón de §3.8 (una acción humana
que se registra; todos los campos como texto; `_actions` rechaza un asiento mal formado). Es el
campo «sensor bindings» del astronauta (especificación del equipo §3) en la única versión que se
puede afirmar: **EMMA no comprueba quién lleva puesto un dispositivo**; una persona lo declara en
la consola y la declaración queda firmada. No es de un tripulante sino de la tripulación: su
sujeto es `tripulacion`, como el de `hypothesis-review` (§3.17), y cada lectura filtra por tipo.

| Tipo | Campos | Regla (rechazo con 422, sin escribir nada) |
|---|---|---|
| `sensor-binding` | `subject` (= `tripulacion`), `source`, `action` (`bind` o `unbind`), `since` (desde cuándo vale, en UTC), `note` (puede ir vacía), `declared_by`; `device` solo si el vínculo es de un identificador concreto; `crew` solo si `action` es `bind` | `source` que no es una de las tres fuentes de wearable de la ingesta; `action` desconocida; `bind` sin `crew`; `unbind` con `crew`; `device` que no tiene forma de identificador; `since` sin zona horaria; `declared_by` sin nombre |

- **Una sola vía.** `POST /api/sensor-bindings` → `record_sensor_binding` → `_record_action`: un
  asiento encadenado y firmado en un solo `commit`. No hay otra escritura de un vínculo
  (invariante 4). Las reglas de la tabla las impone también `record_sensor_binding` si se le
  llama desde otro sitio (`ingest/bindings.check`).
- **Qué es un dispositivo.** Lo que la ingesta sabe distinguir: la fuente (`wearable-ble`,
  `apple-health`, `google-fit`) y, si quien envía lo pone, un identificador. EMMA no lo lee de la
  trama ni del export. Sin `device`, el vínculo es de la fuente entera y solo vale para las
  lecturas de esa fuente que llegan sin identificador: con dos tripulantes y una sola fuente,
  EMMA no puede distinguir sus relojes, y la lectura lo dice. El identificador se guarda en
  minúsculas y sin espacios alrededor (`ingest/bindings.device_key`, la misma función para
  declarar y para ingerir); es una etiqueta de hasta 64 caracteres, no un texto libre.
- **El identificador puede ser un dato personal** (una dirección MAC). Consta en este asiento y
  en la respuesta a quien pregunta por los vínculos y, desde el 2026-10-13, en la lectura
  firmada que llegó con él (campo opcional, §3.14 bis). **No se escribe en el log** (§12 de la
  especificación; `core/log_privacy.py`), la crónica no lo repite y el estado lo enseña
  abreviado.
- **Qué vale, y en qué instante.** Una declaración vale desde su `since` en adelante, hasta que
  otra firmada después la sustituya desde el suyo. El vínculo vigente de un dispositivo es el de
  su último asiento firmado por la consola (`_counts`, como toda acción del operador; para
  Tierra, además, los que ya existían en su corte y no valen desde un instante posterior a él).
  Los anteriores se conservan y se entregan como historial. **No hay borrado ni edición**:
  retirar un vínculo es otra declaración (`unbind`), y una equivocada se corrige declarando de
  nuevo. Una lectura se juzga contra el vínculo que valía en SU instante: de las declaraciones
  del dispositivo con `since` anterior o igual al instante de la lectura, manda la firmada más
  tarde.
- **Al leer.** `GET /api/sensor-bindings` rotula toda la respuesta «declarado por una persona».
  `_actions` entrega `device` y `crew` solo si el asiento los trae y exige que sean texto.
- **El aviso no bloquea.** Las tres rutas de ingesta de wearables (`POST /api/wearable/ble`,
  `/api/import/apple-health`, `/api/import/google-fit`) admiten un `device` opcional y devuelven
  `binding_notice`. El aviso se compone **después** de registrar las lecturas, así que no puede
  rechazar ninguna: si alguna llega para un tripulante desde un dispositivo que en su instante
  constaba vinculado a otro, lo dice, con cuántas y con qué asiento; si no, es nulo. De un
  dispositivo sin vínculo declarado no se avisa. La lectura queda bajo el tripulante que dijo la
  petición: el vínculo no la mueve. Si el registro de vínculos no se puede leer con garantías, el
  aviso dice que no se ha comparado y la respuesta de la ingesta sigue siendo un 201. Lo único
  que rechaza la ingesta es un `device` sin forma de identificador (422 antes de registrar
  nada): es un fallo de la petición, no un desacuerdo con un vínculo.
- **El aviso, también después de la ingesta (2026-10-13).** Hasta esta fecha era un límite
  declarado: el identificador no se guardaba con la lectura y el aviso existía solo en la
  respuesta de la ingesta. Con el campo opcional de §3.14 bis, `/api/status` lo dice en
  `data.quality.device_bindings` (`ingest/bindings.in_readings`, compuesto por
  `analysis/data_quality.describe`): cuántas lecturas de la ventana reciente —la misma del
  bloque de calidad— llegaron desde un dispositivo que **en su instante** constaba vinculado a
  otro tripulante, de qué indicadores, desde cuándo y con qué asiento de vínculo se comparó. La
  comparación es la de la ingesta: una lectura con identificador, contra el vínculo de ese
  identificador; una de fuente de wearable sin identificador, contra el de la fuente entera. Con
  ningún vínculo declarado el bloque no dice nada (`kind: none`, sin texto): es el caso normal.
  Si el registro de vínculos no se puede leer con garantías, dice que no se ha comparado
  (`not-checked`) y el estado sigue respondiendo. Para Tierra cuentan los vínculos que existían
  en su corte, como en `GET /api/sensor-bindings`. **Describe y nada más:** esas lecturas se
  analizan igual —quitarlas o bajarles la confianza movería el veredicto—, y el texto lo dice
  («EMMA las analiza igual; decidir si son de este tripulante es de una persona»). El
  identificador sale **abreviado** (sus cuatro últimos caracteres; diseño de EMMA): el estado lo
  leen más pantallas que el panel de vínculos, que es donde está entero, y el bloque cita el
  asiento de la declaración para encontrarlo. La consola lo pinta en «Calidad del dato» con la
  señal de baja confianza, no con la de un nivel de salud.
- **Límite declarado.** Solo se puede señalar una lectura que llegó con identificador o desde
  una fuente con vínculo de fuente entera. Las lecturas firmadas antes del 2026-10-13 no llevan
  identificador y no se les añade: lo firmado no se reescribe.
- **Para qué sirve, y para qué no.** La leen la ruta de arriba, el aviso de la ingesta, el
  bloque `device_bindings` del estado y la
  crónica (`app/timeline.py`, en el instante `since`). No entra en `observations` ni en el
  análisis; no mueve lecturas aceptadas, niveles, umbrales ni alertas (invariante 5) y no forma
  parte de `rules_version`. No cuenta como registro real a efectos de §3.9, como las demás
  acciones de la consola.

Pruebas: `tests/test_sensor_bindings.py` (el asiento firmado y la verificación de integridad, lo
vigente y su historial, el vínculo de cada instante, los 422 y el rechazo del almacén, lo que no
firmó la consola, el corte de Tierra, el aviso en las tres rutas con la lectura registrada igual,
el log sin el identificador, la crónica, y las lecturas, niveles y alertas idénticos con y sin
vínculos) y `tests/test_device_in_reading.py` (el aviso sobre las lecturas ya firmadas, el
identificador abreviado, el corte de Tierra, el registro de vínculos dañado y el veredicto
idéntico con y sin dispositivo y con y sin vínculos). Campañas:
`tests/mutants/sensor_binding*.json` y `tests/mutants/device_in_reading*.json`.

### 3.17 quater Disponibilidad declarada de los recursos de a bordo (2026-10-10)

Tipo nuevo `resource-availability`, firmado por `crew-console` con el patrón de §3.8 (una acción
humana que se registra; todos los campos como texto; `_actions` rechaza un asiento mal formado).
Es el campo `available_resources` del contexto de misión (especificación del equipo §3) en la
única versión que se puede afirmar: **EMMA no lleva inventario**; no sabe qué hay a bordo ni
cuenta unidades. Una persona declara en la consola que un recurso está o no está disponible, y la
declaración queda firmada. No es de un tripulante sino de la misión: su sujeto es `mision`.

| Tipo | Campos | Regla (rechazo con 422, sin escribir nada) |
|---|---|---|
| `resource-availability` | `subject` (= `mision`), `resource` (clave del vocabulario), `state` (`available` o `unavailable`), `since` (desde cuándo vale, en UTC), `note` (puede ir vacía), `declared_by` | `resource` fuera del vocabulario; `state` desconocido o `undeclared`; `since` sin zona horaria; `declared_by` sin nombre; cualquier campo de más (no hay cantidades) |

- **Una sola vía.** `POST /api/resources` → `record_resource_availability` → `_record_action`: un
  asiento encadenado y firmado en un solo `commit`. No hay otra escritura de una disponibilidad
  (invariante 4). Las reglas de la tabla las impone también `record_resource_availability` si se
  le llama desde otro sitio (`core/resources.check`).
- **El vocabulario es cerrado y sale de lo que hay.** `app/data/resources.json` tiene una clave y
  un nombre por cada recurso que ya nombraban las contramedidas de
  `app/data/countermeasures.json`, y nada más: no es el inventario de una nave ni de un botiquín,
  y no lleva cantidades. Cada recurso de una contramedida es `{key, description}`: la clave del
  vocabulario y el texto con que esa entrada lo nombraba, conservado tal cual. La carga de la
  biblioteca falla si un recurso no está en el vocabulario o si una clave del vocabulario no la
  nombra ninguna contramedida (`advisor/countermeasures.load_closed`).
- **Tres estados, y solo dos se firman.** «Declarado disponible», «declarado no disponible» y
  «sin declarar». **Sin declarar no es disponible**: es el caso por defecto, significa que EMMA
  no sabe, y no hay asiento que lo diga (no se puede firmar `undeclared`).
- **Qué vale.** La disponibilidad vigente de un recurso es la de su último asiento firmado por la
  consola (`_counts`, como toda acción del operador; para Tierra, además, los que ya existían en
  su corte y no valen desde un instante posterior a él). Los anteriores se conservan y se
  entregan como historial. **No hay borrado ni edición**: una declaración equivocada se corrige
  declarando de nuevo. `since` es lo que dice quien declara; no decide cuál manda.
- **Al leer.** `GET /api/resources` da todo el vocabulario con su estado, qué contramedidas
  nombran cada recurso, qué le consta a cada contramedida y el historial, rotulado «declarado por
  una persona; EMMA no lleva inventario». `/api/status` lleva lo declarado vigente en
  `mission.available_resources` y, junto a cada recomendación, `resource_status`: qué recursos
  pide su contramedida y cuáles constan como no disponibles o sin declarar.
- **Para qué sirve, y para qué no.** Lo leen las dos rutas de arriba y la crónica
  (`app/timeline.py`, en el instante `since`). No entra en `observations` ni en el análisis. **No
  cambia qué se recomienda, ni el orden, ni la urgencia**, ni mueve niveles, umbrales o alertas
  (invariante 5): una contramedida a la que le falta un recurso se sigue ofreciendo y se puede
  adoptar, con el aviso al lado; si se puede hacer lo valora una persona (invariante 7). Las
  declaraciones no forman parte de `rules_version`. (El fichero `countermeasures.json` sí, por
  su sha256: al pasar sus recursos a claves del vocabulario cambió `rules_version`, sin que
  cambie una sola regla ni un solo texto de la biblioteca.) No cuenta como registro real a
  efectos de §3.9, como las demás acciones de la consola.

Pruebas: `tests/test_resources.py` (la biblioteca idéntica a la anterior salvo la forma de
`resources`, el vocabulario cerrado en los dos sentidos, los tres estados, el asiento firmado y la
verificación de integridad, lo vigente y su historial, los 422 y el rechazo del almacén, lo que
no firmó la consola, el corte de Tierra, la crónica, y las recomendaciones, niveles y alertas
idénticos con y sin declaraciones). Campañas: `tests/mutants/resources*.json`.

### 3.17 quinquies Historial misión a misión declarado (2026-10-22)

Tipo nuevo `crew-mission-history`, firmado por `crew-console` con el patrón de §3.8 (una acción
humana que se registra; todos los campos como texto; `_actions` rechaza un asiento mal formado).
Es el campo `mission_history` del astronauta (especificación del equipo §3) en la única versión
que se puede afirmar: **lo que una persona declara** de cada misión previa —nombre, fecha de
inicio, fecha de fin y, si se conoce, su dosis—. EMMA no lo coteja con ningún registro de vuelos
ni de dosimetría. Decisión del usuario (2026-10-22): un asiento **aparte, junto a** la dosis previa
del perfil (`crew-profile`, §3.17), **sin sustituirla**.

| Tipo | Campos | Regla (rechazo con 422, sin escribir nada) |
|---|---|---|
| `crew-mission-history` | `subject`, `missions` (la lista entera, como texto JSON: cada misión `{name, start, end, dose_msv}`, todos sus valores también como texto; `dose_msv` vacío = no se conoce), `declared_by` | un nombre sin letras ni cifras o de más de 80 caracteres; una misión que termina antes de empezar, o después de hoy (UTC: es una misión previa), o después del día en que empieza la misión en curso (`mission_start` de la configuración: se solaparía con ella; desde el 2026-10-26); una dosis negativa, no finita o de más de 2000 mSv (este tope, en la API, como el del perfil); dos misiones que se solapan o empiezan el mismo día (una puede empezar el día que acaba la anterior); más de 20 misiones; `declared_by` sin nombre; cualquier campo de más (tampoco «días») |

- **Una sola vía.** `POST /api/crew/mission-history` → `record_mission_history` →
  `_record_action`: un asiento encadenado y firmado en un solo `commit`. No hay otra escritura de
  un historial (invariante 4). Las reglas de la tabla las impone también `record_mission_history`
  si se le llama desde otro sitio (`core/mission_history.check`); la del solape con la misión
  en curso, cuando se le pasa su inicio (`current_start`, que la API toma siempre de la
  configuración). **Al leer solo se exige la
  forma** (`decode`: cuatro campos de texto, fechas ISO, dosis vacía o cifra finita), y solo del
  asiento vigente: volver a pasar las reglas de hoy dejaría ilegible, si una regla se endurece,
  un asiento firmado bien antes. Un vigente sin esa forma es un asiento mal formado: 409. Desde
  el 2026-10-26 (`hmi-state-of-the-art.md` §5.38.10), si una previa del vigente se solapa con la
  misión en curso según el `mission_start` de hoy (firmada antes de la regla, o con otro inicio),
  la lectura lo **avisa** en `checks` (`key` = `overlap`, `matches` = `false`, cada misión con su
  fin), con la misma función que rechaza al firmar (`overlaps_current`); no rechaza ni corrige.
- **Un tipo nuevo, no un campo nuevo del perfil.** Los asientos `crew-profile` siguen siendo los
  de siempre: ni su payload, ni su hash, ni su firma cambian, y un ledger escrito antes de este
  cambio verifica y se lee igual (prueba con un ledger guardado tal cual lo escribió el código
  anterior, `tests/data/profile_pre_mission_history.db`, y sus hashes de contenido).
- **Los días no se declaran.** Se calculan al leer, entre las dos fechas (`días entre fechas`),
  y la respuesta lo rotula así: un campo «días» junto a las fechas sería una segunda declaración
  del mismo hecho que podría contradecirlas. Con precisión de día la cuenta puede diferir en uno
  de la duración oficial en horas, y también se dice.
- **Qué vale.** El último asiento firmado por la consola (`_counts`, como toda acción del
  operador; para Tierra, además, el que ya existía en su corte). Se declara la lista entera: una
  corrección es una declaración nueva, y los anteriores se conservan. **No hay borrado ni
  edición.** Una lista vacía es una declaración («ninguna misión previa»), distinta de no haber
  declarado nada.
- **Al leer.** `GET /api/crew/mission-history` (con `until`, que lleva zona horaria o es un 422,
  lo del corte de Tierra) da los topes de arriba (`limits`, para que el formulario no los copie),
  la lista vigente con los días de cada misión,
  la suma de las dosis conocidas, cuántas misiones no tienen dosis y dos cotejos con el perfil
  vigente: el número de misiones frente a `prior_missions` y la suma frente a
  `prior_career_dose_msv`. Cada cotejo dice si casa, si no casa o si no hay con qué cotejar
  (perfil sin declarar, o alguna misión sin dosis: una suma incompleta no se coteja, y **sin
  dosis no es cero**). Dos dosis casan si difieren en menos de 0,005 mSv: es la tolerancia de la
  suma en coma flotante, no un umbral; no decide nada salvo la palabra «casa».
- **Lo que no casa se dice; no se corrige.** Ni el perfil ni el historial se tocan, y no se elige
  uno: elegir sería decidir qué declaración es la buena, y eso lo hace una persona.
- **Para qué sirve, y para qué no.** Lo lee la ruta de arriba, que pinta la consola de
  tripulación junto a la declaración del perfil y, desde el 2026-10-23, la de Tierra de solo
  lectura y con su corte; y la crónica (§3.20), que cuenta cada misión previa del vigente como
  un hecho de la etapa «carrera», con la misma regla de qué vale. **La dosis de carrera y su proyección
  (`analysis/radiation.py`, vía `routes._latest_profile`) siguen leyendo solo
  `prior_career_dose_msv` del perfil**: el estado entero es idéntico con y sin historial, también
  cuando su suma no casa (prueba). No entra en `observations` ni en el análisis; no mueve niveles,
  umbrales ni alertas (invariante 5) y no forma parte de `rules_version`. No cuenta como registro
  real a efectos de §3.9, como las demás acciones de la consola.

Pruebas: `tests/test_mission_history.py` (las reglas en los dos sentidos, el asiento firmado y la
verificación de integridad, el ledger escrito antes del cambio, lo vigente, los 422 y el rechazo
del almacén, el asiento mal formado como 409, lo que no firmó la consola, el corte de Tierra, los
cotejos, y el estado y la escala de carrera idénticos con y sin historial). Campaña:
`tests/mutants/mission_history.json`.

### 3.17 sexies Cambio de turno o de horario de sueño declarado (2026-10-26)

No es un tipo de asiento nuevo: es un cuarto valor de `kind` en el asiento `mission-event` de
§3.17, `shift`, y recorre exactamente su camino —`POST /api/mission/events`,
`record_mission_event`, `_record_action`: un asiento encadenado y firmado por `crew-console` en un
solo `commit`—. No hay otra vía que escriba un cambio de turno (invariante 4). Lo pide la
conversación de ideación («carga de trabajo, turnos y eventos críticos», «ciclo día/noche»);
decisión del usuario, 2026-10-26 (decimoctava ronda, U4).

- **Sin campo nuevo.** Lleva los campos de una EVA: `subject`, `kind`, `start`, `end`, `label`,
  `declared_by`. Ni `module` (solo de `location`) ni un campo de horas de desplazamiento: la
  fuente leída no da un umbral de horas, y el desplazamiento, si se sabe, va en la descripción.
- **Qué es, y en qué se distingue de un `workload`.** Un `workload` es el intervalo en que se
  trabajó; un `shift`, el intervalo en que el horario de sueño y vigilia impuesto queda desplazado
  respecto al habitual (dormir horas antes o después, o pasar a otro turno). Pasan por separado:
  un turno doble sin mover la hora de dormir es un `workload`; dormir seis horas antes para un
  atraque es un `shift` aunque ese día no se trabaje más. Si pasan las dos, se declaran las dos.
  Lo dice `GET /api/mission/shift` (`core/shift.py`), que el formulario enseña al elegir el tipo.
- **Qué se rechaza, y dónde.** Como en una EVA: un `shift` sin descripción o con `module` es un
  422 en la API, y `record_mission_event` rechaza el módulo también si se le llama desde otro
  sitio; uno que termina antes de empezar, lo mismo. No se escribe nada.
- **Los ledgers ya escritos siguen verificando.** El vocabulario de `kind` solo se comprueba al
  escribir; al leer, `_actions` exige los mismos campos que antes. Los asientos `eva`, `workload`
  y `location` firmados antes de este cambio conservan su payload, su hash, su firma y su raíz de
  Merkle, y se leen igual; y un asiento `shift` lo lee también un código que no conoce el tipo
  (prueba con el vocabulario anterior, en los dos sentidos).
- **Para qué sirve, y para qué no.** Lo leen la línea temporal de la misión (con su dibujo), la
  crónica (`app/timeline.py`, nombrado en español) y el contexto de una alerta
  (`analysis/alert_context.py`): una fuente más, con el rótulo «correlación temporal, no causa» y
  la misma ventana de diseño. Con un cambio de turno en la ventana, la nota de la fuente dice lo
  que la leída cuenta (Flynn-Evans 2016, introducción: los cambios bruscos del horario de sueño
  impuesto pueden desalinear el ritmo circadiano) y lo que no (no clasifica sus sueños por si hubo
  cambio de turno ni dice cuánto dura el efecto). No entra en `observations` ni en el análisis
  fisiológico; no mueve niveles, umbrales ni alertas (invariante 5) y no forma parte de
  `rules_version`. No cuenta como registro real a efectos de §3.9, como las demás acciones de la
  consola.

Pruebas: `tests/test_shift_event.py` (el asiento firmado y la verificación de integridad, el
ledger escrito con el vocabulario anterior, los 422 y el rechazo del almacén, la crónica, la base
y su fuente, el contexto de la alerta con y sin turno en la ventana, y el estado y la versión de
reglas idénticos con y sin turno en una alerta de sueño). Campaña: `tests/mutants/shift_event.json`.

### 3.18 Instantáneas de proyección (2026-09-28)

Tipo `prediction-snapshot`, firmado por `emma-forecast` (identidad reservada: la ingesta pública
no puede firmar así). Cada proyección que muestra el estado de a bordo se firma **como mucho una
vez por indicador y día**, con `key`, `made_at`, `horizon_at`, `anchor_value` (media del último
día), el cambio proyectado y su margen, `model_version` y `rules_version`. La vista de Tierra
(`until`) no firma nada. Es la única escritura que hace una consulta de estado, y se documenta
aquí por eso (desde el 2026-11-11 hay otra, la discrepancia de efemérides de §3.30). Cuando llega el horizonte, `analysis/forecast_check.py` la compara con lo medido.
No entra en `observations` ni en el análisis. Pruebas: `tests/test_context_round3.py`.

**La crónica no firma (2026-10-22).** `GET /api/timeline/chronicle` (y su PDF) pedía el estado
entero solo para leer de él las alertas con su inicio, las trayectorias, los seguimientos y los
eventos del plan, y sin `until` firmaba de paso las instantáneas del día de un tripulante cuyo
estado nadie había pedido: una escritura que la crónica, de solo lectura, no enseña. Ahora toma
esas piezas de la misma evaluación (`routes.chronicle_status`, con las mismas funciones que
`/api/status`) y no escribe nada. Tampoco verifica la cadena: eso lo sigue haciendo `/api/status`
entera en cada consulta (§3.5), y lo que la crónica lee pasa por las mismas comprobaciones de hash
que cualquier consulta. Siguen firmando, como antes, `/api/status` de a bordo y quien lo pide entero
sin `until` («esta semana», lo que espera y el PDF del estado). Pruebas:
`tests/test_status_performance.py` (la crónica no escribe ni verifica; lo que toma del estado es,
campo a campo, lo que el estado enseña, a bordo y en cortes de Tierra); campaña
`tests/mutants/status_performance.json`.

### 3.19 Fuente de una firma, identidad del tripulante e identidad de un informe (2026-09-29)

Decisiones del usuario sobre Polaris (`docs/polaris-divergencias.md`), con su código copiado tal
cual en `polaris/tools/`:

- **`draft-signoff` y `draft-countersign`** llevan, si la firma cita algo, `source` (texto libre:
  PMID, DOI, NCT, contramedida…) y `source_check` (`estado` y `detalle` de
  `decision_alto_riesgo._existencia_citas`: `confirmada`, `FABRICADA`, `no_resoluble`, `n/a`).
  La comprobación la hace la API antes de firmar (en modo sin red, `no_resoluble`) y **no
  bloquea** la firma. Las firmas sin fuente no llevan estos campos. Pruebas:
  `tests/test_source_check.py`. (Desde el 2026-10-13 hay una excepción, y solo una: la segunda
  firma que cita un informe se rechaza si la cita no se localiza o la frase no se declara vista,
  §3.24. Desde el 2026-10-15 esa misma excepción se extiende: la segunda firma que no cita un
  informe se rechaza también, y por eso ya no se le consulta la fuente en su registro.
  `source_check` sigue sin bloquear nada por sí mismo, y la primera firma, tampoco.)
- **`crew-identity`** (nuevo tipo, firmado por `crew-console`, patrón de §3.8): `subject`,
  `given_name`, `surnames`, `birth_date` (ISO), `declared_by`. Vale la última. Aparte de
  `crew-profile` para que el perfil siga sin datos personales y esto se pueda redactar solo.
- **`crew-sex`** (2026-11-14, lote «ciclo»; decisión del usuario que revierte la §5.36.19 de
  `hmi-state-of-the-art.md`): el sexo que declara el propio tripulante, para llegar a una línea
  base consciente de la fase del ciclo. Firmado por `crew-console` con el patrón de §3.8:
  `subject`, `sex` (`female` o `male`), `declared_by`.
  - **Un tipo aparte, no un campo.** Ni de `crew-profile` (un campo obligatorio más en
    `_PROFILE_FIELDS` dejaría por mal formados los perfiles ya firmados, como dice §3.17 quinquies)
    ni de `crew-identity`: así se borra **solo**, con la redacción de §3.6
    (`POST /api/audit/redact/{ledger_index}`), sin tocar el perfil ni la identidad, y la
    identidad sigue siendo lo que coteja los informes y nada más.
  - **Privacidad.** Con dos valores posibles, el hash de su contenido se invertiría probando; lo
    impide la sal de todo asiento (`_salt`, §3.1), que se borra con el contenido. El valor no va en la
    ruta ni en la consulta (`subject` y `until` solo) y no llega al log
    (`core/log_privacy.py`, punto 4 del inventario).
  - **Una sola vía.** `POST /api/crew/sex` → `record_crew_sex` → `_record_action`: un asiento
    encadenado y firmado en un solo `commit` (invariante 4). Rechazo con 422, sin escribir nada:
    un valor fuera de `female`/`male` (también en mayúsculas o vacío), un campo de más,
    `declared_by` sin nombre. `record_crew_sex` impone las mismas reglas si se le llama desde
    otro sitio.
  - **Qué vale.** El último sin redactar firmado por la consola (`_counts`; para Tierra, el que
    ya existía en su corte: `GET /api/crew/sex?until=…`, con zona horaria o 422). Se borra
    asiento a asiento: redactar el vigente deja vigente el anterior que quede sin redactar, y sin
    ninguno la respuesta dice `declared: false`, `sex: null`, `status: "no declarado"`. **Nunca
    hay un valor por omisión.** La respuesta declarada lleva su `ledger_index`, que es el que se
    redacta. Un valor firmado fuera de los dos es un asiento mal formado: 409.
  - **Para qué sirve, y para qué no.** Solo lo lee `api/`. Ninguna regla de `analysis/`,
    `advisor/` ni `ingest/` lo recibe (`test_no_rule_of_emma_reads_sex_or_age`); no entra en
    `observations`, no mueve niveles, umbrales ni alertas (el estado entero es idéntico con y
    sin él, prueba) y no forma parte de `rules_version`. No cuenta como registro real a efectos
    de §3.9, como las demás acciones de la consola.

  Pruebas: `tests/test_crew_sex.py` (el asiento firmado con su sal, lo vigente, el borrado y lo
  que queda, el corte de Tierra, los 422 y el rechazo del almacén, lo que no firmó la consola,
  el 409, el estado idéntico) y `tests/test_logs_privacy.py` (el valor no llega al log).
- **`scanned-report`** lleva `identity`: `verdict` y `explanation` de
  `identidad_paciente.verificar` sobre el texto leído antes de des-identificarlo, y `usable`. Un
  informe de otra persona (`otro_paciente`) se guarda (el original es prueba) pero la interfaz no
  muestra ni su texto ni su original. La explicación no repite datos de la otra persona. Pruebas:
  `tests/test_report_identity.py`.
- **`draft-interpretation`** lleva `language_notes`: lo que las listas completas de Polaris
  marcan y EMMA no bloquea (`text_guard.advisories`), para quien firma.

### 3.20 Modo seguro y estados de una alerta (2026-10-01)

Dos tipos nuevos, firmados por `crew-console` con el patrón de §3.8 (una acción humana que se
registra, nunca una edición):

| Tipo | Campos | Reglas (rechazo con 422) |
|---|---|---|
| `safe-mode` | `subject` (= `sistema`), `active` (`true`/`false`), `reason`, `declared_by` | activarlo exige motivo; levantarlo y activarlo exigen persona con nombre; no se repite el estado vigente |
| `alert-resolution` | `subject`, `domain`, `level`, `reference_time`, `state` (`en_arreglo`, `resuelto`), `note`, `declared_by` | la alerta tiene que existir en ese estado (como reconocer); persona con nombre |

- **`safe-mode`** toma la regla de Polaris `codigo_rojo.py` (lo activa cualquiera con motivo, lo
  levanta una persona) y no su mecanismo (carpeta personal, Telegram, demonios de macOS). Vale el
  último asiento. Su efecto lo impone `core/egress.py`: con el modo activo, ninguna llamada sale a
  internet. El modelo local, el análisis y las alertas siguen. Pruebas: `tests/test_safe_mode.py`.
  Desde el 2026-10-26 (§5.38.13 de `hmi-state-of-the-art.md`) el estado que sirve
  `GET/POST /api/safe-mode` lleva `version`: cuántos asientos `safe-mode` hay (hasta el recién
  firmado, en la respuesta de un cambio), y `store_epoch`, de qué almacén (la hora en que se abrió,
  creciente: cambiar de escenario o reiniciar abre otro y la versión vuelve a 0). **Lo firmado no
  cambia**: ninguno de los dos es un campo del asiento; la versión se cuenta sobre los asientos
  firmados con las garantías de `_actions` (uno alterado es un 409 antes de contarlo) y, como el
  ledger solo crece, sube en uno con cada cambio y nunca baja. Mirar el estado vigente, firmar el
  asiento y calcular su versión van bajo el cerrojo del almacén (`change_safe_mode`): dos cambios
  cruzados se firman uno detrás de otro, cada uno con su versión, y no pasan los dos la regla de
  «no se repite el estado vigente».
- **`alert-resolution`** son los estados de Polaris `salud.py` (detectado → en arreglo →
  resuelto). No cambian el cálculo: una alerta resuelta cuyos datos siguen fuera sigue en la
  lista, y el tiempo hasta la acción no se mueve. Pruebas: `tests/test_alert_resolution.py`.
- **Crónica** (`app/timeline.py`, `GET /api/timeline/chronicle`): lectura de estos asientos y de
  los de §3.8, §3.15 y §3.17, con el número de asiento como clave estable. No escribe nada.
  Desde el 2026-10-07 lee también los silencios de alertas y las lecturas de cabina, y cuenta
  hechos que no son asientos (desde cuándo está una alerta, cambios de fase, excursiones): salen
  del estado ya calculado, su clave no es un número de asiento y su fuente lo dice. Un asiento
  se fecha con el instante de datos que declara (`reference_time`); si no declara ninguno, con
  su hora de firma, y la respuesta distingue los dos relojes (`time_basis`).
  Desde el 2026-10-23 lee también el historial misión a misión vigente (§3.17 quinquies; el último
  firmado por la consola y, con `until`, el que ya existía en el corte; uno mal formado es un
  409, como cualquier asiento de los que lee): cada misión previa es un hecho de la etapa
  `career`, antes del prevuelo, fechado en su inicio declarado con un tercer reloj
  (`time_basis` = `declared`: una fecha con día que declaró una persona, sin día de misión), con
  clave `ledger:<asiento>:mission:<n>` y fuente que dice de qué asiento sale y que EMMA no lo
  comprueba. Va primero en el orden de la crónica; no lleva nivel ni cotejo, y no lee el perfil.
- **Qué cuenta la crónica** (decisión del usuario, 2026-10-26). Lo que cuenta el estado, con sus
  mismas funciones (`routes._counts`, y para descartes y silencios `_acceptable_dismissal` y
  `_within_limits`): de los asientos de una persona —reconocimientos, «en arreglo», «resuelta»,
  descartes, silencios, contramedidas, eventos de misión y ubicaciones, estado de los sistemas,
  vínculos de sensores y recursos declarados—, solo los firmados por la consola y, para Tierra,
  los de su corte. Antes contaba cada uno lo firmara quien lo firmara, y un «resuelto» de otra
  identidad cerraba en la crónica un arreglo que el estado veía abierto. Lo que no cuenta **se
  omite**, no se marca: sigue en la cadena, que lo conserva y lo verifica, pero un hecho de la
  crónica es algo que EMMA tuvo en cuenta. El modo seguro no se filtra porque tampoco lo filtra
  el estado (vale el último asiento, de quien sea); la fase de contraste ya pedía la consola.
  Pruebas: `tests/test_timeline.py`; campaña `tests/mutants/timeline.json`.

### 3.20 bis Descartar una alerta (2026-10-26)

Decisión del usuario (2026-10-26): la conversación de ideación (`docs/contexto/conversacion-ideacion-v1.md`
L161-162) termina el flujo de una alerta en «HUMAN DECISION / Accept / Dismiss / Investigate».
Reconocer, «en arreglo» y «resuelta» cubrían aceptar e investigar; faltaba decir, con motivo, que
una alerta concreta no se considera real o ya tiene explicación. Tipo nuevo, firmado por
`crew-console` con el patrón de §3.8 (una acción humana que se registra, nunca una edición):

| Tipo | Campos | Reglas (rechazo) |
|---|---|---|
| `alert-dismissal` | `subject`, `domain`, `level`, `reference_time`, `reason` (`sensor_artifact`, `explained_by_context`, `other`), `note`, `declared_by` | la alerta tiene que existir en ese estado (409, como reconocer); motivo del vocabulario; `other` exige nota; persona con nombre (422) |

- **Por qué un tipo y no un cuarto estado de `alert-resolution`.** El descarte lleva un motivo de un
  vocabulario cerrado, y un campo nuevo en `alert-resolution` dejaría por mal formados los asientos
  ya firmados (`_actions` exige todos los campos del tipo). La palabra de cada motivo la da el
  backend (`DISMISSAL_REASONS` en `core/storage.py`, servida en `GET /api/alerts/dismissal-reasons`
  junto con la frase que explica lo que el descarte es); la interfaz no la redacta.
- **No cambia ningún cálculo.** No es un dato clínico: no entra en `observations` ni en el
  análisis. Niveles, riesgo, `rules_version`, detalle y tiempo hasta la acción son los mismos con o
  sin descarte (salvo el texto del paso «decisión humana» del flujo, que lo cuenta); la alerta sigue
  en `alerts`, con `dismissal` (motivo, su palabra, nota, quién y asiento) en vez de `null`.
- **No reconoce ni silencia.** Una alerta descartada sin reconocer sigue parpadeando y cuenta como
  pendiente: el reconocimiento (§3.8) y el anuncio (`alert-annunciation`) son otros asientos. Se
  puede reconocer después, y el reconocimiento no retira el descarte.
- **Qué cubre.** Lo mismo que un reconocimiento: ese dominio a ese nivel, mientras su
  `reference_time` siga dentro de la ventana de cálculo (`CURRENT_WINDOW`, 2 días). Un cambio de
  nivel es otra alerta y llega sin descartar; pasada la ventana, lo que siga alertando se apoya en
  lecturas nuevas y llega sin descartar. El descarte no inhibe ninguna alerta futura del mismo
  dominio: eso solo lo hace una inhibición (§3.8), con sus límites.
- **Relación con «en arreglo» y «resuelta».** Lo último que una persona dijo de la alerta es lo que
  se ve: un estado declarado (`alert-resolution`) firmado después del descarte lo deja atrás
  (`dismissal` vuelve a `null`), y un descarte firmado después de un estado lo muestra. Así,
  `dismissal` no nulo quiere decir que el descarte es lo último dicho; `resolution` sigue siendo el
  último estado declarado (un hecho firmado), y la consola no lo enseña como vigente mientras haya
  descarte: ofrece volver a «en arreglo». Lo que espera a una persona (`app/waiting.py`) tampoco
  cuenta como pendiente un «en arreglo» descartado después. Nada se borra: los dos asientos siguen
  en la cadena, en la historia de alertas y en la crónica.
- **Qué cuenta en el estado y en la historia.** Como toda acción sobre alertas: solo las firmadas
  por la consola, para Tierra solo las registradas antes de su corte (`_counts`), y solo las que
  la API habría aceptado (`_acceptable_dismissal`: un motivo fuera del vocabulario, `other` sin
  nota o un firmante sin letras no se enseñan, aunque los firme la consola por fuera de la API).
  La crónica, desde el 2026-10-26, con la misma regla y las mismas funciones (antes contaba lo
  firmado tal cual, lo firmara quien lo firmara; ver «Qué cuenta la crónica» en §3.20). Un descarte cuyo
  contenido no coincide con su hash firmado es un 409, como cualquier acción (`_actions`).
- **Dónde se lee.** `/api/status` (`alerts[].dismissal`), la historia de alertas (`kind` =
  `dismissal`, junto al episodio), la crónica (`alert-dismissed`, etapa de intervención, con su
  motivo y su nota; una nota que no cabe en los 280 caracteres del hecho se corta con «…»), el paso
  «decisión humana» del flujo de la alerta (descriptivo: no vuelve al nivel) y el PDF del estado.
  La tabla de auditoría de Tierra lo agrupa con la campana de las alertas.

Pruebas: `tests/test_alert_dismissal.py`; campaña `tests/mutants/alert_dismissal.json`.

### 3.21 Cifras de una analítica escaneada (2026-10-01)

Al subir un informe, `biomarcadores.parse_line` y `fecha_de` de Polaris (tal cual) leen sobre el
texto **antes** de des-identificarlo. El asiento `scanned-report` guarda solo lo estructurado
(`lab_readings`: fecha y, por lectura, analito, valor, unidad del catálogo, unidad leída, rango del
informe, confianza, comparador y si exige corrección), nunca la línea. El cociente BUN/creatinina
lo deriva `_añadir_bun_cr` de Polaris.

Ninguna cifra entra en el análisis por subir el informe. Una persona confirma cada una
(`POST /api/reports/{índice}/labs/confirm`) y `record_lab_reading` escribe **en un solo
`commit`** dos asientos:

| Tipo | Campos | Reglas (rechazo) |
|---|---|---|
| `vital-observation` | los de §3.14, `source` = `analitica:<índice>`, efectiva a medianoche UTC del día de extracción | — |
| `lab-confirmation` | `report_index`, `reading_index`, `confirmed_by`, `value`, `corrected`, `subject`, `observation_index` | informe vigente y sin manipular; mismo tripulante y acreditado como suyo (§3.19); la lectura existe y es de ese analito; persona con nombre; una sola vez (409) |

- Una lectura de unidad de otra familia o censurada («<9») solo se confirma con valor y unidad
  nuevos, y la unidad tiene que ser la del catálogo: EMMA no convierte (invariante 2).
- Los analitos que solo vienen de analítica (`LAB_REPORT_ONLY`) no entran por ninguna otra vía:
  `record_many` los rechaza.
- **Lo que devuelve el almacén es una copia profunda** (`_blob`, `_blob_entries`). Antes era
  superficial, y anotar el estado de una lectura en la lista de informes cambiaba el asiento
  firmado en memoria: la verificación lo denunció como manipulación. Prueba:
  `test_what_the_store_returns_is_a_copy_of_the_signed_entry`.

Pruebas: `tests/test_lab_readings.py`; mutantes `lab_readings.json` y `storage_lab_readings.json`.

### 3.22 Nota del informe de dolor, escrita o dictada (2026-10-01)

`pain-report` admite dos campos opcionales: `note` (texto del tripulante, hasta 1000 caracteres)
y `note_origin` (`escrita` o `dictada-revisada`). Un informe sin nota no los lleva. La nota
dictada la transcribe Whisper en local (`app/voice.py`, Polaris `transcribe_audios.py`) y vuelve
a la interfaz como **borrador**: nada se firma al transcribir. Se firma solo cuando la persona
envía el informe, y `note_origin` deja constancia de que un modelo escribió el primer texto.
Pruebas: `tests/test_voice.py`.

Desde el 2026-11-03 `note_origin` admite un tercer valor, `asistente-confirmada`: el asistente de
voz (`app/assistant/`) preparó el informe con lo que dijo la persona, que va como nota, y ella lo
confirmó antes de enviarlo por esta misma ruta. El asistente no firma nada; el PDF lo presenta así
(`export._note_heading`). Pruebas: `tests/test_assistant.py`.

### 3.23 La cita de una firma, cotejada contra el informe; objeciones del comité (2026-10-04)

- **`source_check` de un informe.** Si `source` es `informe:<n>` y la firma trae `source_fragment`,
  `source_check` es el resultado de `fuente_clinica.cotejar` de Polaris sobre el texto
  des-identificado de ese informe (`app/evidence/vault.py`):
  - `estado`: `confirmada`, `existe`, `no_existe`, `fragmento_ausente`, `fragmento_corto`,
    `identidad_ajena`…;
  - `detalle`;
  - `sha256` del texto cotejado, `sha256_fragmento`;
    - El `sha256` es el del texto des-identificado en UTF-8, páginas unidas por una línea en
      blanco y saltos de línea LF: el mismo en cualquier máquina (`tests/test_vault.py`).
    - Hasta el 2026-10-07, en Windows la copia de la bóveda se escribía con CRLF y la huella
      salía de esos bytes. Una firma anterior hecha en Windows lleva esa huella; no se reescribe.
  - `identidad`: el veredicto firmado en el informe, u "otro_paciente" si es de otro tripulante.
  - El fragmento y el texto no se guardan en `source_check`: solo sus huellas. Cada cotejo deja
    una línea en `vault/accesos.jsonl` del estado. (La segunda firma sí guarda, aparte, la frase
    literal que se vio: §3.24.)
  - No bloquea la firma. La copia del informe en la bóveda se regenera desde el asiento
    (comprobando su hash) y se borra si el informe se redacta.
  - **Un cotejo a la vez (2026-10-08).** El cotejo entero va bajo un cerrojo del proceso
    (`_LOCK` de `app/evidence/vault.py`): leer el asiento, poner la copia en la bóveda (o
    borrarla), sustituir los ganchos de Polaris y que `cotejar` la lea.
    - La copia se escribe en un fichero aparte (`informe-<n>.md.tmp`) y sustituye a la anterior
      de forma atómica (`os.replace`): si el proceso muere a media escritura, queda la copia
      anterior entera, no medio informe.
    - El `sha256` no cambia por ello: se escribe el mismo texto, en UTF-8 y con saltos LF.
    - Antes la copia se escribía fuera del cerrojo, y dos cotejos del mismo informe a la vez
      podían dar un `estado` o una huella que no eran los del informe.
    - Límite: el cerrojo es de un proceso. Dos procesos de EMMA sobre el mismo estado no están
      cubiertos.
    - Pruebas: `tests/test_vault.py`; mutantes en `tests/mutants/vault.json`.
- **`draft-interpretation` lleva `objections`:** cada objeción del comité, estructurada. Son
  `model`, `quote` (la frase citada, vacía si no contaba), `reason` y `counted` (si bloqueó).
  - Es lo mismo que `verifier_problems` y `discarded_objections`, sin aplanar.
  - El dosier del comité (Polaris `paso_consolidacion`, `app/committee_dossier.py`) se calcula
    de ahí al leer; no se guarda.
- **`pain-report`** (§3.22) y **`lab-confirmation`** (§3.21), sin cambios.

### 3.24 La frase literal de la fuente, en la segunda firma (2026-10-07)

Decisión del usuario (2026-10-07). No es un tipo de asiento nuevo: es un campo más del asiento
`draft-countersign` de §3.12, que sigue su mismo camino (`POST
/api/imaging/drafts/{i}/countersign`, `countersign_draft`, `_record_action`: un asiento encadenado
y firmado por `crew-console` en un solo `commit`).

- **Por qué.** `source_check` (§3.23) dice «confirmada» sobre un fragmento que alguien tecleó, y
  guarda solo huellas. Quien pone la segunda firma de una decisión de alto riesgo tiene que leer
  lo que el informe dice, y el registro tiene que conservar qué leyó.
- **Campo añadido: `source_quote`.** Lo lleva el asiento **solo** si la segunda firma cita un
  informe (`source` = `informe:<n>`). Las contrafirmas sin informe, y todas las firmadas antes de
  este cambio, no lo llevan: su payload, su hash y su firma son los de siempre y se verifican
  igual. `draft-signoff` (la primera firma) no cambia. (Esto vale para lo firmado hasta el
  2026-10-13; lo que cambió ese día está al final de esta sección.) Contenido:
  - `estado`: `localizada` o `no_localizada`;
  - `frase`: el tramo del texto **des-identificado** del informe que casa con el fragmento
    citado, **tal cual** está en la bóveda (con sus mayúsculas, signos y saltos de línea). Vacío
    si no se localiza: nunca es el fragmento tecleado ni una paráfrasis;
  - `puntero` (`informe:<n>`), `informe` y `asiento` (el índice del asiento `scanned-report`),
    `inicio` y `fin` (posición de la frase, en caracteres, dentro de ese texto);
  - `sha256`: la huella del texto de la bóveda del que sale la frase (la de §3.23: UTF-8, páginas
    unidas por una línea en blanco, saltos LF);
  - `desidentificado`: siempre verdadero; `detalle`: el motivo, el del cotejo si no se localizó;
  - `vista`: si la firma declaró lo que vio (abajo).
- **De dónde sale la frase** (`app/evidence/vault.py`, `locate`). Solo si `fuente_clinica.cotejar`
  de Polaris da `confirmada` (informe vigente, del mismo tripulante, fragmento de longitud
  suficiente y presente). Entonces se lee la copia de la bóveda, se exige que su SHA-256 sea el
  que `cotejar` acaba de devolver, y se toma el tramo cuya forma normalizada —con el `normaliza`
  de la copia de Polaris— es la del fragmento. Si la normalización propia con la que se calcula
  la posición no da lo mismo que la de Polaris, o la frase extraída no normaliza a lo citado:
  `no_localizada`. La lectura deja su propia línea en `vault/accesos.jsonl` (`FRASE-…`, quién e
  informe; no el texto).
- **El cotejo y la lectura, bajo un mismo cerrojo (2026-10-08).** `locate` toma el cerrojo de
  §3.23 una sola vez para las dos cosas, de modo que ningún otro cotejo del proceso rehace o
  borra la copia entre que `cotejar` la lee y se saca de ella la frase. La comprobación de la
  huella de arriba se mantiene. Mismo límite que en §3.23: un solo proceso.
- **Ver antes de firmar.** `POST /api/imaging/drafts/{i}/source-quote` devuelve el cotejo y esa
  misma frase. Es una lectura: no escribe en el ledger y no sale a la red (una fuente que no es
  un informe da `no_aplica`, sin consultar ningún registro).
- **Se firma lo que se vio** (patrón de `text_sha256`, §3.12). La segunda firma puede traer
  `seen_quote` (`estado`, `frase`, `sha256` de lo que vio). `countersign_draft` vuelve a sacar la
  frase de la bóveda en el momento de firmar y, bajo el cerrojo del almacén, exige que estado,
  frase y huella sean los vistos; si no (el informe se redactó, o se cita otro fragmento), 409 y
  no hay asiento. Lo que se guarda es siempre lo que da la bóveda al firmar, con `vista: true`.
  La frase se lee antes de tomar ese cerrojo; por eso, ya dentro, se vuelve a exigir que el
  informe citado siga vigente (`report_blob`): si se redactó entre medias, 409 y no hay asiento.
  La lectura de la bóveda queda anotada en `accesos.jsonl` aunque la firma se rechace después:
  el registro de accesos dice quién leyó, no quién firmó.
- **Lo que se admitía hasta el 2026-10-13.** La fuente no bloqueaba la firma (§3.19): se podía
  contrafirmar con la cita `no_localizada`, y el asiento lo decía. Y una segunda firma que citara
  un informe sin `seen_quote` se aceptaba: el asiento llevaba la frase de la bóveda con
  `vista: false`. Endurecerlo era decisión del usuario; la tomó ese día (abajo).
- **Lo que esto supone para la redacción (§3.6).** La frase es texto des-identificado del
  informe y ahora vive también en el asiento de la segunda firma. Redactar el informe borra su
  texto y su copia en la bóveda, pero **no** la frase ya citada: para retirarla hay que redactar
  también el asiento `draft-countersign`, que deja su lápida como cualquier otro.
- **Límite.** Acredita procedencia (esa frase está en ese texto), no fidelidad (que sostenga lo
  que se firma): eso sigue siendo juicio de quien firma. La persona que firma es declarada, sin
  autenticar, como en el resto de la consola.

Pruebas: `tests/test_source_quote.py`; mutantes en `tests/mutants/source_quote.json` y
`tests/mutants/storage_source_quote.json`.

#### La regla del 2026-10-13: la segunda firma se rechaza sin la frase localizada y vista

Decisión del usuario (2026-10-13), las tres cosas: una contrafirma se **rechaza** si la cita no se
localiza en el informe, se rechaza si quien firma no declara haber visto la frase, y la frase se
enseña también en la **primera** firma. No hay tipo de asiento nuevo ni campo obligatorio nuevo en
lo ya firmado. La regla y sus textos viven en un solo sitio, `app/countersign_rule.py`.

- **Qué se rechaza.** Una segunda firma cuya `source` es `informe:<n>` —la única fuente que se
  puede cotejar— no se escribe si (a) la bóveda no localiza la cita (`estado` distinto de
  `localizada`: el fragmento no está, es demasiado corto, el informe no existe, está redactado o
  no acredita ser del mismo tripulante), o (b) la petición no trae `seen_quote`. Quien se niega es
  el almacén (`countersign_draft` → `_quoted(..., strict=True)` → `CountersignRefused`), bajo su
  cerrojo y antes de `_record_action`: **no hay asiento**, ni de firma ni de rechazo. La ruta lo
  devuelve como **422** con el motivo en `detail` (nombra el puntero y el motivo del cotejo;
  nunca el fragmento tecleado ni la frase). El rechazo no se registra en el ledger; la lectura de
  la bóveda que lo precede sí deja su línea en `accesos.jsonl`, como antes.
- **Orden de las comprobaciones.** Primero las de §3.12 (primera firma, alto riesgo, otra
  persona, misma huella, sin segunda firma previa: 409) y que el informe citado siga vigente
  (409); después, si la firma declara lo que vio, que sea lo que la bóveda da ahora (409, «vuelve
  a ver la frase»); y por último la regla nueva (422). Así, quien vio una frase de un informe que
  se redactó después recibe un 409 —lo que vio ya no está— y no un «no localizada».
- **Lo que NO se puede cotejar, y no se rechazaba (hasta el 2026-10-15).** `source` es texto
  libre (§3.19): un PMID, un DOI, un NCT, una contramedida o cualquier otra cosa. Para esas
  fuentes no hay frase que localizar. Hasta el 2026-10-15 la segunda firma se admitía, y el
  asiento lo decía: lleva `source_quote` con `estado` = `no_aplica`, `frase` vacía y `detalle` =
  «la fuente no es un informe guardado: no hay frase que cotejar», **sin** `vista` (no hay nada
  que declarar visto). Una segunda firma que no citaba nada tampoco se rechazaba, y su asiento es
  el de siempre, sin el campo. **Límite que se declaraba:** la regla solo obligaba a quien citaba
  un informe; bastaba citar otra fuente, o ninguna, para que no se aplicara. Se cerró el
  2026-10-15 (abajo): esas dos segundas firmas ya no se escriben, y las ya escritas no cambian.
- **Admitida no es callada (2026-10-14).** Hasta entonces el «no cotejable» solo quedaba dentro
  del asiento, y en la consola una segunda firma sin cotejo se veía igual que una cotejada. Ahora
  la respuesta de `POST /api/imaging/drafts/{i}/countersign` lleva `collation` y cada borrador de
  `GET /api/imaging/studies/{n}/drafts` lleva, al lado del asiento y no dentro,
  `countersign_collation`: `collated`, `label` («cotejada» / «no cotejada»), `why` y `text`, que
  la consola pinta tal cual (gris, «no disponible» de la tabla F.5-1). Solo es «cotejada» la que
  lleva la frase `localizada` y `vista: true`; el porqué de las demás sale de lo que dice el
  asiento: fuente que no es un informe, ninguna fuente, cita no localizada, frase no declarada
  vista, o —en las anteriores al cambio— un asiento sin frase guardada. Lo deriva
  `countersign_rule.collation` al **leer**: ningún campo nuevo en el asiento, nada se rechaza por
  ello y los hashes de lo ya firmado no cambian (misma prueba con `countersign_pre_strict.db`).
- **Antes de intentarlo.** `POST /api/imaging/drafts/{i}/source-quote` devuelve además
  `second_signature`: `collatable`, `allowed` y `reason` (el mismo texto con el que la firma se
  rechazaría). Hasta el 2026-10-15 llevaba también `note`, el aviso de fuente no cotejable que
  se admitía; desde entonces esa fuente se rechaza y el aviso es su `reason`. `GET
  /api/imaging/studies/{n}/drafts` lleva en cada borrador `second_signature_rule` (los textos de
  la regla, para que la consola los pinte sin redactarlos). Son lecturas: no escriben nada.
- **Lo ya firmado no cambia.** Las contrafirmas anteriores con `no_localizada` o con
  `vista: false`, y las que citaban otra fuente sin `source_quote`, siguen en la cadena con su
  payload, su hash y su firma, y `verify_integrity` las da por buenas igual. No se reescriben, no
  se enmiendan y no se marcan. Lo único que cambia es al **leer**: la lista de borradores añade,
  al lado del asiento y no dentro, `countersign_note` —«Contrafirmada antes del 2026-10-13, con la
  regla anterior…»—, deducido de lo que el asiento dice (no de su fecha) por
  `countersign_rule.prior_rule_note`. Prueba con un ledger escrito por el código anterior al
  cambio (`tests/data/countersign_pre_strict.db`): hashes de contenido idénticos, lectura entera
  y la regla nueva aplicada a un borrador nuevo sobre esa misma cadena.
- **La frase, también en la primera firma (`draft-signoff`).** La primera firma ya podía citar
  una fuente (§3.19) y cotejar un informe (§3.23). Ahora quien la pone puede pedir la frase con la
  misma lectura (`source-quote`) y devolver `seen_quote`; entonces el asiento lleva `source_quote`
  con los mismos campos que en la segunda firma, y con las mismas dos garantías: se firma lo que
  se vio (409 si la bóveda ya no da eso) y el informe tiene que seguir vigente bajo el cerrojo.
  Es **opcional y no bloquea**: la decisión del usuario solo endurece la segunda firma, y una
  cita `no_localizada` en la primera se firma y queda dicha. Sin `seen_quote`, la ruta no saca
  ninguna frase de la bóveda (no queda una línea `FRASE-…` de una lectura que nadie pidió) y el
  asiento es el de siempre, sin el campo: los `draft-signoff` anteriores se verifican igual.
  Consecuencia para la redacción (§3.6), la misma que arriba: la frase vive ahora también en ese
  asiento, y para retirarla hay que redactarlo.
- **Qué no es.** No es una regla del motor: no entra en el análisis, en los niveles ni en las
  alertas, ni en la huella de `core/versioning.py`. Solo decide si se escribe un asiento de
  firma. El borrador sigue segregado (§2.1 de `software-safety-classification.md`). Y el límite
  de arriba no cambia: localizar la frase acredita procedencia, no que sostenga la decisión.

Pruebas: `tests/test_countersign_strict.py` (y los dos casos de `tests/test_source_quote.py` que
describían la regla anterior, ahora con 422); mutantes en `tests/mutants/countersign_rule.json`,
`countersign_strict.json` y `countersign_route.json`.

#### La regla del 2026-10-15: toda segunda firma de alto riesgo cita un informe guardado

Decisión del usuario (2026-10-15). Cierra el límite declarado de arriba: toda contrafirma de
alto riesgo tiene que citar un informe guardado (`informe:<n>`), con la frase localizada en él y
declarada vista; si no, se rechaza sin escribir asiento. No hay tipo de asiento nuevo ni campo
nuevo: lo que cambia es qué asientos `draft-countersign` se dejan escribir. La regla y sus textos
siguen en `app/countersign_rule.py`.

- **Qué se rechaza, además.** Una segunda firma cuya `source` no es `informe:<n>` (un PMID, un
  DOI, un NCT, una contramedida, cualquier otro texto) o que no cita nada. Quien se niega es el
  almacén, igual que con la regla del 2026-10-13: `countersign_draft` → `_quoted(...,
  strict=True)` → `CountersignRefused`, bajo su cerrojo y antes de `_record_action`. **No hay
  asiento**, ni de firma ni de rechazo; la ruta devuelve **422** con el motivo («no cita ninguna
  fuente» o «la fuente citada no es un informe guardado y no hay frase que cotejar», seguido de lo
  que hace falta). El motivo no repite la fuente tecleada.
- **Riesgo alto, y solo ahí.** No existe segunda firma que no sea de alto riesgo: el almacén solo
  la admite si la primera registró `high_risk.applies` (409 si no, §3.12). La primera firma
  (`draft-signoff`) no cambia: con o sin fuente, con o sin informe, se escribe como antes, y una
  decisión que no es de alto riesgo no pide segunda firma.
- **Orden de las comprobaciones.** El de arriba, sin cambios: primero las de §3.12 (409), después
  que lo visto sea lo que da la bóveda (409), y al final la regla (422). Una segunda firma de la
  misma persona sigue dando 409 cite lo que cite.
- **Sin red para rechazar.** Hasta ahora la ruta consultaba en su registro un PMID, DOI o NCT
  citado en la segunda firma (`evidence/source_check.py`, con red solo si no está en modo sin red)
  y guardaba el resultado en el asiento. Como esa segunda firma ya no se escribe, la ruta no la
  consulta: rechazarla no sale a la red. La primera firma sí la sigue consultando, como antes.
- **Antes de firmar.** `second_signature_rule` gana `must_cite` (lo que hace falta: citar un
  informe guardado, con la frase localizada y declarada leída); `not_collatable` dice ahora que
  esa fuente no se admite; `since` es la fecha de la regla vigente. La lectura previa
  (`source-quote`) da `allowed: false` y el `reason` del 422 para una fuente que no es un informe
  y, sin fuente, el de «no cita ninguna fuente». La consola no ofrece la segunda firma hasta que
  se cita un informe, se pide la frase, está localizada y se declara leída, y en cada paso enseña
  con el texto del backend qué falta (`frontend/src/imaging/sourceQuote.ts`).
- **Lo ya firmado no cambia.** Las contrafirmas escritas antes con `no_aplica`, sin fuente o con
  una fuente sin `source_quote` siguen en la cadena con su payload, su hash y su firma, y
  `verify_integrity` las da por buenas. Al leerlas, `countersign_note` las rotula —«Contrafirmada
  antes del 2026-10-15, con la regla anterior: entonces se admitía una segunda firma citando una
  fuente que no es un informe guardado / sin citar ninguna fuente / sin guardar en el asiento una
  frase cotejada de la fuente que cita…»—, deducido de lo que dice el asiento, y
  `countersign_collation` las sigue diciendo «no cotejada» con su motivo. La fecha del rótulo es
  la de la parte de la regla que no cumplen (2026-10-13 para la cita no localizada o la frase no
  declarada vista). Prueba con un ledger escrito por `main` en 534f276, anterior a este cambio
  (`tests/data/countersign_pre_cite.db`: una contrafirma con PMID y `no_aplica`, una sin fuente y
  una cotejada): hashes de contenido idénticos, lectura entera, rótulos al lado del asiento y la
  regla nueva aplicada a un borrador nuevo sobre esa misma cadena. La del PMID sin `source_quote`
  de `countersign_pre_strict.db` también se rotula ahora.
- **Qué no es.** Igual que arriba: ni regla del motor ni de la huella de `core/versioning.py`;
  solo decide si se escribe un asiento de firma. Y el mismo límite: localizar la frase acredita
  procedencia, no que sostenga la decisión.

Pruebas: `tests/test_countersign_strict.py`, `tests/test_source_quote.py` (la contrafirma sin
informe, ahora 422) y `tests/test_decision_risk.py` (la segunda firma de alto riesgo, ahora con
su cita); mutantes en las mismas tres campañas.

### 3.25 Notas de Tierra a bordo (2026-10-26)

Decisión del usuario (2026-10-26): la conversación de ideación (`docs/contexto/conversacion-ideacion-v1.md`
L182, L190, L510) pide que el nodo de a bordo, cuando hay enlace, «permite supervisión médica» desde
Tierra, con una sincronización en los dos sentidos. Hasta aquí todo asiento lo firmaba a bordo una
fuente o la consola de tripulación; la consola de Tierra solo leía. Tipo nuevo, firmado por una
identidad nueva, `ground-console`, con el patrón de §3.8 (una acción humana que se registra, nunca
una edición):

| Tipo | Campos | Reglas (rechazo con 422) |
|---|---|---|
| `ground-note` | `subject` (un tripulante o `tripulacion`), `kind` (`information`, `question`), `text`, `signed_by` | clase del vocabulario; texto con letras y de 600 caracteres como mucho; una `question` lleva «?»; el texto pasa `text_guard.check` (dosis, diagnóstico, certeza, orden y tratamiento, absolutos) y no lleva formas de mandato fuera de una pregunta (`core/ground_notes.MANDATE`: «debe», «tiene que», «hay que», «es obligatorio», «ordeno», el imperativo de cortesía de los verbos de pauta, con hasta dos pronombres pegados; una pregunta va de «¿» a «?» sin cruzar un fin de frase, o sin «¿» desde el último corte de frase o de cláusula, y una orden con coletilla «, ¿vale?» sigue siendo orden; el imperativo de pauta solo lo tapa una pregunta abierta con «¿»; desde 2026-10-31, qué es una pregunta lo dice una regla común con el filtro general, `text_guard.stated` y `text_guard.outside_opened_questions`, mientras que el imperativo de pauta sigue siendo solo de las notas); persona con nombre; el destinatario es un tripulante con lecturas o toda la tripulación |

- **Quién firma y cuándo.** La clave es la de la consola de Tierra (`routes.GROUND_IDENTITY`),
  distinta de la de a bordo y reservada: la ingesta pública no puede firmar como ella
  (`_is_reserved_source`). `signed_by` es lo declarado, sin autenticar, como en toda acción de
  consola (§7.5). La hora de firma es la del asiento (`recorded`); no hay un campo aparte que
  pudiera contradecirla. **Límite:** la clave dice por qué ruta entró la nota, no desde qué
  máquina. La API no autentica, así que cualquier cliente que llegue a `POST /api/ground-notes`
  firma como Tierra, del mismo modo que cualquiera que llegue a reconocer una alerta firma como la
  consola de a bordo; lo que la clave sí impide es que una lectura, o una acción de la consola de
  a bordo, pase por una nota de Tierra.
- **El retardo.** La nota viaja cuando se firma. `GET /api/ground-notes?subject=…&until=…` entrega
  lo firmado hasta `until` (`recorded <= until`), y la consola de tripulación lo pide con el reloj
  menos un tiempo de luz (`arrivalCut`, la cuenta con que la consola de Tierra corta lo que baja).
  Lo firmado después **no se entrega ni se cuenta**: a bordo no se puede saber que hay una nota en
  camino. Sin efemérides no hay retardo que aplicar y se entrega todo, y la consola lo dice.
- **Qué se enseña.** Solo lo firmado por `ground-console` y que la regla vigente aceptaría
  (`ground_notes.problem` al leer, como `_acceptable_dismissal` en §3.20 bis): una nota firmada con
  otra clave, o cuyo texto el filtro de hoy rechaza aunque lo aceptara el de ayer, no se enseña y
  se cuenta en `withheld`, con su frase. Una nota cuyo contenido no coincide con su hash firmado es
  un 409, como cualquier acción (`_actions`).
- **No cambia ningún cálculo.** No es una lectura: no entra en `observations` ni en el análisis.
  Niveles, alertas, reconocimientos, riesgo y `rules_version` son los mismos con o sin nota
  (`test_a_note_changes_no_level_alert_or_rules_version`). Tampoco es una acción sobre alertas: la
  clave de Tierra no reconoce, silencia ni descarta nada (el estado solo cuenta lo firmado por
  `crew-console`).
- **Sin borrado ni edición.** Una nota equivocada se corrige con otra. La redacción de §3.6 la
  retira como a cualquier asiento: su lápida queda, y `_actions` ya no la entrega.
- **Límite.** El filtro es de patrones: una pauta en tono suave y sin palabras gatillo pasa, y
  alguna frase inocente se rechaza («dosis» de radiación, «1 g»; los falsos positivos de siempre
  del filtro, más el subjuntivo de un verbo de pauta en una subordinada). La barrera de fondo es
  que la nota no decide nada: informa o pregunta, y quien la lee decide.

Pruebas: `tests/test_ground_notes.py`; campaña `tests/mutants/ground_notes.json`.

### 3.26 La versión de las reglas, firmada con cada decisión (2026-10-31)

Decisión del plan de la decimonovena ronda (U9). La especificación (§12) pide que «todo
modelo/regla debe estar versionado y disponer de trazabilidad/audit trail». La huella de las reglas
(`core/versioning.rules_version`, «reglas@…») iba en la respuesta del estado y en las instantáneas
de proyección (§3.18), pero **no** en los asientos de las decisiones humanas; y como la historia de
alertas cerradas se recalcula con las reglas de hoy, no se podía saber con qué reglas salió la
alerta que alguien firmó. No es un tipo de asiento nuevo: los asientos de decisión de §3.8, §3.15,
§3.15 bis, §3.20 y §3.20 bis ganan **un campo opcional**.

| Asiento | Campo | Contenido |
|---|---|---|
| `alert-acknowledgement`, `alert-resolution`, `alert-dismissal`, `countermeasure-followup` (`adopted`, `closed` y `declined`) | `rules_version` | La huella vigente en el momento de firmar, tal cual la da `rules_version()` («reglas@» y 16 hexadecimales) |

- **Quién lo pone.** La ruta que firma —`POST /api/alerts/acknowledge`, `/alerts/resolution`,
  `/alerts/dismissal`, `/countermeasures/adopt`, `/close` y `/decline`—, con la huella del proceso
  en ese instante. El cliente no lo manda: ningún cuerpo tiene ese campo y todos rechazan los que
  sobran (422). El almacén (`storage._decided_with`) recibe el texto y lo guarda; no calcula la
  huella (no importa `versioning`, que importa el análisis). Si se da, no va en blanco: el almacén
  lo rechaza y no escribe nada. Recorre el camino de siempre (`_record_action`: un asiento
  encadenado y firmado por `crew-console` en un solo `commit`), invariante 4.
- **Lo ya firmado no cambia y sigue verificándose.** El campo es opcional en la lectura
  (`_actions(..., optional=_DECIDED_WITH_OPTIONAL)`; en el seguimiento, junto a los de §3.15 ter):
  un asiento firmado antes no lo lleva, conserva su payload, su hash y su firma, y se entrega con
  sus campos de siempre. Un asiento nuevo firmado sin él (por fuera de las rutas) es, campo por
  campo, el de antes del cambio. Prueba: un ledger con las seis decisiones escrito con el código
  anterior al cambio (`tests/data/decisions_pre_rules_version.db`, generado con `main` en
  `6372fad`) se abre, se verifica, entrega sus seis asientos con los hashes de contenido que firmó
  aquel código, admite después un reconocimiento con la versión y vuelve a verificarse.
- **Cómo se lee, y qué no se hace.** Una sola redacción (`versioning.decided_with`), para el
  detalle de alerta (`acknowledgement_rules`, `resolution.rules`, `dismissal.rules` en cada alerta
  de `/api/status`), el seguimiento (`adoption_rules`, `closure_rules` en `followups`), el «no»
  (`decision.rules` en cada recomendación), la historia recalculada (`rules` en cada entrada de
  `signed`; `null` en los anuncios, que no llevan el campo) y la crónica (la fuente del hecho: «asiento 12;
  decidido con reglas@…; misma versión que hoy»): **«decidido con reglas@…; misma versión que
  hoy»**, **«decidido con reglas@…; distinta de la de hoy: reglas@… hoy»**, o **«sin versión
  registrada: el asiento no la lleva»** para lo firmado antes del campo o por fuera de las rutas.
  Se compara la huella firmada con la de hoy y se dice; **no se recalcula nada ni cambia el
  veredicto**: una alerta reconocida con otras reglas sigue siendo la que se reconoció. La interfaz
  enseña la frase tal cual, sin color: es información, no una señal.
- **No es una regla ni decide.** El campo no entra en `FINGERPRINTED`: `rules_version()` es la
  misma antes y después de este cambio (`reglas@c89d7ebf4d5f4aa9` el día del cambio; la cifra
  vigente la da `/api/status`). Tampoco entra en `observations`, en el análisis ni en la
  puntuación: el mismo ledger, leído con el campo y sin él, da el mismo estado salvo las frases
  (`test_the_verdict_is_identical_with_and_without_the_field`, invariante 5).
- **FHIR.** Estos asientos no se serializan hoy como recurso FHIR (§4: `AuditEvent` es diseño, no
  implementado). Cuando se exporten, `rules_version` irá como extensión propia de EMMA junto a
  `prev_hash`, `signature` y `merkle_leaf` (§4), no como campo estándar: `AuditEvent` no tiene
  elemento para la versión de las reglas con que se decidió.
- **Límite.** La huella dice qué **valores** de reglas regían (umbrales, ventanas, catálogo,
  límites de hábitat, biblioteca de contramedidas: `versioning.FINGERPRINTED`), no qué código
  corría ni qué datos había: eso lo dicen el asiento (`reference_time`) y el ledger. Una regla que
  cambie fuera de la lista vigilada (`GUARDED`, un número dentro de una función) no cambia la
  huella, y eso ya lo declara `core/versioning.py`.

Pruebas: `tests/test_decided_with_rules.py`; campañas `tests/mutants/decided_with_rules.json`
(almacén, redacción y crónica) y `tests/mutants/decided_with_rules_api.json` (rutas, seguimiento
y «no»).

### 3.27 Nivel de misión: desconexión progresiva (2026-11-02)

Idea del equipo para el evento (2026-11-02): «un protocolo de desconexión progresiva de funciones
para ver lo mínimo básico en ambientes con restricción de recursos, sobre todo energéticos y
humanos». Con la energía racionada o la tripulación sin tiempo, la consola seguía esperando cada
muestra y cada ecografía. Tipo nuevo, firmado por `crew-console` con el patrón de §3.8 (una acción
humana que se registra, nunca una edición) y las garantías de versión del modo seguro (§3.20):

| Tipo | Campos | Reglas |
|---|---|---|
| `mission-mode` | `subject` (= `sistema`), `level` (`nominal`, `reduced`, `minimal`), `reason`, `declared_by`; con cita, además `cited_system` (`power`, `communications`) y `cited_state` (el estado declarado del sistema entero al firmar) | persona con nombre; bajar exige motivo y puede saltar niveles; subir no exige motivo y va de un nivel en un nivel; no se repite el nivel vigente (409 lo que choca con el vigente; 422 lo demás, sin asiento) |

- **Quién baja y quién sube.** El modo seguro toma de Polaris (`codigo_rojo`) «lo activa
  cualquiera con motivo, lo levanta una persona». Aquí la dirección protectora es bajar: lo firma
  cualquiera con nombre y un motivo, también de nominal a mínimo de una vez. Subir es volver a
  comprometer muestras, consumibles y tiempo: lo firma una persona con nombre, un nivel cada vez,
  cada paso con su asiento. Las reglas las aplica el almacén (`storage._change_mission_mode`, con
  `core/mission_modes.check_change`) bajo su cerrojo, como `change_safe_mode`: mirar el nivel,
  leer el sistema citado y firmar van juntos, y dos cambios cruzados no pasan los dos.
- **Qué cuenta.** Vale el último asiento firmado por la consola y, para Tierra, el que ya existía
  en su corte (`GET /api/mission-mode?until=…`, `identities.action_counts`, como toda acción del
  operador). `version` es cuántos de esos asientos hay (hasta el corte, con `until`) y
  `store_epoch` de qué almacén: ni una ni otra son campos firmados (§3.20). Un asiento que no
  coincide con su hash, al que le falta un campo, cuyo `level` no está en el vocabulario o cuya
  cita va a medias (sistema sin estado o al revés) o fuera del vocabulario del hábitat es un 409
  (`mission_modes.entry_problem`), sea el último o uno anterior: no se adivina qué quiso decir ni
  se cuenta en la versión como un cambio válido. **Límite**, el mismo del modo seguro: un asiento
  redactado (§3.6) ya no lo entrega `_actions`, y la versión baja en uno.
- **La cita.** `cited_system` es opcional y solo admite los sistemas citables del vocabulario
  (`data/mission_modes.json`: energía y comunicaciones). El cliente no manda `cited_state` (el
  cuerpo rechaza lo que sobra, 422): lo pone el almacén con la última declaración del sistema
  entero firmada por la consola (§3.16 bis; una de un módulo no cuenta), o `undeclared`. Se firma
  lo que constaba entonces, el mismo que enseña el panel del hábitat (`systems.overview`); una
  declaración posterior no lo reescribe. EMMA no mide la energía ni
  el enlace, y no escribe vatios: no hay potencia de los equipos con fuente.
- **Qué se espera en cada nivel.** `core/mission_modes.py` sobre `data/mission_modes.json`,
  rotulado «vocabulario de diseño de EMMA». Cada nivel nombra las clases de medida y el gasto de
  consumibles del coste de medir (`ingest/cost.py`, `measurement_cost.json`) que se siguen
  esperando; un calculado sigue a sus entradas; la única lista a mano (`also_expected`, síntomas y
  dolor en mínimo) lleva motivo. El cargador falla si una clase o un consumible no existen, si lo
  añadido a mano no está en el catálogo o pide muestra, laboratorio, consumibles o análisis en
  Tierra, si nominal no lo espera todo o si bajar añade medidas. `expected_measurements(level)` es
  la pieza que leen las rutinas: lo suspendido no se da por atrasado ni roto.
- **En la crónica.** `app/timeline.py` cuenta cada asiento que cuenta el estado (los mismos, con
  `action_counts` y el corte `until` de Tierra) como hecho `mission-mode-change`, en su hora de
  firma (no declara instante de datos, como el modo seguro), con el nivel anterior y el nuevo,
  `declared_by`, el motivo y la cita. El anterior sale de esos mismos asientos en orden
  (`mission_modes.history`): con uno redactado, el siguiente cuenta desde el que queda, coherente
  con la versión que baja en uno. Un asiento inservible (`entry_problem`) es el mismo 409 que en
  el estado. La frase la redacta el backend (`mission_modes.chronicle_sentence`) y no manda nada.
- **No cambia ningún cálculo.** No es una lectura ni una regla de `rules_version`: ningún módulo de
  `analysis/`, `advisor/`, `ingest/`, `api/routes.py` ni `core/egress.py` lo importa (lo comprueba
  una prueba). La ingesta, la línea base, la tendencia, el riesgo, las alertas y el modo seguro son
  los mismos en cualquier nivel: con el mismo dato, el estado y las alertas son idénticos
  (`test_status_and_alerts_are_identical_at_every_level`), y una medida suspendida que llega entra
  por el ledger y se analiza (invariante 5: el análisis y las alertas no se apagan).
- **El aviso.** Fuera de nominal, `notice` (como `halt_notice`): lo redacta el backend, no lleva el
  motivo libre de quien firmó, pasa `text_guard.check` y no manda nada (invariante 7).
- **Sin borrado ni edición.** Un nivel equivocado se corrige firmando otro. La redacción de §3.6 lo
  retira como a cualquier asiento.

Pruebas: `tests/test_mission_mode.py`, y la crónica en `tests/test_timeline.py`; campaña `tests/mutants/mission_mode.json` (almacén y
reglas).

### 3.28 Entorno de la misión declarado (2026-11-04)

Petición del usuario: «poder elegir el entorno: como está seleccionado entorno de la misión Tránsito
a Marte, poder elegir las otras opciones como órbita baja». Hasta aquí el perfil de misión
(`evidence/mission_profiles.py`) salía solo de la configuración (`EMMA_MISSION_PROFILE`), y
cambiarlo pedía reiniciar sin dejar constancia. Tipo nuevo, firmado por `crew-console` con el patrón
del nivel de misión (§3.27):

| Tipo | Campos | Reglas |
|---|---|---|
| `mission-profile` | `subject` (= `sistema`), `profile` (uno de `mission_profiles.EXPECTED_IDS`), `previous` (el entorno vigente al firmar, que en el primer cambio es el de la configuración), `reason` (opcional, ≤ 300), `declared_by` | persona con nombre; el motivo es opcional; no se repite el entorno vigente (409); un entorno fuera del catálogo, un campo de más (`previous` lo pone el almacén) o un firmante sin nombre es un 422, sin asiento |

- **Quién y cómo.** `POST /api/mission/profile`, solo desde la consola de a bordo (Tierra lo ve y
  no lo declara, como el nivel). Las reglas las aplica el almacén
  (`storage._change_mission_profile`, con `core/mission_profile_changes.check_change`) bajo su
  cerrojo: mirar el vigente y firmar van juntos, y dos declaraciones cruzadas no pasan las dos.
- **Qué cuenta.** Vale el último asiento firmado por la consola y, para Tierra, el que ya existía en
  su corte (`GET /api/mission/profile?until=…`, `identities.action_counts`); sin asientos, el de la
  configuración, con `source` = `configuración` (con asiento, `registro`). `version` y
  `store_epoch` como en §3.27, sin firmar. Un asiento que no coincide con su hash, al que le falta
  un campo, cuyo `profile` no está en el catálogo o que repite el que dejaba atrás es un 409
  (`mission_profile_changes.entry_problem`), sea el último o uno anterior, también en la matriz y en
  la crónica. **Límite**, el de §3.27: uno redactado (§3.6) ya no lo entrega `_actions`.
- **Lo que lo lee.** `/api/status` (`mission.profile`, con `declaration`) y `/api/mission/profiles`
  (la columna señalada, también con `until`) describen el entorno vigente. La crónica
  (`app/timeline.py`) cuenta cada asiento que cuenta el estado como hecho `mission-profile-change`,
  en su hora de firma, con el anterior y el nuevo tal como se firmaron y el motivo
  (`mission_profile_changes.chronicle_sentence`).
- **Solo cambia hacia dónde se mide.** Descriptivo, como el perfil (decisión del usuario,
  2026-10-13): el riesgo sale del tiempo de luz real de las efemérides. Desde el 2026-11-11
  (decisión del usuario) el entorno vigente decide además el cuerpo de esas efemérides
  (`mission_profiles.ephemeris_target`; uno sin cuerpo no las consulta y no escala el riesgo), así
  que un cambio firmado puede mover el factor de aislamiento, y nada más. Ningún módulo de
  `analysis/` ni de `advisor/` lo importa, y fuera de ese tiempo de luz el estado entero, salvo
  `mission.profile` y la cobertura de efemérides, es idéntico antes y después de declarar otro
  entorno (`test_status_levels_and_alerts_are_identical_before_and_after_a_declared_change`,
  `test_the_profile_acts_only_through_the_light_time_of_its_target`, invariante 5). No entra en
  `rules_version`.
- **Por voz.** El asistente propone el cuerpo (`mission_profile`), sin firmante; firma la interfaz
  por la misma ruta tras «confirmo» (§3.27, `software-safety-classification.md` §2.2).
- **Sin borrado ni edición.** Un entorno equivocado se corrige declarando otro.

Pruebas: `tests/test_mission_profile_declaration.py` (y la propuesta por voz en
`tests/test_assistant.py`); campaña `tests/mutants/mission_profile_declaration.json`.

### 3.29 Enlace con Tierra simulado: caído y restablecido (2026-11-05)

Del ideograma del usuario: P3, «Sincronizar con enlace roto» (idea 10 de
`docs/contexto/prioridades-evento.md`, «sincronización diferida con enlace roto»). La consola de
Tierra solo descontaba el tiempo de luz. Suponía el enlace siempre arriba y seguía avanzando aunque
a bordo se supiera que no lo estaba. Tipo nuevo, firmado por `crew-console` con el patrón de §3.8
(una acción humana que se registra, nunca una edición):

| Tipo | Campos | Reglas |
|---|---|---|
| `simulated-link` | `subject` (= `sistema`), `state` (`down`, `up`), `at` (el instante al que se refiere quien declara, en la hora de los datos; con zona), `note` (≤ 300, opcional), `declared_by` | persona con nombre; no se repite el estado vigente (sin asientos, arriba); `at` no es anterior al del último cambio (409 lo que choca con lo firmado; 422 lo demás, sin asiento) |

- **No es la declaración del sistema Comunicaciones.** §3.16 bis sigue siendo solo texto, por
  decisión del usuario del 2026-10-21: ni el corte de Tierra ni nada más la lee. Este asiento es
  otro, propio de la simulación del enlace, y lo dice su rótulo («declarado por una persona», como
  en §3.16 bis). Pueden discrepar. **Unificar los dos es una decisión pendiente del usuario.** EMMA
  no mide el enlace y en este prototipo no hay enlace: las dos consolas corren en la misma máquina
  y leen el mismo registro. Nada sale a la red.
- **Quién y cómo.** `POST /api/link-sync`, solo desde la consola de a bordo. Las reglas las aplica
  el almacén (`storage.change_simulated_link`, con `core/link_sync.check_change`) bajo su
  cerrojo, como el modo seguro. Mirar los cambios y firmar van juntos, y dos cambios cruzados no
  pasan los dos. Solo cuentan los firmados por la consola. Uno con un `state` fuera del vocabulario
  o un `at` ilegible o sin zona es un 409 (`simulated_link_entries`): con él no se calcula ningún
  corte.
- **El corte de Tierra.** `GET /api/link-sync?light_cut=…` recibe el corte por tiempo de luz que
  calcula la consola (`groundCut`: la última lectura de a bordo menos el retardo de un sentido;
  sin efemérides no lo hay) y devuelve el de Tierra (`cut`). Cada caída abre un tramo
  `[caído, restablecido)`. Si el corte por tiempo de luz cae dentro de un tramo, Tierra tiene hasta
  su inicio; si no, hasta el corte por tiempo de luz (`link_sync.ground_cut`). Lo firmado en el
  instante de la caída ya salió. El corte nunca queda por delante del tiempo de luz ni del último
  instante con enlace, y crece con la hora de a bordo. La consola lo pide a todas las rutas con
  `until` (`linkedCut` en `lib/crew.ts`, que además se niega a adelantar a cualquiera de los dos).
  Las rutas no cambian. El instante de una lectura es su hora; el de cualquier otro asiento, la hora
  de su firma: la regla de siempre (`query`, `action_counts`).
- **Lo pendiente, sin perder ni reordenar.** `to_send` es lo que espera a bordo con el enlace
  caído: los asientos posteriores a la caída. `to_arrive` es lo que le falta a Tierra: los
  posteriores a su corte, lo retenido y lo que va de camino. Los dos sin lo que firma
  `ground-console`, que sube. Se ordenan por instante y, a igualdad, por número de asiento
  (`link_sync.backlog`, sobre `ObservationStore.ledger_instants`, que comprueba el hash de lo que
  fecha: una hora alterada es un 409). El registro es la fuente: la cola no copia ni retiene nada,
  solo cuenta. Al restablecerse, lo retenido llega a Tierra un tiempo de luz después, de golpe y
  entero, porque el corte salta de la caída al tiempo de luz. **Límite:** en una misión real
  Tierra no sabría cuántos asientos le faltan. Aquí lo sabe porque lee el mismo registro, y la
  frase lo dice (`known_only_here`).
- **Qué lo lee.** Solo el corte de Tierra y esta cola. El riesgo y su factor de aislamiento (que
  salen del tiempo de luz de las efemérides), las alertas, las recomendaciones, `notify_ground`, el
  estado de a bordo y la declaración de §3.16 bis no lo leen. Ningún módulo de `analysis/` ni de
  `advisor/`, ni `api/routes.py`, ni `environment/systems.py` lo importa, y `/api/status` es
  idéntico antes y después de declararlo, sin corte y con el mismo `until`
  (`test_the_status_is_identical_before_and_after_a_declared_drop`, invariante 5). No entra en
  `rules_version` ni en la crónica.
- **Las ecografías, el dolor y el historial** se cortan con el reloj (`arrivalCut`, lo que viaja
  al firmarse) y **no** siguen todavía al enlace simulado. Queda declarado aquí y en
  `hmi-state-of-the-art.md` §5.47.
- **Sin borrado ni edición.** Un cambio equivocado se corrige con otro: un instante posterior o
  igual al último. La redacción de §3.6 lo retira como a cualquier asiento.

Pruebas: `tests/test_link_sync.py`; campaña `tests/mutants/link_sync.json` (cuenta, almacén y ruta).

### 3.30 Discrepancia del cálculo local de efemérides con JPL Horizons (2026-11-11)

Decisión del usuario (2026-11-11): con SPICE primero (`environment/spice.py`), un día cuyo cálculo
local discrepa de la efeméride de JPL Horizons en caché por encima del error declarado
(`spice.DECLARED_MAX_ERROR`) se sirve con Horizons, la referencia (`EphemerisClient._contrasted`).
Hasta aquí eso solo quedaba en el registro de la aplicación, que no se firma ni viaja. Ahora deja
además un asiento firmado. Tipo nuevo, firmado por el propio sistema con el patrón de las
instantáneas de proyección (§3.18):

| Tipo | Campos | Reglas |
|---|---|---|
| `ephemeris-discrepancy` | `subject` (= `sistema`), `epoch` (el día de la efeméride), `target`, `observer`, `local` (la fuente local, con su núcleo), `reference` (`JPL Horizons`), `reference_fetched_at` (cuándo se obtuvo la efeméride de Horizons en caché), `one_way_seconds_difference`, `elongation_deg_difference` (vacío si una de las dos no la tiene: no se comparó), `one_way_seconds_tolerance`, `elongation_deg_tolerance`, `used` (la fuente con que se sirve el día), `text` (la frase del contraste) | todo texto (las cifras con `repr`, como §3.18); **como mucho un asiento por día de efeméride, objetivo y observador**; firma `emma-ephemeris`, identidad reservada (la ingesta pública no puede firmar así) |

- **Quién y cuándo.** Solo `/api/status` de a bordo (sin `until`), cuando la ventana del día trae
  un contraste que no coincide (`comms_status.discrepancy_payload`). Mirar lo firmado y firmar van
  bajo el cerrojo del almacén (`ObservationStore.record_ephemeris_discrepancy`): pedir el estado
  muchas veces, o a la vez, deja un solo asiento por día. Un contraste que coincide no firma nada.
  Un payload con campos de más o de menos, o con algo que no es texto, no llega al ledger
  (`ValueError`, sin asiento).
- **El corte de Tierra.** Con `until` no se firma nada, como en §3.18. El aviso de la consola sí se
  da (es el contraste de las efemérides, no un dato de a bordo), pero el asiento solo se nombra si
  se firmó hasta el corte (`ephemeris_discrepancies(until)`, por la hora de su firma, la regla de
  cualquier asiento que no es una lectura).
- **Lo que lo lee.** `/api/status` → `comms_status.discrepancy.signed` (índice y hora del asiento) y
  la tabla de auditoría de Tierra (grupo «sistema», `ground/ledgerEntries.ts`). **No es una
  observación clínica**: no entra en `observations`, ni en el análisis, ni en el riesgo ni en las
  alertas; el día discrepante ya se sirvió con Horizons antes de firmarlo, y los niveles, el factor
  de aislamiento y las alertas de la consulta que firma son los de las siguientes
  (`test_a_discrepancy_is_said_and_signed_once`, invariante 5). No entra en `rules_version` ni en
  la crónica.
- **Sin borrado ni edición.** La redacción de §3.6 lo retira como a cualquier asiento.

Pruebas: `tests/test_comms_status.py`; campaña `tests/mutants/comms_status.json` (frase, almacén y
ruta).

### 3.31 La base de datos de Marplanner, en el ledger (2026-11-12)

Marplanner (`marplanner/`, copia literal, MIT) guarda todo en SQLite. Decisión del usuario: en
EMMA ese almacén es este ledger, no un fichero. Marplanner corre su SQLite **en memoria**; cada
transacción sale como un changeset de sesión de SQLite (`node:sqlite`) y se anota aquí **antes de
responder** a su cliente. Al arrancar, reproduce los changesets en orden y su base vuelve a ser la
del ledger. No hay un `.db` de Marplanner en disco.

| Tipo | Campos | Regla (sin escribir nada) |
|---|---|---|
| `planner-changeset` | `subject` (= `planner`), `changeset` (base64), `sha256` (del changeset decodificado), `written_by` | 422: no es base64; vacío; más de 8 MiB; `written_by` sin nombre. **409**: `expected` (cuántos había reproducido quien escribe) no es el número de changesets anotados |

- **Una sola vía.** `POST /api/planner/changesets` → `record_planner_changeset` → `_record_action`,
  firmado por `marplanner`, identidad reservada (`_is_reserved_source`): ninguna lectura puede
  firmar así. No es de un tripulante, no entra en `observations` ni en el análisis.
- **Orden y concurrencia.** El 409 impide que un escritor con la base atrasada anote un cambio
  hecho sobre una base que el ledger no tiene; se comprueba y anexa bajo un mismo cerrojo.
- **Al leer.** `GET /api/planner/changesets?after=N` entrega los posteriores a N, numerados desde 1.
  Además del hash firmado del asiento (`_actions`), cada changeset se compara con su `sha256`: uno
  alterado en disco con la huella intacta es `TamperedRecordError` y no se reproduce.
- **No hay borrado ni edición.** Deshacer algo en Marplanner es otra transacción, otro asiento.
  Rectificar un dato personal de Marplanner seguiría la vía general de redacción (§3.6): su
  consecuencia (la base deja de poder reproducirse desde ese punto) queda **abierta**.

Pruebas: `tests/test_planner_ledger.py`.

### 3.32 Petición de ayuda urgente y su cierre (2026-11-14)

Decisión del usuario: el botón rojo de «Inicio» pasa de «modo esencial» a emergencia, «por si
necesitas ayuda urgente», y «Tierra está muy lejos: tiene que alertar a quien tengas más cerca y,
obviamente, a Tierra». Dos tipos nuevos, firmados por la consola de a bordo (`CONSOLE_IDENTITY`), con
el patrón de §3.8 (una acción humana que se registra, nunca una edición):

| Tipo | Campos | Reglas (rechazo con 422) |
|---|---|---|
| `help-request` | `subject` (un tripulante con lecturas), `signed_by` (puede ir vacío), `reason` (puede ir vacío), `at` (instante de la misión, ISO con zona) | nombre de 64 y motivo de 280 caracteres como mucho, **ninguno obligatorio**; tripulante con lecturas; `at` con zona horaria. El motivo **no** pasa `text_guard` a propósito: son las palabras de quien pide ayuda, no un texto de EMMA, y rechazar «dolor en el pecho» dejaría a alguien sin poder pedirla |
| `help-request-close` | `subject` (el de la petición), `request_index` (índice de la petición, en texto), `signed_by` | persona con nombre; la petición existe y no está ya cerrada (se comprueba y anexa bajo un mismo cerrojo) |

- **Un solo toque.** Pedirla no exige nombre, motivo ni confirmación (decisión del usuario, 2026-11-14:
  «solo haces que sea más probable que se muera si le restas tiempo de acción por parte de los
  demás»). El asiento se firma igual con la clave de la consola, sin que nadie haga nada; quién la pide
  lo dice `subject`, y el nombre, si lo hay, es el recordado en el equipo. Darla por atendida sí lleva
  nombre.
- **Una sola vía.** `POST /api/help-requests` → `record_help_request`, y
  `POST /api/help-requests/{índice}/close` → `record_help_close`, ambas por `_record_action`. No son
  lecturas: no entran en `observations` ni en el análisis, y no cambian ningún nivel, alerta ni
  `rules_version` (prueba en `tests/test_help_requests.py`).
- **Quién la ve y cuándo.** `GET /api/help-requests` entrega las abiertas firmadas por la consola de a
  bordo. La consola de tripulación las pide sin corte: se ven al firmarse. La de Tierra pide con
  `until` = su corte de reloj (el reloj menos un tiempo de luz, o la caída del enlace simulado) y lo
  firmado después —peticiones **y cierres**— no se entrega: para Tierra, una petición sigue abierta
  hasta que le llega que alguien la atendió.
- **Cercanía.** Cada petición abierta lleva al resto de la tripulación ordenada: mismo módulo, otro
  módulo, ubicación desconocida, con la ubicación del estado en `at` (declarada por la consola o
  estimada por las anclas). Sin más tripulantes con lecturas, un texto dice que se avise por el
  procedimiento de la nave.
- **Límite.** EMMA no tiene megafonía ni intercomunicador: «avisar» es enseñarlo y leerlo en voz alta
  en las consolas. No sustituye al procedimiento de emergencia de la nave. `signed_by` es lo
  declarado, sin autenticar (§7.5).
- **No hay borrado ni edición.** El cierre cita la petición y la deja en la cadena.

Pruebas: `tests/test_help_requests.py`.

### 3.33 Inventario contado y abastecimiento declarado (2026-11-14)

Decisión del usuario: las existencias de a bordo (medicamentos, alimentos, equipo médico) son un
**inventario real firmado**. EMMA no lee ningún sistema de estiba; una persona cuenta y lo declara
en la consola, y la autonomía se calcula de ahí (`core/inventory.py`). Dos tipos nuevos, firmados
por `crew-console` con el patrón de §3.8 (acción humana; todos los campos como texto; `_actions`
rechaza un asiento mal formado). Son de la misión: su sujeto es `mision`. A diferencia de
`resource-availability` (§3.17 quater), aquí **sí** hay cantidades: las que la persona firmó.

| Tipo | Campos | Regla (rechazo con 422, sin escribir nada) |
|---|---|---|
| `inventory-count` | `subject` (= `mision`), `category` (`medications`, `food` o `medical-equipment`), `item` (clave), `name`, `unit`, `quantity` (cifra como texto), `counted_at` (UTC), `declared_by`; y solo si se declararon: `daily_use`, `family` (clave), `min_days`, `expires` (AAAA-MM-DD) | categoría fuera del vocabulario; `item` o `family` que no sean clave (minúsculas, cifras, guiones); cifra negativa, no finita o no numérica; `min_days` cero; `counted_at` sin zona horaria; fecha inválida; `name`/`unit` vacíos o largos; `declared_by` sin nombre; cualquier campo de más |
| `inventory-resupply` | `subject` (= `mision`), `name`, `eta` (UTC), `declared_at` (UTC), `declared_by`; `capacity_kg` solo si se declaró | instantes sin zona horaria; cifra negativa o no finita; `declared_by` sin nombre; cualquier campo de más |

- **Una sola vía.** `POST /api/inventory/count` → `record_inventory_count` y
  `POST /api/inventory/resupply` → `record_inventory_resupply`, ambos → `_record_action`: un
  asiento encadenado y firmado en un solo `commit`. Las reglas de la tabla las impone el almacén
  (`inventory.count_payload` / `resupply_payload`), no solo la ruta. Los dos `POST` exigen
  `X-EMMA-Console: 1` (403 sin ella, antes de validar nada).
- **Las cifras, como texto.** Un entero se firma sin decimales y lo demás con `repr`, que
  reproduce el mismo número al leerlo; así el hash no depende de cómo se serialice un `float`.
- **Qué vale.** De cada artículo (`item`, único en todo el inventario), su último recuento firmado
  por la consola (`_counts`); del abastecimiento, la última declaración. Para Tierra, además, solo
  lo que ya existía en su corte y no se contó (`counted_at`) ni declaró (`declared_at`) después de
  él. **No hay borrado ni edición**: se corrige contando de nuevo y los anteriores se conservan.
- **Al leer.** `GET /api/inventory` da las tres categorías con lo vigente y sus totales. Lo
  calculado: `autonomy_days = quantity / daily_use` solo con consumo declarado y mayor que cero;
  `critical` = autonomía menor que `min_days`, y `null` si falta cualquiera de las dos (no se
  inventa umbral); `alternatives` = otros artículos de la misma `family` con cantidad mayor que
  cero, que es lo que hay a bordo y no una equivalencia clínica (invariante 7). Sin ningún asiento,
  `declared: false` y las categorías vacías: el paquete no lleva existencias de ejemplo.
- **Para qué sirve, y para qué no.** No entra en `observations` ni en el análisis; no cambia
  niveles, alertas, recomendaciones ni `rules_version` (invariante 5): un artículo crítico no
  levanta ninguna alerta. No cuenta como registro real a efectos de §3.9.

Pruebas: `tests/test_inventory.py` (sin declarar, autonomía, crítico solo con mínimo, alternativas,
último recuento, abastecimiento, los 422 y el rechazo del almacén, la cabecera, el asiento firmado
y verificable, lo que no firmó la consola, el corte de Tierra y el estado idéntico con y sin
inventario).

### 3.34 Idioma del registro (2026-11-15)

Desde que la interfaz se lee en castellano o en inglés (`app/core/i18n.py`), el idioma de quien
mira no puede cambiar lo que se firma: dos consolas en idiomas distintos tienen que dejar el mismo
registro. Reglas:

1. **Los identificadores y las claves no se traducen nunca** (`entry_type`, estados como
   `localizada` o `confirmada`, orígenes de nota, claves de indicador). Son parte de los asientos
   ya firmados.
2. **El texto que redacta EMMA y firma** (la frase de una discrepancia de efemérides, una
   instantánea de predicción) **se escribe siempre en el idioma del registro**, `RECORD_LANG =
   "es"`: el asiento se construye dentro de `i18n.record_language()`. Los bytes firmados no
   dependen del lector.
3. **El texto libre de una persona se firma tal como lo escribió**, en el idioma en que lo
   escribió. No se traduce ni al firmar ni al leer.
4. **Al leer**, una frase se vuelve a redactar en el idioma de la petición a partir de los campos
   estructurados cuando existen; un `text` firmado se enseña tal cual.
5. **La interfaz nunca manda texto traducido en el cuerpo de una petición que firma**: un `tr()`
   es para la pantalla.

No cambia `core/ledger.py` ni los bytes canónicos de ningún asiento. Prueba:
`tests/test_i18n_record_language.py` siembra dos veces lo mismo, lee el estado y las rutas
principales en castellano en una y en inglés en la otra, y exige los dos registros idénticos (sin
la sal, que es aleatoria a propósito).

## 4. Formato: FHIR AuditEvent / IHE ATNA

**Estado: diseño, no implementado.** Los asientos del ledger no se exportan todavía como
`AuditEvent`; `GET /api/audit` devuelve una estructura propia. Lo que sigue es el formato objetivo.

El modelo canónico de datos del proyecto ya es FHIR R4, así que los registros de auditoría usan el
recurso [`AuditEvent`](https://hl7.org/fhir/R4/auditevent.html), alineado con el perfil
[IHE ATNA](https://profiles.ihe.net/ITI/TF/Volume1/ch-9.html) (formato heredado de RFC 3881, hoy
gestionado por DICOM).

Mapeo a los mínimos que pide ISO 27789:

| Requisito ISO 27789 | Campo FHIR AuditEvent |
|---|---|
| Identificar al usuario | `agent.who` |
| Identificar al sujeto de atención | `entity.what` (referencia a `Patient`) |
| Función realizada | `type` + `action` (C/R/U/D) |
| Fecha y hora | `recorded` |

Los campos propios de EMMA (`prev_hash`, `signature`, `merkle_leaf`) van como extensiones, no
sustituyen campos estándar.

---

## 5. Matriz requisito → implementación

Una fila marcada **parcial** o **pendiente** dice exactamente qué falta. La versión anterior de
esta tabla atribuía al código garantías que no daba (§7); se corrigió fila a fila.

| Requisito | Fuente | Implementación |
|---|---|---|
| Discernir registros alterados | 21 CFR 11.10(a) | Cadena de hashes SHA-256 que cubre la firma (§3.1). Truncar la cola solo se detecta contra un ancla (§3.3) |
| Recuperación fiel durante la retención | 21 CFR 11.10(c) | Almacén append-only + verificación en lectura. Excepción: una redacción autorizada suprime el contenido y deja lápida (§3.6) |
| Audit trail seguro con marca de tiempo | 21 CFR 11.10(e) | Asiento firmado con `recorded` generado por el sistema, UTC, no decreciente (§3.1). Corregir un dato no oculta el anterior: la enmienda lo deja registrado (§3.7). **Sigue en conflicto** la redacción, que borra el contenido, reservada al dato que nunca debió existir (§3.6). **Pendiente**: exportación como `AuditEvent` (§4) |
| Registro independiente de la acción | 21 CFR 11.10(e) | Ancla RFC 6962 con tamaño y algoritmo (§3.3). **Parcial**: transmisión y sellado en Tierra sin implementar |
| Mecanismos de auditoría de actividad | 45 CFR 164.312(b) | Asiento firmado en cada alta y lápida en cada supresión (§3.6). **Parcial**: las lecturas no se auditan |
| Protección contra alteración impropia | 45 CFR 164.312(c)(1) | Firma Ed25519 contra registro de claves fijadas (§3.2). **Sin control de acceso**: la API no autentica ni la ingesta ni la redacción |
| Corroborar no-alteración ni destrucción | 45 CFR 164.312(c)(2) | Verificación de cadena, registro y disco; todo contenido ausente exige una lápida de la autoridad de redacción aprovisionada (§3.6); prueba de Merkle. **Parcial**: sin fuentes aprovisionadas ni ancla comprobada, quien escribe en la base puede truncar la cola y reencadenarla (§3.2) |
| Enmienda de información de salud | 45 CFR 164.526 | Asiento `amendment` atado por hash a la entrada que corrige, que permanece; `query()` entrega la versión vigente (§3.7). **Parcial**: el procedimiento de la norma —plazos, denegación motivada, notificación a terceros— es organizativo y queda fuera del software, y `amended_by` no está autenticado |
| Registro por cada lectura/escritura | ISO 27789:2021 | **Parcial**: altas y supresiones sí; lecturas no. No existe interceptor en la capa de repositorio |
| Orden de la cadena = orden real de escritura | 21 CFR 11.10(a) | Cerrojo único del almacén (§3.4) |
| La cadena en memoria no afirma registros ausentes en disco | 21 CFR 11.10(c) | Lotes atómicos con retirada de asientos si falla el `commit` (§3.4) |
| Discernir registros alterados **con el sistema en marcha** | 21 CFR 11.10(a) | Verificación del disco contra la cadena (§3.5) |
| El análisis clínico solo usa datos cubiertos por una firma | 21 CFR 11.10(a) · 45 CFR 164.312(c)(2) | `query()` solo sirve datos de una cadena verificada: firma, firmante, encadenamiento, contenido y lápidas (§3.5) |
| Identificar usuario, sujeto, función, hora | ISO 27789:2021 | `signer` (fuente), sujeto en el payload, `entry_type`, `recorded`; en la lápida, `requested_by` **declarado, sin autenticar**. **Pendiente**: formato `AuditEvent` (§4) |
| Un registro de imagen no se altera sin que se note | 21 CFR 11.10(a) · 45 CFR 164.312(c)(2) | SHA-256 del binario firmado en el asiento, recalculado al servir y en cada verificación (§3.10) |
| Un autoinforme de dolor no se separa de lo que lo explica | 21 CFR 11.10(e) | Lectura e informe `pain-report` en un solo `commit`, citados por índice; la intensidad no entra sin informe ni se enmienda (§3.11) |
| No registrar identificadores innecesarios | 45 CFR 164.514 (des-identificación) | Perfil básico DICOM PS3.15 antes de guardar (§3.10). **Parcial**: el texto quemado en los píxeles no se elimina |

---

## 6. Verificación

Suite en `backend/tests/test_ledger.py` — 141 pruebas en verde a 2026-09-22 (eran 19). Ninguna
requiere red: la propiedad de autonomía queda verificada por construcción.

**Regla de esta suite: una prueba de seguridad ejecuta el ataque, no la implementación.** La suite
anterior pasaba en verde con los siete fallos de §7 abiertos porque sus pruebas espejaban el código.
Las marcadas B1–M6 reproducen cada ataque de la primera revisión tal y como se ejecutó contra la
versión vulnerable; las marcadas R, los de la segunda; las T, los de la tercera, y las C, los de la
cuarta.

| Prueba | Qué demuestra | Requisito |
|---|---|---|
| `test_chain_verifies_when_intact` | Encadenamiento correcto desde génesis | — |
| `test_ledger_detects_tampering` | Editar el contenido se detecta y señala la entrada | 11.10(a) |
| `test_tampering_with_content_hash_breaks_the_chain` | Recalcular el hash para encubrir tampoco cuela: la firma ya no cubre | 11.10(a) |
| `test_signature_that_does_not_match_the_declared_key_fails` | Una firma que no casa con la clave declarada falla. Es el caso fácil: **no** prueba que suplantar falle | — |
| `test_impersonation_by_rewriting_the_whole_chain_fails` | **B1** — reescribir toda la cadena con una clave propia y el mismo id falla | 164.312(c)(1) |
| `test_an_identity_cannot_be_repinned_to_another_key` · `test_unregistered_signer_cannot_append` | **B1** — una identidad no cambia de clave; nadie sin registrar escribe | 164.312(c)(1) |
| `test_redaction_leaves_a_signed_tombstone` | **B2** — redactar una alerta crítica deja lápida firmada con motivo, autor y hash | 11.10(e) |
| `test_suppressing_content_without_a_tombstone_is_detected` | **B2** — vaciar un payload a mano se detecta | 164.312(c)(2) |
| `test_clearing_the_redacted_flag_is_detected` · `test_restoring_redacted_content_is_detected` | **B2** — ni borrar la marca ni deshacer la rectificación pasan | 164.312(c)(2) |
| `test_a_tombstone_cannot_be_redacted_nor_an_entry_twice` · `test_the_redaction_entry_type_is_reserved` · `test_redaction_requires_reason_and_requester` | **B2** — la lápida no se puede redactar ni duplicar, y exige motivo y solicitante. Que un tercero no la pueda falsificar lo prueban las **R1** | 11.10(e) |
| `test_anchor_taken_before_redaction_still_verifies` | El ancla anterior sigue válida; la siguiente registra la redacción | §3.3 |
| `test_merkle_root_matches_an_independent_rfc6962_implementation` | **B3** — la raíz coincide con RFC 6962 recursiva para 0–33 hojas | §3.3 |
| `test_duplicating_the_odd_leaf_changes_the_root` · `test_a_phantom_duplicated_leaf_has_no_valid_proof` · `test_an_internal_node_cannot_pass_as_an_entry` | **B3** — CVE-2012-2459 y la segunda preimagen quedan cerrados | §3.3 |
| `test_merkle_proof_roundtrip` · `test_merkle_proof_rejects_foreign_leaf` · `test_merkle_proofs_hold_for_any_chain_length` · `test_merkle_root_changes_when_entry_added` · `test_empty_ledger` | Pruebas de inclusión correctas para cualquier tamaño; raíz vacía distinta del centinela de génesis | 164.312(c)(2) |
| `test_concurrent_appends_keep_the_chain_intact` | **B4** — 8 hilos × 30 escrituras sobre el ledger desnudo | 11.10(a) |
| `test_canonical_serialization_is_key_order_independent` · `test_non_json_payloads_are_rejected` | **M1** — Decimal, datetime, claves enteras, tuplas, NaN, infinito y objetos se rechazan | §3.1 |
| `test_without_an_anchor_tail_truncation_is_invisible` | **Límite declarado**: sin ancla, truncar la cola no se detecta | §3.3 |
| `test_tail_truncation_is_detected_against_an_anchor` · `test_an_anchored_prefix_cannot_be_rewritten` · `test_an_anchor_with_an_unknown_algorithm_is_refused` | **M2** — contra un ancla, ni truncar ni reescribir el prefijo, aunque sea con la clave legítima | 11.10(a) |
| `test_the_ledger_sets_the_timestamp_not_the_caller` · `test_a_clock_that_goes_back_never_produces_an_earlier_entry` · `test_a_naive_clock_is_rejected` · `test_a_backdated_entry_is_detected_even_with_the_legitimate_key` | **M3** — marca de tiempo del sistema, UTC y no decreciente | 11.10(e) |
| `test_caller_mutation_after_append_does_not_touch_the_ledger` · `test_mutating_the_view_does_not_touch_the_ledger` | **M4** — el ledger no comparte su estado | 11.10(c) |
| `test_redact_rejects_out_of_range_indices` | **M5** — `redact(-1)` ya no redacta la última entrada | 164.312(c)(1) |
| `test_the_chain_commits_to_signatures` · `test_skipping_known_signatures_still_catches_a_changed_one` | **M6** — la cadena compromete las firmas; con una entrada detrás, el atajo no oculta una firma cambiada | 11.10(a) |
| `test_the_signature_shortcut_trusts_process_memory` | **R4 — límite declarado**: la última entrada no la cubre el encadenamiento; el atajo confía en la memoria del proceso | §3.5 |
| `test_a_source_key_cannot_sign_a_tombstone` · `test_a_newly_registered_identity_cannot_authorise_a_suppression` · `test_declaring_the_authority_key_without_its_signature_does_not_count` | **R1** — ni una fuente registrada, ni una identidad recién dada de alta, ni quien declare la clave de la autoridad sin su firma pueden justificar una supresión, tampoco contra el ancla | 164.312(c)(2) |
| `test_without_an_authority_there_are_no_redactions` · `test_the_authority_cannot_sign_clinical_data` | **R1** — sin autoridad no hay redacciones; la autoridad no firma datos | 164.312(c)(1) |
| `test_a_malformed_tombstone_is_a_failure_not_a_crash` · `test_an_earlier_edit_is_reported_before_a_later_bad_tombstone` | **R2, R7** — una lápida basura es un fallo, no una excepción, y no tapa una edición anterior | 11.10(a) |
| `test_a_malformed_anchor_is_refused` | **R8** — un ancla con tamaño negativo o raíz mal formada no valida | §3.3 |
| `test_merkle_proofs_match_an_independent_rfc6962_path` | **R11** — las pruebas de inclusión coinciden con el PATH recursivo de RFC 6962 | §3.3 |
| `test_the_salt_field_is_reserved` · `test_a_payload_nested_beyond_the_limit_is_rejected` · `test_unencodable_text_is_rejected` | **C3, C2** — la sal la pone el ledger; el JSON está acotado y es codificable | §3.1 |
| `test_the_clock_only_follows_a_previous_entry_that_verifies` | **C4** — una fecha futura en un asiento manipulado no arrastra el reloj | 11.10(e) |
| `test_a_failed_transaction_rolls_back_chain_redaction_and_registry` | Un `commit` fallido no deja asientos, lápidas ni claves en memoria | 11.10(c) |

Suite en `backend/tests/test_storage_concurrency.py` (§3.4):

| Prueba | Qué demuestra | Requisito |
|---|---|---|
| `test_concurrent_writers_keep_the_chain_intact` | 4 hilos, 800 escrituras con lecturas intercaladas: sin índices duplicados y cadena íntegra. **Sin el cerrojo falla 3 de 3 veces** | 11.10(a) |
| `test_failed_batch_leaves_nothing_behind` | Un `commit` fallido no deja filas ni asientos en memoria, y se puede seguir escribiendo | 11.10(c) |
| `test_failed_redaction_is_not_half_applied` | Una redacción fallida no queda aplicada solo en memoria: ni la supresión ni la lápida | 164.312(c)(1) |
| `test_a_batch_is_one_transaction` | El camino normal escribe el lote entero y verificable | 11.10(c) |

Suite en `backend/tests/test_storage_integrity.py` (§3.5):

| Prueba | Qué demuestra | Requisito |
|---|---|---|
| `test_runtime_disk_tampering_is_detected_without_restart` | Editar lectura, editar asiento, borrar fila y añadir fila falsa se detectan sin reiniciar, en el asiento correcto | 11.10(a) |
| `test_the_engine_only_ever_sees_signed_values` | Lo editado en `observations` no llega al análisis | 11.10(a) |
| `test_a_mutated_payload_is_refused_not_analysed` | Un contenido que ya no casa con su hash no se entrega al motor | 164.312(c)(2) |
| `test_an_untouched_store_verifies_now_and_after_restart` | Una base sana verifica, también por el camino incremental y tras reiniciar | — |
| `test_redaction_still_verifies_against_disk` | Redactar sigue siendo compatible con la verificación del disco | 164.312(c)(1) |
| `test_skipping_known_signatures_still_checks_chain_and_content` | No repetir firmas no es dejar de verificar encadenamiento y contenido | 11.10(a) |

Suite en `backend/tests/test_incremental_verification.py` (§3.5 bis), cada ataque entre dos
verificaciones y con la base en fichero y en memoria; sus defensas, en la campaña de mutantes
`backend/tests/mutants/incremental_verification.json`:

| Prueba | Qué demuestra | Requisito |
|---|---|---|
| `test_editing_a_verified_row_by_the_same_connection_is_detected` | Editar un asiento, una lectura o una firma ya verificados por la conexión del almacén se detecta en la siguiente verificación (`total_changes`) | 11.10(a) |
| `test_editing_the_file_from_another_connection_is_detected` | Otra conexión de SQLite editando el fichero se detecta (`data_version`) | 11.10(a) |
| `test_a_schema_change_is_detected` | Vaciar `observations` borrándola y rehaciéndola se detecta (`schema_version`) | 11.10(a) |
| `test_an_edit_followed_by_an_own_write_is_not_absorbed` · `test_another_connection_writing_during_an_own_write_is_not_absorbed` | Una edición ajena justo antes o durante una escritura propia no queda dada por buena | 11.10(a) |
| `test_legitimate_appends_are_verified_and_only_they` · `test_a_new_row_that_disagrees_with_its_entry_is_detected` · `test_status_with_new_data_still_reads_the_whole_reading_set` | Lo añadido se verifica a fondo, y solo eso; su fila en disco se coteja como siempre, y el motor sigue leyendo todas las lecturas | 11.10(a) |
| `test_a_redaction_or_an_amendment_goes_back_to_the_full_check` · `test_an_anchor_always_gets_the_full_check` · `test_a_tombstone_slipped_behind_verified_entries_is_not_trusted` | Lo que depende de un asiento anterior, y el ancla, vuelven a la verificación completa | 164.312(c)(2) |
| `test_mutating_verified_memory_is_detected` · `test_a_nested_mutation_is_detected` · `test_a_list_that_is_not_watched_is_never_trusted` · `test_a_reopened_store_watches_what_it_loaded` | Mutar un payload (también anidado), sustituir un asiento o la lista, o desfijar una clave se detecta; lo cargado de disco está vigilado igual | 164.312(c)(2) |
| `test_an_unpinned_key_is_seen_by_the_bare_ledger` · `test_another_authority_is_seen_by_the_bare_ledger` | Sin almacén, el registro y la autoridad van en la marca de memoria | 164.312(c)(1) |
| `test_a_write_rejected_before_touching_the_base_keeps_the_short_path` · `test_an_unreadable_mark_falls_back_to_the_full_check` | Una escritura rechazada sin tocar la base no cuesta una verificación completa; sin contadores de SQLite, completa y sin 500 | — |
| `test_copies_of_a_payload_are_not_mutations` · `test_watched_payloads_serialise_and_hash_as_before` | Copiar no es mutar, y la clase vigilada no cambia los bytes canónicos ni el hash | — |
| `test_query_rechecks_readings_after_a_memory_mutation` | El atajo de `query()` se cae con la primera mutación en sitio: 409, como antes | 164.312(c)(2) |

Suite en `backend/tests/test_api.py` (§3.2, §3.6):

| Prueba | Qué demuestra | Requisito |
|---|---|---|
| `test_redaction_leaves_a_signed_tombstone` | La redacción por la API deja lápida visible en `/api/audit`, con motivo y solicitante, y el ancla la cubre | 11.10(e) |
| `test_redaction_requires_reason_and_requester` · `test_redacting_twice_or_a_tombstone_is_a_conflict` | Sin motivo es un 422; redactar dos veces o una lápida es un 409 | 11.10(e) |
| `test_the_audit_identity_is_reserved` | Ninguna fuente puede llamarse `emma-audit` y bloquear las redacciones | 164.312(c)(1) |

Suite en `backend/tests/test_integrity_attacks.py` (§3.2, §3.5, §3.6), de la segunda, la tercera y
la cuarta revisión:

| Prueba | Qué demuestra | Requisito |
|---|---|---|
| `test_a_forged_tombstone_cannot_erase_an_anchored_reading` | **R1** — el ataque completo en SQLite, sin claves: alta en `trusted_keys`, lápida propia, payload a NULL y fila borrada. Falla la verificación, también contra el ancla, y `query()` da error en vez de omitir la lectura | 164.312(c)(2) |
| `test_a_legitimate_redaction_survives_restart_with_the_same_authority` · `test_existing_tombstones_need_the_same_authority_after_restart` | La redacción legítima sobrevive a un reinicio; **límite declarado**: con otra autoridad, o sin ninguna, no | §3.6 |
| `test_an_observation_row_pointing_at_a_tombstone_is_a_failure_not_a_crash` · `test_unreadable_values_on_disk_are_a_failure_not_a_crash` · `test_a_malformed_tombstone_can_still_be_shown` | **R2** — disco incoherente o lápida mal formada: fallo de verificación, sin 500 | 11.10(a) |
| `test_a_reading_in_another_timezone_is_not_a_false_alarm` | **R3** — una lectura en `+02:00` no dispara una falsa alarma de integridad | 11.10(a) |
| `test_query_only_serves_a_chain_whose_signatures_hold` | **R5, T1** — tras reabrir, ni una lectura movida a otro tripulante con el hash recalculado, ni un valor cambiado con el hash recalculado, ni un tipo de asiento cambiado llegan al motor: error, no omisión | 11.10(a) |
| `test_a_tombstone_copied_from_another_store_justifies_nothing` · `test_the_api_refuses_to_analyse_an_unsigned_chain` | **T1** — una lápida legítima copiada de otro almacén no suprime nada; la API responde 409 en `/api/observations` y `/api/status` | 164.312(c)(2) |
| `test_odd_types_on_disk_are_a_failure_not_a_crash` · `test_binary_header_fields_are_a_failure_not_a_crash` · `test_a_damaged_tombstone_header_is_a_failure_not_a_crash` | **T3** — BLOBs y tipos inesperados en disco: fallo de verificación, sin 500, y sin ancla sobre una cadena rota | 11.10(a) |
| `test_a_corrupted_store_still_opens_and_says_so` | **T3** — una base corrupta en reposo abre y declara la integridad rota | 11.10(c) |
| `test_redaction_cannot_launder_a_tampered_entry` | **T4** — no se redacta sobre una cadena que no verifica | 11.10(a) |
| `test_concurrent_first_requests_share_one_store` | **T2** — las primeras peticiones simultáneas comparten almacén; no se pierde ninguna lectura confirmada | 11.10(c) |
| `test_a_provisioned_store_rejects_rechaining_with_a_new_identity` · `test_a_provisioned_store_accepts_no_new_signers` · `test_an_extra_trusted_key_on_disk_is_a_failure` | **C1** — con fuentes aprovisionadas, reencadenar con una identidad nueva falla | 164.312(c)(2) |
| `test_without_provisioning_rechaining_is_invisible` | **C1 — límite declarado**: con el registro aprendido, el reencadenado pasa | §3.2 |
| `test_undecodable_text_while_running_is_a_failure_not_a_crash` · `test_undecodable_text_at_rest_still_opens` · `test_a_deeply_nested_payload_is_a_failure_not_a_crash` · `test_an_unencodable_reason_can_still_be_shown` · `test_a_null_on_disk_is_a_failure_not_a_crash` · `test_a_duplicated_trusted_key_still_opens` · `test_unencodable_text_through_the_api_is_rejected_not_a_crash` | **C2** — UTF-8 inválido, JSON profundo, un NULL, una identidad repetida y sustitutos sueltos: fallo o 422, nunca un 500 ni un almacén que no abre | 11.10(a) |
| `test_redaction_leaves_no_trace_in_the_file` · `test_identical_readings_do_not_share_a_content_hash` | **C3** — tras redactar, el dato no queda en el fichero; la sal impide invertir el hash | §3.6 |
| `test_a_forged_future_timestamp_does_not_drag_the_clock` | **C4** — una fecha falsa no se hereda | 11.10(e) |
| `test_storage_refuses_to_redact_over_a_disk_edit` · `test_writing_before_the_first_query_does_not_bless_a_tampered_store` | **C5** — las dos correcciones de la tercera ronda que ninguna prueba cubría | 11.10(a) |
| `test_adding_a_provisioned_source_is_not_a_false_alarm` | **Q1** — dar de alta una fuente aprovisionada no deja la verificación en rojo | 11.10(a) |
| `test_a_malformed_reading_signed_by_an_intruder_is_a_conflict_not_a_crash` | **Q3** — una lectura mal formada bien firmada es un 409 y un fallo de verificación, no un 500 | 11.10(a) |
| `test_readings_keep_being_recorded_after_a_damaged_entry` · `test_a_deep_payload_never_reaches_memory` | **Q6** — se sigue registrando detrás de una cabecera dañada; un payload profundo no llega a memoria | 11.10(a) |
| `test_redaction_without_a_provisioned_authority_is_unavailable` · `test_an_invisible_reason_is_rejected` · `test_a_key_conflict_is_a_conflict_not_a_server_error` | **R1, R9, R6** — 503 sin autoridad, 422 con un motivo invisible, 409 ante un conflicto de clave | 11.10(e) |

### Enmienda anexada — `backend/tests/test_amendment.py`

La misma regla del resto de la suite: cada salvaguarda de §3.7 se comprueba ejecutando su burla, en
las tres capas —ledger, almacén y API—.

| Prueba | Qué demuestra | Requisito |
|---|---|---|
| `test_the_amended_entry_stays_readable_and_signed` · `test_the_previous_version_stays_registered_and_auditable` | La versión anterior sigue entera, firmada y visible en la auditoría: el cambio no oculta lo registrado | 11.10(e) · 164.526 |
| `test_the_engine_analyses_the_corrected_value` · `test_the_corrected_reading_is_not_counted_twice` | El motor analiza la versión vigente, y una sola vez | 164.526 |
| `test_a_misattributed_reading_moves_to_the_right_crew_member` | Una lectura mal atribuida se reasigna sin borrar nada, y deja de inventar un tripulante | 164.526 |
| `test_append_cannot_write_an_amendment` | El tipo de asiento está reservado: nadie declara corregida una lectura ajena | 164.312(c)(1) |
| `test_an_amendment_bound_to_another_entry_is_refused` · `test_an_amendment_cannot_point_forward` | Atada a la entrada exacta; una enmienda de otro almacén no retira nada aquí | 164.312(c)(2) |
| `test_two_amendments_of_the_same_entry_are_refused` · `test_a_second_amendment_smuggled_into_the_chain_fails_verification` | Una enmienda por entrada: nunca dos versiones vigentes del mismo dato | 164.526 |
| `test_the_redaction_authority_cannot_amend` · `test_an_unregistered_identity_cannot_amend` | La clave de rectificar no fabrica datos clínicos; quien no está registrado no corrige | 164.312(c)(1) |
| `test_a_malformed_amendment_is_a_verification_failure_not_a_crash` · `test_a_tampered_replacement_breaks_the_chain` · `test_an_amendment_with_a_broken_signature_supersedes_nothing` | Una enmienda manipulada es un fallo de verificación, nunca un 500, y no retira nada | 11.10(a) |
| `test_redacting_a_correction_before_its_original_is_refused` · `test_both_versions_can_be_erased_in_the_right_order` | Borrar la corrección no resucita el valor equivocado | §3.7 |
| `test_an_amendment_survives_the_redaction_of_what_it_corrected` · `test_erasing_the_original_keeps_the_correction_alive` | Redactar el original no deshace la corrección | §3.7 |
| `test_the_mirror_table_follows_the_current_version` · `test_the_amendment_survives_reopening_the_store` | La tabla espejo y el cotejo con el disco siguen a la versión vigente, también tras reabrir | 11.10(a) |
| `test_no_amendment_over_a_chain_that_does_not_verify` · `test_a_damaged_entry_is_not_amended` | No se enmienda sobre lo manipulado: daría apariencia de dato revisado | 11.10(a) |
| `test_the_api_corrects_without_erasing` · `test_amending_the_same_entry_twice_is_a_conflict` · `test_amending_an_index_that_does_not_exist_is_a_404` | Por HTTP: la corrección entra, la anterior sigue en `/api/audit`, y los conflictos son 409 y 404 | 164.526 |
| `test_a_correction_of_another_indicator_is_refused_without_writing` · `test_an_amendment_is_compared_with_the_reading_it_puts_in_force` · `test_an_entry_that_is_not_a_reading_is_not_amended_with_one` · `test_the_api_refuses_another_indicator_with_a_reason_in_spanish` | La corrección es del mismo indicador (también al enmendar una enmienda); si no, 422 y no se escribe nada | §3.7 |
| `test_the_api_still_moves_a_reading_to_the_right_crew_member` · `test_the_indicator_rule_is_of_the_write_not_of_verification` · `test_an_entry_already_amended_is_a_conflict_whatever_the_indicator` | El tripulante se sigue pudiendo reasignar (H3), un ledger ya escrito sigue verificando y lo ya enmendado sigue siendo 409 | 164.526 |
| `test_a_correction_with_an_impossible_value_is_a_422` · `test_a_correction_without_a_reason_is_a_422` · `test_an_unencodable_subject_is_a_422_not_a_conflict` · `test_a_redacted_reading_cannot_be_amended_through_the_api` | Un dato malo de quien llama es 422 y no escribe nada; un estado imposible es 409 | 11.10(a) |

### Estudios de imagen — `backend/tests/test_imaging.py`

| Prueba | Qué demuestra | Requisito |
|---|---|---|
| `test_identifying_data_does_not_survive_ingestion` · `test_the_image_itself_is_kept_intact` | Nombre, identificadores, centro, operador, etiqueta privada y un nombre escondido en una secuencia anidada no llegan a los bytes guardados; los píxeles sí, intactos | 164.514 |
| `test_a_hash_that_is_not_of_these_bytes_is_refused` | No se firma el hash de unos bytes que no se guardan; no se escribe nada | 11.10(e) |
| `test_an_image_edited_on_disk_is_detected_and_never_served` · `test_rewriting_the_hash_column_along_with_the_image_is_detected` · `test_a_deleted_image_is_detected` | Cambiar un byte, reescribir imagen y columna de hash a la vez o borrar el binario: la verificación falla y la imagen no se sirve | 11.10(a) |
| `test_redacting_a_study_deletes_the_image` · `test_a_study_cannot_be_amended_into_a_reading` | Redactar borra el binario y la cadena sigue verificando; un estudio no se enmienda con una lectura | §3.10 |
| `test_a_study_counts_as_a_real_record` · `test_a_study_is_not_lost_by_switching_scenario` | Una ecografía real impide sustituir el almacén simulado | §3.9 |
| `test_studies_survive_a_restart` | Asiento y binario verifican tras reabrir el almacén | 11.10(c) |

### Informes de dolor — `backend/tests/test_pain.py`

| Prueba | Qué demuestra | Requisito |
|---|---|---|
| `test_report_records_the_peak_and_the_signed_report` | Un informe escribe la lectura y el asiento `pain-report`, en ese orden y firmados por `pain-report` | 11.10(e) |
| `test_malformed_reports_are_rejected_and_nothing_is_written` | Zona desconocida o repetida, intensidad fuera de 1-10 o con decimales, tipo desconocido: 422 y ningún asiento | 11.10(a) |
| `test_intensity_cannot_enter_through_generic_ingest` · `test_nobody_else_can_sign_as_the_pain_report` | La cifra suelta no entra, y nadie firma como `pain-report` | 164.312(c)(1) |
| `test_store_refuses_a_reading_that_is_not_the_report_peak` | El almacén no escribe una lectura que no sea el máximo del informe | 11.10(a) |
| `test_redacting_the_reading_withdraws_the_whole_report` · `test_an_intensity_is_not_amended` | Redactar la lectura retira el informe; la intensidad no se enmienda | §3.11 |

**Pendiente:** `test_auditevent_fhir_valid` — validar los registros contra el perfil FHIR R4
`AuditEvent`. `app/ingest/fhir.py` ya existe; falta la exportación de los asientos (§4).

---

## 7. Revisiones adversarias

### 7.1 Primera revisión (2026-09-21)

Una revisión independiente de `ledger.py`, hecha contra este documento, ejecutó cada ataque sobre la
versión entonces vigente. Veredicto: **bloquear**. Los 19 tests pasaban, y la suite era ciega a
todos los ataques porque sus pruebas espejaban la implementación. Tres de los hallazgos invalidaban
filas concretas de la matriz de §5, que el proyecto presentaba como evidencia de cumplimiento.

| | Hallazgo | Corrección | Sección |
|---|---|---|---|
| **B1** | La firma se verificaba con la clave de la propia entrada: la entrada se certificaba a sí misma | Registro de claves fijadas, persistido aparte | §3.2 |
| **B2** | Redactar borraba contenido sin rastro; la marca no estaba firmada | Lápida firmada; `verify()` exige una por contenido ausente | §3.6 |
| **B3** | Merkle con nodo impar duplicado y sin prefijos (CVE-2012-2459) | RFC 6962, verificado contra una implementación independiente | §3.3 |
| **B4** | `append()` sin cerrojo en el ledger | Cerrojo propio y transacciones | §3.4 |
| **M1** | `default=str`: contenidos distintos con el mismo hash | JSON canónico estricto | §3.1 |
| **M2** | Truncar la cola verificaba limpio | Ancla con tamaño; el límite sin ancla, declarado y probado | §3.3 |
| **M3** | `recorded` lo ponía quien llamaba | Marca del sistema, UTC, no decreciente | §3.1 |
| **M4** | El payload se guardaba por referencia | Copias en toda salida pública | — |
| **M5** | `redact(-1)` redactaba la última entrada | Índice validado | §3.6 |
| **M6** | El hash encadenado no cubría la firma | `entry_hash` incluye la firma | §3.1 |

Además, al integrar los arreglos aparecieron tres fallos que la revisión no cubría: la comprobación
del disco omitía tres columnas del asiento; un payload vacío se guardaba como `NULL` y al recargar
parecía un contenido suprimido; y cualquier cliente podía bloquear las redacciones enviando una
lectura con `source="emma-audit"`.

### 7.2 Segunda revisión (2026-09-22)

Una segunda revisión independiente atacó el arreglo de §7.1 y volvió a bloquear. El hallazgo
principal era un fallo del propio arreglo, y este documento lo contradecía en cuatro sitios. Cada
hallazgo se reprodujo antes de corregirlo, y tiene su prueba en §6.

| | Hallazgo | Corrección | Sección |
|---|---|---|---|
| **R1** | Cualquier clave del registro firmaba lápidas, y el registro se aprende en la misma base. Sin ninguna clave privada, quien escribiera en la base daba de alta una identidad, firmaba una lápida y borraba una lectura anclada con `verify()` en verde, también contra el ancla | Autoridad de redacción aprovisionada fuera del almacén | §3.6 |
| **R2** | Varias ediciones del disco, y una lápida mal formada, lanzaban excepciones en vez de devolver un fallo: `/api/status` y `/api/audit` en 500 | Fallo de verificación en cada caso probado | §3.5 |
| **R3** | Una lectura en `+02:00` dejaba `integrity_ok: false` para siempre, sin ningún ataque | Lecturas guardadas en UTC | §3.5 |
| **R4** | El código y este documento justificaban el atajo `signatures_from` con el encadenamiento, que no cubre la última entrada | Justificación corregida y límite probado | §3.5 |
| **R5** | `query()` filtraba por campos sin verificar: una lectura movida a otro tripulante desaparecía sin error | Contenido verificado antes de filtrar | §3.5 |
| **R6** | Carrera al crear identidades en la API; un conflicto de clave salía como 500 | Cerrojo; 409 | — |
| **R7** | Una lápida basura al final desviaba `failed_index` y tapaba una edición anterior | Las lápidas inválidas fallan en su posición | — |
| **R8** | Un ancla con tamaño negativo validaba | Ancla validada | §3.3 |
| **R9** | Un motivo invisible (U+200B) pasaba | Se exige al menos una letra o cifra | §3.6 |
| **R10** | `/api/audit` verificaba y anclaba en instantes distintos | Una sola instantánea | — |
| **R11** | Dos pruebas espejo: una comparaba la función con lo que ella misma llama | Sustituidas por comparación con RFC 6962 | §6 |

Las cuatro afirmaciones sin respaldo, ya corregidas: que la parte anclada no se podía falsificar
(§3.2) —las cabeceras no, pero el contenido sí se podía suprimir—; que el ancla protegía frente a una
reescritura con control total del almacén (§3.3) —no cubre el payload—; que se corroboraba la
no-destrucción (§5); y que una lápida no se podía falsificar (§6).

### 7.3 Tercera revisión (2026-09-22)

Una tercera revisión atacó la segunda ronda. `verify()` resistió todos los ataques de autoridad que
probó; el bloqueante estaba otra vez en una corrección anterior, y de nuevo este documento afirmaba
lo contrario (§3.5, §5 y §6).

| | Hallazgo | Corrección | Sección |
|---|---|---|---|
| **T1** | La marca de agua de `query()` comparaba cada payload con un `content_hash` sin verificar. Tras reabrir, recalcular el hash o cambiar `entry_type` —sin ninguna clave— hacía que el motor omitiera una lectura o la recibiera alterada. Y `redacted_indices()` aceptaba una lápida legítima copiada de otro almacén con la misma autoridad | `query()` verifica la cadena entera antes del primer uso; la lápida queda atada a su entrada | §3.5, §3.6 |
| **T2** | Carrera en `get_store()`: peticiones simultáneas creaban almacenes distintos y se perdían lecturas confirmadas con 201 | Cerrojo | — |
| **T3** | Valores de tipo inesperado en disco (BLOB, índice decimal) seguían lanzando en caliente y al reabrir; una base corrupta en reposo impedía arrancar | Cabecera comprobada por tipos; cotejo con el disco cubierto entero; carga tolerante | §3.5 |
| **T4** | La autoridad podía redactar un asiento ya manipulado, y la cadena pasaba a verde | No se redacta sobre una cadena que no verifica | §3.6 |
| **T5** | Una prueba de R5 seguía espejando la corrección: movía la lectura sin recalcular el hash | Sustituida por el ataque con el hash recalculado | §6 |

Cada hallazgo se reprodujo con una prueba que fallaba antes de corregirlo. Los scripts de ataque del
revisor, ejecutados después contra el código corregido, fallan todos.

### 7.4 Cuarta revisión (2026-09-22)

La cuarta revisión no rompió `verify()` ni la marca de agua de `query()`: aguantaron las seis
secuencias de ataque que probó. Lo que encontró estaba alrededor, y de nuevo este documento afirmaba
algo falso.

| | Hallazgo | Corrección | Sección |
|---|---|---|---|
| **C1** | Con el registro aprendido de la base, quien escribiera en ella borraba la cola desde la taquicardia y volvía a encadenar las lecturas inocuas con una identidad nueva: verificación en verde. Este documento decía que nadie podía suprimir contenido "anclado o no", y en la práctica nada está anclado | Modo de fuentes aprovisionadas; el límite del modo aprendido, declarado y probado | §3.2, §3.3 |
| **C2** | La carga y el cotejo seguían lanzando con UTF-8 inválido, JSON anidado a miles de niveles, un NULL o una identidad repetida; un sustituto UTF-16 suelto daba un 500 en la API | Decodificación tolerante, límite de anidamiento, tipos comprobados y un manejador de validación que siempre se puede serializar | §3.5 |
| **C3** | La redacción no borraba: el dato quedaba en el fichero, y el hash de la lápida se invertía con un diccionario | `secure_delete` y una sal aleatoria en cada payload | §3.1, §3.6 |
| **C4** | Una fecha futura falsa en el último asiento se heredaba en todas las escrituras siguientes | El reloj solo sigue a un asiento anterior que verifica | §3.1 |
| **C5** | Dos correcciones de la tercera ronda no las cubría ninguna prueba: quitándolas, la suite seguía en verde | Pruebas que ejecutan lo que esas correcciones impiden | §6 |
| **C6** | §1.1 citaba 21 CFR 11.10(e) cortado justo antes de *"Record changes shall not obscure previously recorded information"*, que choca con la redacción; §2 atribuía a HIPAA una capacidad de suprimir que su norma de rectificación, §164.526, no da | Cita completa, conflicto declarado | §1.1, §1.2, §3.6 |

El revisor citó C6 de memoria; el texto de 11.10(e) y de §164.526 se verificó después en Cornell
LII.

### 7.5 Quinta revisión (2026-09-22)

La quinta revisión bloqueó por los dos endpoints de importación nuevos (Apple Health y Google Fit):
unidades ignoradas —170 lb guardadas como 170 kg—, fechas sin límite —una lectura de 2099 tapaba
las desviaciones de hoy—, entradas triviales que daban 500, amplificación lineal de entidades XML y
topes comprobados con el cuerpo ya en memoria. No son hallazgos de integridad de registros; están
corregidos y probados en `backend/tests/test_import.py` y `backend/tests/test_wearable.py`. Las
correcciones de la cuarta ronda aguantaron: modo aprovisionado, sal, `secure_delete` en el fichero
principal y reloj en modo aprovisionado. Lo que sí toca a este documento:

| | Hallazgo | Corrección | Sección |
|---|---|---|---|
| **Q1** | En modo aprovisionado, dar de alta una fuente nueva en una base existente dejaba la verificación en rojo para siempre y bloqueaba las redacciones | Se añaden las fuentes aprovisionadas que falten en `trusted_keys` | §3.2 |
| **Q2** | La corrección del reloj se afirmaba sin condiciones y solo protege en modo aprovisionado | Declarado | §3.1 |
| **Q3** | "Nunca en un 500" era falso: una lectura mal formada firmada por una identidad dada de alta en la base tumbaba `query()` y la verificación | 409 y fallo de verificación; el límite del esquema, declarado | §3.5 |
| **Q4** | "Borrar es borrar" en el fichero principal, pero el journal de SQLite conserva el dato en bloques libres del disco | Declarado | §3.6 |
| **Q5** | El manejador de validación seguía dando 500 con un JSON anidado a cientos de niveles | Ya no devuelve el dato recibido, solo su tipo | — |
| **Q6** | `_link_hash` y el saneado de anidamiento no tenían prueba propia; la prueba de XXE ponía la entidad donde el importador no lee y no podía fallar | Pruebas nuevas y corregida | §6 |
| **Q7** | Cifras del documento medidas sin fijar el proceso a un núcleo de rendimiento, y una fórmula que atribuía sal también a las lápidas | Cifras remedidas con sus condiciones; fórmula corregida | §3.1, §3.4, §3.5 |

**Lo que sigue abierto**, y este documento no reclama: autenticación de operadores; auditoría de
lecturas; transmisión y sellado del ancla en Tierra, y con ella cualquier verificación contra un
ancla, que hoy no hace ningún camino de la aplicación; aprovisionamiento del registro de claves y de
la clave de redacción desde Tierra (en la demo, la autoridad es efímera por proceso y la API usa el
registro aprendido); rotación de claves de las fuentes aprovisionadas; claves privadas en hardware
seguro; cifrado del disco, sin el cual el journal de SQLite conserva lo redactado en bloques libres;
un almacén en fichero entre reinicios, porque las claves de las fuentes se generan por proceso y
chocarían con las ya fijadas; exportación como `AuditEvent`; y JCS para verificadores escritos en
otro lenguaje.

**Cerrado después de esa revisión:** la enmienda anexada de §164.526, que era la carencia más citada
de este documento, está implementada y especificada en §3.7.

**Lo que no cierra la cabecera de la consola (2026-10-31).** `POST /api/simulate`, `POST
/api/comms/preload` y las dos importaciones (`/api/import/apple-health`, `/api/import/google-fit`)
exigen desde esa fecha la cabecera `X-EMMA-Console: 1` y sin ella responden 403
(`backend/app/api/console_header.py`; `hmi-state-of-the-art.md` §5.39.23). Es una barrera a la
**petición simple**: la que otra página abierta en el mismo navegador que la consola podía mandar
sin comprobación previa de CORS, porque esas órdenes no llevan cuerpo JSON. **No es autenticación**:
el valor es fijo y público, no identifica a nadie ni autoriza nada, y cualquier cliente que llegue
al puerto la pone y pasa. La «autenticación de operadores» del párrafo de arriba sigue abierta tal
como está, y todo campo «declarado, sin autenticar» de este documento lo sigue siendo. Tampoco
cubre toda la API: otros `POST` fuera de `api/routes.py` siguen al alcance de una petición simple
y están apuntados en `hmi-state-of-the-art.md` §5.39.23, pendientes de decisión. **Cerrado el
2026-11-16** por orden de Ellande: esas diez rutas llevan ya la cabecera y la lista de pendientes
está vacía (§5.39.23, «Cerrado»).

**Solo por loopback: Host y Origin (2026-11-16).** La cabecera no frena el *DNS rebinding*: una
página cuyo nombre pasa a resolver a 127.0.0.1 es, para el navegador, de mismo origen, lee las
respuestas y pone `X-EMMA-Console` (auditoría run-2, `emma:api:dns-rebinding-no-host-allowlist`;
podía forzar `/api/app-update/check` → `/download` → `/install` o el modo seguro). Desde esa fecha
`backend/app/core/host_guard.py`, por fuera de todo, rechaza con 400 un `Host` que no sea
`127.0.0.1`, `localhost` o `[::1]` (cualquier puerto; `testserver` en las pruebas) y con 403 toda
orden que no sea GET/HEAD/OPTIONS con un `Origin` ajeno a loopback. Sin `Origin` pasa: el arranque
de escritorio, el puente de Marplanner y `curl` no son navegadores. Tampoco esto es autenticación:
un proceso de la misma máquina sigue llegando al puerto. Pruebas en
`backend/tests/test_host_guard.py`, campaña `tests/mutants/host_guard.json`.

### 7.6 Sexta revisión (2026-09-22)

Acotada otra vez a la importación, y de nuevo fuera de la integridad de registros: los cinco
hallazgos están en `ingest/wearable.py` y en el bloque de importación de `api/routes.py`. Ninguna
caída provocable desde el cuerpo de la petición, que era lo que más se buscó. Se corrigieron todos.

| | Hallazgo | Corrección |
|---|---|---|
| **S1** | La saturación se escalaba "si el valor es ≤ 1": un `1` —que el catálogo acepta como 1 %, hipoxia muy por debajo del límite crítico de 88— se guardaba como **100 %**, nominal y firmado. La alerta más grave posible se volvía normalidad, en silencio | La escala la decide el formato, no la magnitud: en un export de Apple la saturación **es** una fracción 0-1 y siempre se escala; lo que no cabe en 0-1 se rechaza con su motivo |
| **S2** | `element.clear()` dejaba cada registro vacío colgado de la raíz | Se suelta también la raíz. **La medición del hallazgo era otra cosa**: el multiplicador de ~4× es del parser y del texto en memoria, no de los elementos retenidos —200 registros grandes cuestan lo mismo que 20 000 pequeños del mismo tamaño—. La retención eran ~80 bytes por registro. Declarado en el código con las dos cifras |
| **S3** | El riesgo real que S2 dejaba abierto: el tope por petición no acota **cuántas** importaciones corren a la vez, y el pool de Starlette admite 40 | `MAX_CONCURRENT_IMPORTS = 2`, esperando en la corrutina para no ocupar un hilo del pool. Pico acotado a ~200 MB |
| **S4** | El motivo "unidad no admitida" no truncaba la unidad: 20 registros con una unidad de 500 KB devolvían 9,5 MB de JSON, justo lo que `_RejectionLog` dice impedir | Se trunca la unidad como el resto de partes variables, y `_RejectionLog.append` trunca el mensaje entero como red de seguridad |
| **S5** | Dos pruebas no ejercían lo que documentaban: la bomba de entidades y el XXE los corta el filtro textual de `_xml_text` antes de llegar al parser, así que el límite de amplificación de expat no tenía ninguna prueba viva | Docstrings corregidos —dicen qué capa corta— y una prueba nueva que llama al adaptador directamente para que ese límite siga vigilado |

Lo verificado y descartado también quedó dicho: no hay middleware de compresión que amplifique el
cuerpo, `Content-Length` mentiroso no cuela, `float()`/`int()` sobre atributos gigantes no son un
DoS, y ElementTree no resuelve entidades externas ni con DTD externa.

Pruebas nuevas, en `backend/tests/test_import.py`:
`test_a_percentage_saturation_is_rejected_not_inverted` ·
`test_a_low_saturation_arrives_as_the_critical_reading_it_is` ·
`test_a_real_apple_saturation_still_becomes_a_percentage` (S1) ·
`test_the_parser_does_not_keep_every_record_in_memory` (S2) ·
`test_a_giant_unit_does_not_come_back_in_the_response` (S4) ·
`test_expat_still_cuts_the_amplification_behind_the_filter` (S5).
