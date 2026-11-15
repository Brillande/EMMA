# Genera el dictado de prueba de Whisper (8 s, 16 kHz mono) con la voz española de Windows.
# Es audio sintético, no de nadie: así la medida de Whisper se puede repetir igual en cualquier equipo.
# Uso, desde la raíz del repositorio:  powershell -File docs/apagado-progresivo/scripts/generar-dictado.ps1
Add-Type -AssemblyName System.Speech
$out = Join-Path $PSScriptRoot "..\datos\dictado.wav"
New-Item -ItemType Directory -Force (Split-Path $out) | Out-Null
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice('Microsoft Helena Desktop')
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo 16000, ([System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen), ([System.Speech.AudioFormat.AudioChannel]::Mono)
$s.SetOutputToWaveFile($out, $fmt)
$s.Speak('EMMA, anota que esta mañana me duele la rodilla derecha, intensidad cuatro sobre diez, y que he dormido unas seis horas.')
$s.Dispose()
Write-Output "dictado en $out"
