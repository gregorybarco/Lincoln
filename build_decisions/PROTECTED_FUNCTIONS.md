# Lincoln Protected Functions

**Version:** v0.7.0
**Purpose:** Prevent AI-generated code from accidentally overwriting or
breaking Lincoln's core UI functions. The ban list checker reads this file
and fires a warning banner if generated code touches any listed symbol.

These are not "banned" patterns like the OptionsPricing ban list -- they are
*protected* symbols that Lincoln already owns. Generated code that redefines
them will silently break the UI. The warning tells the user before they run
or save anything.

---

## Protected JS Namespaces (top-level objects)

Any generated code that **declares** one of these as a `const`, `let`, `var`,
or `function` at module level should trigger a warning.

```
lincolnChat
lincolnCanvas
lincolnSidebar
lincolnSettings
lincolnCanvasUI
```

---

## Protected JS Functions (method names within Lincoln modules)

These are the critical entry points. Generated code that **redefines** any
of these (e.g. `function sendMessage() { ... }` or
`lincolnChat.sendMessage = function() { ... }`) should trigger a warning.

### lincolnChat
- `sendMessage`
- `newSession`
- `loadSession`
- `setActiveProject`
- `clearActiveProject`
- `openFileAttach`
- `clearPendingFile`
- `handleInputKeydown`
- `autoResizeTextarea`
- `toggleWebSearch`
- `toggleThinkDropdown`
- `setThinkMode`
- `showWelcome`
- `showProjectHome`
- `startNewChat`
- `saveMemory`
- `init`

### lincolnSettings
- `open`
- `close`
- `loadModels`
- `toggleAdminMode`
- `toggleModelDropdown`
- `selectModel`
- `addPromptBlock`
- `_updatePromptField`
- `_deletePromptBlock`
- `_saveEnvField`

### lincolnCanvas
- `pinCodeBlock`
- `clear`
- `switchTab`
- `extractCodeBlocks`
- `resolveFilename`
- `toggle`
- `hasSelection`
- `clearSelection`
- `runBlock`

### lincolnSidebar
- `loadHistory`
- `loadMemory`
- `openFileBrowser`
- `createProject`
- `closeNewProjectPanel`
- `closeProjectSettings`
- `hasSelection`
- `clearSelection`
- `editMemoryEntry`
- `saveMemoryEdit`
- `cancelMemoryEdit`
- `openAddMemoryForm`
- `saveNewMemory`

---

## Protected HTML IDs

Generated HTML that reuses these IDs will collide with Lincoln's own elements.

```
chatMessages
chatInput
sendBtn
canvasBody
canvasCol
settingsOverlay
settingsPanelContent
newProjectOverlay
projectSettingsOverlay
modelDropdown
modelPill
activeModelLabel
thinkModePill
thinkDropdown
thinkModeLabel
webSearchPill
pendingFileChip
contextStrip
toastContainer
topbarProjectBadge
globalPromptBlocks
```

---

## Protected Python Functions

Generated Python that redefines these Lincoln internals will break core
functionality if saved via Aider.

### lincoln_database.py
- `initialise_database`
- `get_active_system_prompt`
- `create_system_prompt`
- `update_system_prompt`
- `get_all_settings`
- `save_settings`
- `get_setting`
- `save_memory_entry`
- `update_memory_entry`

### lincoln_ollama_service.py
- `stream_chat`
- `chat`
- `build_messages_with_rag_context`
- `resolve_num_ctx_for_request`
- `get_available_models`

### lincoln_routes_chat.py
- `send_message`
- `create_new_session`

---

## Regex Patterns for the Checker

These are the patterns `lincoln_ban_list_checker.py` uses to detect violations.
Each pattern fires a WARNING (not a block) -- the user can still proceed.

```
# Reassigns a critical Lincoln method
\b(lincolnChat|lincolnSettings|lincolnCanvas|lincolnSidebar)\.(sendMessage|loadSession|newSession|setActiveProject|open|close|loadModels|toggleModelDropdown|selectModel|addPromptBlock|pinCodeBlock|clear|switchTab|loadHistory|loadMemory|editMemoryEntry|saveMemoryEdit|cancelMemoryEdit|openAddMemoryForm|saveNewMemory)\s*=

# Redefines a protected Python function by name
^\s*def\s+(initialise_database|get_active_system_prompt|stream_chat|chat|build_messages_with_rag_context|resolve_num_ctx_for_request|send_message|create_new_session|save_memory_entry|update_memory_entry)\s*\(

# Redefines a protected Python function by name
^\s*def\s+(initialise_database|get_active_system_prompt|stream_chat|chat|build_messages_with_rag_context|resolve_num_ctx_for_request|send_message|create_new_session)\s*\(

# Writes to a protected HTML ID
id\s*=\s*["'](chatMessages|chatInput|sendBtn|canvasBody|settingsOverlay|modelDropdown|modelPill|thinkModePill|thinkDropdown|webSearchPill|toastContainer|topbarProjectBadge|globalPromptBlocks)["']
```
