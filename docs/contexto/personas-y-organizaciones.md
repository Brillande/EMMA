# Personas y organizaciones citadas

Pestaña "People & Organizations" que proponía la conversación de ideación. Solo entra quien
aparece en una fuente pública que el proyecto ya ha leído, con esa fuente. No es una lista de
contactos: es trazabilidad de quién produjo lo que EMMA usa.

Cada fila lleva su ficha del registro de evidencia (`backend/app/data/evidence_refs.json`)
cuando la tiene: ahí están la frase leída, la fecha de lectura y cuánto se leyó. Un cargo o una
afiliación solo se escriben si la fuente los escribe, y con la fecha de esa fuente: un cargo de
un artículo de 2016 es el de 2016. La afiliación de un artículo es la que firma en él, no la de
hoy.

**Servido desde la decimosexta ronda (2026-10-23).** `GET /api/people` y el panel «Personas y
organizaciones» de la consola de Tierra lo derivan del registro en cada consulta: cada
organización que da una ficha, con sus fichas y su año, y cada persona que firma una ficha
(`authors`, con la grafía de la cita) o que la fuente nombra (`named_people`, con el cargo que le
da), con su papel. El registro no admite una persona que la ficha no escriba letra a letra ni un
dato de contacto (`evidence/registry.py`). Esa es la lista completa; este documento guarda el
porqué de cada fila y lo que el registro no tiene (TRISH, ICON y BIG, NSRL por su página). Dos
reglas de la ruta: la organización de una
ficha no es la afiliación de cada firmante (en un artículo suele ser la del primer autor; la nota
de la ficha dice cuál), y se agrupa por la grafía exacta: un nombre escrito de dos formas en dos
citas («Dinges DF» y «Dinges, David») sale dos veces, porque no se juntan nombres por parecido, y
dos personas con las mismas iniciales («Anderson A» en dos presentaciones) salen juntas, porque
ninguna ficha dice si lo son; la ruta sirve esa regla junto a la lista. Por lo mismo, «NASA OCHMO»
y «NASA Office of the Chief Health and Medical Officer» salen en dos filas. Las tablas de abajo se
pusieron al día el 2026-10-23 con todas las organizaciones y firmantes del registro de ese día;
una ficha posterior sale en la ruta aunque aquí falte. `tests/test_people.py` exige que cada
ficha que cita este documento exista.

**Desde la decimonovena ronda (U4, 2026-10-31)** la ruta sirve dos cosas más. Una organización que
una fuente nombra sin darla (`named_organizations`) sale entre las organizaciones con el papel que
la fuente le da, en su fecha, y la ficha que la nombra; y una persona lleva la organización que el
documento escribe junto a su nombre (`affiliations`), solo si la ficha la escribe: sin frase, nada.
La columna «especialidad y tecnología» de cada persona que pedía la conversación de ideación no
se añade: ninguna ficha la da con esas palabras, más allá del cargo que ya sale.

## Proveedores y organizaciones que nombran las fuentes

| Organización | Papel que le da la fuente | Ficha que la nombra |
|---|---|---|
| The Boeing Co. (la ruta no la junta con «The Boeing Company», que da una ficha) | «sustaining engineering of station hardware and software» (2010) | `nasa-iss-sustaining-boeing-2010` |
| Teledyne Brown Engineering Inc. | «International Space Station payload operations and ground systems» (2022) | `nasa-mossi-ii-teledyne-2022` |
| Center for the Advancement of Science in Space (CASIS) | «help manage the U.S. segment of the International Space Station» (2022) | `nasa-iss-national-lab-casis-2022` |
| National Science Foundation (NSF) | «has accepted two immunology-focused studies for this upcoming winter-over season» (sin fecha en la ficha) | `nasa-antarctic-stations-nsf` |
| United States’ Antarctic Program (USAP) | «maintains McMurdo» (sin fecha en la ficha) | `nasa-antarctic-stations-nsf` |
| DLR | «on bedrest studies examining the effects of microgravity on the human body» (sin fecha en la ficha); que opera :envihab lo da la columna de proveedores del banco | `nasa-envihab-mission` |
| Naval Aerospace Medical Research Laboratory | «the organization that operates the Kraken» (2023) | `nasa-kraken-2023` |

