"""Arranque del backend dentro de la aplicacion de escritorio.

Es el punto de entrada que congela PyInstaller (`emma-backend.exe`). Lo lanza el
proceso principal de Electron con un puerto libre, y lo mata al cerrar.

Solo escucha en 127.0.0.1: la API no autentica a quien llama (riesgo residual H3 de
`compliance/risk-management-file.md`), asi que no puede quedar expuesta a la red.

La configuracion llega por variables de entorno `EMMA_*`, que es como la lee ya
`app/core/config.py`: `EMMA_FRONTEND_DIST` y `EMMA_CACHE_DIR` las fija Electron.
"""

from __future__ import annotations

import argparse

import uvicorn

from app.main import app

LOOPBACK = "127.0.0.1"


def main() -> None:
    parser = argparse.ArgumentParser(description="Backend de EMMA para la aplicacion de escritorio")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    uvicorn.run(app, host=LOOPBACK, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
