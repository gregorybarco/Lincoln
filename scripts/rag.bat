@echo off
cd /d B:\Homebrewed_AI\Lincoln
call venv\Scripts\activate.bat
python scripts\rag_query.py %*