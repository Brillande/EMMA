// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Sustituto de `better-sqlite3` para Marplanner: SQLite en memoria cuya única persistencia es el
 * ledger firmado de EMMA.
 *
 * Por qué existe: decisión del usuario (2026-11-12) de migrar la base de Marplanner al registro
 * firmado de EMMA. `better-sqlite3` además no tiene binario para Node 26 en Windows. La copia de
 * Marplanner (`marplanner/`) no se toca: `register.mjs` hace que su `import "better-sqlite3"`
 * resuelva aquí. Implementa la parte de la API que Marplanner usa (prepare, transaction, exec,
 * pragma, backup, close, inTransaction) sobre `node:sqlite`.
 *
 * Qué va al ledger: cada transacción confirmada, como un registro
 *   {"v":1,"ops":[{"cs":"<changeset>"} | {"sql":"...","temp":[...]}]}
 * `cs` son filas cambiadas (sesiones de SQLite). Las sesiones no registran cambios de ESQUEMA, así
 * que una escritura que cambia el esquema de la base se anota como su SQL (`sql`) y se repite al
 * reconstruir. Si una escritura cambia el esquema o no se sabe por el texto: se mira el esquema de
 * `main` antes y después (la primera versión miraba el texto, y la migración base de Marplanner, que
 * lee una tabla `temp.`, se tomó por temporal y no se anotó). Ese SQL puede leer tablas temporales
 * de la conexión; su contenido en ese instante va en `temp` y se recrea al repetirlo.
 *
 * Todo se anota ANTES del COMMIT: si el ledger no lo acepta, la transacción se deshace y el error
 * llega a Marplanner como cualquier fallo de escritura.
 *
 * Qué base es la del ledger: la ruta que Marplanner abre como suya (DATA_DIR + DATABASE_PATH). En
 * disco solo queda un fichero vacío que marca el sitio (Marplanner comprueba que existe). Un fichero
 * NO vacío en esa ruta es una restauración de copia de seguridad: su contenido se incorpora al
 * ledger como una transacción más y el fichero vuelve a quedar vacío. Cualquier otra ruta (una
 * copia de seguridad que se valida) se abre como fichero normal.
 */
import fs from "node:fs";
import path from "node:path";
import { DatabaseSync, backup as sqliteBackup } from "node:sqlite";
import { LedgerConflict, LedgerUnavailable, getLedger } from "./ledger-client.mjs";

const BEGIN = /^\s*begin(\s+(deferred|immediate|exclusive))?(\s+transaction)?\s*;?\s*$/i;
const COMMIT = /^\s*(commit|end)(\s+transaction)?\s*;?\s*$/i;
const ROLLBACK = /^\s*rollback(\s+transaction)?\s*;?\s*$/i;
const READER = /^\s*(select|explain)\b/i;
// No pueden ir dentro de una transacción y no cambian filas de la base: van tal cual. `VACUUM INTO`
// es la copia que Marplanner hace antes de migrar.
const OUTSIDE_TX = /^\s*(vacuum|attach|detach)\b/i;
const SQLITE_CHANGESET_ABORT = 2;

function plain(row) {
  return row && typeof row === "object" && !Array.isArray(row) ? { ...row } : row;
}

function quoteIdent(name) {
  return `"${String(name).replaceAll('"', '""')}"`;
}

function quoteText(text) {
  return `'${String(text).replaceAll("'", "''")}'`;
}

// Valores de una fila temporal a JSON y de vuelta, sin perder tipo.
function encodeValue(value) {
  if (value instanceof Uint8Array) return { b64: Buffer.from(value).toString("base64") };
  if (typeof value === "bigint") return { big: value.toString() };
  return value;
}
function decodeValue(value) {
  if (value && typeof value === "object" && "b64" in value) return Buffer.from(value.b64, "base64");
  if (value && typeof value === "object" && "big" in value) return BigInt(value.big);
  return value;
}

