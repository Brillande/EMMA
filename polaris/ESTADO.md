# Estado de la copia de Polaris en esta máquina

Generado por `backend/scripts/polaris_estado.py` en Windows 11, Python 3.12.10. No se edita a mano.

**130 de 134 herramientas cargan.** Las que no, y por qué:

| Herramienta | Motivo |
|---|---|
| `laminillas_jaulas` | ModuleNotFoundError: No module named 'pwd' |
| `laminillas_ventanilla` | ModuleNotFoundError: No module named 'pwd' |

**No se importan para hacer este inventario: 2.** Hacen algo solo con importarse (la lista es
`NOT_IMPORTED`, en `backend/app/polaris/__init__.py`), así que no se sabe si cargarían:

| Herramienta | Por qué no se importa |
|---|---|
| `rodaje_muro` | al importarse lanza git para preguntar por la rama de la carpeta que contiene la copia |
| `transcribe_audios` | es un guion sin función de entrada: importarlo es ejecutarlo entero; EMMA lo lanza como programa aparte |

Las herramientas no se modifican (la copia es literal): lo que falta aquí se instala o
se decide aparte (`docs/polaris-divergencias.md`). Lo que a la copia le falta en Windows
lo pone EMMA desde fuera de ella, en `backend/app/polaris/compat/`:

- `backend/app/polaris/compat/fcntl.py`: `fcntl.flock` para Windows, solo para el código de Polaris copiado tal cual.
- `backend/app/polaris/compat/memguard.py`: `guarda_memoria` de Polaris en Windows: sus mediciones de macOS, con la API de Windows.
- `backend/app/polaris/compat/resource.py`: `resource.getrusage` para Windows, solo para las pruebas de Polaris copiadas tal cual.
- `backend/app/polaris/compat/sitecustomize.py`: Activa el pegamento de `_lock` en los procesos de las pruebas de Polaris, en Windows.
- `backend/app/polaris/compat/winlock.py`: El candado entre procesos de Polaris (`_lock.py`) en Windows: una sonda de proceso de verdad.

Cargan: `_casa`, `_lexico_publico`, `_lock`, `_net`, `_secrets`, `anticipa`, `aprobaciones`, `atascos`, `audit_agentes`, `audit_comites`, `audit_constelacion`, `avisos_flush`, `bandeja`, `bench_determinista`, `biomarcadores`, `borde`, `bucles_colgados`, `caja`, `canarios`, `capacidades`, `carril_gratis`, `cascada_clinica`, `cascada_mapa`, `caso_publico`, `ciclo_agentes`, `codigo_rojo`, `cola`, `contexto_caso`, `continuity`, `correo`, `correo_imap`, `cosecha_checklists`, `cosecha_correcciones`, `cosecha_entregables`, `cosecha_hilos`, `cosecha_whatsapp`, `cost_guard`, `coste`, `cotejo_invariante`, `cronica`, `cumbre`, `decide_peticion`, `decision_alto_riesgo`, `dedup_hilos`, `deid`, `deid_eval`, `deid_ner`, `deuda`, `dosier_invariantes`, `elegibilidad_ensayos`, `enruta`, `enruta_comite`, `errores`, `esqueleto_referencia`, `esquema_estado`, `estado_actual`, `estado_rutina`, `etiquetar_hilos`, `eval_reescritura`, `eval_triage`, `evals`, `fichas`, `frescura_dosier`, `fuente_clinica`, `fugu`, `gasto`, `git_mutex`, `guarda_memoria`, `guardian_evals`, `healthcheck`, `historial`, `honestidad_lint`, `ia`, `ia_health`, `identidad_paciente`, `incongruencias_caso`, `indice_memoria`, `instagram`, `inventario`, `kb`, `kb_embed`, `kpi_ned`, `laminillas_sello`, `lector_clinico`, `lentes`, `local`, `md_to_pdf_pro`, `memoria_radar`, `minador_sesiones`, `mutantes`, `normas`, `nvidia`, `observabilidad`, `ocr_informes`, `panel`, `paso_consolidacion`, `pendientes`, `persecucion`, `polaris_estado`, `promesas_caso`, `prueba_entregable`, `radar_personas`, `ramas`, `rebuild_agents`, `reconciliar_estado`, `reescribe_consulta`, `reglas_repetidas`, `replay_gate`, `replay_guard`, `responder_con_datos`, `rituales`, `rotar_logs`, `salida`, `salud`, `salud_memoria`, `score_local`, `seguimiento`, `sintomas`, `sonda_silencio`, `soporte_cita`, `tier_evidencia`, `triage_route`, `triage_route_correo`, `triage_tareas`, `usage_coste`, `verifica_citas`, `vigia_sesiones`, `visor3d`, `visor3d_superpone_focos`, `web_lint`.
