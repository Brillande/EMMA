"""TotalSegmentator con cuDNN apagado, para la prueba de fiabilidad (`fiabilidad_segmentacion.py`).

Estuvo en `backend/app/volumes/totalseg_launch.py` del 2026-11-11 hasta que se vio que la causa era el
overclock de MSI Center; de serie, EMMA vuelve a lanzar el ejecutable con cuDNN. Se guarda aquí para
repetir la comparación.

Por qué existe: en el portátil de desarrollo (RTX 4070 Laptop, torch 2.11.0+cu128, cuDNN 9.19,
nnunetv2 2.8.1, TotalSegmentator 2.18.0) la segmentación en GPU fallaba SIEMPRE con «CUDA error:
misaligned address» o «illegal memory access» en una `Conv3d` del decodificador de nnU-Net, y la
única salida era la CPU (preset de hígado: 238 s). Con cuDNN apagado, la tarea `total` fue bien 5
de 5 veces; con solo `cudnn.benchmark = False`, 4 de 5, así que se apaga cuDNN entero. No basta:
sin cuDNN, las otras tareas del hígado aún fallan a veces, y por eso `segment.run` pasa a CPU
cuando la GPU falla (`docs/apagado-progresivo-inventario.md` §F, 2026-11-11). Sin GPU, esto no
cambia nada.

Corre con el Python del entorno de TotalSegmentator (`backend/.venv-seg`), NO con el de EMMA: no
importa nada de `app`, solo torch y totalsegmentator. Recibe los mismos argumentos que el
ejecutable `TotalSegmentator`. La guarda `__main__` es obligatoria: en Windows TotalSegmentator
abre subprocesos que vuelven a importar este fichero, y sin ella se cuelga.
"""

from __future__ import annotations


def main() -> None:
    import torch
    from totalsegmentator.bin.TotalSegmentator import main as totalsegmentator

    torch.backends.cudnn.enabled = False
    totalsegmentator()


if __name__ == "__main__":
    main()
