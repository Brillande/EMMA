// Copia de `PrinterTransportSettings` de `marplanner/src/shared/index.ts` (Marplanner, MIT,
// © 2026 Diego Mariño), lo único que necesita `transport.ts` de ese módulo.

export interface PrinterTransportSettings {
  deviceId: string;
  name: string;
  serviceUuid: string;
  characteristicUuid: string;
}
