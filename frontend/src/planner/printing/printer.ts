/**
 * La impresora térmica de la hoja diaria, vista desde la consola.
 *
 * Por qué existe: Marplanner encola en su servidor lo que hay que imprimir, pero quien imprime es
 * un navegador con la impresora emparejada por Bluetooth (su quiosco). En EMMA ese navegador es
 * la consola (petición del usuario, 2026-11-13: «vamos a hacernos con una impresora de calor»).
 * Esto sigue el protocolo de `marplanner/src/client/printing/PrintExecutor.tsx` (MIT, © 2026
 * Diego Mariño) sin su interfaz: reclamar un trabajo (`/printing/claim`), leer sus bytes ESC/POS
 * con el testigo del reclamo, mandarlos por `transport.ts` y confirmar (`ack`) o informar del
 * fallo (`fail`). Dos reglas suyas se mantienen: un `ack` que falla tras imprimir se reintenta y
 * nunca se convierte en `fail` (el papel ya salió), y mientras haya un `ack` pendiente no se
 * reclama otro trabajo.
 *
 * Vive fuera de los paneles: la impresora sigue conectada y recogiendo trabajos aunque se cambie
 * de sección. Todo va por el backend de EMMA (`/api/planner/app/printing/*`); nada sale de la nave.
 */

import { withConsoleHeader } from "../../lib/api";
import { loadRememberedPrinter, saveRememberedPrinter } from "./rememberedPrinter";
import { type PrintTransport, PrintTransportError, createPrintTransport } from "./transport";

const BASE = "/api/planner/app/printing";
/** Cada cuánto se mira la cola con la impresora conectada (Marplanner usa 15 s). */
export const POLL_MS = 5_000;

export type PrinterConnection = "unpaired" | "pairing" | "paired" | "disconnected";

export interface PrinterSnapshot {
  connection: PrinterConnection;
  /** Nombre que anuncia la impresora, o "" si aún no se ha conectado ninguna. */
  name: string;
  printing: boolean;
  printed: number;
  lastError: string | null;
}

interface Claim {
  job: { id: string };
  leaseToken: string;
}

type AckOutcome = "success" | "dropped" | "retry";

/** El fallo del transporte en palabras de la consola. */
export function describePrinterError(err: unknown): string {
  if (err instanceof PrintTransportError) {
    switch (err.code) {
      case "unsupported":
        return "Este equipo no tiene Bluetooth para la impresora.";
      case "secure_context_required":
        return "El Bluetooth solo funciona en la aplicación de escritorio o en una página local.";
      case "pairing_required":
        return "No se eligió ninguna impresora.";
      case "connect_failed":
        return "No se pudo conectar con la impresora: compruebe que está encendida y cerca.";
      case "characteristic_not_found":
        return "Esa impresora no ofrece un canal de impresión conocido (¿es Bluetooth LE y ESC/POS?).";
      case "write_failed":
        return "La impresora no aceptó los datos.";
    }
  }
  if (err instanceof DOMException && err.name === "NotFoundError") return "No se eligió ninguna impresora.";
  return err instanceof Error ? err.message : String(err);
}

function post(path: string, body?: unknown): Promise<Response> {
  return fetch(
    `${BASE}${path}`,
    withConsoleHeader(
      body === undefined
        ? { method: "POST" }
        : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
    ),
  );
}

export class Printer {
  private snapshot: PrinterSnapshot = { connection: "unpaired", name: "", printing: false, printed: 0, lastError: null };
  private readonly listeners = new Set<() => void>();
  private timer: ReturnType<typeof setInterval> | null = null;
  private busy = false;
  private pendingAck: { jobId: string; leaseToken: string } | null = null;

  constructor(private readonly transport: PrintTransport) {
    transport.onDisconnect(() => this.set({ connection: "disconnected" }));
    const remembered = loadRememberedPrinter();
    if (remembered) this.snapshot = { ...this.snapshot, name: remembered.name };
  }

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = (): PrinterSnapshot => this.snapshot;

  private set(change: Partial<PrinterSnapshot>): void {
    this.snapshot = { ...this.snapshot, ...change };
    if (this.snapshot.connection === "paired" || this.pendingAck !== null) this.startPolling();
    else this.stopPolling();
    for (const listener of this.listeners) listener();
  }

  private startPolling(): void {
    if (this.timer === null) this.timer = setInterval(() => void this.tick(), POLL_MS);
  }

  private stopPolling(): void {
    if (this.timer !== null) clearInterval(this.timer);
    this.timer = null;
  }

  /** Esta consola se declara capaz de imprimir; Marplanner no deja reclamar trabajos sin ello. */
  private async registerCapability(): Promise<void> {
    const response = await post("/capability");
    if (!response.ok) throw new Error(`Marplanner no aceptó la impresora (${response.status}).`);
  }

