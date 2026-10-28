# Uso: .\publicar.ps1 "mensaje del cambio"
param([string]$Mensaje = "Actualización de la página")
$g = "C:\Program Files\Git\cmd\git.exe"
Set-Location $PSScriptRoot
& $g add -A
& $g commit -m $Mensaje
& $g push origin main
Write-Host "Listo. En 1-2 minutos se actualiza https://luisrga.github.io/Ing.Wolf/"
