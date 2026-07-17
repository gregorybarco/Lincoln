## July-17-2026

## Lincoln - Agentic AI model - Initial build session and testing on local machine

- Initialized 'Lincoln' the Qwen Model on ollama, connected to the aider-chat, exposed the ai model to the machine.
- Initialized Lincoln repository under B:\Homebrewed_AI\Lincoln
- Configured Python virtual environment (venv)
- Installed aider-chat and froze dependencies to requirements.txt
- Configured .gitignore to exclude venv, .env, and all Aider temporary files
- Set OLLAMA_API_BASE=http://localhost:11434 in .env for permanent Ollama connection
- Confirmed Aider connected to Qwen 3.5 9B through Ollama with no errors
- Confirmed suggestion-only mode working via --no-auto-commits and --dry-run flags
- Tested first /ask query against mathematical finance use case - Qwen responded with accurate domain knowledge
- Learned: PowerShell requires Out-File -Encoding utf8 for correct UTF-8 file output
- Learned: CLI command structure - program --option value --flag pattern
- Learned: localhost:11434 is Ollama's local server address and port

### Status
Lincoln is operational. Next session: write first build decision document, then begin RAG pipeline planning.
terminal> lincoln  opens lincoln from the batch file with preset model and change directories and the local host

/ask = to ask lincoln a question
/add [directory] to give the file relevant to the ai
/drop [file] to remove context
/exit - close lincoln

- Fixed lincoln.bat with /d flag for cross-drive launching
- Added lincoln.bat to Windows PATH - lincoln now launches from anywhere
- Confirmed /ask workflow operational
- Written build_decisions/decision-001-stack-selection.md
- README.md completed
- Identified future capability: date/time tool for Qwen