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
    echo   websearch search "query"        Search web, default 5 results
    echo   websearch search "query" 10     Search with custom result count
    echo   websearch fetch "url"           Fetch full page content
    echo   websearch --help                Show websearch help
    echo.
    echo WORKFLOW:
    echo   Inside Lincoln use:
    echo   /ask "question"      Get suggestions without touching files
    echo   /add filepath        Add a file to Lincolns context
    echo   /drop filepath       Remove a file from context
    echo   /exit                Close Lincoln
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