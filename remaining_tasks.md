# Lincoln Model Evaluation Report
Generated: 2026-07-24T04:19:35
Models: qwen2.5-coder:latest, gemma4:12b

## Summary

| Task | Model | Tokens/sec | VRAM delta (MB) | Processor | Tool call valid? |
|---|---|---|---|---|---|
| 4_long_context | qwen2.5-coder:latest | 70.5 | 6433 | 100% GPU     32768 | - |
| 4_long_context | gemma4:12b | 41.1 | 2207 | 100% GPU     32768 | - |
| 5_sanity_check | qwen2.5-coder:latest | 76.2 | 5355 | 100% GPU     16384 | - |
| 5_sanity_check | gemma4:12b | 43.2 | -250 | 100% GPU     16384 | - |

---

## 4_long_context — Long-context handling

### qwen2.5-coder:latest

**Response:**
```
This Python source file is part of Lincoln Ollama Service version 0.7.0, a local AI assistant designed to communicate with an Ollama server. The service handles various aspects such as model discovery, health checks, context window management, and streaming chat responses.

### Responsibilities:
1. **Model Discovery**: Fetches available models from the Ollama server.
2. **Health Check**: Verifies if the Ollama server is running and reachable.
3. **Context Window Management**: Computes the appropriate context window size for each request based on input length, system constraints, and hardware limits.
4. **Chat Handling**:
   - **Single Response**: Sends a chat request to the Ollama server and returns a single response.
   - **Streaming Chat**: Streams chat responses, handling tool calls if enabled.
5. **Tool Manifest**: Builds and injects a manifest of available tools into system prompts, ensuring the LLM knows what capabilities are available on the machine.

### Functions Reading Database Settings:
- `_get_timeout()`
  - Reads `ollama_timeout_sec` from DB settings at call time.

All other functions do not directly read database settings but may indirectly use settings via helper functions like `_get_timeout()` or through configuration variables imported from other modules.
```

_tokens/sec: 70.5, VRAM: 1434 -> 7867 MB, processor: 100% GPU     32768_

### gemma4:12b

**Response:**
```
### Summary of Responsibilities
This file serves as the primary communication layer between the "Lincoln" application and a local **Ollama** server. Its main responsibilities include:

1.  **Request Management:** Handling all interactions with the Ollama API, including standard chat requests and streaming responses.
2.  **Context Window Optimization:** Dynamically calculating the `num_ctx` (context window) for each request to ensure there is enough "headroom" for long model outputs while staying within hardware limits.
3.  **System Prompt Construction:** Building complex system prompts that include a **Tool Manifest**, which informs the LLM about available capabilities (e.g., OCR, web search, specific programming tools).
4.  **Model Intelligence:** Detecting if a model is in "thinking mode" (for models like Qwen or DeepSeek) and handling specialized output formatting for those models.
5.  **Tool Integration:** Providing a specialized `stream_chat_with_tools` function that allows the system to detect and process structured tool calls from the LLM during streaming.

---

### Functions that read settings from the database
The following functions contain logic to fetch values from `lincoln_database`:

1.  **`_get_max_context_ceiling()`**: Retrieves the `max_context_tokens` setting.
2.  **`_get_timeout()`**: Retrieves the `ollama_timeout_sec` setting.
3.  **`_build_tool_manifest()`**: Reads multiple settings to construct the tool list, specifically:
    *   `wsl_distro`
    *   `nvfortran_path`
    *   `maple_path`
    *   `oneapi_path`
    *   `web_search_enabled`
```

_tokens/sec: 41.1, VRAM: 7867 -> 10074 MB, processor: 100% GPU     32768_


## 5_sanity_check — Plain conversational sanity check

### qwen2.5-coder:latest

**Response:**
```
A locally-run AI assistant is generally considered more privacy-preserving than a cloud-based one for several key reasons:

1. **Data Local Storage**: With a locally-run AI, all the data processed and learned from interactions stays on the user's device rather than being transmitted to remote servers. This reduces the risk of sensitive information leaving the user’s control.

2. **Control Over Data**: Users have complete control over their data with a local AI assistant. They can decide what data gets shared and with whom, as opposed to cloud-based solutions where data is managed by third-party providers who might store it in multiple locations or with other users.

3. **Lower Exposure**: Since the AI model and data don't need to be accessed from remote servers, there's a lower exposure of sensitive information to potential cyber threats and breaches at external data centers.

4. **Offline Functionality**: Local AI assistants can function without an internet connection, allowing for use in environments where connectivity might be unreliable or non-existent.

5. **Performance**: Local processing typically results in faster response times as data doesn't need to travel across networks.

6. **Security Measures**: Users can implement stronger security measures and have more control over how their data is protected on their local device.

Overall, the localized nature of a locally-run AI assistant minimizes risks associated with data privacy and security compared to cloud-based solutions.
```

_tokens/sec: 76.2, VRAM: 10074 -> 15429 MB, processor: 100% GPU     16384_

### gemma4:12b

**Response:**
```
A locally-run AI assistant is more privacy-preserving primarily because of **where the data is processed** and **who has access to it**. 

Here are the three main reasons:

*   **Data Residency:** With a cloud-based AI, your prompts, files, and personal information are transmitted over the internet to a remote server. With a local AI, all processing happens on your own hardware (laptop, desktop, or private server), meaning your data never leaves your physical control.
*   **Elimination of Third-Party Logging:** Cloud providers often log user interactions to improve their models, monitor for safety violations, or provide analytics. Local models do not require a connection to a central authority, so there is no third party "listening" or recording your inputs.
*   **No Training Risk:** Many cloud AI companies use anonymized (or even non-anonymized) user data to retrain and refine their models. Because local models run in an isolated environment, your private data cannot be harvested to improve a product used by others.

In short: **Cloud AI shares your data with a provider; Local AI keeps your data on your machine.**
```

_tokens/sec: 43.2, VRAM: 15429 -> 15179 MB, processor: 100% GPU     16384_