function isLedgerPath(file, options) {
  // El cerrojo de instancia de Marplanner (`runtime-storage.ts`) es un fichero real a propósito: su
  // trabajo es que otro proceso no pueda abrir la misma base. No guarda datos del hogar.
  if (String(file).endsWith(".instance-lock.sqlite")) return false;
  if (process.env.EMMA_PLANNER_LEDGER === "memory:") {
    // Solo para la suite de Marplanner: toda base que abre es del ledger (cada ruta con el suyo),
    // salvo una copia de seguridad que se abre para validarla (existe con datos y se pide así).
    const existing = fs.existsSync(file) && fs.statSync(file).size > 0;
    return !(existing && (options.readonly || options.fileMustExist));
  }
  const dir = process.env.DATA_DIR ?? process.cwd();
  const name = process.env.DATABASE_PATH ?? "marplanner.db";
  return path.resolve(dir, name) === path.resolve(String(file));
}

export class SqliteError extends Error {
  constructor(message, code) {
    super(message);
    this.code = code;
    this.name = "SqliteError";
  }
}

class Statement {
  constructor(owner, source) {
    this.database = owner;
    this.source = source;
    this._stmt = owner._db.prepare(source);
    this._pluck = false;
    this.reader = this._stmt.columns().length > 0;
    this.readonly = READER.test(source);
  }
  raw(toggle = true) {
    this._stmt.setReturnArrays(Boolean(toggle));
    return this;
  }
  pluck(toggle = true) {
    this._pluck = Boolean(toggle);
    return this;
  }
  safeIntegers(toggle = true) {
    this._stmt.setReadBigInts(Boolean(toggle));
    return this;
  }
  expand() {
    throw new SqliteError("expand() no está soportado por el puente de EMMA", "EMMA_UNSUPPORTED");
  }
  bind() {
    throw new SqliteError("bind() no está soportado por el puente de EMMA", "EMMA_UNSUPPORTED");
  }
  columns() {
    return this._stmt.columns();
  }
  _shape(row) {
    if (row === undefined) return undefined;
    if (this._pluck) return Array.isArray(row) ? row[0] : Object.values(row)[0];
    return plain(row);
  }
  _write(fn) {
    if (OUTSIDE_TX.test(this.source) || this.readonly) return fn();
    return this.database._tracked(this.source, fn);
  }
  run(...params) {
    return this._write(() => this._stmt.run(...params));
  }
  get(...params) {
    return this._write(() => this._shape(this._stmt.get(...params)));
  }
  all(...params) {
    return this._write(() => this._stmt.all(...params).map((row) => this._shape(row)));
  }
  *iterate(...params) {
    for (const row of this.all(...params)) yield row;
  }
}

export default class Database {
  constructor(filename = ":memory:", options = {}) {
    this.name = String(filename);
    this.readonly = Boolean(options.readonly);
    this._ledgered = this.name !== ":memory:" && this.name !== "" && isLedgerPath(this.name, options);
    if (!this._ledgered) {
      if (options.fileMustExist && !fs.existsSync(this.name)) {
        throw new SqliteError(`unable to open database file: ${this.name}`, "SQLITE_CANTOPEN");
      }
      this._db = new DatabaseSync(this.name, { readOnly: this.readonly });
      this.memory = this.name === ":memory:" || this.name === "";
      this.open = true;
      return;
    }
    this.memory = false;
    this._ledger = getLedger(path.resolve(this.name));
    this._db = new DatabaseSync(":memory:");
    this._seq = 0;
    this._session = null;
    this._ops = null;
    this._replay();
    this._absorbRestoredFile();
    this.open = true;
  }

  get inTransaction() {
    return this._db.isTransaction;
  }

