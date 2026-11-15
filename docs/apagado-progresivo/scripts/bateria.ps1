# Consumo del portátil ENTERO (pantalla incluida) con la batería: ritmo de descarga, cada segundo.
#
# Por qué existe: nvidia-smi da la GPU dedicada y RAPL la CPU, pero la pantalla, la GPU integrada,
# el disco y el resto no tienen contador. Con el portátil desenchufado, la batería informa de su
# ritmo de descarga (`root\wmi` BatteryStatus.DischargeRate, en mW), que es todo el equipo. Sin
# administrador. Solo vale desenchufado (PowerOnline = False); el firmware actualiza el valor cada
# pocos segundos, no cada muestra.
#
# Uso:  powershell -File bateria.ps1 -Segundos 2400 -Salida <csv>
# Escribe: t (segundos Unix), enchufado, descarga_w, capacidad_restante_wh, tension_v.
param([int]$Segundos = 60, [string]$Salida)
Set-Content -Path $Salida -Value 't,enchufado,descarga_w,capacidad_restante_wh,tension_v' -Encoding UTF8
$inv = [Globalization.CultureInfo]::InvariantCulture
$end = (Get-Date).AddSeconds($Segundos)
while ((Get-Date) -lt $end) {
    $b = Get-CimInstance -Namespace root\wmi -ClassName BatteryStatus | Select-Object -First 1
    $t = ([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000.0).ToString('0.000', $inv)
    $row = @($t, [int][bool]$b.PowerOnline, ($b.DischargeRate / 1000.0).ToString('0.000', $inv),
             ($b.RemainingCapacity / 1000.0).ToString('0.000', $inv), ($b.Voltage / 1000.0).ToString('0.000', $inv))
    Add-Content -Path $Salida -Value ($row -join ',')
    Start-Sleep -Seconds 1
}
