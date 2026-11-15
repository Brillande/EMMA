"""Fiabilidad de la segmentación en GPU: espera a que la GPU lleve 30 s libre y lanza las 4 tareas del
preset de hígado, 2 rondas con el ejecutable de TotalSegmentator (cuDNN encendido) y 2 con
`totalseg_sin_cudnn.py` (cuDNN apagado, en este directorio), sin paso a CPU, apuntando cada fallo.

Uso, desde backend/:  .venv/Scripts/python.exe ../docs/apagado-progresivo/scripts/fiabilidad_segmentacion.py <TotalSegmentator.exe>
"""
import subprocess, sys, time, shutil
from pathlib import Path
sys.path.insert(0, ".")
from app.volumes import segment, assets

D = Path(__file__).resolve().parent / "_salida-fiabilidad"
EXE = sys.argv[1]
CT = Path("app/data/volume_samples/higado-1/ct.nii.gz")

def gpu():
    o = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,power.draw", "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout
    u, w = [float(x) for x in o.strip().split(",")]
    return u, w

def wait_free():
    quiet = 0; t = time.time()
    while quiet < 30:
        u, w = gpu()
        quiet = quiet + 1 if (u < 10 and w < 15) else 0
        time.sleep(1)
    print(f"GPU libre tras {time.time() - t:.0f} s", flush=True)

def task(launch, task_name, subset, device="gpu"):
    out = D / f"{task_name}-{time.time():.0f}"
    cmd = [*launch, "-i", str(CT), "-o", str(out), "-ta", task_name, "-d", device, "-q"]
    if subset: cmd += ["--roi_subset", *subset]
    t = time.time(); r = subprocess.run(cmd, capture_output=True, text=True)
    err = "" if r.returncode == 0 else ("misaligned" if "misaligned" in r.stderr else "illegal" if "illegal" in r.stderr else r.stderr.strip()[-60:])
    print(f"  {task_name:15} {'ok' if r.returncode == 0 else 'FALLA ' + err} {time.time() - t:.1f} s", flush=True)
    shutil.rmtree(out, ignore_errors=True)

if __name__ == "__main__":
    D.mkdir(parents=True, exist_ok=True)
    tasks = assets.PRESETS["higado"].tasks
    for i in range(2):
        wait_free(); print(f"ronda {i + 1}, ejecutable original (cuDNN encendido):", flush=True)
        for name, subset in tasks:
            task([EXE], name, subset)
    for i in range(2):
        wait_free(); print(f"ronda {i + 1}, sin cuDNN, sin paso a CPU:", flush=True)
        for name, subset in tasks:
            task([str(Path(EXE).with_name('python.exe')), str(Path(__file__).with_name('totalseg_sin_cudnn.py'))], name, subset)
    shutil.rmtree(D, ignore_errors=True)
