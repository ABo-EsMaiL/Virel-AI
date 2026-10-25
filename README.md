<div align="center">

<!-- Animated Top Wave Banner -->
<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0F172A,50:059669,100:10B981&height=185&section=header&text=VIREL%20AI&fontSize=58&fontColor=ffffff&animation=fadeIn&fontAlignY=35&desc=High-Performance%20Autonomous%20Agent%20Gateway%20for%20Google%20AI%20Studio&descAlignY=58&descSize=18" width="100%" alt="Virel AI Banner" />

<a href="https://github.com/ABo-EsMaiL/Virel-AI">
  <img src="https://raw.githubusercontent.com/ABo-EsMaiL/Virel-AI/main/assets/logo.png" alt="Virel AI Logo" width="150" height="150" style="border-radius: 28px; box-shadow: 0 0 35px rgba(16, 185, 129, 0.45);" />
</a>

<br/><br/>

<!-- Animated Multi-Line Typing SVG -->
<a href="https://github.com/ABo-EsMaiL/Virel-AI">
  <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=700&size=20&duration=3000&pause=900&color=10B981&center=true&vCenter=true&multiline=false&width=880&height=45&lines=%E2%9A%A1+Zero-Cost+Gemini+3.8+Flash+%26+Pro+Gateway+for+Coding+Agents;%F0%9F%94%84+Full+OpenAI+Chat%2C+Responses+API+%26+Anthropic+Messages+Parity;%F0%9F%9B%A0%EF%B8%8F+Stateful+Browser+Tool+Continuation+for+Codex%2C+Claude+Code+%26+Cline;%F0%9F%8E%A8+Context-Offloaded+Image+%26+Voice+Generation+Across+500K%2B+Token+Chats;%F0%9F%94%80+Autonomous+Multi-Account+Quota+Rotation+%26+RAM-Aware+Tab+Pool" alt="Virel AI Typing SVG" />
</a>

<!-- Primary Shield Badges -->
<p align="center">
  <a href="https://aistudio.google.com/"><img src="https://img.shields.io/badge/Powered_By-Google_AI_Studio-4285F4?style=for-the-badge&logo=google&logoColor=white" alt="Google AI Studio" /></a>
  <a href="#-api-reference--protocol-matrix"><img src="https://img.shields.io/badge/Protocols-OpenAI_%7C_Anthropic_%7C_Responses-10B981?style=for-the-badge&logo=openai&logoColor=white" alt="Protocols" /></a>
  <a href="#-client-configurations"><img src="https://img.shields.io/badge/Agents-Codex_%7C_Claude_Code_%7C_Cline_%7C_n8n-FF6F00?style=for-the-badge&logo=anthropic&logoColor=white" alt="Autonomous Agents" /></a>
  <a href="#-system-architecture"><img src="https://img.shields.io/badge/Quota-Auto_Account_Rotation-00C853?style=for-the-badge&logo=googlechrome&logoColor=white" alt="Auto Quota Rotation" /></a>
</p>

<!-- Tech Stack Badges -->
<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+" />
  <img src="https://img.shields.io/badge/FastAPI-0.111-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Playwright-Chromium-2EAD33?style=flat-square&logo=playwright&logoColor=white" alt="Playwright" />
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED?style=flat-square&logo=docker&logoColor=white" alt="Docker" />
  <img src="https://img.shields.io/badge/PRs-Welcome-brightgreen?style=flat-square" alt="PRs Welcome" />
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-3B82F6?style=flat-square" alt="License" /></a>
</p>

<!-- Quick Navigation Bar -->
<p align="center">
  <a href="#-why-virel-ai"><b>Why Virel AI</b></a> •
  <a href="#-system-architecture"><b>Architecture</b></a> •
  <a href="#-enterprise-showcase-the-ofok-operations-lab"><b>n8n Enterprise Lab</b></a> •
  <a href="#-quick-start"><b>Quick Start</b></a> •
  <a href="#-client-configurations"><b>Client Setup</b></a> •
  <a href="#-api-reference--protocol-matrix"><b>API Reference</b></a>
</p>

<img src="https://user-images.githubusercontent.com/73097560/115834477-dbab4500-a447-11eb-908a-139a6edaec5c.gif" width="100%" alt="Divider" />

</div>

## ⚡ Why Virel AI?

