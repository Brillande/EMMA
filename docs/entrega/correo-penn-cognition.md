# Borrador: correo a Penn para pedir Cognition

Borrador del 2026-11-05, escrito por un asistente de código a partir del repositorio. **Lo envía el
equipo** (cognition@pennmedicine.upenn.edu), no EMMA. Antes de enviarlo: rellenar los [EQUIPO],
revisar que todo lo que dice siga siendo cierto y decidir quién firma.

Por qué existe: la batería Cognition es software de Penn y Pulsar Informatics; la página oficial
(https://www.med.upenn.edu/uep/cognition.html, leída el 2026-11-04) dice que la NASA la da para
investigación con financiación federal y que la otra vía es colaborar con el equipo de Penn. EMMA
no la reprograma (`backend/app/ingest/cognition.py`): registra lo que puntúa el programa oficial.
Lo que se pide es acceso y un fichero de ejemplo de su exportación «Metrics» para conectar EMMA sin
teclear puntuaciones a mano.

---

**Subject:** Cognition test battery — request for a collaboration / sample export (NASA Space Apps 2026 project)

Dear Cognition R&D team,

We are [EQUIPO: names], a team taking part in the NASA International Space Apps Challenge 2026
(14–15 November) with EMMA, an open-source, offline-first decision-support tool for crew health
monitoring on long-duration missions. EMMA compares each crew member with their own baseline, scales
risk with the light-time delay to Earth, and records every observation in a signed, append-only
log. It is decision support, not a medical device, and makes no diagnostic claims.

EMMA already lists the ten Cognition tests as descriptive indicators, following Basner et al. 2015
and Dev et al. 2024. We deliberately do not reimplement the battery: its stimuli, versions, scoring
and laptop calibration belong to your software, and numbers produced by a copy would not be
Cognition scores. Our goal is the opposite: to record, signed and with who performed them, the scores
that the official Cognition software produces, next to the rest of the crew member's data.

We understand from your page that the software is available through NASA for federally funded
research, and through collaboration with your team. We would like to ask:

1. Whether a collaboration or evaluation access would be possible for this non-commercial project,
   and under which terms.
2. Whether you could share a sample (synthetic or de-identified) «Metrics» export file, so we can
   verify our importer against the real format instead of guessing it.
3. Whether including a link to, or a launcher for, an installed copy of Cognition in our Windows
   desktop app would be acceptable, or whether you would prefer we only import exported files.

We will not redistribute your software or present any result as validated by your team. Any use of
Cognition in EMMA would be clearly labelled with its origin and licence.

Thank you for your time and for making this battery available to the research community.

Best regards,
[EQUIPO: name, role, contact]
EMMA — NASA Space Apps Challenge 2026
