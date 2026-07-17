@echo off
cd /d B:\Homebrewed_AI\Lincoln
call venv\Scripts\activate

if "%1"=="--help" (
    echo.
    echo Lincoln Web Search Tool
    echo -----------------------
    echo USAGE:
    echo   /run websearch "query"            Search web, default 5 results
    echo   /run websearch "query" 10         Search with custom result count
    echo   /run websearch fetch "url"        Fetch full page as clean text
    echo   websearch --help                  Show this help message
    echo.
    goto end
)

python scripts\web_search.py %*
:end