Modern autonomous coding agents (**Claude Code**, **Codex Desktop**, **Cline**, **Continue**, **OpenCode**) and multi-agent orchestrators (**n8n**, **LangGraph**) consume massive context windows across multi-turn tool loops. Per-token API billing quickly becomes expensive, while standard free API tiers enforce strict rate limits.

**Virel AI** bridges your local agent ecosystem directly to **Google AI Studio** via an automated, persistent Chromium pool—exposing standard **OpenAI Chat Completions**, **OpenAI Responses**, and **Anthropic Messages** endpoints on `http://localhost:8000`.

| Feature / Capability | Standard Free API | Basic Web Wrappers | 🚀 **Virel AI Gateway** |
| :--- | :---: | :---: | :---: |
| **OpenAI `/v1/chat/completions` & `/v1/responses`** | ⚠️ Rate-Limited | ❌ Text-only | ✅ **Full Parity (JSON + Paced SSE)** |
| **Anthropic `/v1/messages` & `/claude/v1/messages`** | ❌ No | ❌ No | ✅ **Native Claude Code & Desktop Support** |
| **Multi-Turn Client Tool Execution Loops** | ✅ Yes | ❌ Stateless / Broken | ✅ **Stateful Browser Turn Leases (`virel_client_tools`)** |
| **Context-Offloaded Image & Voice Tools in 500K+ Chats** | ❌ Model Locked | ❌ No | ✅ **Isolated Background Tab Synthesis** |
| **Automatic Multi-Account Failover (`429`)** | ❌ Single Key | ❌ Manual Relogin | ✅ **Zero-Downtime `authuser` & Profile Rotation** |
| **Multimodal Ingestion (PDF, Audio, Video, Office)** | ⚠️ Quota Restricted | ❌ Text Only | ✅ **Subprocess-Validated Native Uploads** |
| **Exact Protobuf Token & Reasoning Telemetry** | ✅ Yes | ❌ Estimated | ✅ **Intercepted `MakerSuiteService` Usage** |

<img src="https://user-images.githubusercontent.com/73097560/115834477-dbab4500-a447-11eb-908a-139a6edaec5c.gif" width="100%" alt="Divider" />

## 🏗️ System Architecture

### 1. End-to-End Gateway & Multi-Tab Pool Topology

```mermaid
flowchart LR
    classDef client fill:#0F172A,stroke:#38BDF8,stroke-width:2px,color:#F8FAFC;
    classDef gateway fill:#064E3B,stroke:#10B981,stroke-width:2px,color:#ECFDF5;
    classDef browser fill:#1E1B4B,stroke:#818CF8,stroke-width:2px,color:#EEF2FF;
    classDef google fill:#3B0764,stroke:#C084FC,stroke-width:2px,color:#FAF5FF;

    subgraph Clients["🤖 Autonomous Agents & Workflows"]
        direction TB
        C1["Codex Desktop (/v1/responses)"]:::client
        C2["Claude Code & Desktop (/claude/v1/messages)"]:::client
        C3["VS Code: Cline & Continue (/v1/chat)"]:::client
        C4["n8n Multi-Agent Workflows"]:::client
        C5["LangChain / LangGraph / OpenCode"]:::client
    end

    subgraph Virel["⚡ Virel AI Gateway (:8000)"]
        direction TB
        MW["Request Size & RAM Admission Guard"]:::gateway
        RT["Protocol Routers (OpenAI / Anthropic / Audio / Image)"]:::gateway
        MS["Isolated Media Validators (PyAV / pypdf / Calamine)"]:::gateway
        TC["Tool Continuation & Background Media Bridge"]:::gateway
        AR["Multi-Account Quota Manager (Cooldown State)"]:::gateway
        MW --> RT --> MS --> TC --> AR
    end

    subgraph Chromium["🌐 Playwright Persistent Chromium"]
        direction TB
        CTRL["Control Page & Live Model Catalog"]:::browser
        TAB1["Task Tab #1: 1M-Context Reasoning & Tool Loop"]:::browser
        TAB2["Task Tab #2: Isolated Image / TTS Worker"]:::browser
        OBS["Network Usage Observer (Token Telemetry)"]:::browser
    end

    subgraph AIStudio["☁️ Google AI Studio Engine"]
        direction TB
        LLM["Gemini 3.8 Flash / Pro (High Thinking)"]:::google
        IMG["Gemini 3.1 Flash Lite Image (Nano Banana)"]:::google
        TTS["Gemini 3.8 Flash TTS Audio"]:::google
    end

    Clients ==> MW
    AR ==> CTRL & TAB1 & TAB2
    TAB1 & TAB2 <--> OBS
    TAB1 ==> LLM
    TAB2 ==> IMG & TTS
```

