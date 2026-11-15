"""Ledger de integridad: log append-only encadenado por hash, firmado y anclable.

Implementa el diseño de `compliance/record-integrity.md`. Satisface:

  - 21 CFR 11.10(a)  discernir registros alterados       -> cadena de hashes
  - 21 CFR 11.10(e)  audit trail con marca de tiempo     -> entradas firmadas
  - 45 CFR 164.312(c)(2)  corroborar no-alteracion       -> verificacion + Merkle

Propiedad de diseño central: **la cadena almacena el hash del contenido clinico, no
el contenido**. Eso permite redactar o suprimir un dato (derecho de rectificacion)
sin romper la demostracion de que el resto no se toco.

Opera sin red. El anclaje externo de la raiz de Merkle es opcional, pero es el unico
testigo que no puede reescribir quien controle todo el almacen local (ver `Anchor`).

LO QUE ENCONTRO UNA REVISION ADVERSARIA (2026-09-21)
----------------------------------------------------
Siete ataques, todos ejecutados contra la version anterior, que la suite no veia
porque sus pruebas espejaban la implementacion en vez de la propiedad:

  - La firma se verificaba con la clave publica **guardada en la propia entrada**.
    Reescribir la cadena entera con una clave propia y el mismo `signer` validaba.
  - Redactar borraba el contenido sin dejar rastro, y la marca `redacted` no estaba
    firmada: se podia borrar una alerta critica y la cadena seguia en verde.
  - El arbol de Merkle duplicaba el nodo impar (CVE-2012-2459) sin separar hojas de
    nodos internos: dos conjuntos de hojas distintos daban la misma raiz.
  - `default=str` al serializar: `Decimal("1.5")` y `"1.5"` tenian el mismo hash.
  - Truncar la cola verificaba limpio; la marca de tiempo la ponia quien llamaba; el
    payload se guardaba por referencia; `redact(-1)` redactaba la ultima entrada; el
    hash encadenado no cubria la firma; y no habia ningun cerrojo.

Cada uno tiene ahora una prueba en `tests/test_ledger.py` que ejecuta el ataque.

Una segunda revision (2026-09-22) rompio el arreglo de la redaccion: cualquier clave
del registro podia firmar una lapida, y el registro se aprende en la misma base que la
cadena. Quien escribiera en la base borraba una lectura ya anclada con `verify()` en
verde. Ver `RedactionAuthority`.

Una cuarta (2026-09-22) encontro que, con el registro aprendido de la base, quien
escribiera en ella podia reencadenar la cola con una identidad nueva; que el hash de
una lapida se invertia con un diccionario; y que una fecha futura falsa arrastraba el
reloj. Ver `KeyRegistry(fixed=True)`, `SALT_FIELD` y `_timestamp`.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import secrets
import threading
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

GENESIS_PREV_HASH = "0" * 64

# Asiento que registra una redaccion. Reservado: solo `redact()` lo escribe.
REDACTION_ENTRY_TYPE = "redaction"

# Asiento que corrige otro sin borrarlo. Reservado: solo `amend()` lo escribe.
#
# Es la via de correccion que presupone 45 CFR 164.526: lo mal registrado se rectifica
# **anexando** la version buena y enlazandola con la anterior, no borrandola. La
# redaccion hace lo contrario —suprime el contenido— y por eso choca con el mandato de
# 21 CFR 11.10(e) de que un cambio no oculte lo registrado antes. Con las dos vias, cada
# caso usa la suya: se enmienda un dato equivocado, se redacta uno que nunca debio
# registrarse.
AMENDMENT_ENTRY_TYPE = "amendment"

# Viaja con cada ancla: una raiz no significa nada sin saber como se calculo. La
# version anterior (duplicacion del nodo impar, sin prefijos) no es compatible, y no
# llego a emitirse ningun ancla con ella.
MERKLE_ALGORITHM = "rfc6962-sha256"

# Campo que el ledger anade a cada payload con 16 bytes aleatorios. Sin el, el
# `content_hash` de una lectura clinica —pocos valores posibles— se invertia probando
# candidatos, y la lapida, que lo repite, permitia recuperar el dato redactado.
SALT_FIELD = "_salt"

# Profundidad maxima de un payload. Un JSON anidado a mil niveles agotaba la pila al
# verificar, y a partir de unos tres mil impedia abrir el almacen.
MAX_JSON_DEPTH = 32

_LEAF_PREFIX = b"\x00"
_NODE_PREFIX = b"\x01"

_TOMBSTONE_FIELDS: dict[str, type] = {
    "target_index": int,
    "target_entry_hash": str,
    "target_content_hash": str,
    "reason": str,
    "requested_by": str,
}

# Una enmienda lleva sal, como cualquier contenido clinico: `replacement` es una lectura
# con pocos valores posibles, y sin sal su `content_hash` se invierte probando. La lapida
# no la lleva porque no contiene el dato, solo su hash.
_AMENDMENT_FIELDS: dict[str, type] = {
    "target_index": int,
    "target_entry_hash": str,
    "target_content_hash": str,
    "reason": str,
    "amended_by": str,
    "replacement": dict,
    SALT_FIELD: str,
}


# --------------------------------------------------------------------------- #
# Serializacion
# --------------------------------------------------------------------------- #


def _check_json(value: Any, path: str = "$", depth: int = 0) -> None:
    """Rechaza todo lo que no sea JSON estricto.

    Con `default=str`, cualquier tipo desconocido se serializaba como su `str()`:
    `Decimal("1.5")` y `"1.5"`, o un `datetime` y su texto, daban los mismos bytes y
    el mismo hash. Se podia cambiar el tipo de un dato clinico sin que `verify()` lo
    viera. Las claves enteras colapsaban con su texto, las tuplas con las listas, y
    NaN salia como un literal que ningun verificador externo puede releer.

    Tambien se rechaza lo que no se puede codificar —un sustituto UTF-16 suelto— y lo
    anidado mas alla de `MAX_JSON_DEPTH`.

    Normalizar es trabajo del origen del dato; el ledger no adivina.
    """
    if depth > MAX_JSON_DEPTH:
        raise ValueError(f"{path}: anidamiento de más de {MAX_JSON_DEPTH} niveles")
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, str):
        _check_text(value, path)
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path}: {value!r} no es un número JSON")
        return
    if isinstance(value, list):
        for position, item in enumerate(value):
            _check_json(item, f"{path}[{position}]", depth + 1)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path}: la clave {key!r} no es texto")
            _check_text(key, path)
            _check_json(item, f"{path}.{key}", depth + 1)
        return
    raise TypeError(f"{path}: {type(value).__name__} no es un tipo JSON")


def _check_text(value: str, path: str) -> None:
    # Un sustituto UTF-16 suelto ("\ud800") es un `str` valido en Python pero no se puede
    # codificar: llegaba hasta `encode("utf-8")` y salia por la API como un 500.
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{path}: texto no representable en UTF-8") from exc


def canonical_bytes(obj: Any) -> bytes:
    """Serializacion canonica: JSON estricto, claves ordenadas, sin espacios.

    Dos procesos distintos deben producir exactamente los mismos bytes para el mismo
    objeto, o los hashes no seran comparables. Entre procesos Python esto basta; para
    interoperar con otro lenguaje haria falta JCS (RFC 8785), que fija tambien el
    formato de los numeros en coma flotante.
    """
    _check_json(obj)
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- #
# Identidad, firma y registro de confianza
# --------------------------------------------------------------------------- #


class Identity:
    """Par de claves Ed25519 de una fuente de datos.

    Una fuente es un wearable, un tripulante o el simulador en modo demo. Firmar
    demuestra *quien* origino la entrada, la parte de 21 CFR 11.10(e) que la marca de
    tiempo no cubre — siempre que la clave se contraste con `KeyRegistry`.
    """

    def __init__(self, identity_id: str, private_key: Ed25519PrivateKey) -> None:
        self.identity_id = identity_id
        self._private_key = private_key

    @classmethod
    def generate(cls, identity_id: str) -> Identity:
        return cls(identity_id, Ed25519PrivateKey.generate())

    @property
    def public_key_hex(self) -> str:
        raw = self._private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return raw.hex()

    def sign(self, data: bytes) -> str:
        return self._private_key.sign(data).hex()

    @staticmethod
    def verify(public_key_hex: str, data: bytes, signature_hex: str) -> bool:
        try:
            public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
            public_key.verify(bytes.fromhex(signature_hex), data)
        except (InvalidSignature, ValueError, TypeError):  # TypeError: un BLOB de disco
            return False
        return True


class UntrustedSigner(Exception):
    """La identidad no esta en el registro, o no con esa clave."""


class KeyConflict(UntrustedSigner):
    """Se intento fijar una identidad ya conocida a otra clave."""


class KeyRegistry:
    """Claves publicas de confianza por identidad: la raiz de la procedencia.

    POR QUE EXISTE
    --------------
    `verify()` comprobaba la firma con `signer_public_key`, un campo de la misma
    entrada que estaba verificando: la entrada se certificaba a si misma. Un atacante
    generaba una clave, reescribia la cadena entera con el mismo `signer` y la firmaba:
    `verify()` daba ok. Ahora la clave de cada identidad vive aqui, fuera de las
    entradas, y toda entrada tiene que usar la registrada.

    Cada identidad queda **fijada** a su primera clave. Eso impide suplantar una fuente
    conocida, que es el ataque real; dar de alta una fuente nueva no suplanta a nadie.

    LIMITE, DECLARADO
    -----------------
    El registro es tan fiable como el sitio donde se guarda. Quien pueda reescribir a
    la vez el registro y la cadena puede falsificar la parte **no anclada**. La
    anclada no: la raiz de Merkle compromete la clave publica y la firma de cada
    entrada. En produccion el registro llegaria aprovisionado desde Tierra antes del
    lanzamiento; aqui se aprende en el primer uso y se persiste aparte.
    """

    def __init__(self, keys: Mapping[str, str] | None = None, *, fixed: bool = False) -> None:
        self._keys: dict[str, str] = {}
        self._fixed = False
        for identity_id, public_key_hex in (keys or {}).items():
            self.register(identity_id, public_key_hex)
        # FIJO: APROVISIONADO, NO APRENDIDO.
        #
        # Aprendido en el primer uso, quien escribiera en la base daba de alta una
        # identidad nueva —el registro la admitia: no suplantaba a nadie— y con ella
        # reencadenaba la cola: la verificacion salia en verde sin ninguna clave del
        # sistema. Un registro fijo no admite altas despues de construirse.
        self._fixed = fixed

    @property
    def fixed(self) -> bool:
        return self._fixed

    def __contains__(self, identity_id: object) -> bool:
        return identity_id in self._keys

    def __len__(self) -> int:
        return len(self._keys)

    def register(self, identity_id: str, public_key_hex: str) -> bool:
        """Fija la clave de una identidad. Devuelve True si es un alta nueva."""
        known = self._keys.get(identity_id)
        if known is None and self._fixed:
            raise UntrustedSigner(
                f"registro aprovisionado: {identity_id!r} no está entre las fuentes de confianza"
            )
        if known is not None:
            if known != public_key_hex:
                raise KeyConflict(f"la identidad {identity_id!r} ya está fijada a otra clave")
            return False
        try:
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        except ValueError as exc:
            raise ValueError(f"clave pública no válida para {identity_id!r}") from exc
        self._keys[identity_id] = public_key_hex
        return True

    def is_trusted(self, identity_id: str, public_key_hex: str) -> bool:
        return self._keys.get(identity_id) == public_key_hex

    def items(self) -> list[tuple[str, str]]:
        return sorted(self._keys.items())

    def _snapshot(self) -> dict[str, str]:
        return dict(self._keys)

    def _restore(self, snapshot: dict[str, str]) -> None:
        self._keys = dict(snapshot)


# --------------------------------------------------------------------------- #
# Entradas
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class LedgerEntry:
    """Una entrada inmutable del ledger.

    `payload` es el contenido clinico y puede ser `None` tras una redaccion.
    `content_hash` se calcula al crear la entrada y **nunca** cambia, de modo que la
    cadena sigue verificando despues de redactar.
    """

    index: int
    recorded: datetime
    entry_type: str
    content_hash: str
    prev_hash: str
    signer: str
    signer_public_key: str
    signature: str
    payload: dict[str, Any] | None
    redacted: bool = False

    def _header(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "recorded": self.recorded.isoformat(),
            "entry_type": self.entry_type,
            "content_hash": self.content_hash,
            "prev_hash": self.prev_hash,
            "signer": self.signer,
            "signer_public_key": self.signer_public_key,
        }

    def signing_material(self) -> bytes:
        """Bytes que se firman: la cabecera, con el hash del contenido y no el contenido.

        Excluye `payload` —por eso redactar no invalida la firma— y `redacted`, que
        cambia despues de firmar. Que una entrada este redactada no lo decide esa
        marca, sino una lapida firmada (ver `HashChainLedger.redact`).
        """
        return canonical_bytes(self._header())

    def entry_hash(self) -> str:
        """Hash que enlaza la entrada siguiente y del que sale la hoja de Merkle.

        Cubre la cabecera **y la firma**. Antes era solo el hash de la cabecera, asi
        que ni la cadena ni la raiz anclada comprometian quien firmo: el ancla
        atestiguaba metadatos, no procedencia.
        """
        return sha256_hex(canonical_bytes({**self._header(), "signature": self.signature}))


def _clone_json(value: Any) -> Any:
    """Copia profunda de JSON estricto, que es lo unico que admite un payload.

    `copy.deepcopy` generico es ~3 veces mas lento (51 ms frente a 15 ms sobre
    21 120 asientos), y `entries` copia la cadena entera en cada consulta del motor.
    """
    if isinstance(value, dict):
        return {key: _clone_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clone_json(item) for item in value]
    return value


def _detached(entry: LedgerEntry) -> LedgerEntry:
    """La entrada con un payload propio: nadie de fuera comparte el guardado."""
    return replace(entry, payload=_clone_json(entry.payload))


# --------------------------------------------------------------------------- #
# Memoria vigilada: saber sin releerla que la cadena no ha cambiado
# --------------------------------------------------------------------------- #
#
# POR QUE EXISTE (2026-11-03)
# ---------------------------
# `/api/status` verificaba en cada consulta el hash de contenido de TODAS las entradas:
# con 40 dias simulados, ~94 000 asientos y ~2,5 s de serializacion canonica por consulta,
# el 75 % del tiempo del estado. La consola lo pide cada 30 s y el asistente de voz en cada
# turno. Recalcular lo ya verificado solo sirve para descubrir que la memoria cambio; eso se
# puede saber sin releerla si cada mutacion deja rastro.
#
# El dataclass `LedgerEntry` es inmutable, pero su payload es un `dict`: mutarlo en sitio
# fue un fallo real (las lecturas de analitica anotadas sobre el asiento firmado). Por eso el
# payload guardado se convierte en estos contenedores, que cuentan cada mutacion en
# `_payload_edits` despues de hacerla. La lista de asientos cuenta en `rewrites` todo lo que no
# sea anadir al final. Con los dos contadores iguales, lo verificado sigue siendo lo que se
# verifico, y `verify()` puede empezar donde lo dejo (`record-integrity.md` §3.5 bis).
#
# Lo que NO cubre, y se declara: quien llame a `dict.__setitem__(payload, ...)` o a
# `object.__setattr__` sobre un asiento congelado esquiva la vigilancia a proposito. Ese es
# codigo dentro del proceso con intencion de enganar, y podria igual de facil sustituir el
# propio verificador: no es una amenaza que la verificacion pueda cerrar.

_payload_edits = 0


def _note_payload_edit() -> None:
    """Deja rastro de una mutacion en sitio de un payload guardado, DESPUES de hacerla.

    Despues y no antes: contado antes, una marca tomada entre la cuenta y la mutacion ya
    incluiria la mutacion y la daria por vista sin haberla visto.
    """
    global _payload_edits
    _payload_edits += 1


def _watched(value: Any, depth: int = 0) -> Any:
    """Copia de un payload en contenedores vigilados, con los mismos valores y tipos.

    Solo cambia la clase de `dict` y `list`: lo demas se deja tal cual, para que un tipo que
    no es JSON siga fallando en `verify()` igual que antes. Mas alla de `MAX_JSON_DEPTH` no se
    desciende: ese payload no verifica nunca, asi que nunca forma parte de lo verificado.
    """
    if depth > MAX_JSON_DEPTH:
        return value
    if isinstance(value, dict):
        return _WatchedDict({key: _watched(item, depth + 1) for key, item in value.items()})
    if isinstance(value, list):
        return _WatchedList([_watched(item, depth + 1) for item in value])
    return value


class _WatchedDict(dict[str, Any]):
    """Un `dict` que cuenta cada cambio una vez hecho. Lo que entra, entra vigilado tambien.

    Copiarlo (`copy`, `deepcopy`, `pickle`) da un `dict` normal: la copia es de quien la
    pide, y mutarla no es mutar el asiento.
    """

    __slots__ = ()

    def __setitem__(self, key: str, value: Any) -> None:
        try:
            super().__setitem__(key, _watched(value))
        finally:
            _note_payload_edit()

    def __delitem__(self, key: str) -> None:
        try:
            super().__delitem__(key)
        finally:
            _note_payload_edit()

    def clear(self) -> None:
        try:
            super().clear()
        finally:
            _note_payload_edit()

    def pop(self, *args: Any) -> Any:
        try:
            return super().pop(*args)
        finally:
            _note_payload_edit()

    def popitem(self) -> tuple[str, Any]:
        try:
            return super().popitem()
        finally:
            _note_payload_edit()

    def setdefault(self, key: str, default: Any = None) -> Any:
        try:
            return super().setdefault(key, _watched(default))
        finally:
            _note_payload_edit()

    def update(self, *args: Any, **kwargs: Any) -> None:
        try:
            for key, value in dict(*args, **kwargs).items():
                super().__setitem__(key, _watched(value))
        finally:
            _note_payload_edit()

    def __ior__(self, other: Any) -> _WatchedDict:  # type: ignore[override,misc]
        self.update(other)
        return self

    def __copy__(self) -> dict[str, Any]:
        return dict(self)

    def __deepcopy__(self, memo: dict[int, Any]) -> dict[str, Any]:
        return {key: copy.deepcopy(item, memo) for key, item in self.items()}

    def __reduce_ex__(self, protocol: Any) -> tuple[Any, ...]:
        return (dict, (dict(self),))


class _WatchedList(list[Any]):
    """Una `list` que cuenta cada cambio una vez hecho, como `_WatchedDict`."""

    __slots__ = ()

    def __setitem__(self, index: Any, value: Any) -> None:
        try:
            if isinstance(index, slice):
                super().__setitem__(index, [_watched(item) for item in value])
            else:
                super().__setitem__(index, _watched(value))
        finally:
            _note_payload_edit()

    def __delitem__(self, index: Any) -> None:
        try:
            super().__delitem__(index)
        finally:
            _note_payload_edit()

    def append(self, value: Any) -> None:
        try:
            super().append(_watched(value))
        finally:
            _note_payload_edit()

    def extend(self, values: Iterable[Any]) -> None:
        try:
            super().extend(_watched(item) for item in values)
        finally:
            _note_payload_edit()

    def insert(self, index: Any, value: Any) -> None:
        try:
            super().insert(index, _watched(value))
        finally:
            _note_payload_edit()

    def pop(self, *args: Any) -> Any:
        try:
            return super().pop(*args)
        finally:
            _note_payload_edit()

    def remove(self, value: Any) -> None:
        try:
            super().remove(value)
        finally:
            _note_payload_edit()

    def reverse(self) -> None:
        try:
            super().reverse()
        finally:
            _note_payload_edit()

    def sort(self, *args: Any, **kwargs: Any) -> None:
        try:
            super().sort(*args, **kwargs)
        finally:
            _note_payload_edit()

    def clear(self) -> None:
        try:
            super().clear()
        finally:
            _note_payload_edit()

    def __iadd__(self, values: Iterable[Any]) -> _WatchedList:  # type: ignore[misc]
        self.extend(values)
        return self

    def __imul__(self, times: Any) -> _WatchedList:  # type: ignore[misc]
        try:
            return super().__imul__(times)
        finally:
            _note_payload_edit()

    def __copy__(self) -> list[Any]:
        return list(self)

    def __deepcopy__(self, memo: dict[int, Any]) -> list[Any]:
        return [copy.deepcopy(item, memo) for item in self]

    def __reduce_ex__(self, protocol: Any) -> tuple[Any, ...]:
        return (list, (list(self),))


def _watched_entry(entry: LedgerEntry) -> LedgerEntry:
    """El asiento con el payload vigilado. Si ya lo esta, el mismo objeto."""
    if entry.payload is None or type(entry.payload) is _WatchedDict:
        return entry
    return replace(entry, payload=_watched(entry.payload))


class _EntryList(list[LedgerEntry]):
    """La lista de asientos: anadir al final es lo normal; cualquier otro cambio, una reescritura.

    `rewrites` cuenta las reescrituras (redaccion, deshacer una transaccion, o un cambio a
    mano). Lo que entra lo hace con el payload vigilado.
    """

    __slots__ = ("rewrites",)

    def __init__(self) -> None:
        super().__init__()
        self.rewrites = 0

    def append(self, entry: LedgerEntry) -> None:
        super().append(_watched_entry(entry))

    def extend(self, entries: Iterable[LedgerEntry]) -> None:
        super().extend(_watched_entry(entry) for entry in entries)

    def __iadd__(self, entries: Iterable[LedgerEntry]) -> _EntryList:  # type: ignore[override,misc]
        self.extend(entries)
        return self

    def __setitem__(self, index: Any, value: Any) -> None:
        try:
            if isinstance(index, slice):
                super().__setitem__(index, [_watched_entry(entry) for entry in value])
            else:
                super().__setitem__(index, _watched_entry(value))
        finally:
            self.rewrites += 1

    def __delitem__(self, index: Any) -> None:
        # Borrar un tramo vacio no reescribe nada: es lo que hace `transaction()` al deshacer
        # una escritura rechazada antes de anadir, y no debe costar una verificacion completa.
        before = len(self)
        try:
            super().__delitem__(index)
        finally:
            if len(self) != before:
                self.rewrites += 1

    def insert(self, index: Any, entry: LedgerEntry) -> None:
        try:
            super().insert(index, _watched_entry(entry))
        finally:
            self.rewrites += 1

    def pop(self, *args: Any) -> LedgerEntry:
        try:
            return super().pop(*args)
        finally:
            self.rewrites += 1

    def remove(self, entry: LedgerEntry) -> None:
        try:
            super().remove(entry)
        finally:
            self.rewrites += 1

    def reverse(self) -> None:
        try:
            super().reverse()
        finally:
            self.rewrites += 1

    def sort(self, *args: Any, **kwargs: Any) -> None:
        try:
            super().sort(*args, **kwargs)
        finally:
            self.rewrites += 1

    def clear(self) -> None:
        try:
            super().clear()
        finally:
            self.rewrites += 1

    def __imul__(self, times: Any) -> _EntryList:  # type: ignore[misc]
        try:
            return super().__imul__(times)
        finally:
            self.rewrites += 1


@dataclass(frozen=True, eq=False)
class MemoryMark:
    """Lo que hace falta para saber, sin releerla, que la memoria no ha cambiado.

    `eq=False`: comparar dos marcas con `==` compararia las listas enteras. Se compara con
    `HashChainLedger.unchanged_since`.
    """

    entries: list[LedgerEntry]
    rewrites: int
    payload_edits: int
    registry: tuple[tuple[str, str], ...]
    authority: RedactionAuthority | None


# Tipos de asiento cuya validez depende de otro asiento anterior. Si uno aparece entre las
# entradas nuevas, lo ya verificado se vuelve a verificar entero (`reusable_prefix`).
_CROSS_ENTRY_TYPES = frozenset({REDACTION_ENTRY_TYPE, AMENDMENT_ENTRY_TYPE})


@dataclass(frozen=True)
class RedactionAuthority:
    """La unica identidad que puede firmar lapidas. Se aprovisiona; no se aprende.

    POR QUE NO BASTA EL REGISTRO
    ----------------------------
    Cualquier clave registrada podia firmar una lapida, y el registro se aprende en el
    primer uso y vive en la misma base que la cadena. Quien pudiera escribir en la base,
    sin ninguna clave privada del sistema, daba de alta una identidad nueva, firmaba una
    lapida y suprimia una lectura ya anclada: `verify()` salia en verde, tambien contra
    el ancla previa, porque la hoja de Merkle no cubre el payload.

    La autoridad llega al ledger al construirlo, desde fuera del almacen, y nunca se lee
    de `trusted_keys`. Sin autoridad no hay redacciones, y cualquier lapida falla.
    """

    identity_id: str
    public_key_hex: str
    # Nombres que la autoridad tuvo antes (`FORMER_AUTHORITY_IDS`). Una lapida firmada con uno
    # de ellos es de la autoridad solo si la clave es la misma: el nombre no basta.
    former_ids: tuple[str, ...] = ()

    @classmethod
    def of(cls, identity: Identity) -> RedactionAuthority:
        return cls(
            identity.identity_id,
            identity.public_key_hex,
            FORMER_AUTHORITY_IDS.get(identity.identity_id, ()),
        )

    def names(self, signer: str) -> bool:
        """`signer` es el nombre de la autoridad, el de hoy o uno anterior."""
        return signer == self.identity_id or signer in self.former_ids

    def matches(self, signer: str, public_key_hex: str) -> bool:
        return self.names(signer) and public_key_hex == self.public_key_hex


# EL NOMBRE DE ANTES DE LA AUTORIDAD (2026-11-02; `record-integrity.md` §3.6)
# ----------------------------------------------------------------------------
# Cuando el proyecto paso de HALO a EMMA, la autoridad de redaccion paso de `halo-audit` a
# `emma-audit`. Las lapidas de antes llevan firmado el nombre viejo, y el nombre va dentro del
# material firmado: no se puede reescribir sin romper la cadena. La autoridad de hoy las
# reconoce como suyas si la clave coincide; lo nuevo se firma siempre con el nombre de hoy.
FORMER_AUTHORITY_IDS: dict[str, tuple[str, ...]] = {"emma-audit": ("halo-audit",)}


@dataclass(frozen=True)
class Redaction:
    """Resultado de una redaccion: la entrada ya sin contenido y su lapida firmada.

    `dependents` son las redacciones que arrastra en el mismo `commit` (las fases de contraste
    declaradas y las segmentaciones de un TAC redactado, `ObservationStore.redact`), cada una
    con su propia lapida.
    """

    target: LedgerEntry
    tombstone: LedgerEntry
    dependents: tuple[Redaction, ...] = ()


@dataclass(frozen=True)
class Amendment:
    """Resultado de una enmienda: la entrada corregida —intacta— y el asiento que la corrige.

    `target` no cambia: esa es toda la diferencia con una redaccion. Lo que cambia es
    que, a partir de `entry`, la version vigente del dato es la de la enmienda.
    """

    target: LedgerEntry
    entry: LedgerEntry


@dataclass(frozen=True)
class Anchor:
    """Lo que se transmite a Tierra: la raiz y cuantas entradas cubre.

    Sin el tamano, borrar las ultimas entradas —justo las del incidente que se quiere
    ocultar— verificaba limpio: lo que queda es una cadena coherente. Contra un ancla,
    una cadena mas corta que `tree_size`, o cuyo prefijo no reproduzca `root`, falla.
    """

    tree_size: int
    root: str
    algorithm: str = MERKLE_ALGORITHM


@dataclass(frozen=True)
class VerificationResult:
    ok: bool
    failed_index: int | None = None
    reason: str | None = None

    def __bool__(self) -> bool:
        return self.ok


def _fail(index: int | None, reason: str) -> VerificationResult:
    return VerificationResult(ok=False, failed_index=index, reason=reason)


# --------------------------------------------------------------------------- #
# Merkle, RFC 6962
# --------------------------------------------------------------------------- #


def leaf_hash(entry_hash: str) -> str:
    """Hoja RFC 6962: SHA-256(0x00 || hash de entrada).

    El prefijo separa hojas de nodos internos. Sin el, un nodo interno podia
    presentarse como hoja, con una prueba mas corta, y validar.
    """
    return sha256_hex(_LEAF_PREFIX + bytes.fromhex(entry_hash))


def _node_hash(left: str, right: str) -> str:
    return sha256_hex(_NODE_PREFIX + bytes.fromhex(left) + bytes.fromhex(right))


def _next_level(level: list[str]) -> list[str]:
    """Combina por pares. El nodo impar sube tal cual, sin hashear ni duplicar.

    Duplicarlo, como se hacia, es CVE-2012-2459: `[a, b, c]` y `[a, b, c, c]` daban
    la misma raiz, y una prueba para una cuarta hoja fantasma validaba contra el
    ancla. Subirlo sin tocar reproduce exactamente el arbol de RFC 6962 §2.1.
    """
    paired = [_node_hash(level[i], level[i + 1]) for i in range(0, len(level) - 1, 2)]
    if len(level) % 2:
        paired.append(level[-1])
    return paired


def merkle_root_of(entry_hashes: Sequence[str]) -> str:
    """Raiz RFC 6962 sobre una secuencia de hashes de entrada."""
    if not entry_hashes:
        return sha256_hex(b"")  # MTH({}) de RFC 6962; distinto del centinela de genesis
    level = [leaf_hash(entry_hash) for entry_hash in entry_hashes]
    while len(level) > 1:
        level = _next_level(level)
    return level[0]


def merkle_proof_of(entry_hashes: Sequence[str], index: int) -> list[tuple[str, bool]]:
    """Prueba de inclusion: lista de (hash_hermano, hermano_a_la_izquierda)."""
    if not 0 <= index < len(entry_hashes):
        raise IndexError(f"índice {index} fuera del árbol")
    proof: list[tuple[str, bool]] = []
    level = [leaf_hash(entry_hash) for entry_hash in entry_hashes]
    position = index
    while len(level) > 1:
        sibling = position ^ 1
        if sibling < len(level):  # sin hermano: es el impar que sube, no aporta paso
            proof.append((level[sibling], sibling < position))
        level = _next_level(level)
        position //= 2
    return proof


def verify_merkle_proof(entry_hash: str, proof: Sequence[tuple[str, bool]], root: str) -> bool:
    """Comprueba que `entry_hash` esta bajo `root`.

    Recibe el hash de la **entrada**, no el de la hoja, y aplica el prefijo de hoja el
    mismo. Si aceptara una hoja ya calculada, se le podria entregar un nodo interno.
    """
    try:
        current = leaf_hash(entry_hash)
        for sibling, sibling_is_left in proof:
            current = (
                _node_hash(sibling, current) if sibling_is_left else _node_hash(current, sibling)
            )
    except ValueError:
        return False
    return current == root


# --------------------------------------------------------------------------- #
# Ledger
# --------------------------------------------------------------------------- #


class HashChainLedger:
    """Log append-only encadenado por hash.

    Alterar cualquier entrada pasada invalida los hashes de todas las posteriores, y
    `verify()` senala la primera entrada inconsistente.
    """

    def __init__(
        self,
        registry: KeyRegistry | None = None,
        clock: Callable[[], datetime] | None = None,
        redaction_authority: RedactionAuthority | None = None,
    ) -> None:
        self._entries: list[LedgerEntry] = _EntryList()
        self.registry = registry if registry is not None else KeyRegistry()
        self._clock = clock or (lambda: datetime.now(UTC))
        # Fija durante toda la vida del ledger: llega de fuera del almacen, nunca de el.
        self.redaction_authority = redaction_authority
        # EL LEDGER SE PROTEGE A SI MISMO.
        #
        # `append` lee el indice y el hash anterior, firma, y solo entonces anade.
        # Sin cerrojo, dos hilos cogian el mismo indice: 8 hilos x 30 escrituras
        # dejaban indices duplicados y una cadena rota para siempre, indistinguible
        # de una manipulacion. `ObservationStore` ya serializa sus escrituras, pero la
        # garantia tiene que vivir aqui, no depender de quien llame.
        #
        # Reentrante: `redact()` escribe su lapida con `append()`, y `transaction()`
        # envuelve a los dos.
        self._lock = threading.RLock()
        self._touched: dict[int, LedgerEntry] | None = None

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def __getitem__(self, index: int) -> LedgerEntry:
        with self._lock:
            return _detached(self._entries[index])

    @property
    def entries(self) -> tuple[LedgerEntry, ...]:
        """Copia de la cadena: mutarla no toca el ledger.

        Antes devolvia las entradas reales en una tupla. La tupla y el dataclass son
        inmutables, pero el `dict` del payload no: `entries[0].payload["value"] = 1`
        cambiaba el dato guardado y `verify()` lo denunciaba como manipulacion. Un
        falso positivo indistinguible de un ataque, en un sistema cuya funcion es
        distinguirlos.
        """
        with self._lock:
            return tuple(_detached(entry) for entry in self._entries)

    def _view(self) -> tuple[LedgerEntry, ...]:
        """Las entradas reales, sin copiar. Solo para lectores internos que no mutan.

        `entries` copia la cadena entera: ~57 ms sobre 21 120 asientos, y el almacen
        la recorre en cada consulta del motor y en cada verificacion de disco. El
        almacen lee los payloads y no los modifica: la copia protegia de un riesgo
        que ese lector no tiene, y costaba ~115 ms por cada `/api/status`.
        """
        with self._lock:
            return tuple(self._entries)

    def entry_hashes(self, size: int | None = None) -> list[str]:
        with self._lock:
            entries = self._entries[: self._checked_size(size)]
        return _anchorable_hashes(entries)

    # ----------------------------------------------------------------------- #
    # Escritura
    # ----------------------------------------------------------------------- #

    def append(self, entry_type: str, payload: dict[str, Any], identity: Identity) -> LedgerEntry:
        """Anade una entrada firmada al final de la cadena.

        La identidad tiene que estar en el registro con esta misma clave. La marca de
        tiempo la pone el ledger: 21 CFR 11.10(e) pide un audit trail
        "computer-generated". El instante clinico del dato va dentro del payload.
        """
        if entry_type == REDACTION_ENTRY_TYPE:
            raise ValueError("las lapidas de redacción solo las escribe redact()")
        # Sin esto, cualquiera con una identidad de confianza escribiria un asiento de
        # tipo `amendment` con los campos que quisiera: podria declarar corregida —y por
        # tanto retirar de las consultas— una lectura ajena que nunca examino.
        if entry_type == AMENDMENT_ENTRY_TYPE:
            raise ValueError("las enmiendas solo las escribe amend()")
        # La sal la pone el ledger: un llamante que la fijara podria reproducir el hash de
        # un contenido conocido, que es justo lo que la sal impide.
        if SALT_FIELD in payload:
            raise ValueError(f"'{SALT_FIELD}' es un campo reservado: la sal la pone el ledger")
        return self._append(entry_type, {**payload, SALT_FIELD: secrets.token_hex(16)}, identity)

    def _append(self, entry_type: str, payload: dict[str, Any], identity: Identity) -> LedgerEntry:
        # Se valida y despues se copia: guardado por referencia, mutar el dict del
        # llamante despues de anadir cambiaba el dato registrado. La copia es vigilada:
        # mutarla despues deja rastro (`_WatchedDict`).
        content_hash = sha256_hex(canonical_bytes(payload))
        stored: dict[str, Any] = _watched(payload)
        public_key = identity.public_key_hex

        with self._lock:
            if not self._trusted(entry_type, identity.identity_id, public_key):
                raise UntrustedSigner(
                    f"la identidad {identity.identity_id!r} no puede firmar asientos "
                    f"{entry_type!r} con esta clave"
                )
            previous = self._entries[-1] if self._entries else None
            entry = LedgerEntry(
                index=len(self._entries),
                recorded=self._timestamp(previous),
                entry_type=entry_type,
                content_hash=content_hash,
                prev_hash=_link_hash(previous) if previous else GENESIS_PREV_HASH,
                signer=identity.identity_id,
                signer_public_key=public_key,
                signature="",
                payload=stored,
            )
            entry = replace(entry, signature=identity.sign(entry.signing_material()))
            self._entries.append(entry)
        return _detached(entry)

    def _trusted(self, entry_type: str, signer: str, public_key_hex: str) -> bool:
        """Quien firma que: las lapidas, solo la autoridad; lo demas, el registro.

        La autoridad no firma datos clinicos. Si pudiera, una clave pensada para
        rectificar serviria tambien para fabricar lecturas.
        """
        authority = self.redaction_authority
        if entry_type == REDACTION_ENTRY_TYPE:
            return authority is not None and authority.matches(signer, public_key_hex)
        if authority is not None and authority.names(signer):
            return False
        return self.registry.is_trusted(signer, public_key_hex)

    def _timestamp(self, previous: LedgerEntry | None) -> datetime:
        """Instante del asiento: del reloj del sistema, en UTC, y nunca hacia atras.

        Si el reloj retrocede (un ajuste de hora al recuperar enlace), el asiento se
        iguala al anterior en vez de rechazarse: perder un dato clinico por un
        problema de reloj seria peor.
        """
        now = self._clock()
        if now.tzinfo is None:
            raise ValueError("el reloj del ledger debe dar instantes con zona horaria")
        now = now.astimezone(UTC)
        # Solo se iguala a un anterior que verifica por si solo. Una fecha futura en un
        # asiento manipulado —9999-12-31— se heredaba en todas las escrituras siguientes,
        # que quedaban firmadas con ella. La comprobacion solo corre si el reloj va por
        # detras, que es lo raro: no encarece la escritura normal.
        if (
            previous is not None
            and isinstance(previous.recorded, datetime)
            and previous.recorded.tzinfo is not None
            and now < previous.recorded
            and self._entry_problem(previous) is None
        ):
            return previous.recorded
        return now

    def redact(self, index: int, identity: Identity, reason: str, requested_by: str) -> Redaction:
        """Suprime el contenido clinico de una entrada y deja constancia firmada.

        Es la via de rectificacion que presupone 45 CFR 164.312(c)(1). Antes mutaba la
        entrada en su sitio y nada mas: sin asiento, sin motivo, sin autor, y la marca
        `redacted` fuera de lo firmado. Borrar una alerta critica dejaba la cadena en
        verde y la raiz anclada identica. Y 21 CFR 11.10(e) exige registrar tambien
        las acciones que *borran*.

        Ahora se anade primero una **lapida**: un asiento firmado que identifica la
        entrada exacta (su hash y el de su contenido), el motivo y quien lo pidio. El
        contenido desaparece; la constancia de que existio y de quien lo quito, no.
        `verify()` exige una lapida por cada contenido ausente.

        Solo la firma la autoridad de redaccion aprovisionada (`RedactionAuthority`).
        """
        if not _has_text(reason) or not _has_text(requested_by):
            raise ValueError("una redacción exige motivo y solicitante")
        authority = self.redaction_authority
        if authority is None:
            raise UntrustedSigner("no hay autoridad de redacción aprovisionada")
        # Lo nuevo se firma con el nombre de hoy: un nombre anterior solo vale para lo ya escrito.
        if (
            identity.identity_id != authority.identity_id
            or not authority.matches(identity.identity_id, identity.public_key_hex)
        ):
            raise UntrustedSigner("solo la autoridad de redacción aprovisionada firma lapidas")

        with self._lock:
            # `redact(-1)` redactaba en silencio la ultima entrada: normalmente la
            # alerta recien generada.
            if not 0 <= index < len(self._entries):
                raise IndexError(f"índice {index} fuera de la cadena")
            target = self._entries[index]
            if target.entry_type == REDACTION_ENTRY_TYPE:
                raise ValueError("una lápida no se redacta: es la prueba de otra redacción")
            if target.payload is None:
                raise ValueError(f"la entrada {index} ya está redactada")
            # Redactar una correccion devolveria a las consultas el valor que corrigio, y
            # ese valor se sabe equivocado. Se exige el orden contrario: primero el dato
            # original, despues su enmienda. Asi ninguna version resucita.
            amended = {
                amendment.index: amended_index
                for amended_index, amendment in self._amendments(self._entries).items()
            }
            if index in amended and self._entries[amended[index]].payload is not None:
                raise ValueError(
                    f"la entrada {index} corrige a la {amended[index]}, que sigue registrada: "
                    "redacta primero la original, o la corrección la haría resucitar"
                )
            # No se redacta lo que no verifica: la lapida de la autoridad sustituiria la
            # prueba de una manipulacion por una rectificacion de apariencia legitima.
            problem = self._entry_problem(target)
            if problem is not None:
                raise ValueError(f"la entrada {index} no verifica ({problem}): no se redacta")
            if _header_problem(self._entries[-1]) is not None:
                raise ValueError("la última entrada no verifica: no se encadena nada detrás")

            tombstone = self._append(
                REDACTION_ENTRY_TYPE,
                {
                    "target_index": index,
                    "target_entry_hash": target.entry_hash(),
                    "target_content_hash": target.content_hash,
                    "reason": reason,
                    "requested_by": requested_by,
                },
                identity,
            )
            if self._touched is not None:
                self._touched.setdefault(index, target)
            redacted = replace(target, payload=None, redacted=True)
            self._entries[index] = redacted

        return Redaction(target=_detached(redacted), tombstone=tombstone)

    def amend(
        self, index: int, replacement: dict[str, Any], identity: Identity, reason: str
    ) -> Amendment:
        """Corrige una entrada anexando la version buena, sin tocar la anterior.

        Es la rectificacion que prescribe 45 CFR 164.526, y la que no choca con
        21 CFR 11.10(e): el registro anterior sigue ahi, legible y firmado, y queda
        enlazado con el que lo corrige. La redaccion, que borra, se reserva para el dato
        que nunca debio registrarse.

        La enmienda se ata a la entrada exacta que corrige —su `entry_hash` y su
        `content_hash`—, igual que una lapida. Sin esa atadura, una enmienda copiada de
        otro almacen retiraria de las consultas una lectura de este.

        La firma una fuente del registro, **no** la autoridad de redaccion: una clave
        pensada para rectificar no debe poder fabricar datos clinicos, y el `replacement`
        de una enmienda es un dato clinico.

        Se puede enmendar una enmienda —una correccion tambien puede estar mal—, y cada
        eslabon queda atado al anterior. Lo que no se admite es **dos** enmiendas sobre
        la misma entrada: dejaria dos versiones vigentes del mismo dato sin forma de
        decidir cual vale.
        """
        if not _has_text(reason):
            raise ValueError("una enmienda exige motivo")
        # Lo que no se admita aqui tiene que ser lo mismo que `_amendment_problem` da por
        # invalido: si no, `amend()` escribiria un asiento que deja la cadena en rojo.
        if not isinstance(replacement, dict) or not replacement:
            raise ValueError("una enmienda exige la versión corregida del dato")
        if SALT_FIELD in replacement:
            raise ValueError(f"'{SALT_FIELD}' es un campo reservado: la sal la pone el ledger")

        with self._lock:
            if not 0 <= index < len(self._entries):
                raise IndexError(f"índice {index} fuera de la cadena")
            target = self._entries[index]
            if target.entry_type == REDACTION_ENTRY_TYPE:
                raise ValueError("una lápida no se enmienda: es la prueba de una redacción")
            if target.payload is None:
                raise ValueError(f"la entrada {index} está redactada: no hay nada que corregir")
            problem = self._entry_problem(target)
            if problem is not None:
                raise ValueError(f"la entrada {index} no verifica ({problem}): no se enmienda")
            if _header_problem(self._entries[-1]) is not None:
                raise ValueError("la última entrada no verifica: no se encadena nada detrás")
            if index in self._amendments(self._entries):
                raise ValueError(f"la entrada {index} ya está enmendada")

            entry = self._append(
                AMENDMENT_ENTRY_TYPE,
                {
                    "target_index": index,
                    "target_entry_hash": target.entry_hash(),
                    "target_content_hash": target.content_hash,
                    "reason": reason,
                    "amended_by": identity.identity_id,
                    "replacement": _clone_json(replacement),
                    SALT_FIELD: secrets.token_hex(16),
                },
                identity,
            )

        return Amendment(target=_detached(target), entry=entry)

    def amendments(self, entries: Sequence[LedgerEntry] | None = None) -> dict[int, LedgerEntry]:
        """Las enmiendas validas, por indice de la entrada que cada una corrige.

        Quien lea la cadena necesita saber que version de un dato esta vigente, y esa
        pregunta se responde aqui: una entrada que aparece como clave de este diccionario
        esta **sustituida** por la enmienda que la acompana.

        `entries` permite responder sobre la misma foto de la cadena que ya se tiene
        delante; sin ella, sobre la actual. Consultar dos veces daria dos fotos, y una
        lectura podria quedar fuera de las dos.
        """
        with self._lock:
            return self._amendments(entries if entries is not None else self._entries)

    def _amendments(self, entries: Sequence[LedgerEntry]) -> dict[int, LedgerEntry]:
        """Como `_collect_redactions`: solo cuenta la enmienda que se sostiene entera.

        Bien formada, atada a su entrada, con el contenido intacto, firmada por una
        fuente de confianza y con esa firma comprobada. Una enmienda que no lo sea no
        retira nada de las consultas, y falla en su propia posicion en `verify()`.
        """
        amendments: dict[int, LedgerEntry] = {}
        for position, entry in enumerate(entries):
            payload = entry.payload
            if (
                entry.entry_type != AMENDMENT_ENTRY_TYPE
                or payload is None
                or _header_problem(entry) is not None
                or entry.index != position
                or not self._trusted(entry.entry_type, entry.signer, entry.signer_public_key)
                or _amendment_problem(payload, position, entries) is not None
                or _content_hash_problem(payload, entry.content_hash) is not None
                or not Identity.verify(
                    entry.signer_public_key, entry.signing_material(), entry.signature
                )
            ):
                continue
            amendments.setdefault(payload["target_index"], entry)
        return amendments

    def _entry_problem(self, entry: LedgerEntry) -> str | None:
        """Que le impide a una entrada verificar por si sola, sin mirar el resto."""
        header_problem = _header_problem(entry)
        if header_problem is not None:
            return header_problem
        if not self._trusted(entry.entry_type, entry.signer, entry.signer_public_key):
            return "firmante no autorizado"
        if not Identity.verify(entry.signer_public_key, entry.signing_material(), entry.signature):
            return "firma inválida"
        if entry.payload is not None:
            return _content_hash_problem(entry.payload, entry.content_hash)
        return None

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Todo o nada: si el bloque falla, cadena y registro vuelven a como estaban.

        Para quien persiste la cadena. Los asientos se crean en memoria antes del
        `commit`, porque la fila necesita su hash y su firma; si el `commit` falla,
        se deshacen aqui. No es reescribir historia: nunca llegaron a disco, y bajo el
        cerrojo nadie ha podido encadenar detras.
        """
        with self._lock:
            if self._touched is not None:  # anidada: decide la exterior
                yield
                return
            start = len(self._entries)
            keys = self.registry._snapshot()
            self._touched = {}
            try:
                yield
            except BaseException:
                del self._entries[start:]
                for index, original in self._touched.items():
                    if index < start:
                        self._entries[index] = original
                self.registry._restore(keys)
                raise
            finally:
                self._touched = None

    def load(self, entries: Iterable[LedgerEntry]) -> None:
        """Reconstruye la cadena desde el almacen, tal cual, sin recalcular nada.

        Si alguien edito el almacen por fuera, `verify()` tiene que poder verlo:
        cargar no valida ni corrige. Los payloads entran en contenedores vigilados
        (`_EntryList.extend`), con los mismos valores y tipos.
        """
        with self._lock:
            if self._entries:
                raise RuntimeError("solo se carga sobre un ledger vacío")
            self._entries.extend(entries)

    # ----------------------------------------------------------------------- #
    # Verificacion
    # ----------------------------------------------------------------------- #

    def memory_mark(self) -> MemoryMark:
        """La marca de la memoria ahora: con ella, `unchanged_since` dice si algo cambio."""
        with self._lock:
            entries = self._entries
            return MemoryMark(
                entries=entries,
                rewrites=entries.rewrites if type(entries) is _EntryList else -1,
                payload_edits=_payload_edits,
                registry=tuple(self.registry.items()),
                authority=self.redaction_authority,
            )

    def unchanged_since(self, mark: MemoryMark) -> bool:
        """Lo que habia en memoria al tomar `mark` sigue ahi tal cual. Sin releer nada.

        Cierto si la lista es la misma y nadie la ha reescrito (solo anadido al final),
        ningun payload guardado se ha mutado, la autoridad es la misma y cada clave del
        registro de entonces sigue fijada igual. Que el registro gane claves no cambia lo
        ya verificado: un asiento que verifico ya tenia la suya.

        Una lista sustituida por otra (`ledger._entries = [...]`) no esta vigilada: con
        ella nunca se da nada por intacto.
        """
        with self._lock:
            entries = self._entries
            if (
                type(entries) is not _EntryList
                or entries is not mark.entries
                or entries.rewrites != mark.rewrites
                or _payload_edits != mark.payload_edits
                or self.redaction_authority != mark.authority
            ):
                return False
            current = dict(self.registry.items())
            return all(current.get(identity) == key for identity, key in mark.registry)

    def reusable_prefix(
        self, verified: tuple[int, MemoryMark] | None, entries: Sequence[LedgerEntry]
    ) -> int:
        """Cuantas entradas del principio se pueden dar por verificadas sin repetirlo.

        `verified` es (tamano, marca) de una verificacion completa anterior que salio bien.
        Vale si la memoria no ha cambiado desde la marca y si ninguna entrada nueva es una
        lapida o una enmienda: esas dependen de un asiento anterior —que este redactado, que
        no tenga otra enmienda—, y con una delante se vuelve a verificar todo. Si no vale,
        0: verificacion completa.
        """
        if verified is None:
            return 0
        size, mark = verified
        if not 0 < size <= len(entries) or not self.unchanged_since(mark):
            return 0
        if any(entries[position].entry_type in _CROSS_ENTRY_TYPES
               for position in range(size, len(entries))):
            return 0
        return size

    def verify(
        self,
        signatures_from: int = 0,
        anchor: Anchor | None = None,
        trusted_prefix: tuple[int, MemoryMark] | None = None,
    ) -> VerificationResult:
        """Verifica toda la cadena, en orden; con `anchor`, tambien contra el testigo.

        Por entrada: posicion, encadenamiento, firmante registrado con esa clave,
        firma, marca de tiempo, y contenido — presente y coincidente con su hash, o
        ausente con una lapida firmada que lo justifique.

        `signatures_from` evita repetir la comprobacion Ed25519 de entradas cuya firma
        ya se verifico **en este proceso**: es lo caro. Todo lo demas se comprueba
        siempre en todas. El atajo se apoya en que la memoria del ledger es privada del
        proceso —toda salida publica es una copia— y en que lo cargado de disco se
        verifica entero la primera vez. NO lo sostiene el encadenamiento: cambiar la
        firma de una entrada rompe el `prev_hash` de la siguiente, pero la ultima no
        tiene siguiente.

        Sin ancla, borrar las ultimas entradas no es detectable: lo que queda es una
        cadena coherente. Es un limite de cualquier log local, no de este en concreto.

        `trusted_prefix` es (tamano, marca) de una verificacion anterior que salio bien.
        Si `reusable_prefix` lo admite, se verifican a fondo solo las entradas nuevas,
        encadenadas a la ultima ya verificada; si no, todas. Con `anchor`, siempre todas.
        """
        with self._lock:
            entries = list(self._entries)
            start = 0 if anchor is not None else self.reusable_prefix(trusted_prefix, entries)

        if start:
            # Ninguna entrada nueva es lapida (`reusable_prefix`), y una lapida solo apunta
            # hacia atras: ninguna de las nuevas esta redactada, ni hay dianas que repetir.
            redactions: dict[int, dict[str, Any]] = {}
            expected_prev = entries[start - 1].entry_hash()
            previous_recorded: datetime | None = entries[start - 1].recorded
        else:
            redactions = _collect_redactions(entries, self.redaction_authority)
            expected_prev = GENESIS_PREV_HASH
            previous_recorded = None
        redacted_targets: set[int] = set()
        amended_targets: set[int] = set()
        for position in range(start, len(entries)):
            entry = entries[position]
            header_problem = _header_problem(entry)
            if header_problem is not None:
                return _fail(position, header_problem)
            if entry.index != position:
                return _fail(position, "índice fuera de orden")
            if entry.prev_hash != expected_prev:
                return _fail(
                    entry.index, "prev_hash no coincide con el hash de la entrada anterior"
                )
            if not self._trusted(entry.entry_type, entry.signer, entry.signer_public_key):
                return _fail(entry.index, "firmante no autorizado")
            if entry.index >= signatures_from and not Identity.verify(
                entry.signer_public_key, entry.signing_material(), entry.signature
            ):
                return _fail(entry.index, "firma inválida")
            if entry.recorded.tzinfo is None:
                return _fail(entry.index, "marca de tiempo sin zona horaria")
            if previous_recorded is not None and entry.recorded < previous_recorded:
                return _fail(entry.index, "marca de tiempo anterior a la entrada previa")
            if entry.entry_type == REDACTION_ENTRY_TYPE and entry.payload is not None:
                tombstone_problem = _tombstone_problem(entry.payload, position, entries)
                if tombstone_problem is not None:
                    return _fail(entry.index, tombstone_problem)
                target = entry.payload["target_index"]
                if target in redacted_targets:
                    return _fail(entry.index, "redacción duplicada de la misma entrada")
                redacted_targets.add(target)
            if entry.entry_type == AMENDMENT_ENTRY_TYPE and entry.payload is not None:
                amendment_problem = _amendment_problem(entry.payload, position, entries)
                if amendment_problem is not None:
                    return _fail(entry.index, amendment_problem)
                amended = entry.payload["target_index"]
                # Dos enmiendas sobre la misma entrada dejarian dos versiones vigentes
                # del mismo dato. Una correccion de una correccion enmienda la enmienda.
                if amended in amended_targets:
                    return _fail(entry.index, "enmienda duplicada de la misma entrada")
                amended_targets.add(amended)
            content_problem = _check_content(entry, redactions.get(entry.index))
            if content_problem is not None:
                return _fail(entry.index, content_problem)
            expected_prev = entry.entry_hash()
            previous_recorded = entry.recorded

        if anchor is not None:
            # Un tamano negativo cortaba la cadena por la cola y validaba la raiz de
            # un prefijo mas corto.
            if anchor.tree_size < 0 or len(anchor.root) != 64:
                return _fail(None, "ancla mal formada")
            if anchor.algorithm != MERKLE_ALGORITHM:
                return _fail(None, f"algoritmo de ancla desconocido: {anchor.algorithm}")
            if len(entries) < anchor.tree_size:
                return _fail(len(entries), "la cadena es más corta que el ancla: faltan entradas")
            prefix = [entry.entry_hash() for entry in entries[: anchor.tree_size]]
            if merkle_root_of(prefix) != anchor.root:
                return _fail(None, "el prefijo anclado no reproduce la raíz del ancla")

        return VerificationResult(ok=True)

    # ----------------------------------------------------------------------- #
    # Merkle: anclaje externo con 32 bytes
    # ----------------------------------------------------------------------- #

    def _checked_size(self, size: int | None) -> int:
        if size is None:
            return len(self._entries)
        if not 0 <= size <= len(self._entries):
            raise IndexError(f"tamaño {size} fuera de la cadena")
        return size

    def merkle_root(self, size: int | None = None) -> str:
        """Raiz del arbol sobre las primeras `size` entradas (todas, por defecto).

        Es lo unico que se transmite a la Tierra para anclar la cadena: 32 bytes, sin
        ningun dato medico. Con `size` se recalcula la raiz de un ancla antigua.
        """
        return merkle_root_of(self.entry_hashes(size))

    def merkle_proof(self, index: int, size: int | None = None) -> list[tuple[str, bool]]:
        """Prueba de inclusion de una entrada, de tamano logaritmico.

        Demuestra que una observacion concreta estaba en la cadena al anclar, sin
        revelar las demas.
        """
        return merkle_proof_of(self.entry_hashes(size), index)

    def anchor(self) -> Anchor:
        """El ancla de la cadena en este momento: lo que viajaria a Tierra."""
        with self._lock:
            hashes = _anchorable_hashes(self._entries)
        return Anchor(tree_size=len(hashes), root=merkle_root_of(hashes))

    def redacted_indices(self) -> frozenset[int]:
        """Entradas con una lapida valida de la autoridad atada a ellas.

        Valida: firmada por la autoridad, con firma y contenido correctos, bien formada y
        atada a la entrada exacta que redacta. NO comprueba el resto de la cadena: para
        saber si la cadena entera se sostiene, `verify()`.
        """
        with self._lock:
            entries = list(self._entries)
        return frozenset(_collect_redactions(entries, self.redaction_authority))

    verify_merkle_proof = staticmethod(verify_merkle_proof)


