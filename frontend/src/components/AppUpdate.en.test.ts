/**
 * «Actualizar EMMA» en inglés (`lib/i18n.ts`): los rótulos de los mandos salen en inglés; las notas
 * y los mensajes son del backend y llegan tal cual (marcadores en mayúsculas).
 */
import "../test/english";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AppUpdate, type AppUpdateState, AppUpdateView } from "./AppUpdate";

const state: AppUpdateState = {
  state: "ready",
  phase: null,
  current_version: null,
  available: { version: "0.2.0", size: null, notes: "NOTES" },
  comparable: true,
  done_bytes: 0,
  total_bytes: 0,
  ready: { version: "0.2.0" },
  install_requested: false,
  error: null,
  network: true,
  network_note: null,
  restart_note: "RESTART-NOTE",
};

describe("AppUpdate in English", () => {
  it("labels the fold and the controls in English", () => {
    expect(renderToStaticMarkup(createElement(AppUpdate))).toContain("Update EMMA");
    const html = renderToStaticMarkup(
      createElement(AppUpdateView, { state, busy: false, problem: null, upToDate: false, onAction: () => undefined }),
    );
    for (const text of ["Installed version:", "unknown", "Published version:", "Check for a new version", "Install and restart", "NOTES", "RESTART-NOTE"]) {
      expect(html, text).toContain(text);
    }
    expect(
      renderToStaticMarkup(
        createElement(AppUpdateView, {
          state: { ...state, install_requested: true },
          busy: false,
          problem: null,
          upToDate: false,
          onAction: () => undefined,
        }),
      ),
    ).toContain("Closing EMMA to install the new version");
  });
});
