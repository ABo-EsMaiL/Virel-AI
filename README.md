<div align="center">

<a href="https://github.com/ABo-EsMaiL/Virel-AI">
  <img src="assets/logo.png" alt="Virel AI Logo" width="130" height="130" style="border-radius: 26px;" />
</a>

# Virel AI

### High-Performance Local AI Studio Gateway for Autonomous Coding Agents

<p align="center">
  <a href="https://readme-typing-svg.demolab.com">
    <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=600&size=20&pause=1000&color=10B981&center=true&vCenter=true&width=750&lines=Local+Browser+Gateway+for+Google+AI+Studio;Full+OpenAI%2C+Anthropic+%26+Responses+API+Parity;Zero-Cost+Gemini+3.8+Flash+%26+Pro+Inference;Native+Tool+Loops+for+Codex%2C+Claude+Code+%26+Cline;Production-Grade+Multi-Account+Quota+Rotation" alt="Typing SVG" />
  </a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Powered_By-Google_AI_Studio-4285F4.svg?logo=google&logoColor=white" alt="Google AI Studio" />
  <img src="https://img.shields.io/badge/Model-Gemini_3.8_Flash_%26_Pro-8E24AA.svg?logo=google&logoColor=white" alt="Gemini 3.8" />
  <img src="https://img.shields.io/badge/Clients-Codex_|_Claude_Code_|_Cline_|_n8n-FF6F00.svg" alt="Autonomous Agents" />
  <img src="https://img.shields.io/badge/Quota-Auto_Account_Rotation-00C853.svg" alt="Auto Quota Rotation" />
  <img src="https://img.shields.io/badge/PRs-Welcome-brightgreen.svg" alt="PRs Welcome" />
  <img src="https://img.shields.io/badge/Python-3.12+-3776AB.svg?logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/Playwright-Chromium-2EAD33.svg?logo=playwright&logoColor=white" alt="Playwright" />
  <img src="https://img.shields.io/badge/FastAPI-Framework-009688.svg?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED.svg?logo=docker&logoColor=white" alt="Docker" />
  <img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License" />
</p>

---

</div>

## Overview

**Virel AI** is a local gateway that connects modern autonomous coding agents to **Google AI Studio**. Instead of paying prohibitive per-token API costs or running into strict free-tier rate limits, Virel AI exposes standard HTTP interfaces (**OpenAI Chat Completions**, **OpenAI Responses API**, and **Anthropic Messages API**) driven by an automated, persistent Chromium session in Google AI Studio.

Your developer tools and orchestration workflows connect to Virel AI as if it were an official API provider. Under the hood, Virel AI handles DOM automation, native tool continuation loops, streaming response emulation, multimodal file uploads, and transparent Google account rotation when daily request limits are met.

---

## Architectural Highlights

```mermaid
flowchart LR
    subgraph Clients["Autonomous Clients & Agents"]
        direction TB
        C1["Codex Desktop"]
        C2["Claude Code"]
        C3["VS Code (Cline / Continue)"]
        C4["n8n Workflows"]
        C5["LangChain / LangGraph"]
    end

    subgraph Virel["Virel AI Gateway (:8000)"]
        direction TB
        GW["FastAPI Core & Router"]
        BP["Browser Pool & RAM Admission"]
        TR["Tool Continuation Engine"]
        AR["Multi-Account Quota Rotation"]
        GW --> BP
        BP --> TR
        TR --> AR
    end

    subgraph Browser["Chromium Engine"]
        direction TB
        PW["Playwright Persistent Context"]
        T1["Isolated Task Tab 1"]
        T2["Isolated Task Tab 2"]
        PW --> T1
        PW --> T2
    end

    subgraph Google["Google AI Studio"]
        direction TB
        GS["Gemini 3.8 Flash / Pro"]
        TTS["Flash TTS Audio"]
        IMG["Flash Lite Image Gen"]
    end

    C1 --> GW
    C2 --> GW
    C3 --> GW
    C4 --> GW
    C5 --> GW
    AR --> PW
    T1 --> GS
    T2 --> GS
```

### Key Technical Pillars