# --------------------------------------------------------------------------- #
# Redacciones
# --------------------------------------------------------------------------- #


_HEADER_TEXT_FIELDS = (
    "entry_type",
    "content_hash",
    "prev_hash",
    "signer",
    "signer_public_key",
    "signature",
)


def _header_problem(entry: LedgerEntry) -> str | None:
    """Los tipos de la cabecera, antes de hashearla o de comprobar su firma.

    Un campo en BLOB cargado de disco llegaba a `signing_material()` y lanzaba
    TypeError: la verificacion, `/api/status` y el calculo del ancla daban 500 en vez de
    senalar el asiento.
    """
    if isinstance(entry.index, bool) or not isinstance(entry.index, int):
        return "cabecera mal formada: index"
    if not isinstance(entry.recorded, datetime):
        return "cabecera mal formada: recorded"
    for field in _HEADER_TEXT_FIELDS:
        if not isinstance(getattr(entry, field), str):
            return f"cabecera mal formada: {field}"
    if not isinstance(entry.redacted, bool):
        return "cabecera mal formada: redacted"
    return None


def _link_hash(previous: LedgerEntry) -> str:
    """El enlace con el asiento anterior, aunque su cabecera este danada.

    Las constantes vitales se siguen registrando sobre una cadena rota: perderlas seria
    peor. Una cabecera ilegible no tiene `entry_hash`, asi que se enlaza con el hash de
    su representacion; la verificacion seguira senalando el asiento danado.
    """
    if _header_problem(previous) is None:
        return previous.entry_hash()
    return sha256_hex(repr(previous._header()).encode("utf-8", "backslashreplace"))


