@echo off
cd /d B:\Homebrewed_AI\Lincoln
call venv\Scripts\activate
python -m lincoln.lincoln_web_search %*
