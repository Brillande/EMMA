# Saca cada pestaña de maquetas.html a PNG (1672x941) con Edge sin interfaz.
$ErrorActionPreference = 'Continue'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$edge = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
$page = (Join-Path $here 'maquetas.html') -replace '\\', '/'
$profile = Join-Path $env:TEMP 'emma-maquetas-edge'
$tabs = 'hazards', 'routines', 'body', 'mission', 'data', 'log', 'imaging', 'planner', 'library',
        'received', 'history', 'trends', 'ghabitat', 'framework', 'ledger'
$i = 1
foreach ($t in $tabs) {
  $out = Join-Path $here ('{0:D2}-{1}.png' -f $i, $t)
  & $edge --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 `
    --user-data-dir="$profile" --window-size=1672,941 --virtual-time-budget=2000 `
    --screenshot="$out" "file:///$page#$t" 2>$null | Out-Null
  $i++
}
Get-ChildItem $here -Filter *.png | Select-Object Name, Length