def _anchorable_hashes(entries: Sequence[LedgerEntry]) -> list[str]:
    """Hashes de entrada para Merkle. Una cabecera danada no se puede anclar, y se
    dice asi en vez de lanzar un TypeError desde la serializacion."""
    for position, entry in enumerate(entries):
        problem = _header_problem(entry)
        if problem is not None:
            raise ValueError(f"asiento {position}: {problem}; no se puede anclar")
    return [entry.entry_hash() for entry in entries]


def _has_text(value: str) -> bool:
    """Al menos una letra o una cifra. `strip()` no quita U+200B: un motivo invisible pasaba."""
    return any(character.isalnum() for character in value)


def _tombstone_problem(
    payload: Any, position: int, entries: Sequence[LedgerEntry]
) -> str | None:
    """Que le falta a una lapida para ser valida, o `None`.

    Por posicion y con `isinstance`: indexar por el indice declarado, o suponer que el
    payload era un dict, convertia una lapida basura en una excepcion en vez de en un
    fallo de verificacion.
    """
    if (
        not isinstance(payload, dict)
        or set(payload) != set(_TOMBSTONE_FIELDS)
        or not all(
            isinstance(payload[field], kind) and not isinstance(payload[field], bool)
            for field, kind in _TOMBSTONE_FIELDS.items()
        )
    ):
        return "lápida de redacción mal formada"
    target_index = payload["target_index"]
    if not 0 <= target_index < position:
        return "la lápida apunta a una entrada inexistente o posterior"
    target = entries[target_index]
    if _header_problem(target) is not None:
        return "la lápida apunta a una entrada con la cabecera dañada"
    if target.entry_type == REDACTION_ENTRY_TYPE:
        return "una lápida no puede redactar otra lápida"
    # Atada a la entrada exacta. Sin esto, la lapida legitima de otro almacen con la
    # misma autoridad —todos los de la API la comparten—, copiada aqui, suprimia una
    # lectura para `redacted_indices()`.
    if (
        payload["target_entry_hash"] != target.entry_hash()
        or payload["target_content_hash"] != target.content_hash
    ):
        return "la lápida no corresponde a su entrada"
    return None


