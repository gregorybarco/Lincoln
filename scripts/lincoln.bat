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
    echo   /run lhelp                                             Show Lincoln help
    echo   /ask "question"                                        Get suggestions from LLM
    echo   /run rag "question"                                    Query Project 1 index
    echo   /run rag "question" --top-k 8                         Query with more chunks
    echo   /run websearch search "query"                         Search web, 5 results
    echo   /run websearch search "query" 10                      Custom result count
    echo   /run websearch fetch "url"                            Fetch full page
    echo   /add filepath                                          Add file to context
    echo   /drop filepath                                         Remove file from context
    echo   /exit                                                  Close Lincoln
    echo.
    echo INFO:
    echo   Model:     Set via LINCOLN_LLM_MODEL in .env
    echo   Mode:      Suggestion only - no files modified without approval
    echo   Config:    main_configuration\config.py
    echo   Location:  B:\Homebrewed_AI\Lincoln
    echo.
    goto end
)
aider
:end