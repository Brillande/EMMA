# Demo en directo: el portátil, el instalador y el aviso de Windows

Nota del 2026-11-05 para el día del evento. La escribió un asistente de código; el equipo la
comprueba en el ensayo del día 13 sobre el portátil de la demo.

## Por qué sale el aviso

El instalador de EMMA (`desktop/release/EMMA Setup <versión>.exe`) no va firmado con un certificado
de firma de código: cuesta dinero y lleva días de trámite, y no hace falta para un prototipo. Por
eso, la primera vez que se abre en un equipo, Windows Defender SmartScreen lo para con una pantalla
azul que dice **«Windows protegió su PC»**. No es un fallo del instalador; es lo que hace Windows con
cualquier programa nuevo sin firmar.

## Cómo seguir

1. En la pantalla azul, pulsar **«Más información»** (es un enlace pequeño, debajo del texto).
2. Aparece el nombre del programa y «Editor: Editor desconocido». Pulsar **«Ejecutar de todas
   formas»**.
3. El instalador sigue con normalidad. Si Windows pide permiso de administrador, aceptar.

Delante del jurado, si sale, se dice tal cual: «El instalador no está firmado porque es un
prototipo; Windows avisa con cualquier programa sin firmar». No hay que esconderlo.

## Mejor: que no salga delante del jurado

- **Instalarlo antes**, el día 13, en el portátil de la demo y abrirlo una vez: el aviso solo sale
  la primera vez que se ejecuta ese fichero en ese equipo.
- Hacerlo **sin red**, como en la demo (modo avión), y comprobar que arranca, que carga el escenario
  y que el asistente contesta.
- Tener a mano **el vídeo** como plan B por si algo falla en directo (`guion-video.md`).
- Si se recompila el instalador después de instalarlo, el fichero nuevo vuelve a ser «nuevo» para
  SmartScreen: el aviso puede volver a salir. Por eso se instala la versión etiquetada `demo-v1` y
  no se recompila después.

## Lo que no se hace

- No se desactiva SmartScreen ni Windows Defender en el portátil: es tocar la seguridad del equipo
  para salir del paso, y no hace falta.
- No se dice que EMMA «está certificado» ni «verificado por Microsoft» (invariante 6).
