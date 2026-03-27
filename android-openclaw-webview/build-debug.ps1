param(
    [string]$BaseUrl = "http://10.0.2.2:8105"
)

$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

Write-Host "Building debug APK with OPENCLAW_BASE_URL=$BaseUrl"
if (Test-Path ".\gradlew.bat") {
    & ".\gradlew.bat" assembleDebug "-POPENCLAW_BASE_URL=$BaseUrl"
} else {
    gradle assembleDebug "-POPENCLAW_BASE_URL=$BaseUrl"
}