### 2. Stateful Client-Tool Continuation & Context-Offloaded Media Synthesis

```mermaid
sequenceDiagram
    autonumber
    participant Agent as 💻 Coding Agent (Codex / Claude / Cline)
    participant Gateway as ⚡ Virel AI Gateway
    participant MainTab as 🧠 Main Reasoning Tab (1M Context)
    participant MediaTab as 🎨 Isolated Media Tab (Image / TTS)

    Agent->>Gateway: POST Request (500K Token History + Client Tools)
    Gateway->>MainTab: Inject "virel_client_tools" Batch + Prompt
    MainTab-->>Gateway: Calls "virel_ai_image_creator" or Client Function
    alt Internal Media Tool Called (Image / Voice Needed Mid-Chat)
        Gateway->>MediaTab: Spawn Fresh Tab with Image/TTS Model (Short Prompt Only)
        MediaTab-->>Gateway: Return Generated Binary Asset & Local File Path
        Gateway->>MainTab: Feed Local Asset Path into Active Function Response
    end
    MainTab-->>Gateway: Emit Validated Client Tool Calls (Bash / Edit / MCP)
    Gateway-->>Agent: Return Standard tool_calls / tool_use Payload
    Note over Agent: Agent Executes Tools Locally & Returns Results
    Agent->>Gateway: POST Continuation with tool_call_id Outputs
    Gateway->>MainTab: Submit Outputs into Retained Browser Turn
    MainTab-->>Gateway: Final Response + Exact Token Telemetry
    Gateway-->>Agent: Deliver Completed Response
```

### 🛡️ Key Architectural Innovations

* **Context-Offloaded Media Bridge (`virel_ai_image_creator` & `virel_ai_voice_generator`)**: Image and TTS models cannot ingest massive 200K–500K token coding conversations. Virel AI keeps your main conversation on the 1M-token Gemini Flash/Pro model and automatically delegates image or voice generation requests to an isolated background tab—returning the generated file path right back into your active agent turn.
* **Client-Owned Tool Continuation (`virel_client_tools`)**: External tools are executed strictly by your client. Virel AI projects complex JSON Schemas (`anyOf`/`oneOf`, `$ref`, `additionalProperties`) into a unified native batch declaration and locks the active browser turn (`SHA-256` owner & state lease) until the multi-turn tool loop finishes.
* **Cryptographic Multi-Tenant Tab Isolation & RAM Admission**: Every concurrent request gets an isolated browser page guarded by real-time RAM availability checks (`psutil` + cgroup limits).
* **Multi-Account Quota Rotation**: Automatically shifts to the next configured Google account (`authuser=0`, `authuser=1`, etc.) upon detecting rate limits (`HTTP 429`) or daily quota banners, persisting cooldown timers across restarts.

<img src="https://user-images.githubusercontent.com/73097560/115834477-dbab4500-a447-11eb-908a-139a6edaec5c.gif" width="100%" alt="Divider" />

## 🏢 Enterprise Showcase: The Ofok Operations Lab

Included in [`examples/n8n_ofok_operations_lab.json`](examples/n8n_ofok_operations_lab.json) is a production-grade, **94-node autonomous multi-agent business workflow** built natively in **n8n** and powered by **Virel AI**.

<div align="center">

<a href="https://raw.githubusercontent.com/ABo-EsMaiL/Virel-AI/main/assets/n8n_workflow.png">
  <img src="https://raw.githubusercontent.com/ABo-EsMaiL/Virel-AI/main/assets/n8n_workflow.png" alt="Virel AI - Ofok Operations Lab (94 Nodes)" width="100%" style="border-radius: 12px; border: 1px solid rgba(16, 185, 129, 0.3);" />
</a>

<br/><br/>

<p align="center">
  <a href="https://raw.githubusercontent.com/ABo-EsMaiL/Virel-AI/main/assets/n8n_workflow.png"><img src="https://img.shields.io/badge/%F0%9F%94%8D_View_Full_Resolution_Diagram-0F172A?style=for-the-badge&logoColor=white" alt="View Full Diagram" /></a>
  <a href="examples/n8n_ofok_operations_lab.json"><img src="https://img.shields.io/badge/%F0%9F%93%A5_Download_94--Node_Workflow_JSON-10B981?style=for-the-badge&logo=n8n&logoColor=white" alt="Download Workflow JSON" /></a>
