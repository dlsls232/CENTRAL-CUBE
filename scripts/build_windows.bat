
@echo off
setlocal

cd /d "%~dp0\.."

echo ========================================
echo CENTRAL CUBE Windows build
echo ========================================

where py >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python launcher not found.
    exit /b 1
)

echo Creating Python 3.12 virtual environment...
py -3.12 -m venv .venv
if errorlevel 1 exit /b 1

call .venv\Scripts\activate.bat
if errorlevel 1 exit /b 1

echo.
echo Python version:
python --version

echo.
echo Updating pip...
python -m pip install --upgrade pip
if errorlevel 1 exit /b 1

echo.
echo Installing CENTRAL CUBE dependencies...
python -m pip install -e ".[dev]"
if errorlevel 1 exit /b 1

echo.
echo Running tests...
python -m pytest -q
if errorlevel 1 exit /b 1

echo.
echo Running coverage tests...
python -m pytest --cov=central_cube.agent.commands --cov=central_cube.agent.server --cov=central_cube.core.database --cov=central_cube.core.pairing --cov=central_cube.network.client --cov=central_cube.network.protocol --cov=central_cube.network.wol --cov-fail-under=80 -q
if errorlevel 1 exit /b 1

echo.
echo Compiling Python files...
python -m compileall -q src
if errorlevel 1 exit /b 1

echo.
echo Building CENTRAL CUBE GUI...
python -m PyInstaller --noconfirm --clean --windowed --name CentralCube --icon assets\central_cube.ico --add-data "assets;assets" --paths src src\central_cube\main.py
if errorlevel 1 exit /b 1

echo.
echo Building CENTRAL CUBE Agent...
python -m PyInstaller --noconfirm --clean --console --name CentralCubeAgent --icon assets\central_cube.ico --add-data "assets;assets" --paths src src\central_cube\agent\main.py
if errorlevel 1 exit /b 1

echo.
echo ========================================
echo BUILD COMPLETED
echo ========================================

echo dist\CentralCube\CentralCube.exe
echo dist\CentralCubeAgent\CentralCubeAgent.exe

endlocal
