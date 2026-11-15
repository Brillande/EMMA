# Instala el paquete de modelos de EMMA desde esta carpeta (disco o USB), sin red.
#
# Copia el paquete a %LOCALAPPDATA%\EMMA-modelos (o a -Destino) y comprueba el tamaño y el SHA-256
# de cada fichero contra MANIFIESTO.json, ya en el destino: lo que cuenta es lo que queda en el
# disco, no lo que había en el USB. Solo al final escribe instalado.json, que es lo que busca la
# aplicación de escritorio: un paquete a medio copiar o con un fichero alterado no se usa.
#
# Lo construye backend/packaging/models_pack.py.

param(
    [string]$Destino = (Join-Path $env:LOCALAPPDATA "EMMA-modelos")
)

$ErrorActionPreference = "Stop"
$origen = $PSScriptRoot
$manifiesto = Join-Path $origen "MANIFIESTO.json"
if (-not (Test-Path $manifiesto)) { throw "No hay MANIFIESTO.json junto a este script." }

# Nunca se vacía una carpeta que no sea de una instalación anterior del paquete: robocopy /MIR
# borra lo que sobra en el destino.
if (Test-Path $Destino) {
    $previo = Join-Path $Destino "MANIFIESTO.json"
    $vacio = -not (Get-ChildItem -LiteralPath $Destino -Force | Select-Object -First 1)
    if (-not $vacio -and -not (Test-Path $previo)) {
        throw "$Destino ya existe y no es una instalación del paquete de modelos de EMMA."
    }
    Remove-Item -LiteralPath (Join-Path $Destino "instalado.json") -ErrorAction SilentlyContinue
}

Write-Host "Copiando a $Destino ..."
robocopy $origen $Destino /MIR /NFL /NDL /NJH /NP /R:2 /W:2 /XF instalado.json | Out-Host
if ($LASTEXITCODE -ge 8) { throw "robocopy falló (código $LASTEXITCODE)." }

Write-Host "Comprobando las huellas en el destino ..."
$datos = Get-Content -LiteralPath (Join-Path $Destino "MANIFIESTO.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$ficheros = $datos.files.PSObject.Properties
$total = @($ficheros).Count
$n = 0
$malos = @()
foreach ($f in $ficheros) {
    $n++
    $ruta = Join-Path $Destino ($f.Name -replace "/", "\")
    $tam = [int64]$f.Value[0]
    $huella = [string]$f.Value[1]
    if (-not (Test-Path -LiteralPath $ruta)) { $malos += "falta: $($f.Name)"; continue }
    if ((Get-Item -LiteralPath $ruta).Length -ne $tam) { $malos += "tamaño: $($f.Name)"; continue }
    if ((Get-FileHash -LiteralPath $ruta -Algorithm SHA256).Hash.ToLower() -ne $huella) {
        $malos += "huella: $($f.Name)"
    }
    if ($n % 500 -eq 0) { Write-Host "  $n / $total" }
}
if ($malos.Count -gt 0) {
    $malos | Select-Object -First 20 | ForEach-Object { Write-Host "  $_" }
    throw "$($malos.Count) ficheros no coinciden con el manifiesto. No se ha activado el paquete."
}

@{ installed = (Get-Date).ToUniversalTime().ToString("o"); pack_created = $datos.created } |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $Destino "instalado.json") -Encoding UTF8
Write-Host "Paquete de modelos instalado y comprobado ($total ficheros) en $Destino."
Write-Host "EMMA lo usará la próxima vez que se abra."
