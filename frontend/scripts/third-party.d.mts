// SPDX-License-Identifier: AGPL-3.0-or-later
// Tipos de `third-party.mjs`, para que su prueba (src/lib/thirdPartyNotices.test.ts) pase `tsc`.
export interface LockFile {
  packages?: Record<string, { version?: string; license?: string; dev?: boolean; devOptional?: boolean }>;
}
export interface ProductionPackage {
  name: string;
  dir: string;
  version?: string;
  license?: string;
}
export const HEADER: string;
export function productionPackages(lock: LockFile, root: string): ProductionPackage[];
export function notices(lock: LockFile, root: string): string;