  // --- esquema y tablas temporales ----------------------------------------------------------
  _mainSchema() {
    return JSON.stringify(
      this._db
        .prepare("SELECT type, name, tbl_name, sql FROM main.sqlite_schema ORDER BY type, name")
        .all()
        .map(plain)
    );
  }
  _tempState() {
    const tables = this._db
      .prepare("SELECT name, sql FROM temp.sqlite_schema WHERE type = 'table' AND sql IS NOT NULL")
      .all()
      .map(plain);
    return tables.map(({ name, sql }) => {
      const stmt = this._db.prepare(`SELECT * FROM temp.${quoteIdent(name)}`);
      stmt.setReturnArrays(true);
      return { name, sql, rows: stmt.all().map((row) => row.map(encodeValue)) };
    });
  }
  _runWithTemp(sql, temp) {
    for (const t of temp) {
      // SQLite guarda el SQL de una tabla temporal sin TEMP: recrearlo tal cual la haría normal.
      this._db.exec(t.sql.replace(/^\s*create\s+table/i, "CREATE TEMP TABLE"));
      for (const row of t.rows) {
        const marks = row.map(() => "?").join(", ");
        this._db.prepare(`INSERT INTO temp.${quoteIdent(t.name)} VALUES (${marks})`).run(...row.map(decodeValue));
      }
    }
    try {
      this._db.exec(sql);
    } finally {
      for (const t of temp) this._db.exec(`DROP TABLE IF EXISTS temp.${quoteIdent(t.name)}`);
    }
  }

  // --- reconstrucción desde el ledger ------------------------------------------------------
  _replay() {
    this._applyRecords(this._ledger.list(0));
    // Marplanner comprueba que su fichero existe; queda vacío, solo marca el sitio.
    if (!fs.existsSync(this.name)) fs.writeFileSync(this.name, "", { mode: 0o600 });
  }

  /** Reproduce registros del ledger sobre la base en memoria y avanza `_seq`. */
  _applyRecords(records) {
    this._db.exec("PRAGMA foreign_keys = OFF");
    try {
      this._applyEach(records);
    } finally {
      this._db.exec("PRAGMA foreign_keys = ON");
    }
  }

  _applyEach(records) {
    for (const { seq, changeset } of records) {
      const record = JSON.parse(Buffer.from(changeset, "base64").toString("utf8"));
      if (record.v !== 1 || !Array.isArray(record.ops)) {
        throw new SqliteError(`registro ${seq} del ledger con formato desconocido`, "EMMA_LEDGER_FORMAT");
      }
      for (const op of record.ops) {
        if (typeof op.sql === "string") {
          this._runWithTemp(op.sql, Array.isArray(op.temp) ? op.temp : []);
        } else if (typeof op.cs === "string") {
          // Un conflicto al reproducir es una base que no cuadra con el ledger: se aborta.
          const ok = this._db.applyChangeset(Buffer.from(op.cs, "base64"), {
            onConflict: () => SQLITE_CHANGESET_ABORT,
          });
          if (!ok) throw new SqliteError(`el registro ${seq} no se reproduce limpio`, "EMMA_LEDGER_REPLAY");
        } else {
          throw new SqliteError(`registro ${seq}: operación desconocida`, "EMMA_LEDGER_FORMAT");
        }
      }
      this._seq = seq;
    }
  }