- **Full Protocol Parity**: Native compatibility with `/v1/chat/completions`, `/v1/responses`, `/v1/messages`, and `/claude/v1/messages`.
- **Client-Owned Tool Continuation**: Clients execute their own tools locally. Virel AI retains the exact browser chat turn until the entire multi-turn tool cycle concludes.
- **Cryptographic Multi-Tenant Tab Isolation**: Every incoming request receives its own dedicated browser page. Different clients operating concurrently (such as Codex, Hermes, and n8n) are strictly partitioned by authorization hashes.
- **Multi-Account Quota Rotation**: Automatically shifts to the next configured Google account (`authuser=0`, `authuser=1`, etc.) upon detecting rate limits (HTTP 429) or daily quotas, tracking cooldown periods automatically.
- **Multimodal Processing**: Native ingestion of text, source code, large PDFs, audio, video, and images, along with native image generation and speech synthesis (TTS).

---

## Enterprise Showcase: The Ofok Operations Lab

A production-grade, 58-node autonomous multi-agent business workflow built natively in **n8n**, powered by **Gemini 3.8 Flash** via Virel AI.

<div align="center">

[![Virel AI - Ofok Operations Lab](assets/n8n_workflow.png)](assets/n8n_workflow.png)

<p align="center">
  <a href="assets/n8n_workflow.png"><b>View Full-Resolution Diagram</b></a> &nbsp;|&nbsp; 
  <a href="examples/n8n_ofok_operations_lab.json"><b>Download Workflow JSON</b></a>
</p>

</div>

### Verified Operations Matrix

| Operations Domain | Integrated Nodes | Execution Nature |
|---|---|---|
| **Central Intelligence** | OpenAI Chat Model (`:8000/v1`) | Gemini 3.8 Flash with high reasoning effort |
| **Omnichannel Ingestion**| Telegram, WhatsApp, n8n Chat | Customer service and executive reporting channels |
| **Sequential Multimodal**| Voice Transcribe, Vision, PDF Extractor | Preprocessing incoming multimedia before agent reasoning |
| **Enterprise Database** | Google Sheets ERP (6 Tabs) | Read/Save for Employees, Customers, Inventory, Tickets, Tasks, Knowledge |
| **Business Execution** | SearchApi, Gmail API, Calculator | Real-time market research, financial math, executive report dispatch |
| **Developer Extensibility**| Model Context Protocol (MCP) | Read-only MCP server exposing ERP knowledge to IDE agents |

---

## Quick Start

### Prerequisites

