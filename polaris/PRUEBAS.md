# Pruebas de Polaris en esta máquina

Generado por `backend/scripts/polaris_tests.py` en Windows 11, Python 3.12.10. No se edita a mano.

Son las pruebas del propio Polaris sobre lo copiado, sin tocar, con el adaptador de
EMMA, sin red y con el estado en un directorio temporal. Corren sobre una copia temporal
de `polaris/` (aquí `polaris\…` es esa copia, `<estado>` su estado, `<pasada>` la
carpeta de la pasada, `<tmp>` el temporal de las pruebas, `TMP`, dentro de ella y
borrado con ella, y `<tmp del sistema>` lo que, aun así, cayó en el del sistema), con
`python` y `python3` en el `PATH` apuntando al intérprete de
arriba. Un rojo no se arregla tocando la copia: se explica en la columna «Causa».

**115 verdes, 57 rojas y 19 saltadas** de 191.

## Por qué sale en rojo cada una

| Clase | Rojas | Qué significa |
|---|---|---|
| Windows | 16 | la prueba o la herramienta piden algo de macOS o de Unix que Windows no tiene |
| no copiado | 39 | falta un fichero del entorno de la autora que la copia no trae |
| decisión de EMMA | 1 | consecuencia de una decisión declarada en `docs/polaris-divergencias.md` |
| fuera de su casa | 1 | la prueba da por hecho que corre dentro del lazo de Polaris, en casa de su autora |
| pegamento de EMMA | 0 | fallo real del adaptador de EMMA: se arregla en `backend/app/polaris/` |
| **sin explicar** | 0 | roja sin causa en `CAUSES` (`backend/scripts/polaris_tests.py`): hay que leerla |

## Una a una