  _absorbRestoredFile() {
    if (fs.statSync(this.name).size === 0) return;
    // Una restauración dejó una base completa en la ruta: su contenido pasa a ser el vigente.
    const restored = new DatabaseSync(this.name, { readOnly: true });
    const schemaOf = (db, prefix) =>
      db
        .prepare(
          `SELECT type, name, sql FROM ${prefix}sqlite_schema
           WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'
           ORDER BY type = 'table' DESC, rowid`
        )
        .all()
        .map(plain);
    const wanted = schemaOf(restored, "");
    restored.close();
    const current = schemaOf(this._db, "main.");
    const sqlSet = (items) => JSON.stringify(items.map((t) => t.sql).sort());
    this._db.exec(`ATTACH DATABASE ${quoteText(this.name)} AS restored`);
    try {
      this._db.exec("PRAGMA foreign_keys = OFF");
      this._begin();
      if (sqlSet(wanted) !== sqlSet(current)) {
        // Esquema distinto: se rehace entero, y eso también queda en el ledger.
        for (const t of current.filter((x) => x.type === "table")) {
          this._schemaOp(`DROP TABLE IF EXISTS main.${quoteIdent(t.name)}`);
        }
        for (const t of wanted) this._schemaOp(t.sql);
      }
      for (const t of wanted.filter((x) => x.type === "table")) {
        const q = quoteIdent(t.name);
        this._db.exec(`DELETE FROM main.${q}; INSERT INTO main.${q} SELECT * FROM restored.${q}`);
      }
      this._commit();
    } catch (err) {
      this._abort();
      throw err;
    } finally {
      this._db.exec("PRAGMA foreign_keys = ON");
      this._db.exec("DETACH DATABASE restored");
    }
    fs.writeFileSync(this.name, "");
  }

  // --- captura de transacciones -------------------------------------------------------------
  _begin(mode = "") {
    this._db.exec(`BEGIN ${mode}`);
    this._ops = [];
    this._session = this._db.createSession();
  }
  _flush() {
    if (!this._session) return;
    const cs = this._session.changeset();
    this._session.close();
    this._session = null;
    if (cs.length) this._ops.push({ cs: Buffer.from(cs).toString("base64") });
  }
  _schemaOp(sql) {
    this._flush();
    const temp = this._tempState();
    this._db.exec(sql);
    this._ops.push(temp.length ? { sql, temp } : { sql });
    this._session = this._db.createSession();
  }
  _commit() {
    this._flush();
    const ops = this._ops ?? [];
    this._ops = null;
    if (ops.length) {
      const record = Buffer.from(JSON.stringify({ v: 1, ops }), "utf8").toString("base64");
      try {
        this._seq = this._ledger.append(record, this._seq);
      } catch (err) {
        this._db.exec("ROLLBACK");
        // El ledger puede haber anotado lo que aquí se dio por fallido: una respuesta que llegó
        // tarde (el backend ocupado al arrancar, visto el 2026-11-12) dejaba la base un registro
        // por detrás y TODA escritura posterior en 409, para siempre. Se ponen al día con lo que
        // haya; si lo anotado es justo esta transacción, quedó hecha y no se da por fallida.
        if (err instanceof LedgerConflict || err instanceof LedgerUnavailable) {
          let pending = [];
          try {
            pending = this._ledger.list(this._seq);
          } catch {
            throw err;
          }
          if (pending.length > 0) {
            const mine = pending.length === 1 && pending[0].changeset === record;
            this._applyRecords(pending);
            if (mine) return;
          }
        }
        throw err;
      }
    }
    this._db.exec("COMMIT");
  }
  _abort() {
    if (this._session) {
      this._session.close();
      this._session = null;
    }
    this._ops = null;
    if (this._db.isTransaction) this._db.exec("ROLLBACK");
  }
  _autocommit(fn) {
    if (!this._ledgered || this._db.isTransaction) return fn();
    this._begin();
    let out;
    try {
      out = fn();
    } catch (err) {
      this._abort();
      throw err;
    }
    this._commit();
    return out;
  }
  /**
   * Una escritura dentro de la captura. Si cambia el esquema de `main`, sus efectos no pueden ir
   * como changeset: se deshace con un punto de guardado, se repite sin sesión y se anota su SQL
   * (con el estado de las tablas temporales que pudiera leer).
   */
  _tracked(sql, fn) {
    if (!this._ledgered) return fn();
    if (!this._db.isTransaction) return this._autocommit(() => this._tracked(sql, fn));
    this._flush();
    this._session = this._db.createSession();
    const before = this._mainSchema();
    const temp = this._tempState();
    this._db.exec("SAVEPOINT emma_schema");
    let out;
    try {
      out = fn();
    } catch (err) {
      this._db.exec("ROLLBACK TO emma_schema");
      this._db.exec("RELEASE emma_schema");
      throw err;
    }
    if (this._mainSchema() === before) {
      this._db.exec("RELEASE emma_schema");
      return out;
    }
    this._db.exec("ROLLBACK TO emma_schema");
    this._db.exec("RELEASE emma_schema");
    this._session.close();
    this._session = null;
    out = fn();
    this._ops.push(temp.length ? { sql, temp } : { sql });
    this._session = this._db.createSession();
    return out;
  }

