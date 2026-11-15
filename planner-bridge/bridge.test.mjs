// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Pruebas del puente Marplanner → ledger de EMMA. Se corren con:
 *   node --import ./register.mjs --test bridge.test.mjs
 *
 * Fijan lo que hace que la base de Marplanner SEA el ledger: lo confirmado se reconstruye igual
 * al reabrir; lo deshecho (transacción o punto de guardado) no llega al ledger; si el ledger
 * rechaza, la escritura se deshace también en memoria; una restauración entra como una
 * transacción más; en disco no queda la base; y el ledger por HTTP solo puede estar en loopback.
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";

process.env.EMMA_PLANNER_LEDGER = "memory:";
const dir = fs.mkdtempSync(path.join(os.tmpdir(), "emma-bridge-"));
process.env.DATA_DIR = dir;

const { default: Database } = await import("better-sqlite3");
const { getLedger, LedgerUnavailable } = await import("./ledger-client.mjs");

let n = 0;
function fresh() {
  n += 1;
  process.env.DATABASE_PATH = `planner-${n}.db`;
  return path.join(dir, process.env.DATABASE_PATH);
}

test("import de better-sqlite3 resuelve al puente", () => {
  assert.equal(typeof Database.SqliteError, "function");
});

test("lo confirmado se reconstruye igual desde el ledger y la base no queda en disco", () => {
  const file = fresh();
  const db = new Database(file);
  db.exec("CREATE TABLE a (id INTEGER PRIMARY KEY, v TEXT)");
  db.prepare("INSERT INTO a (v) VALUES (?)").run("uno");
  db.transaction(() => db.prepare("UPDATE a SET v = 'UNO' WHERE id = 1").run())();
  db.close();
  assert.equal(fs.statSync(file).size, 0);
  const again = new Database(file);
  assert.deepEqual(again.prepare("SELECT * FROM a").all(), [{ id: 1, v: "UNO" }]);
});

test("lo deshecho no llega al ledger", () => {
  const file = fresh();
  const db = new Database(file);
  db.exec("CREATE TABLE a (id INTEGER PRIMARY KEY, v TEXT)");
  const before = getLedger(path.resolve(file)).records.length;
  assert.throws(() => db.transaction(() => {
    db.prepare("INSERT INTO a (v) VALUES ('fantasma')").run();
    throw new Error("se deshace");
  })());
  db.exec("BEGIN IMMEDIATE");
  db.prepare("INSERT INTO a (v) VALUES ('otro fantasma')").run();
  db.exec("ROLLBACK");
  assert.equal(getLedger(path.resolve(file)).records.length, before);
  db.transaction(() => {
    db.prepare("INSERT INTO a (v) VALUES ('queda')").run();
    try {
      db.transaction(() => {
        db.prepare("INSERT INTO a (v) VALUES ('punto deshecho')").run();
        throw new Error("x");
      })();
    } catch {
      // el punto de guardado se deshace; la transacción de fuera sigue
    }
  })();
  assert.deepEqual(new Database(file).prepare("SELECT v FROM a").pluck().all(), ["queda"]);
});

test("si el ledger rechaza, la escritura se deshace también en memoria", () => {
  const file = fresh();
  const db = new Database(file);
  db.exec("CREATE TABLE a (id INTEGER PRIMARY KEY)");
  // Otro escritor anota antes: este se ha quedado atrás.
  getLedger(path.resolve(file)).records.push(
    Buffer.from(JSON.stringify({ v: 1, ops: [] })).toString("base64")
  );
  assert.throws(() => db.prepare("INSERT INTO a DEFAULT VALUES").run(), /hay \d+, se vio/);
  assert.equal(db.prepare("SELECT count(*) AS n FROM a").get().n, 0);
  assert.equal(db.inTransaction, false);
});

test("una respuesta tardía del ledger no deja la base atascada (fallo del 2026-11-12)", () => {
  const file = fresh();
  const db = new Database(file);
  db.exec("CREATE TABLE a (id INTEGER PRIMARY KEY, v TEXT)");
  const ledger = getLedger(path.resolve(file));
  const append = ledger.append.bind(ledger);
  // El ledger anota, pero la respuesta no llega a tiempo.
  ledger.append = (b64, expected) => {
    append(b64, expected);
    throw new LedgerUnavailable("el ledger de EMMA no respondió a tiempo");
  };
  db.prepare("INSERT INTO a (v) VALUES ('tarde')").run(); // anotado: no es un fallo
  ledger.append = append;
  db.prepare("INSERT INTO a (v) VALUES ('después')").run(); // antes: 409 para siempre
  assert.deepEqual(db.prepare("SELECT v FROM a ORDER BY id").all().map((r) => r.v), ["tarde", "después"]);
  const again = new Database(file);
  assert.deepEqual(again.prepare("SELECT v FROM a ORDER BY id").all().map((r) => r.v), ["tarde", "después"]);
});