  /** Emparejar: lo abre el usuario con un gesto (el navegador enseña su selector). */
  async pair(): Promise<void> {
    this.set({ connection: "pairing", lastError: null });
    const remembered = loadRememberedPrinter();
    try {
      const identity = await this.transport.pair(
        remembered ? { serviceUuid: remembered.serviceUuid, characteristicUuid: remembered.characteristicUuid } : undefined,
      );
      await this.registerCapability();
      saveRememberedPrinter(identity);
      this.set({ connection: "paired", name: identity.name || "impresora" });
      void this.tick();
    } catch (err) {
      this.transport.disconnect();
      this.set({ connection: remembered ? "disconnected" : "unpaired", lastError: describePrinterError(err) });
    }
  }

  /** Volver a la impresora recordada sin selector, si el navegador aún la tiene concedida. */
  async reconnect(): Promise<boolean> {
    const remembered = loadRememberedPrinter();
    if (!remembered || this.snapshot.connection === "paired" || this.snapshot.connection === "pairing") return false;
    try {
      const identity = await this.transport.reconnect(remembered);
      await this.registerCapability();
      this.set({ connection: "paired", name: identity.name || remembered.name, lastError: null });
      void this.tick();
      return true;
    } catch {
      this.transport.disconnect();
      return false;
    }
  }

  disconnect(): void {
    this.transport.disconnect();
    this.set({ connection: "disconnected" });
  }

  /** Mira la cola ya, sin esperar al siguiente turno (tras encolar algo). */
  wake(): void {
    void this.tick();
  }

  /** Encola una página de prueba de Marplanner y la imprime. */
  async testPrint(): Promise<void> {
    const response = await post("/test-print", {});
    if (!response.ok) throw new Error(`Marplanner no encoló la prueba (${response.status}).`);
    this.wake();
  }

  private async ack(jobId: string, leaseToken: string): Promise<AckOutcome> {
    try {
      const response = await post(`/jobs/${encodeURIComponent(jobId)}/ack`, { leaseToken });
      if (response.ok) return "success";
      return response.status === 409 ? "dropped" : "retry";
    } catch {
      return "retry";
    }
  }

  private settleAck(jobId: string, leaseToken: string, outcome: AckOutcome): void {
    this.pendingAck = outcome === "retry" ? { jobId, leaseToken } : null;
    if (outcome === "success") this.set({ printed: this.snapshot.printed + 1 });
    else this.set({});
  }

  async tick(): Promise<void> {
    if (this.busy) return;
    this.busy = true;
    try {
      if (this.pendingAck !== null) {
        const { jobId, leaseToken } = this.pendingAck;
        this.settleAck(jobId, leaseToken, await this.ack(jobId, leaseToken));
        return;
      }
      if (this.snapshot.connection !== "paired") return;
      if (!this.transport.isReady()) {
        this.set({ connection: "disconnected" });
        return;
      }
      const response = await post("/claim");
      if (response.status === 204) return;
      if (response.status === 403) {
        const body = (await response.json().catch(() => null)) as { code?: unknown } | null;
        if (body?.code === "printer_capability_missing") await this.registerCapability().catch(() => undefined);
        return;
      }
      if (!response.ok) return;
      await this.execute((await response.json()) as Claim);
    } catch {
      // Un fallo de red al reclamar: se sigue conectado y se prueba en el siguiente turno.
    } finally {
      this.busy = false;
    }
  }

  private async execute({ job, leaseToken }: Claim): Promise<void> {
    this.set({ printing: true });
    try {
      let bytes: Uint8Array;
      try {
        const payload = await fetch(
          `${BASE}/jobs/${encodeURIComponent(job.id)}/payload?leaseToken=${encodeURIComponent(leaseToken)}`,
          withConsoleHeader(),
        );
        // 404, 409 o 422: Marplanner ya lo ha resuelto; no hay nada que confirmar.
        if (!payload.ok) return;
        bytes = new Uint8Array(await payload.arrayBuffer());
      } catch {
        return; // el reclamo caduca en Marplanner y el trabajo vuelve a la cola
      }
      try {
        await this.transport.printJob(bytes);
      } catch (err) {
        const permanentCode =
          err instanceof PrintTransportError && err.code === "unsupported"
            ? "unsupported_transport"
            : err instanceof PrintTransportError && err.code === "secure_context_required"
              ? "secure_context"
              : null;
        await post(`/jobs/${encodeURIComponent(job.id)}/fail`, {
          leaseToken,
          reason: err instanceof Error ? err.message : String(err),
          permanentCode,
        }).catch(() => undefined);
        this.set({ lastError: describePrinterError(err) });
        if (!this.transport.isReady()) this.set({ connection: "disconnected" });
        return;
      }
      // Ya está en papel: desde aquí un fallo es del `ack`, nunca del trabajo.
      this.set({ lastError: null });
      this.settleAck(job.id, leaseToken, await this.ack(job.id, leaseToken));
    } finally {
      this.set({ printing: false });
    }
  }
}

let shared: Printer | null = null;

/** La impresora de esta consola (una por pestaña), creada al primer uso. */
export function printer(): Printer {
  shared ??= new Printer(createPrintTransport());
  return shared;
}