  // --- API de better-sqlite3 ---------------------------------------------------------------
  prepare(source) {
    return new Statement(this, source);
  }

  exec(source) {
    if (!this._ledgered) {
      this._db.exec(source);
      return this;
    }
    if (BEGIN.test(source)) {
      this._begin(source.replace(/^\s*begin/i, "").replace(/transaction|;/gi, "").trim());
      return this;
    }
    if (COMMIT.test(source)) {
      this._commit();
      return this;
    }
    if (ROLLBACK.test(source)) {
      this._abort();
      return this;
    }
    if (OUTSIDE_TX.test(source)) {
      this._db.exec(source);
      return this;
    }
    this._tracked(source, () => this._db.exec(source));
    return this;
  }

  pragma(source, options = {}) {
    // En memoria no hay WAL: se responde lo que es, "memory".
    if (this._ledgered && /^\s*journal_mode/i.test(source)) {
      return options.simple ? "memory" : [{ journal_mode: "memory" }];
    }
    const rows = this._db.prepare(`PRAGMA ${source}`).all().map(plain);
    if (!options.simple) return rows;
    return rows[0] ? Object.values(rows[0])[0] : undefined;
  }

  transaction(fn) {
    const db = this;
    const make = (mode) =>
      function (...args) {
        if (db._db.isTransaction) {
          db._db.exec("SAVEPOINT emma_nested");
          try {
            const out = fn.apply(this, args);
            db._db.exec("RELEASE emma_nested");
            return out;
          } catch (err) {
            db._db.exec("ROLLBACK TO emma_nested");
            db._db.exec("RELEASE emma_nested");
            throw err;
          }
        }
        if (!db._ledgered) {
          db._db.exec(`BEGIN ${mode}`);
          try {
            const out = fn.apply(this, args);
            db._db.exec("COMMIT");
            return out;
          } catch (err) {
            if (db._db.isTransaction) db._db.exec("ROLLBACK");
            throw err;
          }
        }
        db._begin(mode);
        let out;
        try {
          out = fn.apply(this, args);
        } catch (err) {
          db._abort();
          throw err;
        }
        db._commit();
        return out;
      };
    const tx = make("");
    tx.default = tx;
    tx.deferred = make("DEFERRED");
    tx.immediate = make("IMMEDIATE");
    tx.exclusive = make("EXCLUSIVE");
    return tx;
  }

  function(name, options, fn) {
    if (typeof options === "function") {
      fn = options;
      options = {};
    }
    this._db.function(name, options, fn);
    return this;
  }
  aggregate(name, options) {
    this._db.aggregate(name, options);
    return this;
  }
  backup(destination) {
    // Una copia de seguridad de Marplanner es un fichero local, como en el original.
    return sqliteBackup(this._db, destination).then((pages) => ({ totalPages: pages, remainingPages: 0 }));
  }
  serialize() {
    throw new SqliteError("serialize() no está soportado por el puente de EMMA", "EMMA_UNSUPPORTED");
  }
  loadExtension() {
    throw new SqliteError("las extensiones no se cargan en EMMA", "EMMA_UNSUPPORTED");
  }
  unsafeMode() {
    return this;
  }
  defaultSafeIntegers() {
    return this;
  }
  close() {
    if (this.open) {
      this._db.close();
      this.open = false;
    }
    return this;
  }
}

Database.SqliteError = SqliteError;
export { Database };
