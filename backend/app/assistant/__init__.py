"""El cerebro del asistente de voz «EMMA»: entender, contestar y proponer; nunca firmar.

Por qué existe: el usuario pidió (2026-11-03) una EMMA «tipo Jarvis» para toda la interfaz, manos
libres, con iniciativa y con memoria de la conversación, sobre un modelo local. Con guantes, con
una mano ocupada o con dolor, pedir «abre radiación» o «¿cómo estoy?» cuesta menos que buscar el
botón. Lo difícil no es que un modelo hable: es que lo que dice no invente, no recete y no firme.

Cómo se reparte (cada pieza explica su porqué en su módulo):

  * `catalog.py`: la lista cerrada de lo que se puede pedir (`data/assistant_intents.json`), con
    el esquema de los argumentos y las palabras clave para cuando no hay modelo.
  * `context.py`: lo único que ve el modelo, compuesto con el texto que el backend ya da a esa
    consola; en Tierra, con su corte de retardo.
  * `guards.py`: las cuatro barreras de cada respuesta del modelo (lenguaje, cifras, no recetar
    y esquema). Si una falla se dice el texto del backend tal cual.
  * `proposals.py`: las escrituras solo se proponen, con el cuerpo exacto de la ruta del
    formulario; la firma es de la interfaz, por esa ruta, tras la confirmación de la persona.
  * `turn.py`: el turno entero, que sale igual sin modelo.

CLASE C, SEGREGADO (invariante 6; `compliance/software-safety-classification.md` §2.2). Lo que
redacta el modelo es un texto sin validar que se oye: no entra en el ledger, ni en el análisis,
ni en una alerta, ni en una recomendación. El asistente no escribe en ningún sitio; lo que llega
al registro lo firma una persona por la ruta de siempre. Lo comprueban las pruebas de
`tests/test_assistant.py`.

EL HISTORIAL NO SE GUARDA. Vive en la memoria de la consola (los últimos ocho turnos) y viaja con
cada petición; el backend lo usa para ese turno y lo olvida.

Modelo: `Settings.assistant_model`, solo en loopback (el cliente de `app/interpret/llm.py`), a
temperatura 0, sin razonamiento previo y con salida JSON.
"""