- Python 3.12 or higher
- Google Chrome or Chromium installed
- A Google account with access to [Google AI Studio](https://aistudio.google.com/)

---

### Step 1: Clone and Setup Environment

```powershell
# Clone the repository
git clone https://github.com/ABo-EsMaiL/Virel-AI.git
cd Virel-AI

# Create and activate virtual environment
python -m venv .venv
./.venv/Scripts/Activate.ps1

# Install dependencies and Playwright browser
pip install -r requirements.txt
playwright install chromium
```

---

### Step 2: Generate API Key and Configure `.env`

Generate a secure random 32-byte hexadecimal key for your local gateway:

**Using OpenSSL:**
```powershell
openssl rand -hex 32
```

**Or using Python:**
```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Copy the example configuration:
```powershell
Copy-Item .env.example .env
```

Open `.env` and configure your parameters:

```ini
# ==============================================================================
# Virel AI Gateway - Environment Configuration
# ==============================================================================

# Master API Key required in client requests (Authorization: Bearer <key>)
VIREL_API_KEY=your-generated-hex-key-here

# Persistent browser profile folder (where Google account login is stored)
CHROME_PROFILE_DIR=./chrome_profile

# Server Port (default 8000)
PORT=8000

# Browser visibility (false = visible window for inspection, true = headless)
HEADLESS=false

# Default model used when no explicit model is specified
DEFAULT_MODEL=gemini-flash-latest

# Default thinking level for reasoning models (high, low, or minimal)
THINKING_MODE=high

# Multi-Account Quota Rotation (Google authuser indices: 0, 1, 2...)
VIREL_GOOGLE_ACCOUNTS_COUNT=2
VIREL_ACCOUNT_COOLDOWN_HOURS=6

# Concurrency & Memory Management
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

# Built-in Google AI Studio tools for ordinary prompts
ENABLE_URL_CONTEXT=true
ENABLE_SEARCH_GROUNDING=false

# Media and Request Payload Bounds
VIREL_MAX_REQUEST_MB=128
VIREL_MAX_PDF_MB=50
VIREL_MAX_PDF_PAGES=1000
VIREL_MAX_AUDIO_MB=25
VIREL_MAX_VIDEO_MB=50
VIREL_MAX_GENERATED_IMAGE_MB=20
VIREL_MAX_GENERATED_AUDIO_MB=50
```

---

### Step 3: Google Account Authentication

To authenticate your Google account in the persistent profile:

```powershell
python get_session.py
```

1. A Chromium browser window will open.
2. Sign in with your Google account.
3. Navigate to [Google AI Studio](https://aistudio.google.com/), accept any initial onboarding modals.
4. If configuring multiple accounts (`authuser=0`, `authuser=1`), switch to each account in Google AI Studio to initialize them.
5. Close the browser window once done.

---

### Step 4: Launch the Gateway

```powershell
python app.py
```

The gateway is now running at `http://127.0.0.1:8000`.

---

### Alternative: Docker Deployment

To run Virel AI inside a container:

```bash
# Build the Docker image
docker build -t virel-ai .

# Run container mapping port 8000 and the browser profile volume
docker run -d \
  -p 8000:8000 \
  -v ./chrome_profile:/app/runtime/browser-profile \
  --name virel-gateway \
  virel-ai
```

---

## Client Configurations

### Codex Desktop

Configure Virel AI as a custom provider in your Codex configuration file (`config.toml`):

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

---

### Claude Desktop & Claude Code CLI

#### Claude Desktop (Third-Party Gateway)
In your `claude_desktop_config.json`, configure the gateway URL pointing to the `/claude` base:

```json
{
  "gateway": {
    "url": "http://localhost:8000/claude",
    "api_key": "your-generated-hex-key-here"
  }
}
```

#### Claude Code CLI
Point Claude Code to the dedicated `/claude` endpoint:

```powershell
$env:ANTHROPIC_BASE_URL = "http://localhost:8000/claude"
$env:ANTHROPIC_API_KEY = "your-generated-hex-key-here"

claude --model gemini-flash-latest
```

---

### OpenCode

In your `opencode.json` configuration:

```json
{
  "api_endpoint": "http://localhost:8000/v1",
  "api_key": "your-generated-hex-key-here",
  "model": "gemini-flash-latest",
  "temperature": 0.2
}
```

---

### VS Code (Cline & Continue)

In your VS Code extension settings:
- **Provider**: OpenAI Compatible
- **Base URL**: `http://localhost:8000/v1`
- **API Key**: `your-generated-hex-key-here`
- **Model ID**: `gemini-flash-latest`

---

### n8n Automation Workflows

When adding an OpenAI credential in n8n:
- **Credential**: OpenAI API
- **API Key**: `your-generated-hex-key-here`
- **Base URL**: `http://host.docker.internal:8000/v1` (if n8n runs in Docker) or `http://127.0.0.1:8000/v1`
- **Supported Nodes**:
  - `Chat Model (OpenAI)` -> For AI Agents and conversational agents.
  - `Message a Model` -> For both Chat Completions and modern Responses API.
  - `Generate an Image` & `Edit an Image` -> Native binary output via `gemini-3.1-flash-lite-image`.
  - `Transcribe an Audio` -> Native audio transcription.

---

### LangChain & LangGraph (Python)

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

---

## API Reference & Supported Endpoints

| Protocol | Route | Method | Description |
|---|---|---|---|
| **OpenAI Chat** | `/v1/chat/completions` | `POST` | Standard Chat Completions with JSON or SSE streaming |
| **OpenAI Responses** | `/v1/responses` | `POST` | Modern Responses API with structured output items |
| **Anthropic Messages** | `/v1/messages` | `POST` | Anthropic Messages endpoint for Claude Code |
| **Claude Desktop** | `/claude/v1/messages` | `POST` | Third-party desktop client endpoint with Claude model aliases |
| **Image Generation** | `/v1/images/generations` | `POST` | Text-to-image synthesis using AI Studio image models |
| **Image Editing** | `/v1/images/edits` | `POST` | Image-to-image variations and modifications |
| **Audio Speech** | `/v1/audio/speech` | `POST` | Text-to-speech generation (TTS) with selectable voices |
| **Model Catalog** | `/v1/models` | `GET` | Live catalog of observed models in AI Studio |
| **System Health** | `/health` | `GET` | Server readiness, active account, and concurrency state |

---

## License

Virel AI is licensed under the [Apache License 2.0](LICENSE).  
Copyright 2026 Ahmed AbdElHady Esmail; see [NOTICE](NOTICE).
