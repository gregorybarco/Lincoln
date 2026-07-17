@echo off
cd /d B:\Homebrewed_AI\Lincoln
call venv\Scripts\activate

if "%1"=="--help" (
    echo.
    echo Lincoln Web Search Tool
    echo -----------------------
    echo USAGE:
    echo   websearch search "your query"         Search web, default 5 results
    echo   websearch search "your query" 10      Search with custom result count
    echo   websearch fetch "https://url.com"     Fetch full page as clean text
    echo   websearch --help                      Show this help message
    echo.
    echo EXAMPLES:
    echo   websearch search "QuantLib Monte Carlo pricing"
    echo   websearch search "Hull White model Python" 10
    echo   websearch fetch "https://quantlib.org/docs"
    echo.
    goto end
)

python scripts\web_search.py %1 %2 %3
:end