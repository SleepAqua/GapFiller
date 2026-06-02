@echo off
SETLOCAL
set DIST_URL=https://services.gradle.org/distributions/gradle-8.7-bin.zip
set WRAPPER_DIR=%~dp0.gradle-wrapper
set GRADLE_DIR=%WRAPPER_DIR%\gradle-8.7

if not exist "%GRADLE_DIR%\bin\gradle.bat" (
  echo Gradle distribution not found. Downloading...
  if not exist "%WRAPPER_DIR%" mkdir "%WRAPPER_DIR%"
  powershell -Command "Invoke-WebRequest -Uri '%DIST_URL%' -OutFile '%WRAPPER_DIR%\gradle.zip'"
  powershell -Command "Expand-Archive -LiteralPath '%WRAPPER_DIR%\gradle.zip' -DestinationPath '%WRAPPER_DIR%'"
)

"%GRADLE_DIR%\bin\gradle.bat" %*