def _amendment_problem(payload: Any, position: int, entries: Sequence[LedgerEntry]) -> str | None:
    """Que le falta a una enmienda para ser valida, o `None`.

    Mismas cautelas que con una lapida: por posicion, con `isinstance`, y sin suponer
    que el payload sea un dict. Una enmienda basura tiene que ser un fallo de
    verificacion, no una excepcion.
    """
    if (
        not isinstance(payload, dict)
        or set(payload) != set(_AMENDMENT_FIELDS)
        or not all(
            isinstance(payload[field], kind) and not isinstance(payload[field], bool)
            for field, kind in _AMENDMENT_FIELDS.items()
        )
    ):
        return "enmienda mal formada"
    if not payload["replacement"]:
        return "la enmienda no propone ninguna corrección"
    if SALT_FIELD in payload["replacement"]:
        return f"'{SALT_FIELD}' es un campo reservado del ledger"
    if not _has_text(payload["reason"]) or not _has_text(payload["amended_by"]):
        return "la enmienda exige motivo y autor"
    target_index = payload["target_index"]
    if not 0 <= target_index < position:
        return "la enmienda apunta a una entrada inexistente o posterior"
    target = entries[target_index]
    if _header_problem(target) is not None:
        return "la enmienda apunta a una entrada con la cabecera dañada"
    if target.entry_type == REDACTION_ENTRY_TYPE:
        return "una enmienda no corrige una lápida"
    # Atada a la entrada exacta, como la lapida. `content_hash` y `entry_hash` no cambian
    # al redactar, asi que una enmienda anterior a una redaccion sigue siendo valida
    # despues de ella: la correccion ocurrio, y eso no se deshace.
    if (
        payload["target_entry_hash"] != target.entry_hash()
        or payload["target_content_hash"] != target.content_hash
    ):
        return "la enmienda no corresponde a su entrada"
    return None