</p>

</div>

| Operations Domain | Integrated Nodes | Execution Nature |
| :--- | :--- | :--- |
| **🧠 Central Intelligence** | OpenAI Chat Model (`:8000/v1`) | Gemini 3.8 Flash with high reasoning effort & 40-iteration tool loops |
| **💬 Omnichannel Ingestion**| Telegram, WhatsApp, n8n Chat | Authenticated owner gate, customer service, and executive reporting channels |
| **🎞️ Sequential Multimodal**| Voice Transcribe, Vision, PDF & Video | Sequential attachment preprocessing before business agent reasoning |
| **📊 Enterprise Database** | Google Sheets ERP (6 Live Tabs) | Full-row RAW upserts for *Employees, Customers, Inventory, Tickets, Tasks, Knowledge* |
| **🚀 Business Execution** | SearchApi, Gmail API, Calculator, Media | Real-time web research, financial math, image/audio synthesis & report dispatch |
| **🔌 Developer Extensibility**| Model Context Protocol (MCP) | Authenticated read-only MCP server exposing ERP knowledge to IDE agents |

<img src="https://user-images.githubusercontent.com/73097560/115834477-dbab4500-a447-11eb-908a-139a6edaec5c.gif" width="100%" alt="Divider" />

## 🚀 Quick Start

### Prerequisites