test("una restauración entra al ledger como una transacción más", async () => {
  const file = fresh();
  const db = new Database(file);
  db.exec("CREATE TABLE a (id INTEGER PRIMARY KEY, v TEXT)");
  db.prepare("INSERT INTO a (v) VALUES ('antes')").run();
  const snapshot = path.join(dir, `snap-${n}.db`);
  await db.backup(snapshot);
  db.prepare("UPDATE a SET v = 'después'").run();
  db.close();
  fs.copyFileSync(snapshot, file);
  const restored = new Database(file);
  assert.deepEqual(restored.prepare("SELECT v FROM a").pluck().all(), ["antes"]);
  assert.equal(fs.statSync(file).size, 0);
  assert.deepEqual(new Database(file).prepare("SELECT v FROM a").pluck().all(), ["antes"]);
  // La copia de seguridad se valida como fichero, en solo lectura.
  const check = new Database(snapshot, { readonly: true, fileMustExist: true });
  assert.equal(check.prepare("SELECT count(*) AS n FROM a").get().n, 1);
});

test("el cerrojo de instancia de Marplanner sigue siendo un fichero", () => {
  const lock = path.join(dir, "x.db.instance-lock.sqlite");
  const db = new Database(lock);
  db.exec("CREATE TABLE IF NOT EXISTS ownership (id INTEGER PRIMARY KEY)");
  db.close();
  assert.ok(fs.statSync(lock).size > 0);
});

test("el ledger por HTTP solo puede estar en esta máquina", async () => {
  const { spawnSync } = await import("node:child_process");
  const probe = `import { getLedger } from ${JSON.stringify(new URL("./ledger-client.mjs", import.meta.url).href)};
    try { getLedger("x"); console.log("ACEPTADO"); } catch (e) { console.log(e.constructor.name); }`;
  const out = spawnSync(process.execPath, ["--input-type=module", "-e", probe], {
    env: { ...process.env, EMMA_PLANNER_LEDGER: "http://ejemplo.org/api/planner" },
    encoding: "utf8",
  });
  assert.equal(out.stdout.trim(), LedgerUnavailable.name);
});

test("VACUUM INTO (copia previa a migrar) funciona y no anota nada", () => {
  const file = fresh();
  const db = new Database(file);
  db.exec("CREATE TABLE a (id INTEGER PRIMARY KEY)");
  const before = getLedger(path.resolve(file)).records.length;
  const copy = path.join(dir, `vacuum-${n}.db`);
  db.prepare("VACUUM INTO ?").run(copy);
  assert.ok(fs.statSync(copy).size > 0);
  assert.equal(getLedger(path.resolve(file)).records.length, before);
});

test("una migración que lee una tabla temp. se anota y se reproduce (fallo del 2026-11-12)", () => {
  const file = fresh();
  const db = new Database(file);
  db.exec("CREATE TEMP TABLE ctx (kind TEXT)");
  db.prepare("INSERT INTO temp.ctx VALUES (?)").run("fresh");
  db.transaction(() => {
    db.exec(
      "CREATE TABLE lineage (id INTEGER PRIMARY KEY, kind TEXT);" +
        "INSERT INTO lineage (id, kind) SELECT 1, kind FROM temp.ctx;" +
        "CREATE TABLE reminder (id INTEGER PRIMARY KEY, v TEXT)"
    );
    db.prepare("INSERT INTO reminder (v) VALUES ('x')").run();
  })();
  db.exec("DROP TABLE temp.ctx");
  db.close();
  const again = new Database(file);
  assert.deepEqual(again.prepare("SELECT kind FROM lineage").pluck().all(), ["fresh"]);
  assert.deepEqual(again.prepare("SELECT v FROM reminder").pluck().all(), ["x"]);
  // La tabla temporal no se queda en la base reconstruida.
  assert.equal(again.prepare("SELECT count(*) FROM temp.sqlite_schema").pluck().get(), 0);
});

test("a internet solo se sale por la puerta de EMMA", async () => {
  const { purposeFor, guardFetch } = await import("./egress.mjs");
  assert.equal(purposeFor("https://zenquotes.io/api/today"), "planner-quotes");
  assert.equal(purposeFor("https://es.wikipedia.org/api/rest_v1/feed/onthisday/all/11/12"), "planner-onthisday");
  assert.equal(purposeFor("https://api.open-meteo.com/v1/forecast?latitude=40"), null);
  assert.equal(purposeFor("https://api.ui.com/v1/hosts"), null);
  assert.equal(purposeFor("http://zenquotes.io/api/today"), null);
  const calls = [];
  const fake = async (url, init) => {
    calls.push({ url: String(url), init });
    return new Response(JSON.stringify({ status: 200, content_type: "application/json", body: "[1]" }), { status: 200 });
  };
  process.env.EMMA_PLANNER_LEDGER = "http://127.0.0.1:8000/api/planner";
  try {
    const guarded = guardFetch(fake);
    await assert.rejects(guarded("https://api.open-meteo.com/v1/forecast?latitude=40"), /no tiene propósito/);
    await assert.rejects(guarded("https://zenquotes.io/api/today", { method: "POST", body: "x" }), /no sale/);
    const res = await guarded("https://zenquotes.io/api/today");
    assert.deepEqual(await res.json(), [1]);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, "http://127.0.0.1:8000/api/planner/fetch");
    assert.deepEqual(JSON.parse(calls[0].init.body), { purpose: "planner-quotes", url: "https://zenquotes.io/api/today" });
  } finally {
    process.env.EMMA_PLANNER_LEDGER = "memory:";
  }
});

test("undici solo llega a esta máquina", async () => {
  const undici = await import("undici");
  await assert.rejects(undici.fetch("https://api.ui.com/v1/hosts"), /no sale/);
  assert.equal(typeof undici.Agent, "function");
});
