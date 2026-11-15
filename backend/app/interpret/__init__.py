# SPDX-License-Identifier: AGPL-3.0-or-later
"""Borrador de interpretación asistida por un modelo de lenguaje local.

Por qué existe: una medida sola es un número. Lo que un médico de a bordo quiere leer es "la
vaina derecha pasó de 5,1 a 5,9 mm en tres semanas, medida con la misma técnica, sin alertas
porque aún no hay base personal". Redactar eso a partir del registro es trabajo mecánico que un
modelo hace bien. Lo que no puede hacer es decidir nada, y este paquete está construido para que
no pueda.

Arquitectura de Polaris (github.com/BeyondTheProtocol/polaris): un redactor, un verificador
adversarial y una única puerta de salida con aprobación humana. Usa además código suyo
(AGPL-3.0-or-later, la licencia de EMMA): la guarda contra inyección `_ANTI` de `tools/local.py`,
leída en `draft.py` de la copia literal (`polaris/`); y el cotejo de presencia y ausencia de
`tools/cotejo_invariante.py`, que en `cotejo.py` sigue adaptado porque el original solo reconoce
afirmaciones sobre genes (divergencia pendiente de decisión, `docs/polaris-divergencias.md`).
Adaptado a una nave sin enlace con Tierra:

  * **Solo local.** El modelo corre en la propia nave (servidor tipo Ollama en loopback). Una URL
    que no sea de loopback se rechaza: los datos clínicos no salen, y hacia Marte no habría a
    quién mandarlos.
  * **Solo hechos del registro.** El modelo recibe medidas, historial y método firmados, nunca
    texto libre del tripulante.
  * **Seis barreras antes de que valga nada:** salida estructurada, verificador adversarial,
    cifras que tienen que salir de los hechos, signos presentes o ausentes que tienen que estar
    anotados (`cotejo.py`), linter de lenguaje (`app/text_guard.py`) y firma humana. Un borrador
    que falla una de las cinco primeras no se muestra.
  * **Borrador, no informe.** Queda "sin validar" hasta que alguien lo acepta o lo rechaza, y las
    dos cosas se firman en el ledger. La firma cita la huella del texto leído: se firma lo que
    se vio (patrón de Polaris `tools/salida.py`).
"""
