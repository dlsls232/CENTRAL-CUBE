@echo off
setlocal
cd /d "%~dp0\.."
echo === CENTRAL CUBE Windows build ===
where py >nul 2>nul || (echo Python launcher py not found. Install Python 3.11+ and retry.& exit /b 1)
py -3 -m venv .venv
if errorlevel 1 exit /b 1
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
if errorlevel 1 exit /b 1
pip install -e ".[dev]"
if errorlevel 1 exit /b 1
python -m pytest -q
if errorlevel 1 exit /b 1
python -m pytest --cov=central_cube.agent.commands --cov=central_cube.agent.server --cov=central_cube.core.database --cov=central_cube.core.pairing --cov=central_cube.network.client --cov=central_cube.network.protocol --cov=central_cube.network.wol --cov-fail-under=80 -q
if errorlevel 1 exit /b 1
python -m compileall -q src
if errorlevel 1 exit /b 1
pyinstaller --noconfirm --clean --windowed --name CentralCube --icon assets\central_cube.ico --add-data "assets;assets" --paths src src\central_cube\main.py
if errorlevel 1 exit /b 1
pyinstaller --noconfirm --clean --console --name CentralCubeAgent --icon assets\central_cube.ico --add-data "assets;assets" --paths src src\central_cube\agent\main.py
if errorlevel 1 exit /b 1
echo.
echo Build files:
echo dist\CentralCube\CentralCube.exe
echo dist\CentralCubeAgent\CentralCubeAgent.exe
echo.
echo IMPORTANT: Provision a dedicated CA and issue unique mTLS certificates.
echo Keep private keys protected and restrict inbound TCP to trusted networks.
endlocal