**COLSA** sigue sin fuente: el 2026-10-31 no se encontró ninguna página viva de nasa.gov que la
nombre (la nota de 2012 del contrato del HOSC devuelve 404; las hojas de datos del POIC y de
Marshall y el Marshall Star de agosto de 2012 no la nombran), y por eso no sale en la ruta.

## Organizaciones

| Organización | Qué aporta a EMMA | Fuente leída |
|---|---|---|
| NASA Human Research Program (HRP) | Riesgos por dominio, Twins Study, repositorios de datos | [nasa.gov/hrp](https://www.nasa.gov/hrp/) (portada releída el 2026-10-21, «Page Last Updated: Oct 14, 2026») |
| NASA OCHMO (Office of the Chief Health & Medical Officer) | Resúmenes técnicos de NASA-STD-3001: ECLSS (OCHMO-TB-002), acústica (OCHMO-TB-035), iluminación (OCHMO-TB-026), ejercicio (OCHMO-TB-031); resúmenes médicos de desincronía circadiana (OCHMO-MTB-009) y pérdida ósea (OCHMO-MTB-013) | Fichas `ochmo-tb-002`, `ochmo-tb-026`, `ochmo-tb-031`, `ochmo-mtb-009`, `ochmo-mtb-013`; [OCHMO-TB-035](https://www.nasa.gov/wp-content/uploads/2023/12/ochmo-tb-035-acoustics.pdf) (sin ficha) |
| NASA/JSC Toxicology Group | SMAC de contaminantes de cabina (JSC 20584 Rev C) | Ficha `jsc-20584-rev-c` |
| NASA Space Food Systems Laboratory (JSC) | Escala hedónica de 9 puntos: los extremos que escribe NASA hoy, los rótulos de su panel de catadores (1981 y 2015) y la leyenda de las valoraciones de astronautas en la ISS (2025) | Fichas `douglas-2025-iss-food-acceptability`, `massa-2015-leafy-greens-iss` («sent to the JSC Space Food Systems Laboratory»), `ahmed-1981-high-density-foods` |
| NASA Johnson Space Center | Organización de las fichas de CO2 y cefalea (Law 2014), escala hedónica (Douglas 2025, Ahmed 1981), virus latentes y recogida de muestras en vuelo (Mehta 2017) y sangre en la ISS (Brawley 2026); una de las dos de Scully 2019. El artículo de Orion sitúa allí el trabajo de protección radiológica | Fichas `law-2014`, `douglas-2025-iss-food-acceptability`, `ahmed-1981-high-density-foods`, `mehta-2017-latent-virus-iss`, `brawley-2026-raman-sers`, `scully-2019`, `nasa-orion-radiation-protection` |
| NASA Ames Research Center | Arquitectura de datos médicos (huecos Med 07 y Med 10), recomendaciones de entorno de sueño y el NASA-TLX de su grupo de rendimiento humano | Fichas `ntrs-20200000567`, `caddick-2016-sleep-environment`, `nasa-tlx-1986` |
| NASA Kennedy Space Center | Organización del artículo de 2015 con los nueve rótulos numerados de la escala hedónica | Ficha `massa-2015-leafy-greens-iss` |
| Translational Research Institute for Space Health (TRISH) | Nada que EMMA use. NASA la describe como un acuerdo de cooperación del HRP, «a consortium led by Baylor College of Medicine with the California Institute of Technology in Pasadena and the Massachusetts Institute of Technology in Cambridge», que financia estudios y tecnologías de salud para misiones de espacio profundo. Afín a EMMA: según la misma página, TRISH desarrolla HERMES, una plataforma de datos de salud que «aims to provide astronauts with the health information they need to make informed medical decisions on distant missions from Earth». Leído el 2026-10-26 lo que dicen de HERMES NASA y Baylor: su fila en `compliance/state-of-the-art.md` | [nasa.gov, TRISH](https://www.nasa.gov/hrp/the-translational-research-institute-for-space-health-trish/), leída el 2026-10-21 y releída entera el 2026-10-26 («Page Last Updated: May 18, 2026»). Ficha `nasa-trish` desde el 2026-10-26: la cita el bloque de HERMES de `/api/framework`. TRISH como organización sigue sin ficha: la de la página es del HRP |
| Brookhaven National Laboratory (NSRL) | Simulación de radiación espacial; gestiona el laboratorio, que financia NASA | Fichas `bnl-nsrl` (portada) y `bnl-nsrl-about` ([bnl.gov/nsrl/about.php](https://www.bnl.gov/nsrl/about.php), leída el 2026-10-23) |
| Agencia Espacial Canadiense (Canadian Space Agency) | Rutina de ejercicio diario en la ISS (2006) y el chaleco Bio-Monitor (2026) | Fichas `csa-physical-activity`, `csa-bio-monitor` |
| ESA | Las instalaciones EPM y Biolab de Columbus (páginas sin fecha), el informe de operaciones n.º 84 (2010) y el pie de foto de TripleLux (2015) | Fichas `esa-epm`, `esa-biolab`, `esa-iss-status-report-84`, `esa-image-2015-triplelux` |
| NASA OSDR | Los conjuntos OSD-288 (2019, bazo de ratón), OSD-343 (2020) y OSD-569 (2024) | Fichas `osd-288`, `osd-343`, `osd-569` |
| NASA Glenn Research Center | MEDPRAT y su comparación con el IMM (2018, 2020, 2023 y 2025) y las demostraciones tecnológicas médicas de la ISS (HemoCue, 2022; 2024) | Fichas `ntrs-20180004678`, `ntrs-20200000853`, `ntrs-20200000974`, `ntrs-20230001121`, `ntrs-20240012058`, `ntrs-20210026808`, `ntrs-20240004905` |
| NASA Office of the Chief Health and Medical Officer | NASA-STD-3001 Vol 2 Rev F (2026). Es la misma oficina que otras fichas escriben «NASA OCHMO»; la ruta no las junta | Ficha `nasa-std-3001-vol2-rev-f` |
| NASA Human Research Roadmap | Tarea 1651, la PVT en la ISS (página de 2025) | Ficha `hrr-task-1651-pvt` |
| NASA HumanResearchWiki | Retención urinaria de adaptación al espacio (2014) | Ficha `hrr-urinary-retention` |
| NASA Jet Propulsion Laboratory | Noticia de la pausa de órdenes a Marte por la conjunción (2015) | Ficha `jpl-2015-mars-conjunction` |
| NASA Jet Propulsion Laboratory · Solar System Dynamics | Manual de Horizons (2026): la elongación que acompaña al tiempo de luz | Ficha `jpl-horizons-manual` |
| National Library of Medicine | MedlinePlus, pruebas de función hepática (2023) | Ficha `medlineplus-liver-function-tests` |
| National Cancer Institute | Módulo SEER de anatomía y fisiología (páginas sin fecha): para qué sirve cada órgano o sistema de la figura | Fichas `seer-nervous-system`, `seer-cardiovascular-system`, `seer-respiratory-system`, `seer-skeletal-system`, `seer-muscular-system`, `seer-urinary-system`, `seer-digestive-system`, `seer-digestive-accessory-organs`, `seer-lymphatic-system` |
| National Eye Institute | Cómo funcionan los ojos (2022): para qué sirven los ojos y el nervio óptico en la figura | Ficha `nei-how-the-eyes-work` |
| PhysioNet | MMASH 1.0.0 (2020), el conjunto con que se mide la tasa de falsa alarma | Ficha `mmash` |
| The Boeing Company | Resumen del sistema de control térmico activo de la ISS (2006), publicado en nasa.gov | Ficha `nasa-iss-atcs-overview` |
| ICON | Impresión del hábitat de CHAPEA: «ICON’s next generation Vulcan construction system». Esta fila decía «ICON y BIG», pero la página que citaba no nombra a BIG (releída el 2026-10-23: ni «BIG», ni «Bjarke», ni «Ingels»), y ninguna otra página leída de NASA le atribuye el hábitat | Ficha `nasa-chapea-habitat` ([NASA, CHAPEA, Habitat](https://www.nasa.gov/humans-in-space/chapea/habitat/)) |

Otras organizaciones, por la afiliación que firma el primer autor (o el autor de NASA) en un
artículo que EMMA cita, o la que da la ficha; es la del artículo, no la de hoy:

| Organización | Artículo | Ficha |
|---|---|---|
| JES Tech | Hardy et al. 2025, Spaceflight Standard Measures | `hardy-2025-spaceflight-standard-measures` |
| The University of Texas Medical Branch | Kerstman et al. 2012, dolor de espalda de adaptación | `kerstman-2012` |
| University of Manchester | Brown et al. 2022, luz en interiores | `brown-2022-melanopic-light` |
| University of Pennsylvania School of Medicine | Basner et al. 2011, PVT-B | `basner-2011-pvt-b` |
| Brigham and Women's Hospital | Lockley y Brainard 2016, Lighting Effects | `lockley-brainard-2016-lighting-effects` |
| University of Central Florida | Hayslip et al. 2026, envejecimiento acelerado (hígado de ratón) | `hayslip-2026` |
| KBRwyle | Scully et al. 2019 (con NASA JSC); Kunz et al. 2017, índices hematológicos en vuelo | `scully-2019`, `kunz-2017-hematologic-indices-iss` |
| KBR | Marshall-Goebel et al. 2019, flujo de la vena yugular interna en vuelo; Clément et al. 2022, protocolo del reposo en cama AGBRESA (filiación leída el 2026-10-26) | `marshall-goebel-2019-ijv`, `clement-2022-agbresa` |
| University of Konstanz | Kramer et al. 2021, resultados de AGBRESA sobre la capacidad física (leído el 2026-10-26) | `kramer-2021-agbresa` |
| Wyle Integrated Science and Engineering | Sirek et al. 2014, Doppler de la arteria central de la retina en microgravedad | `sirek-2014-onsd-iss` |
| Weill Cornell Medicine | Garrett-Bakelman et al. 2019, el Twins Study; Overbey et al. 2024, SOMA | `garrett-bakelman-2019`, `overbey-2024-soma` |
| University of Pennsylvania Perelman School of Medicine | Jones et al. 2024, la tripulación civil de Inspiration4 | `jones-2024-inspiration4` |
| University of Waterloo | Hughson et al. 2012, Fraser et al. 2012 y Xu et al. 2013, regulación cardiovascular, frecuencia cardiaca y su variabilidad en la ISS | `hughson-2012-cardiovascular-iss`, `fraser-2012-heart-rate-iss`, `xu-2013-hrv-sleep-iss` |
| Universities Space Research Association | Norsk et al. 2015, presión arterial ambulatoria en vuelo | `norsk-2015-ambulatory-bp-iss` |
| Tokyo Women's Medical University | Otsuka et al. 2016, estructura temporal de la variabilidad de la frecuencia cardiaca | `otsuka-2016-hrv-time-structure` |
| Charité - Universitätsmedizin Berlin | Stahn et al. 2017, temperatura central en misiones largas | `stahn-2017-core-temperature` |
| Ottawa Hospital Research Institute | Trudel et al. 2022, hemólisis y anemia en vuelo | `trudel-2022-hemolysis` |
| University of Zurich | Thiel et al. 2017, macrófagos en microgravedad (células, no personas) | `thiel-2017-macrophage-microgravity` |
| European Space Agency (ESTEC) | Petit et al. 2019, eventos de sueño local en vigilia en la ISS | `petit-2019-local-sleep-iss` |

## Personas (por su trabajo publicado)

| Persona | Trabajo | Fuente |
|---|---|---|
| Kerry Lee | Citado en el artículo de NASA sobre el plan de protección radiológica de Orion como «radiation system manager for Orion» (cargo en 2016): «Our goal is to limit the risk of radiation exposure over an astronaut’s lifetime». EMMA toma del artículo el tiempo de montar el refugio y de permanecer en él | Ficha `nasa-orion-radiation-protection` (releída el 2026-10-21) |
| Jessica Vos | Citada en el mismo artículo como «deputy health and medical technical authority for Orion» (cargo en 2016), sobre la evaluación de los procedimientos de refugio con la tripulación | Ficha `nasa-orion-radiation-protection` |
| M. A. Garcia | Firma ese artículo (NASA, 22 de septiembre de 2016) | Ficha `nasa-orion-radiation-protection` |
| G. L. Douglas, S. T. Bell, P. G. Roma, T. Oswald, M. Young | Aceptabilidad de la comida en la ISS (2025): los extremos de la escala hedónica y la leyenda de su figura 1. El ISS Research Explorer de NASA da a Grace Douglas como investigadora principal de «Food Acceptability, Menu Fatigue, and Aversion in ISS Missions» (leído el 2026-10-21) | Ficha `douglas-2025-iss-food-acceptability`; [ISS Research Explorer, investigación 7562](https://www.nasa.gov/mission/station/research-explorer/investigation/?#id=7562) |
| G. D. Massa, R. M. Wheeler, G. W. Stutte, J. T. Richards, L. E. Spencer, M. E. Hummerick, G. L. Douglas, T. Sirmons | Verduras de hoja para la ISS (2015): los nueve rótulos numerados de la escala hedónica del panel de JSC | Ficha `massa-2015-leafy-greens-iss` |
| S. M. Ahmed | Alimentos de alta densidad para una estación orbital (1981): los rótulos 2 a 8 que sirve EMMA | Ficha `ahmed-1981-high-density-foods` |
| S. K. Mehta, M. L. Laudenslager, R. P. Stowe, B. E. Crucian, A. H. Feiveson, C. F. Sams, D. L. Pierson | Reactivación de virus latentes en la ISS (2017): cómo se recogieron en vuelo la orina y la saliva | Ficha `mehta-2017-latent-virus-iss` |
| J. G. Hardy, C. A. Theriot, T. Oswald, G. Clément | Spaceflight Standard Measures (2025): sangre en vuelo y orina solo antes y después | Ficha `hardy-2025-spaceflight-standard-measures` |
| H. N. Brawley, I. D. Juárez, D. Kurouski, S. R. Zwart, S. M. Smith | Raman SERS portátil para la sangre (2026): qué se hace hoy con la sangre tomada en la ISS | Ficha `brawley-2026-raman-sers` |
| T. M. Brown, G. C. Brainard, C. Cajochen, C. A. Czeisler et al. | Recomendaciones de luz en interiores (2022): la cifra para la persona, en Tierra; se enseña, no se evalúa | Ficha `brown-2022-melanopic-light` |
| S. W. Lockley, G. C. Brainard | Diseño del estudio Lighting Effects en la ISS (2016) | Ficha `lockley-brainard-2016-lighting-effects` |
| Z. A. Caddick, K. Gregory, E. E. Flynn-Evans | Recomendaciones de entorno de sueño para vehículos futuros (2016) | Ficha `caddick-2016-sleep-environment` |
| S. G. Hart | NASA-TLX, manual de papel y lápiz (1986) | Ficha `nasa-tlx-1986` |
| Kerstman et al. | Dolor de espalda de adaptación al espacio (2012) | Ficha `kerstman-2012` |
| N. Hayslip et al. | Radiación y microgravedad como envejecimiento acelerado (2026): estudio en hígado de ratón, con una comparación con sangre humana | Ficha `hayslip-2026` |
| M. Krihak, B. Burian, B. Schmitt, S. Shetye, T. Shaw | *Medical Data Architecture Prototype Development* (2020): huecos Med 07 y Med 10. La portada del PDF da una afiliación por autor (leída el 2026-10-31): Krihak, Universities Space Research Association, Mountain View, CA; Schmitt, KBR Inc, Mountain View, CA (la conversación de ideación decía Wyle); Burian, Shetye y Shaw, NASA Ames Research Center, Moffett Field, CA | Ficha `ntrs-20200000567` |
| Grace Douglas | Investigación 7562 del ISS Research Explorer (comida): «lead scientist for the Advanced Food Technology project at NASA’s Johnson Space Center in Houston» (cargo en 2021) y «principal investigator» de CHAPEA (la página no da fecha). No se junta con «Douglas GL», que firma los artículos y el póster de 2020 | Fichas `nasa-food-appeal-2021`, `nasa-chapea-program`, `ntrs-20200001311` |
| J. Law et al. | CO2 y cefalea en la ISS (2014) | Ficha `law-2014` |
| R. R. Scully et al. | CO2 agudo y cognición en sujetos tipo astronauta (2019) | Ficha `scully-2019` |
| M. Basner, D. Mollicone, D. F. Dinges | PVT-B de 3 minutos (2011) | Ficha `basner-2011-pvt-b` |
| J. Wasserthal et al. | TotalSegmentator (2023), visor 3D | `compliance/imaging-data-provenance.md` |
| David Dinges (la tarea lo escribe «Dinges, David») | Investigador principal de la tarea 1651 del Roadmap, la PVT en la ISS, según su página (2025). Firma también los dos artículos de la PVT como «Dinges DF»; la ruta no junta las dos grafías | Ficha `hrr-task-1651-pvt` |

Firmantes de las demás fichas, con la grafía y el orden de la cita (o de la firma de la página,
que copia la nota); el año es el de la ficha. Son quienes firman la fuente, no una afiliación:

| Firman | Trabajo | Ficha |
|---|---|---|
| Garrett-Bakelman FE et al. | *The NASA Twins Study: A multidimensional analysis of a year-long human spaceflight* (2019) | `garrett-bakelman-2019` |
| Overbey EG et al. | *The Space Omics and Medical Atlas (SOMA) and international astronaut biobank* (2024) | `overbey-2024-soma` |
| Jones CW et al. | *Molecular and physiological changes in the SpaceX Inspiration4 civilian crew* (2024) | `jones-2024-inspiration4` |
| Sirek AS, Garcia K, Foy M, Ebert D, Sargsyan A, Wu JH, Dulchavsky SA | *Doppler ultrasound of the central retinal artery in microgravity* (2014) | `sirek-2014-onsd-iss` |
| Marshall-Goebel K, Laurie SS, Alferova IV, Arbeille P, Auñón-Chancellor SM, Ebert DJ, et al. | *Assessment of Jugular Venous Blood Flow Stasis and Thrombosis During Spaceflight* (2019) | `marshall-goebel-2019-ijv` |
| Badhwar GD, Braby LA, Cucinotta FA, Atwell W | *Dose rate, dose-equivalent rate, and quality factor in SLS-1* (1992) | `badhwar-1992-sls1-tepc` |
| Pletcher DL, Krihak MK | *Exploration Medical Capability Clinical Decision Support System Architecture Recommendation* (2023) | `ntrs-20220017869` |
| Lindsey T, Shetye S, Shaw T | *Exploration Clinical Decision Support System: Medical Data Architecture* (2016) | `ntrs-20160012678` |
| Russell B, Krihak M, Shetye S, Martin K, Shaw T | *Clinical Decision Support - Concepts of Operation* (2021) | `ntrs-20205008731` |
| Hailey M, Urbina M, Reyes D, Antonsen E | *Interpretation of NASA-STD-3001 Levels of Care for Exploration Medical System Development* (2017) | `ntrs-20170004345` |
| Landon LB, Karasinski JA, Morissette LG, McTigue KR, Parisi ME, Wu S, Panontin TL | *Assessment of the State of Communication Delay Research in Preparation for Missions Beyond Low Earth Orbit* (2025) | `ntrs-20250003885` |
| Anderson A, Fenbert J, Easter B, Lehnhardt K | *Quantifying Medical Risk on a Long Duration Lunar Mission: A Demonstration of NASA’s IMPACT Tradespace Analysis Tool* (2024) | `ntrs-20240011063` |
| Robinson J, Myers J, Goodenow D, McIntyre L, Bhattacharyya K, Bellisario B, Leinweber L, Burba T, Gilkey K | *Introduction to Medical Extensible Dynamic Probabilistic Risk Assessment Tool (MEDPRAT)* (2018) | `ntrs-20180004678` |
| Leinweber L, McIntyre L, Goodenow D, Myers J | *MEDPRAT-SEL: Medical Resource Set Selector Searching High-Dimensionality Space* (2020) | `ntrs-20200000853` |
| McIntyre L, Leinweber L, Myers JG | *Dynamic Medical Risk Assessment Supported by Inference Networks* (2020) | `ntrs-20200000974` |
| Gasiewski C, McIntyre L, Leinweber L, Myers J, Prelich M, Munster D, Matar M, Lovell M | *Assessment of Model Outcomes between MEDPRAT and the IMM* (2023) | `ntrs-20230001121` |
| Boley L, Hilmers D, Kerstman E, Parmar P, Young M, Vega G, Arellano J | *Impact Real World System Validation* (2024) | `ntrs-20230013414` |
| Thompson W, Goodenow D, Hilmers D, Steller JG, Levin D, Anderson A, Stratton E, Nelson A, Kerstman E, Boley L, Lemery J, Lehnhardt K, Easter B | *Medical Risk Estimates and Clinical Capability Needs for A Long Duration Artemis Mission* (2024) | `ntrs-20230014551` |
| Prelich MT, Gasiewski CM, McIntyre L, Kadwa B, Arellano J, Myers JG Jr | *Assessment of Model Outcomes Between the Integrated Medical Model (IMM) and the Medical Extensible Dynamic Probabilistic Risk Assessment Tool (MEDPRAT)* (2025) | `ntrs-20240012058` |
| Anderson A, Nelson A, Nusbaum D, Vega G | *Artemis II Mission Medical Risk: A Comparison of the Impact and IMM Modeling Tools* (2025) | `ntrs-20240013005` |
| Nathan Cranford, Jennifer Turner | *Step 1, Earth: Analogs Help Advance Missions to Moon, Mars* (2021) y *Houston, Do You Copy? HERA Crew Navigates Communication Delays* (2022), páginas de NASA | `nasa-hrp-step1-analogs`, `nasa-hera-comm-delays` |
| Sumer Loggins | *Mission Success: HERA Crew Completes 45-Day Simulated Journey to Mars* (2024), página de NASA | `nasa-hera-45-day-2024` |
| Monica Edwards, Laurie Abadie | *One Small Step Without Ever Leaving Bed* (2019), página de NASA | `nasa-bed-rest-agbresa` |
| Lauren E. Low | *NASA Seeks Volunteers for New Yearlong Simulated Moon, Mars Mission* (2026), página de NASA | `nasa-mmea-announcement` |
| Mark A. Garcia | Dos entradas del blog de la estación (2026), además del artículo de Orion | `nasa-iss-blog-2026-07-08`, `nasa-iss-blog-2026-09-28` |
| Thiel CS, de Zélicourt D, Tauber S, et al.; Ullrich O | *Rapid adaptation to microgravity in mammalian macrophage cells* (2017) | `thiel-2017-macrophage-microgravity` |
| Petit G, Cebolla AM, Fattinger S, Petieau M, Summerer L, Cheron G, Huber R | *Local sleep-like events during wakefulness and their relationship to decreased alertness in astronauts on ISS* (2019) | `petit-2019-local-sleep-iss` |
| Basner M, Dinges DF | *Maximizing Sensitivity of the Psychomotor Vigilance Test (PVT) to Sleep Loss* (2011) | `basner-2011-pvt-metrics` |
| Smith SM, Heer MA, Zwart SR | *Nutritional Status Assessment (SMO 016E)* (2012) | `ntrs-20130000839` |
| Smith SM, Zwart SR | *Nutrition Issues for Space Exploration* (2006) | `ntrs-20060049121` |
| Smith SM, Wastney ME, O'Brien KO, Morukov BV, Larina IM, Abrams SA, Davis-Street JE, Oganov V, Shackelford LC | *Bone markers, calcium metabolism, and calcium kinetics during extended-duration space flight on the mir space station* (2005) | `smith-2005-bone-markers-mir` |
| Zwart SR, Launius RD, Coen GK, Morgan JL, Charles JB, Smith SM | *Body mass changes during long-duration spaceflight* (2014) | `zwart-2014-body-mass` |
| Crucian BE, Stowe RP, Mehta S, Uchakin P, Quiriarte H, Pierson D, Sams CF | *Immune System Dysregulation and Herpesvirus Reactivation Persist During Long-Duration Spaceflight* (2010) | `ntrs-20100040666` |
| Crucian B, Stowe RP, Mehta S, Quiriarte H, Pierson D, Sams C | *Alterations in adaptive immunity persist during long-duration spaceflight* (2015) | `crucian-2015-adaptive-immunity-iss` |
| Kunz H, Quiriarte H, Simpson RJ, Ploutz-Snyder R, McMonigal K, Sams C, Crucian B | *Alterations in hematologic indices during long-duration spaceflight* (2017) | `kunz-2017-hematologic-indices-iss` |
| Gutierrez C, Diak D, Bustos-Lopez S, Nelman-Gonzalez M, Mehta S, Smith SM, et al. | *Monitoring of Deep Space Physiology via Dry Saliva Sampling during Artemis Missions (Artemis Biomarkers) - Project Update* (2026) | `ntrs-20260002312` |
| Perusek GP, Calaway K, Miller R, Valentine R, Humbert S, Crucian B, Lewandowski B | *HemoCue ISS Tech Demo - Results and Lessons Learned* (2022) | `ntrs-20210026808` |
| Gilkey KM, Lewandowski BE, Schkurko CM, Miller RS, Valentine RW, Calaway KM, et al. | *ISS Technology Demonstrations for Future Spaceflight Medical Systems* (2024) | `ntrs-20240004905` |
| Hughson RL, Shoemaker JK, Blaber AP, Arbeille P, Greaves DK, Pereira-Junior PP, Xu D | *Cardiovascular regulation during long-duration spaceflights to the International Space Station* (2012) | `hughson-2012-cardiovascular-iss` |
| Xu D, Shoemaker JK, Blaber AP, Arbeille P, Fraser K, Hughson RL | *Reduced heart rate variability during sleep in long-duration spaceflight* (2013) | `xu-2013-hrv-sleep-iss` |
| Fraser KS, Greaves DK, Shoemaker JK, Blaber AP, Hughson RL | *Heart rate and daily physical activity with long-duration habitation of the International Space Station* (2012) | `fraser-2012-heart-rate-iss` |
| Norsk P, Asmar A, Damgaard M, Christensen NJ | *Fluid shifts, vasodilatation and ambulatory blood pressure reduction during long duration spaceflight* (2015) | `norsk-2015-ambulatory-bp-iss` |
| Otsuka K, Cornelissen G, Furukawa S, Kubo Y, Hayashi M, Shibata K, Mizuno K, Aiba T, Ohshima H, Mukai C | *Long-term exposure to space's microgravity alters the time structure of heart rate variability of astronauts* (2016) | `otsuka-2016-hrv-time-structure` |
| Stahn AC, Werner A, Opatz O, Maggioni MA, Steinach M, et al. | *Increased core body temperature in astronauts during long-duration space missions* (2017) | `stahn-2017-core-temperature` |
| Trudel G, Shahin N, Ramsay T, Laneuville O, Louati H | *Hemolysis contributes to anemia during long-duration space flight* (2022) | `trudel-2022-hemolysis` |
| Broyan JL Jr, Cibuzar BR | *Development of an In-line Urine Monitoring System for the International Space Station* (2009) | `ntrs-20090013860` |
| Feeback DL, Cibuzar BR, Milstead JR, Pietrzyk RA, Clarke MSF | *The International Space Station Urine Monitoring System (UMS)* (2009) | `ntrs-20090007818` |
| Rodriguez BR, Broyan JL Jr | *International Space Station Urine Monitoring System Functional Integration and Science Testing* (2011) | `ntrs-20110008547` |
| Flynn-Evans E, Gregory K, Arsintescu L, Whitmire A | *Evidence Report: Risk of Performance Decrements and Adverse Health Outcomes Resulting from Sleep Loss, Circadian Desynchronization, and Work Overload* (2016) | `hrp-sleep-evidence-report-2016` |
| Barger LK, Flynn-Evans EE, Kubey A, Walsh L, Ronda JM, Wang W, Wright KP Jr, Czeisler CA | *Prevalence of sleep deficiency and use of hypnotic drugs in astronauts before, during, and after spaceflight: an observational study* (2014) | `barger-2014-sleep-spaceflight` |

**Lo que no entra**, por no estar leído: el cargo de hoy de Kerry Lee y de Jessica Vos (el
artículo de Orion es de 2016 y da el de entonces); quién dirige TRISH o quién investiga en ella
(el cuerpo de la página de NASA leída no nombra a nadie); y las iniciales o la afiliación de un autor que su
ficha no escribe (por eso «Kerstman et al.»). La portada del HRP nombra a su director y a su
jefe científico, pero no producen nada de lo que EMMA usa y no entran. La investigación #id=975 del
ISS Research Explorer que daba la conversación sigue sin resolverse, y la 7562 no se pudo releer
en el Explorer: el 2026-10-31 la página sirvió la plantilla sin la investigación y su API respondió
404 en las rutas probadas; lo citado sale del artículo de NASA de 2021 y del póster de 2020. Ni los
nombres de los voluntarios de HERA que da la página de 2024: la nota de su ficha dice que EMMA no
los copia, y no son autores ni responsables de nada que EMMA use.
