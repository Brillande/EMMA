import { useState } from "react";

const OPERATOR_KEY = "emma.operator";

/** Quien esta en la consola segun lo guardado, sin estado de React (lo lee la privacidad). */
export function storedOperator(): string {
  try {
    return localStorage.getItem(OPERATOR_KEY) ?? "";
  } catch {
    return "";
  }
}

/**
 * Quien esta en la consola. Se recuerda en este equipo por comodidad; no es una
 * identidad autenticada, y el ledger lo registra como declarado.
 */
export function useOperator(): [string, (value: string) => void] {
  const [value, setValue] = useState<string>(() => {
    try {
      return localStorage.getItem(OPERATOR_KEY) ?? "";
    } catch {
      return "";
    }
  });
  const update = (next: string) => {
    setValue(next);
    try {
      localStorage.setItem(OPERATOR_KEY, next);
    } catch {
      // sin almacenamiento local: se pide cada vez
    }
  };
  return [value, update];
}
