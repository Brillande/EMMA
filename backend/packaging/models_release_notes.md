Paquete de modelos de EMMA: lo que el instalador no lleva (unos 33 GB).

| Pieza | Qué es | Licencia |
|---|---|---|
| `ollama` | Ollama 0.40.16 con `gemma4:e4b`, `gemma4:12b-it-qat` y `qwen3.5:9b` | Ollama MIT; modelos Apache-2.0 |
| `voice` | Whisper `base` con PyTorch (CPU) | MIT; PyTorch BSD-3 |
| `segmentation` | TotalSegmentator 2.18.0 con sus pesos | Apache-2.0; PyTorch BSD-3 |
| `tesseract` | Tesseract 5.4 con eng, spa y osd | Apache-2.0 |

## Con EMMA

«Acerca de EMMA» → «Modelos de IA» → «Descargar todo», o pieza a pieza. EMMA baja los trozos,
comprueba cada uno con su SHA-256 (`emma-modelos-partes.json`) y cada fichero con
`MANIFIESTO.json`, y lo instala en `%LOCALAPPDATA%\EMMA-modelos`. Se usa al volver a abrir EMMA.

## A mano

Cada pieza es un `tar` cortado en trozos de menos de 2 GB. Para rehacerla, en una carpeta con
`MANIFIESTO.json`, `instalar.cmd`, `instalar.ps1` y los trozos:

```
copy /b emma-modelos-ollama.tar.000 + emma-modelos-ollama.tar.001 + ... ollama.tar
tar -xf ollama.tar
```

(los trozos en orden; igual con `voice`, `segmentation` y `tesseract`). Después, `instalar.cmd`
comprueba cada fichero contra el manifiesto y lo copia a `%LOCALAPPDATA%\EMMA-modelos`.

No incluye la capa de des-identificación por NER del BSC: no hay licencia que permita
redistribuirla. Apoyo a la decisión: no diagnostica ni prescribe.
