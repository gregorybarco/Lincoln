@echo off
cd /d B:\Homebrewed_AI\Lincoln
call venv\Scripts\activate
if "%1"=="--help" (
    echo.
    echo Lincoln - Local AI Agent
    echo ------------------------
    echo COMMANDS:
    echo   lincoln              Launch Lincoln AI agent
    echo   lincoln --help       Show this help message
    echo.
    echo INSIDE LINCOLN PROMPT:
    echo   /ask "question"                                    Get suggestions from Qwen
    echo   /run python scripts\web_search.py search "query"  Search web, 5 results
    echo   /run python scripts\web_search.py search "query" 10  Custom result count
    echo   /run python scripts\web_search.py fetch "url"     Fetch full page
    echo   /add filepath                                      Add file to context
    echo   /drop filepath                                     Remove file from context
    echo   /exit                                              Close Lincoln
    echo.
    echo INFO:
    echo   Model:     Qwen 3.5 9B via Ollama
    echo   Mode:      Suggestion only - no files modified without approval
    echo   Location:  B:\Homebrewed_AI\Lincoln
    echo.
    goto end
)
aider
:end