def _collect_redactions(
    entries: Sequence[LedgerEntry], authority: RedactionAuthority | None
) -> dict[int, dict[str, Any]]:
    """Las lapidas que de verdad autorizan una supresion, por entrada redactada.

    Cuenta solo una lapida firmada por la autoridad, con firma valida, contenido
    intacto y bien formada. La que no lo sea no entra aqui y falla en su propia
    posicion en la pasada principal de `verify()`. Antes se rechazaba aqui primero, y
    una lapida basura al final tapaba en `failed_index` una edicion anterior.

    La firma se comprueba aqui, y no solo en la pasada principal, porque
    `redacted_indices()` responde sin esa pasada. Las lapidas son pocas.
    """
    if authority is None:
        return {}
    redactions: dict[int, dict[str, Any]] = {}
    for position, entry in enumerate(entries):
        payload = entry.payload
        if (
            entry.entry_type != REDACTION_ENTRY_TYPE
            or payload is None
            or _header_problem(entry) is not None
            or entry.index != position
            or not authority.matches(entry.signer, entry.signer_public_key)
            or _tombstone_problem(payload, position, entries) is not None
            or _content_hash_problem(payload, entry.content_hash) is not None
            or not Identity.verify(
                entry.signer_public_key, entry.signing_material(), entry.signature
            )
        ):
            continue
        redactions.setdefault(payload["target_index"], payload)
    return redactions


def _content_hash_problem(payload: Any, content_hash: str) -> str | None:
    try:
        content = canonical_bytes(payload)
    except (TypeError, ValueError, RecursionError):
        return "el contenido no es JSON estricto"
    if sha256_hex(content) != content_hash:
        return "el contenido no coincide con content_hash"
    return None


def _check_content(entry: LedgerEntry, tombstone: dict[str, Any] | None) -> str | None:
    """El contenido esta y coincide con su hash, o falta con una lapida que lo justifica."""
    if entry.payload is None:
        if tombstone is None:
            return "contenido suprimido sin redacción registrada"
        if not entry.redacted:
            return "contenido suprimido sin marca de redacción"
        return None  # `_collect_redactions` ya exige que la lapida este atada a esta entrada

    if entry.redacted:
        return "marcada como redactada pero conserva el contenido"
    if tombstone is not None:
        return "redacción registrada pero el contenido sigue presente"
    return _content_hash_problem(entry.payload, entry.content_hash)