* **Python 3.12+**
* **Google Chrome / Playwright Chromium**
* A **Google Account** with access to [Google AI Studio](https://aistudio.google.com/)

### Step 1: Clone & Setup Environment

```powershell
# Clone the repository
git clone https://github.com/ABo-EsMaiL/Virel-AI.git
cd Virel-AI

# Create and activate virtual environment
python -m venv .venv
./.venv/Scripts/Activate.ps1   # Linux/macOS: source .venv/bin/activate

# Install dependencies and Playwright Chromium
pip install -r requirements.txt
playwright install chromium
```

### Step 2: Generate API Key & Configure `.env`

Generate a random 32-byte hexadecimal key:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
Copy-Item .env.example .env
```

<details open>
<summary><b>⚙️ View <code>.env</code> Configuration Template</b></summary>

```ini
# ==============================================================================
# Virel AI Gateway - Environment Configuration (.env)
# ==============================================================================

# Master API Key required in client requests (Authorization: Bearer <key>)
VIREL_API_KEY=your-generated-hex-key-here

# Persistent browser profile folder (where Google account login is stored)
CHROME_PROFILE_DIR=./chrome_profile

# Server Port (default 8000) & Browser Visibility (false = visible window, true = headless)
PORT=8000
# Optional public domain / Cloudflare Tunnel URL (keeps localhost as fallback)
VIREL_PUBLIC_URL=
HEADLESS=false

# Default Models & Thinking Mode (high, low, or minimal)
DEFAULT_MODEL=gemini-flash-latest
DEFAULT_IMAGE_MODEL=gemini-3.1-flash-lite-image
DEFAULT_SPEECH_MODEL=gemini-3.8-flash-tts
DEFAULT_SPEECH_VOICE=Fola
THINKING_MODE=high

# Multi-Account Quota Rotation (Google authuser indices: 0, 1, 2...)
VIREL_GOOGLE_ACCOUNTS_COUNT=2
VIREL_ACCOUNT_COOLDOWN_HOURS=6

# Concurrency & RAM Admission Management
VIREL_MAX_CONCURRENT=20
VIREL_MAX_QUEUE=100
VIREL_QUEUE_TIMEOUT_SECONDS=120
VIREL_MEMORY_RESERVE_MB=1024
VIREL_TAB_MEMORY_MB=512
VIREL_MAX_WAITING_TABS=20

# Active Tool Continuation Lease Timeout (seconds)
VIREL_TOOL_RUN_TTL_SECONDS=600

# Rate limiting per IP (slowapi)
VIREL_RATE_LIMIT=30/minute

# Built-in Google AI Studio tools & Context-Offloaded Media Tools
ENABLE_URL_CONTEXT=true
ENABLE_SEARCH_GROUNDING=false
VIREL_ENABLE_SERVER_TOOLS=true

# Media and Request Payload Bounds
VIREL_MAX_REQUEST_MB=128
VIREL_MAX_PDF_MB=50
VIREL_MAX_PDF_PAGES=1000
VIREL_MAX_AUDIO_MB=25
VIREL_MAX_VIDEO_MB=50
VIREL_MAX_GENERATED_IMAGE_MB=20
VIREL_MAX_GENERATED_AUDIO_MB=50
```
</details>

### Step 3: Google Account Authentication

Authenticate your Google account(s) once in the persistent profile:

```powershell
# Primary account (authuser=0)
python get_session.py

# Optional: Sign in additional accounts for automatic quota rotation
python get_session.py --authuser 1
```

1. A Chromium window will open—sign in with your Google account.
2. Accept any initial Google AI Studio onboarding modals until the prompt box and **Run** button appear.
3. Return to the terminal and press **Enter** to save the session metadata and close the browser.

### Step 4: Launch the Gateway

```powershell
python app.py
# Optional: Reset all account cooldown timers on startup
python app.py --reset-accounts
```

The gateway is now live at **`http://127.0.0.1:8000`**.

<details>
<summary><b>🐳 Alternative: Docker Deployment</b></summary>

```bash
# Build the Docker image
docker build -t virel-ai .

# Run container mapping port 8000 and the runtime volume
docker run -d \
  -p 8000:8000 \
  --shm-size=2gb \
  -v ./runtime:/app/runtime \
  --env-file .env \
  --name virel-gateway \
  virel-ai
```
</details>

<img src="https://user-images.githubusercontent.com/73097560/115834477-dbab4500-a447-11eb-908a-139a6edaec5c.gif" width="100%" alt="Divider" />

## 🔌 Client Configurations

<details open>
<summary><b>🟣 Claude Code CLI & Claude Desktop</b></summary>

#### Claude Code CLI
```powershell
$env:ANTHROPIC_BASE_URL = "http://localhost:8000/claude"
$env:ANTHROPIC_API_KEY = "your-generated-hex-key-here"

claude --model gemini-flash-latest
```

#### Claude Desktop (`claude_desktop_config.json`)
```json
{
  "gateway": {
    "url": "http://localhost:8000/claude",
    "api_key": "your-generated-hex-key-here"
  }
}
```
</details>

<details open>
<summary><b>🟢 Codex Desktop (<code>config.toml</code>)</b></summary>

```toml
model = "gemini-flash-latest"
model_provider = "virel"
model_reasoning_effort = "high"

[model_providers.virel]
name = "Virel AI"
base_url = "http://localhost:8000/v1"
env_key = "VIREL_API_KEY"
wire_api = "responses"
requires_openai_auth = false
request_max_retries = 0
stream_max_retries = 0
stream_idle_timeout_ms = 1200000
```
</details>

<details>
<summary><b>🔵 VS Code (Cline & Continue)</b></summary>

#### Cline
* **Provider**: `OpenAI Compatible`
* **Base URL**: `http://localhost:8000/v1`
* **API Key**: `your-generated-hex-key-here`
* **Model ID**: `gemini-flash-latest`

#### Continue (`.continue/models/virel.yaml`)
```yaml
name: Virel Gemini Flash
version: 1.0.0
schema: v1
models:
  - name: Virel Gemini Flash
    provider: openai
    model: gemini-flash-latest
    apiBase: http://localhost:8000/v1
    apiKey: ${{ secrets.VIREL_API_KEY }}
    useResponsesApi: false
    roles: [chat, edit, apply]
    capabilities: [tool_use, image_input]
    defaultCompletionOptions:
      contextLength: 65536
      maxTokens: 8192
```
</details>

<details>
<summary><b>🟠 OpenCode (<code>opencode.json</code>)</b></summary>

```json
{
  "$schema": "https://opencode.ai/config.json",
  "model": "virel/gemini-flash-latest",
  "small_model": "virel/gemini-flash-latest",
  "enabled_providers": ["virel"],
  "provider": {
    "virel": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Virel AI",
      "options": {
        "baseURL": "http://localhost:8000/v1",
        "apiKey": "{env:VIREL_API_KEY}"
      },
      "models": {
        "gemini-flash-latest": {
          "name": "Gemini Flash Latest via Virel"
        }
      }
    }
  }
}
```
</details>

<details>
<summary><b>🟡 n8n Workflows & LangChain / LangGraph (Python)</b></summary>

#### n8n OpenAI Credential
* **Base URL**: `http://host.docker.internal:8000/v1` (Docker) or `http://127.0.0.1:8000/v1` (Local)
* **API Key**: `your-generated-hex-key-here`
* **Supported Nodes**: `Chat Model (OpenAI)`, `Message a Model`, `Generate an Image`, `Edit an Image`, `Transcribe an Audio`, `Generate Audio`.

#### LangChain / LangGraph
```python
from langchain_openai import ChatOpenAI

model = ChatOpenAI(
    model="gemini-flash-latest",
    base_url="http://localhost:8000/v1",
    api_key="your-generated-hex-key-here",
    streaming=True,
    max_retries=0,
)

for chunk in model.stream("Analyze this codebase architecture."):
    print(chunk.text, end="", flush=True)
```
</details>

<details>
<summary><b>🧩 Native Model Context Protocol (MCP) Server (<code>/mcp</code>)</b></summary>

Virel AI exposes a built-in **Streamable HTTP MCP Server** at `http://localhost:8000/mcp` providing 3 native tools (`virel_generate_image`, `virel_generate_speech`, and `virel_web_research` with live Google Search Grounding) to any MCP-compatible IDE or agent:

#### Claude Code CLI
```powershell
claude mcp add --transport http virel http://localhost:8000/mcp --header "Authorization: Bearer your-generated-hex-key-here"
```

#### Cursor / Windsurf / Cline / Claude Desktop (`mcpServers`)
```json
{
  "mcpServers": {
    "virel-ai": {
      "url": "http://localhost:8000/mcp",
      "headers": {
        "Authorization": "Bearer your-generated-hex-key-here"
      }
    }
  }
}
```
</details>

<img src="https://user-images.githubusercontent.com/73097560/115834477-dbab4500-a447-11eb-908a-139a6edaec5c.gif" width="100%" alt="Divider" />

## 📡 API Reference & Protocol Matrix

| Protocol | Route | Method | Description |
| :--- | :--- | :---: | :--- |
| **OpenAI Chat** | `/v1/chat/completions` | `POST` | Standard Chat Completions with JSON or SSE streaming & tool loops |
| **OpenAI Responses** | `/v1/responses` | `POST` | Modern Responses API with structured output items & namespaces |
| **Anthropic Messages** | `/v1/messages` | `POST` | Native Anthropic Messages endpoint for Claude Code |
| **Claude Desktop** | `/claude/v1/messages` | `POST` | Desktop client endpoint with automatic `claude-*` model alias mapping |
| **Image Generation** | `/v1/images/generations` | `POST` | Text-to-image synthesis using AI Studio image models (`gemini-3.1-flash-lite-image`) |
| **Image Editing** | `/v1/images/edits` | `POST` | Image-to-image variations and multimodal reference modifications |
| **Audio Speech (TTS)** | `/v1/audio/speech` | `POST` | Text-to-speech synthesis (`gemini-3.8-flash-tts`) with selectable voices & formats |
| **Audio Transcription**| `/v1/audio/transcriptions` | `POST` | Verbatim audio transcription & `/v1/audio/translations` |
| **File Store** | `/v1/files` | `POST/GET/DELETE` | Temporary validated local file uploads (`file-*` IDs) |
| **MCP Server** | `/mcp` | `POST/GET` | Native JSON-RPC 2.0 MCP server (`virel_generate_image`, `virel_generate_speech`, `virel_web_research`) |
| **Model Catalog** | `/v1/models` | `GET` | Live catalog of observed models in Google AI Studio (`?refresh=true`) |
| **Account Quota** | `/accounts` & `/accounts/reset`| `GET/POST` | View multi-account status, cooldown timers, and reset rate limits |
| **System Health** | `/health` | `GET` | Server readiness, active account, RAM pool stats, and concurrency state |

---

## 📄 License

Virel AI is licensed under the **[Apache License 2.0](LICENSE)**.  
Copyright © 2026 **Ahmed AbdElHady Esmail** — see [NOTICE](NOTICE) for details.

<div align="center">
  <img src="https://capsule-render.vercel.app/api?type=waving&color=0:10B981,50:059669,100:0F172A&height=110&section=footer" width="100%" alt="Footer Wave" />
</div>