@echo off

rem Set the path to the virtual environment activation script
set VENV_PATH=.\venv\Scripts\activate

rem Activate the virtual environment
call %VENV_PATH%

rem Run the Python script
python main.py

rem Deactivate the virtual environment
deactivate