| Prueba | Resultado | Causa | Última línea |
|---|---|---|---|
| `test_aprobaciones_atascos.py` | rojo | no copiado: `tools/config/politica_aprobacion.json` | FileNotFoundError: [Errno 2] No such file or directory: 'polaris\\tools\\config\\politica_aprobacion.json' |
| `test_autopoda_residuo.py` | rojo | Windows: no hay `/bin/ps` ni `lsof`: `ramas` no puede leer dónde están las sesiones de Claude vivas, las cuenta como ilegibles y se niega a proponer podas (falla cerrado) | IndexError: list index out of range |
| `test_avisos_origen.py` | rojo | decisión de EMMA: EMMA registra solo Ollama (§1): con ese registro cambia qué fallo de cerebro se clasifica como ambiental y qué se avisa | test_avisos_origen: 7 ok, 7 fallos |
| `test_backup_latido.py` | rojo | no copiado: `tools/backup.sh` | FileNotFoundError: [Errno 2] No such file or directory: 'polaris\\tools\\backup.sh' |
| `test_bucles_colgados.py` | rojo | Windows: lanza un guion de shell (`zsh`) que no existe (WinError 2) | FileNotFoundError: [WinError 2] El sistema no puede encontrar el archivo especificado |
| `test_capacidades.py` | rojo | no copiado: el catálogo de agentes de la autora (`.claude/agents/`) | ❌ revisar fallos |
| `test_casa_estilo.py` | rojo | fuera de su casa: fuera de launchd (`XPC_SERVICE_NAME`/`BTP_LAZO` = `com.btp.*`) `salida` antepone el sello «origen: sesión local» a la alerta, que ya no es idéntica al texto crudo, y el aviso de «hay un borrador esperando» cuenta como entrega; 78 de 80 bien | ❌ revisar fallos |
| `test_caso_publico.py` | rojo | no copiado: la marca `.espejo-publico`: la copia sale del espejo público, donde el léxico vetado llega reescrito, y sin la marca la prueba no se salta el caso que ya no tiene qué cazar | FAILED (failures=1) |
| `test_cerebro_enlace.py` | rojo | Windows: crear un enlace simbólico pide un privilegio que el usuario no tiene (WinError 1314) | FAILED (errors=5) |
| `test_clinico_guard.py` | rojo | no copiado: los ganchos de Claude Code de la autora (`.claude/hooks/`): sin `clinico_guard.py` todo sale denegado | VEREDICTO: 25 FALLOS |
| `test_codigo_rojo_excepciones.py` | rojo | no copiado: `tools/config/` (excepciones de código rojo) | 🔴 CÓDIGO ROJO activado: Fred Hutch declara a {{TITULAR}} no elegible para la vacuna / alerta: espia (test) |
| `test_cola_turnos.py` | rojo | no copiado: `tools/btp_dispatcher.sh` | FAILED (errors=2) |
| `test_cost_guard.py` | rojo | Windows: `os.getuid` no existe (la sonda de `cost_guard` revienta al calcular su carpeta temporal) y los permisos `0600` no se pueden fijar; 84 de 86 bien | cost_guard: no pude escribir el registro de detalle (FileNotFoundError(2, 'No such file or directory')) |
| `test_decision_alto_riesgo.py` | rojo | no copiado: el catálogo de agentes de la autora (`.claude/agents/`): sin él `evaluar` da «panel INCOMPLETO» (3 aserciones). Las otras dos son de Windows: los permisos `0600` del acta y el informe de la propia prueba, escrito en modo texto (su huella no es la del texto); 83 de 88 bien | ❌ revisar fallos |
| `test_deid_eval.py` | rojo | no copiado: `.claude/hooks/zonas_clinicas.py`: sin él la «ventanilla clínica» no reconoce ninguna zona. Lo que EMMA usa de `deid_eval` (`cargar_brat`, `fugas`, la detección) pasa | FAILED (failures=3, skipped=2) |
| `test_deuda_cerrar_ejecuta.py` | rojo | no copiado: `tests/test_all.sh` | FileNotFoundError: [Errno 2] No such file or directory: 'polaris\\tests\\test_all.sh' |
| `test_deuda_disponibilidad.py` | rojo | no copiado: `tests/test_all.sh`, donde busca el enganche | ❌ revisar fallos |
| `test_dominios_con_dueno.py` | rojo | no copiado: `.claude/agents/` | FileNotFoundError: [WinError 3] El sistema no puede encontrar la ruta especificada: 'polaris\\.claude\\agents' |
| `test_escalado_inteligencia.py` | rojo | no copiado: `.claude/rules/normas-que-se-me-olvidan.md`: la prueba lee una norma de las reglas de Claude Code de la autora, no una herramienta | FileNotFoundError: [Errno 2] No such file or directory: 'polaris\\.claude\\rules\\normas-que-se-me-olvidan.md' |
| `test_f1_opus_supervision.py` | rojo | no copiado: los ganchos de Claude Code de la autora (`.claude/hooks/`) | - Agent/consejero-arquitectura en privileged debe PERMITIR |
| `test_fichas.py` | rojo | no copiado: el catálogo cuenta las piezas del repositorio entero de Polaris (más de 200, con `hooks/` y guiones); la copia trae solo las herramientas adoptadas y sus pruebas | FAILED (failures=9, errors=1) |
| `test_fuente_clinica.py` | rojo | Windows: crear un enlace simbólico pide un privilegio que el usuario no tiene (WinError 1314) | OSError: [WinError 1314] El cliente no dispone de un privilegio requerido: '<tmp>\\fuente_clinica_test_hhem3gow\\fuera.md' -> '<tmp>\\fuente_clinica_test_hhem3gow\\_PRIVADO_CLINICO\\enlace-afuera.md' |
| `test_git_mutex_merge_fallido.py` | rojo | no copiado: `tools/githooks/reference-transaction` | FileNotFoundError: [Errno 2] No such file or directory: 'polaris\\tools\\githooks\\reference-transaction' |
| `test_git_mutex_poda.py` | rojo | no copiado: `tools/btp_dispatcher.sh` | FileNotFoundError: [Errno 2] No such file or directory: 'polaris\\tools\\btp_dispatcher.sh' |
| `test_healthcheck_cpu.py` | rojo | Windows: `os.getloadavg` no existe: `_cpu_ahora` no puede tomar la medida real | FAILED (failures=1) |
| `test_healthcheck_halt_inactividad.py` | rojo | Windows: `launchctl` es de macOS: `_check_roster_daemons` sale con «launchctl ilegible» antes de calcular la inactividad; 10 de 13 bien | ✓ telegram bien: sin alerta |
| `test_healthcheck_syspath.py` | rojo | no copiado: `tools/correo_smtp.py` y `tools/postdicom.py` | FAILED (failures=1, errors=1) |
| `test_identidad_paciente.py` | rojo | no copiado: `.claude/hooks/zonas_clinicas.py` (la ventanilla clínica); 24 de 25 bien | ❌ revisar |
| `test_inventario_uso.py` | rojo | no copiado: `tools/onco.py`, cuyo uso mide uno de sus casos (quedó fuera: abre una URL), y `tools/launchd/com.btp.inventario-uso.plist`; 11 de 13 bien | FAILED (errors=2) |
| `test_inventario_viejas_modelos.py` | rojo | Windows: `inventario` busca la fecha de cada pieza con la clave `tools\vieja.py` (`os.path.join`) y `git log --name-only` la da como `tools/vieja.py`: toda fecha sale «?» y `--viejas` no lista ninguna; 9 de 10 bien | FAILED (failures=1) |
| `test_kickstart_bootstrap.py` | rojo | Windows: `os.getuid` no existe | AttributeError: module 'os' has no attribute 'getuid'. Did you mean: 'getpid'? |
| `test_laminillas_jaulas_secretos.py` | rojo | Windows: el módulo `pwd` es de Unix | ModuleNotFoundError: No module named 'pwd' |
| `test_lector_clinico_binario.py` | rojo | Windows: crear un enlace simbólico pide un privilegio que el usuario no tiene (WinError 1314) | OSError: [WinError 1314] El cliente no dispone de un privilegio requerido: '<tmp>\\btp-ventanilla-4x4ey67r\\fuera\\por-el-enlace.pdf' -> '<tmp>\\btp-ventanilla-4x4ey67r\\_PRIVADO_CLINICO\\enlace-bland |
| `test_lentes.py` | rojo | no copiado: los comités de la autora (`.claude/agents/`) | FAILED (failures=1) |
| `test_llavero_mudo.py` | rojo | no copiado: `tools/hoy_compose.sh` | FAILED (failures=4, errors=1) |
| `test_muro_fase0.py` | rojo | Windows: crear un enlace simbólico pide un privilegio que el usuario no tiene (WinError 1314) | OSError: [WinError 1314] El cliente no dispone de un privilegio requerido: '<estado>\\home/claudecode\\tools\\state\\healthcheck' -> '<tmp>\\tmpqg6xyk9i\\z' |
| `test_muro_secreto_stdout.py` | rojo | no copiado: los ganchos de Claude Code de la autora (`.claude/hooks/`) | ❌ revisar |
| `test_nonce_a4_blindado.py` | rojo | no copiado: `.claude/hooks/salida_guard.py`: sin el gancho fallan los cuatro «deja pasar» | test_nonce_a4_blindado: 4 fallos |
| `test_presencia_cc.py` | rojo | no copiado: `.claude/settings.json` y los ganchos de Claude Code de la autora (`.claude/hooks/`); además, un enlace simbólico | FAILED (failures=3, errors=2, skipped=1) |
| `test_prueba_entregable.py` | rojo | no copiado: `.claude/hooks/muro_guard.py` | FAILED (errors=1) |
| `test_ramas_borrador.py` | rojo | Windows: no hay `/bin/ps` ni `lsof`: `ramas` no puede leer dónde están las sesiones de Claude vivas, las cuenta como ilegibles y se niega a proponer podas (falla cerrado) | ❌ revisar fallos |
| `test_ramas_detached.py` | rojo | Windows: no hay `/bin/ps` ni `lsof`: `ramas` no puede leer dónde están las sesiones de Claude vivas, las cuenta como ilegibles y se niega a proponer podas (falla cerrado) | FALLOS: un worktree detached ya fusionado SÍ se propone |
| `test_rc_turnos_agotados.py` | rojo | no copiado: `tools/btp_dispatcher.sh` | FAILED (errors=3) |
| `test_rebuild_agents.py` | rojo | no copiado: `tools/templates/agente_boilerplate.md`: la plantilla que `rebuild_agents` lee nada más importarlo la prueba | FileNotFoundError: [Errno 2] No such file or directory: 'polaris\\tools\\templates\\agente_boilerplate.md' |
| `test_regla_en_accion.py` | rojo | no copiado: los ganchos de Claude Code de la autora (`.claude/hooks/`) | ❌ 41 fallo(s): git push recuerda que el repo no se sube; git push además pide confirmación; editar el hero recuerda el gate de copy; el hero se recuerda pero NO se bloquea; ruta clínica recuerda la ve |
| `test_replay_gate.py` | rojo | no copiado: `.claude/hooks/gate_salida.py` | FAILED (errors=2) |
| `test_replay_guard_json.py` | rojo | no copiado: `.claude/hooks/salida_guard.py` | replay_guard.HookRoto: polaris\.claude\hooks\salida_guard.py no se pudo ejecutar: C:\Users\tidus\AppData\Local\Programs\Python\Python312\python.exe: can't open file 'polaris\\.claude\\hooks\\salida_gu |
| `test_replay_hook_roto.py` | rojo | no copiado: `.claude/hooks/clinico_guard.py`: sin el gancho real `comprueba` lo rechaza e `iniciar` sale con rc 2 sin escribir `rodaje.json`, que la prueba abre después; 3 de 5 bien antes de caer | FileNotFoundError: [Errno 2] No such file or directory: '<tmp>\\tmphh6eomr7\\rodaje.json' |
| `test_rodaje_hook_fijo.py` | rojo | Windows: `rodaje_muro` pide el gancho al commit con `git show <sha>:.claude\hooks\g.py` (`os.path.relpath`) y git solo entiende `/`: da rc 128, la comparación se salta y el árbol reciclado pasa por bueno; 12 de 13 bien | test_rodaje_hook_fijo: 1 fallos |
| `test_rodaje_utc.py` | rojo | no copiado: `.claude/hooks/clinico_guard.py`: `iniciar` sale con rc 2 sin escribir `rodaje.json` | FileNotFoundError: [Errno 2] No such file or directory: '<tmp>\\rodaje-test-ze_96a31\\rodaje.json' |
| `test_saldo_aprende.py` | rojo | no copiado: `tools/run_agent.sh` | FileNotFoundError: [Errno 2] No such file or directory: 'polaris\\tools\\run_agent.sh' |
| `test_seguimiento_objetivo_ned.py` | rojo | no copiado: `.claude/agents/asistente.md` | FileNotFoundError: [Errno 2] No such file or directory: 'polaris\\.claude\\agents\\asistente.md' |
| `test_tools_no_sombrea_stdlib.py` | rojo | no copiado: `tools/correo_smtp.py` | FAILED (failures=1) |
| `test_visor3d.py` | rojo | no copiado: `.claude/hooks/zonas_clinicas.py` | FileNotFoundError: [Errno 2] No such file or directory: 'polaris\\.claude\\hooks\\zonas_clinicas.py' |
| `test_visor3d_cateter.py` | rojo | no copiado: `.claude/hooks/zonas_clinicas.py` | FileNotFoundError: [Errno 2] No such file or directory: 'polaris\\.claude\\hooks\\zonas_clinicas.py' |
| `test_visor3d_colab.py` | rojo | Windows: una ruta de Windows con `\U` dentro de una cadena de código generado | SyntaxError: (unicode error) 'unicodeescape' codec can't decode bytes in position 2-3: truncated \UXXXXXXXX escape |
| `test_web_lint.py` | rojo | no copiado: la marca `.espejo-publico` (como `test_caso_publico`): «ingeniera» es el léxico de marca ya reescrito y no hay qué cazar | FAILED (failures=1, skipped=5) |
| `test_audit_constelacion.py` | saltada |  | y la fuente de verdad (`00_FUENTE-DE-VERDAD/`), que no se publica |
| `test_borde.py` | saltada |  | y `tools/identidad.local.json`: la lista de marcas del titular que el detector busca |
| `test_centralita_cerebros.py` | saltada |  | ⏭️  SKIP: necesita `tools/nombres.local.json`: los nombres de terceros que se redactan |
| `test_contexto_caso.py` | saltada |  | y `tools/identidad.local.json`: la lista de marcas del titular que el detector busca |
| `test_contrato_asiento.py` | saltada |  | ⏭️  SKIP: necesita el estado vivo del lazo (`tools/state/`), que no se publica |
| `test_correo_cuenta_principal.py` | saltada |  | test_correo_cuenta_principal: sin plist (polaris\tools\launchd\com.btp.correo-imap.plist) — SALTADO |
| `test_cumbre_integridad.py` | saltada |  | test_cumbre_integridad: sin estado vivo (<estado>\tools\state\cumbre.json) — SALTADO |
| `test_deid.py` | saltada |  | y `tools/nombres.local.json`: los nombres de terceros que se redactan |
| `test_evals.py` | saltada |  | y `tools/identidad.local.json`: la lista de marcas del titular que el detector busca |
| `test_guarda_memoria.py` | saltada |  | SKIP: la medida de footprint es de `top` de macOS |
| `test_ia.py` | saltada |  | y `tools/identidad.local.json`: la lista de marcas del titular que el detector busca |
| `test_investigacion_fuga.py` | saltada |  | y `tools/perfil.local.json`: las dianas y cifras del caso |
| `test_memoria_radar.py` | saltada |  | ⏭️  SKIP: necesita `tools/perfil.local.json`: las dianas y cifras del caso |
| `test_normas_registro.py` | saltada |  | ⏭️  SKIP: necesita `tools/nombres.local.json`: los nombres de terceros que se redactan |
| `test_secretos_largos.py` | saltada |  | SKIP: el Llavero es de macOS |
| `test_seguimiento.py` | saltada |  | ⏭️  SKIP: necesita `tools/nombres.local.json`: los nombres de terceros que se redactan |
| `test_terminos_carril.py` | saltada |  | ⏭️  SKIP: necesita `tools/identidad.local.json`: la lista de marcas del titular que el detector busca |
| `test_triage_route_enrutado.py` | saltada |  | y `tools/identidad.local.json`: la lista de marcas del titular que el detector busca |
| `test_visor3d_cuelgue.py` | saltada |  | SKIP: `ps -o time=` y `sample` son de macOS |
| `test_anticipa.py` | verde |  | ✅ ANTICIPA EN VERDE |
| `test_atribucion.py` | verde |  | ✅ ATRIBUCIÓN EN VERDE (1 crédito(s), 0 anónimas) |
| `test_audit_agentes_daemon.py` | verde |  | OK (skipped=1) |
| `test_audit_comites_uso.py` | verde |  | OK |
| `test_avisos_nueva_tarea.py` | verde |  | ⚠️ seguimiento: hilo nuevo SIN objetivo_ned (origen=whatsapp): «E». Complétalo; `seguimiento.py sin-ned` lista los que faltan. |
| `test_biomarcadores_fecha_extraccion.py` | verde |  | OK |
| `test_biomarcadores_ggt_alias.py` | verde |  | OK |
| `test_biomarcadores_hormonas.py` | verde |  | OK |
| `test_biomarcadores_muestras.py` | verde |  | OK |
| `test_biomarcadores_vhio.py` | verde |  | OK |
| `test_caja.py` | verde |  | OK |
| `test_canarios.py` | verde |  | OK |
| `test_cascada_clinica.py` | verde |  | ⚠️ seguimiento: hilo nuevo SIN objetivo_ned (origen=cascada-clinica): «Re-validar: Radar de literatura (dianas, rutas) (tu historial cambió)». Complétalo; `seguimiento.py sin-ned` lista los que faltan |
| `test_ciclo_agentes.py` | verde |  | OK |
| `test_clave_deuda_una_forma.py` | verde |  | ✅ clave de deuda: una sola forma, y cada job exige una prueba que se puede cumplir |
| `test_codigo_rojo.py` | verde |  | 🔴 CÓDIGO ROJO activado: la biopsia se borró por un fallo mío / alerta: stub (motivo nuevo) |
| `test_codigo_rojo_repeticion.py` | verde |  | 🔴 CÓDIGO ROJO activado: Barrido de seguridad de la constelación en ROJO (BRECHA) / alerta: alerta no repetida: ya avisado hace 0.0 h y el HALT sigue puesto (repetición nº 3) (ya avisado hace 0.0 h y e |
| `test_cola.py` | verde |  | ✅ COLA EN VERDE |
| `test_cola_diario.py` | verde |  | OK |
| `test_cola_ruido.py` | verde |  | OK: el aviso de caídos separa esta semana del cementerio |
| `test_correo_imap.py` | verde |  | ✅ CORREO_IMAP EN VERDE |
| `test_cosecha_checklists.py` | verde |  | ✅ COSECHA EN VERDE |
| `test_cosecha_correcciones.py` | verde |  | ✅ COSECHA-CORRECCIONES EN VERDE |
| `test_cosecha_entregables.py` | verde |  | ✅ COSECHA_ENTREGABLES EN VERDE |
| `test_cosecha_hilos.py` | verde |  | ✅ COSECHA_HILOS EN VERDE |
| `test_cosecha_whatsapp.py` | verde |  | ⛔ Gate cerrado: activa BTP_WA_COSECHA_OK=1 o crea .claude\hooks\.wa_cosecha_on para permitir --stage. |
| `test_cronica.py` | verde |  | ✅ CRÓNICA EN VERDE |
| `test_cumbre.py` | verde |  | cumbre: aviso, aqui_estamos='biopsia' está hecho (cerrado) → uso el primer nodo accionable |
| `test_dedup_hilos.py` | verde |  | ⚠️ seguimiento: hilo nuevo SIN objetivo_ned (origen=manual): «Call con Bernardo Cordovez Kernis circulo de Sid mie 1-jul 19:00 {{CON». Complétalo; `seguimiento.py sin-ned` lista los que faltan. |
| `test_deid_diccionario.py` | verde |  | OK |
| `test_deid_ner.py` | verde |  | OK (skipped=2) |
| `test_deid_procedencia.py` | verde |  | RESULTADO deid procedencia: 12 OK, 0 fallos |
| `test_deuda_duplicadas.py` | verde |  | test_deuda_duplicadas: 5 casos, 0 fallos |
| `test_dosier_invariantes.py` | verde |  | ✅ L1 EN VERDE |
| `test_elegibilidad_ensayos.py` | verde |  | ✅ L3 EN VERDE |
| `test_enruta.py` | verde |  | OK |
| `test_errores.py` | verde |  | TEST ERRORES EN VERDE |
| `test_esqueleto_niveles.py` | verde |  | AVISO: 3 nivel(es) caen fuera del hueso (vertebrae_T3, vertebrae_T4, vertebrae_T5) — no se reparten |
| `test_esqueleto_referencia.py` | verde |  | ✅ test_esqueleto_referencia: 0 fallo(s) |
| `test_esquema_estado.py` | verde |  | OK (skipped=1) |
| `test_estado_rutina.py` | verde |  | OK |
| `test_etiquetar_hilos.py` | verde |  | OK |
| `test_eval_triage_residuo.py` | verde |  | test_eval_triage_residuo: 11 OK, 0 fallos |
| `test_evals_honestidad.py` | verde |  | test_evals_honestidad: 12 OK, 0 fallos |
| `test_freno_criticidad.py` | verde |  | ✅ FRENO EN VERDE |
| `test_frescura_dosier.py` | verde |  | ✅ FRESCURA DEL DOSIER EN VERDE |
| `test_git_mutex_freno_base.py` | verde |  | Resultado: 27 OK · 0 FAIL |
| `test_git_mutex_rama_ajena.py` | verde |  | git_mutex: NO fusiono a casa base: la rama claude/a es de otra sesión viva (pid 101, en /casa/.claude/worktrees/a). Fusionar a base es gate de {{TITULAR}}, y su OK se da en la sesión dueña de la rama  |
| `test_guardian_evals.py` | verde |  | ✅ L9 EN VERDE |
| `test_healthcheck_acuse.py` | verde |  | ts = (datetime.datetime.utcnow() - datetime.timedelta(hours=edad_h)).strftime("%Y-%m-%dT%H:%M:%SZ") |
| `test_healthcheck_alerta_str.py` | verde |  | OK |
| `test_healthcheck_cerebro.py` | verde |  | OK |
| `test_healthcheck_ci_publico.py` | verde |  | RESULTADO healthcheck ci público: 20 OK, 0 fallos |
| `test_healthcheck_deadman.py` | verde |  | test_healthcheck_deadman: 15 OK, 0 fallos |
| `test_healthcheck_drift_plists.py` | verde |  | OK |
| `test_healthcheck_drive.py` | verde |  | test_healthcheck_drive: 10 OK, 0 fallos |
| `test_healthcheck_llms.py` | verde |  | OK |
| `test_healthcheck_state_aislado.py` | verde |  | test_healthcheck_state_aislado: 4 OK, 0 fallos |
| `test_historial_trazador.py` | verde |  | ✓ test_historial_trazador |
| `test_honestidad_lint.py` | verde |  | HONESTIDAD-LINT EN VERDE |
| `test_honestidad_lint_repo.py` | verde |  | test_honestidad_lint_repo: 14 OK, 0 fallos |
| `test_hoy_ruta_unica.py` | verde |  | OK |
| `test_identidad_tabla.py` | verde |  | test_identidad_tabla: 8/8 OK |
| `test_incongruencias_caso.py` | verde |  | test_incongruencias_caso: OK |
| `test_jobs_caidos.py` | verde |  | ✅ JOBS CAÍDOS VIGILADOS |
| `test_kb_fts5.py` | verde |  | incluida la fila mal-etiquetada; scope=all sí la recupera. |
| `test_kb_hibrido.py` | verde |  | ✅ VERDE (solo fallback FTS5 — sin capa vectorial en este intérprete) |
| `test_kb_lock.py` | verde |  | OK |
| `test_kb_pdf_avisos.py` | verde |  | ✅ KB PDF AVISOS EN VERDE |
| `test_kpi_ned.py` | verde |  | OK |
| `test_lock_dueno.py` | verde |  | test_lock_dueno: 9 OK, 0 fallos |
| `test_memoria_sistema.py` | verde |  | ✅ sistema de memoria OK |
| `test_mutantes.py` | verde |  | ✅ MUTANTES: la herramienta distingue 5/5 |
| `test_normas_gracia.py` | verde |  | test_normas_gracia: 8/8 OK |
| `test_nvidia_tope.py` | verde |  | OK |
| `test_ocr_layout.py` | verde |  | ✅ OCR LAYOUT EN VERDE |
| `test_paso_consolidacion.py` | verde |  | ✅ CONSOLIDADOR EN VERDE |
| `test_pendientes.py` | verde |  | ✅ PENDIENTES EN VERDE |
| `test_perfil_clinico_al_dia.py` | verde |  | ✅ PERFIL CLÍNICO AL DÍA |
| `test_persecucion.py` | verde |  | ✅ PERSECUCIÓN EN VERDE |
| `test_portero_ruido.py` | verde |  | ✅ portero de ruido OK |
| `test_ramas_conflictos.py` | verde |  | OK |
| `test_ramas_fusionar.py` | verde |  | ✅ FUSIÓN SIN TOCAR EL ÁRBOL — EN VERDE |
| `test_readme_modelos.py` | verde |  | OK |
| `test_reap_vivo.py` | verde |  | test_reap_vivo: 7 OK, 0 fallos |
| `test_recall_memoria.py` | verde |  | ℹ️  Sin carpeta de memorias: nada que evaluar (ok en una máquina limpia). |
| `test_recover.py` | verde |  | TEST RECOVER EN VERDE |
| `test_reescribe_consulta.py` | verde |  | OK |
| `test_responder_datos.py` | verde |  | ✅ RESPONDEDOR AGNÓSTICO EN VERDE |
| `test_rodaje_casa_base.py` | verde |  | test_rodaje_casa_base: 4/4 OK |
| `test_rotar_logs.py` | verde |  | TEST ROTAR_LOGS EN VERDE |
| `test_saldo_api.py` | verde |  | OK |
| `test_saldo_prepago.py` | verde |  | test_saldo_prepago: 29 OK, 0 fallos |
| `test_salida.py` | verde |  | ✅ CHOKE-POINT EN VERDE |
| `test_salida_reintento.py` | verde |  | ✅ REINTENTO DE SALIDA EN VERDE |
| `test_salud_reconciliar.py` | verde |  | OK |
| `test_seguimiento_carrera.py` | verde |  | ⚠️ seguimiento: hilo nuevo SIN objetivo_ned (origen=manual): «anidado». Complétalo; `seguimiento.py sin-ned` lista los que faltan. |
| `test_sonda_silencio.py` | verde |  | OK: la sonda está enganchada al healthcheck |
| `test_soporte_cita.py` | verde |  | OK |
| `test_soporte_cita_juez.py` | verde |  | OK |
| `test_sys_path_limpio.py` | verde |  | test_sys_path_limpio: 4 OK, 0 fallos |
| `test_tier_evidencia.py` | verde |  | RESULTADO tier_evidencia: 23 OK, 0 fallos |
| `test_triage.py` | verde |  | ⚠️ seguimiento: hilo nuevo SIN objetivo_ned (origen=chat): «Revisar el correo mañana». Complétalo; `seguimiento.py sin-ned` lista los que faltan. |
| `test_triage_route_correo.py` | verde |  | ✅ TRIAGE_ROUTE_CORREO EN VERDE (21 ok / 0 fallos) |
| `test_verifica_citas.py` | verde |  | ✅ FILTRO DE CITAS EN VERDE |
| `test_verifica_citas_datacite.py` | verde |  | ✅ DATACITE Y LIMPIEZA EN VERDE |
| `test_verifica_citas_estados.py` | verde |  | OK |
| `test_vigia_latidos.py` | verde |  | OK: el vigía distingue «no veo» de «está muerto» (worktree, directorio vacío, cascada) |
| `test_visor3d_carga.py` | verde |  | OK: carga tumoral hepática (fracción, nulos, cableado en el resumen) |
| `test_visor3d_ficha.py` | verde |  | OK test_visor3d_ficha |
| `test_visor3d_losa.py` | verde |  | ✅ visor3d losa: fantoma OK |
| `test_visor3d_malla_recorte.py` | verde |  | ✅ recorte a la caja: malla idéntica y memoria acotada |
| `test_visor3d_marcas.py` | verde |  | VERDE |
| `test_visor3d_mascara_union.py` | verde |  | ✅ máscara del hígado: unión por defecto, la punta queda dentro, el islote fuera |
| `test_visor3d_modelo_port.py` | verde |  | TODO VERDE |
