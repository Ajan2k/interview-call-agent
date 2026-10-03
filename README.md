# 🤖 TeleForce Agent — AI Calling Agent Platform

> An end-to-end AI-powered voice calling platform that makes outbound sales calls and handles inbound customer queries — in **Tamil, English, Hindi, and more** — 24/7, without human intervention.

Built for **Daffytel Technologies** to power *Daffy*, an AI sales agent that books demos, captures leads, and handles objections naturally over the phone.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Setup & Installation](#setup--installation)
- [Environment Variables](#environment-variables)
- [Running the Application](#running-the-application)
- [API Reference](#api-reference)
- [Dashboard Overview](#dashboard-overview)

---

## Overview

TeleForce Agent is a full-stack AI calling platform consisting of:

- **Backend** — FastAPI server that manages WebSocket voice sessions, PostgreSQL data storage, call logging, and REST APIs.
- **Frontend** — React + Vite dashboard for monitoring live calls, viewing call logs, tracking leads, scheduling, and exporting reports.
- **AI Voice Agent (Daffy)** — Powered by Groq (LLM) + Azure Speech Services (TTS/STT), capable of natural multilingual conversations with automatic language detection.

---

## Features

- 🎙️ **Real-time Voice AI** — WebSocket-based bidirectional audio streaming with Azure Speech STT and TTS
- 🧠 **LLM-Powered Conversations** — Groq API (LLaMA) drives natural, context-aware responses
- 🌐 **Multilingual Support** — Tamil, English, Hindi, Telugu, and more with automatic language detection
- 📋 **Lead Capture** — Automatically extracts lead details (name, business, phone, need) from conversations
- 📅 **Meeting Booking** — Detects demo bookings and callback requests from conversation context
- 📊 **Live Dashboard** — Real-time call monitoring, metrics, call history, conversation logs
- 📤 **Reports & Export** — Download call logs and lead reports as CSV
- 🔒 **Secure Config** — All API keys managed via environment variables, never hardcoded

---

## Tech Stack

### Backend
| Technology | Purpose |
|---|---|
| **FastAPI** | REST API + WebSocket server |
| **Uvicorn** | ASGI server |
| **Groq API** | LLM inference (LLaMA models) |
| **Azure Speech SDK** | Speech-to-Text & Text-to-Speech |
| **PostgreSQL** | Persistent storage (calls, leads, meetings, contacts) |
| **psycopg2** | PostgreSQL driver |
| **python-dotenv** | Environment variable management |

### Frontend
| Technology | Purpose |
|---|---|
| **React 19** | UI framework |
| **Vite** | Build tool & dev server |
| **TypeScript** | Type safety |
| **Tailwind CSS v4** | Styling |
| **SIP.js** | SIP/VoIP protocol support |
| **Lucide React** | Icons |
| **XLSX** | Excel report exports |

---

## Project Structure

```
teleforce-agent/
├── backend/
│   ├── main.py               # FastAPI app entry point (lifespan managed)
│   ├── requirements.txt      # Python dependencies
│   ├── .env.example          # Environment variable template
│   ├── pytest.ini            # Pytest configuration
│   ├── core/                 # Central application configuration & logging
│   │   ├── config.py         # BaseSettings, SecretStr, PostgresDsn & default_factory
│   │   ├── logging.py        # Centralized structured logging & polling noise filter
│   │   └── __init__.py
│   ├── routes/               # Modular category routes
│   │   ├── voice.py          # WebSocket voice session router & endpoint (/api/voice/teleforce_stream)
│   │   ├── health.py         # /api/health
│   │   ├── contacts.py       # /api/contacts
│   │   ├── campaigns.py      # /api/campaigns
│   │   ├── calls.py          # /api/call-history, /api/recordings
│   │   ├── meetings.py       # /api/meetings
│   │   ├── callbacks.py      # /api/callbacks
│   │   ├── reports.py        # /api/report
│   │   ├── voice_config.py   # /api/voice-config
│   │   ├── translate.py      # /api/translate
│   │   ├── logs.py           # /api/logs
│   │   └── __init__.py       # Combined API router
│   ├── models/               # Object-oriented domain entities
│   │   ├── contact.py        # Contact dataclass
│   │   ├── campaign.py       # Campaign dataclass
│   │   ├── call.py           # Call dataclass
│   │   ├── meeting.py        # Meeting dataclass
│   │   ├── callback.py       # Callback dataclass
│   │   └── voice_config.py   # VoiceConfig dataclass
│   ├── schemas/              # Pydantic request/response validation
│   │   ├── contact.py
│   │   ├── campaign.py
│   │   ├── call.py
│   │   ├── meeting.py
│   │   ├── callback.py
│   │   ├── voice_config.py
│   │   ├── translate.py
│   │   ├── report.py
│   │   ├── health.py
│   │   └── log.py
│   ├── services/             # Class-based repositories & business services
│   │   ├── database_manager.py # DatabaseManager & entity repositories
│   │   ├── report_service.py   # ReportService & CSV generator
│   │   ├── translation_service.py # TranslationService (Sarvam)
│   │   ├── log_service.py      # LogService
│   │   └── voice/              # Modular Voice AI subsystems
│   │       ├── audio.py        # AudioProcessor & CallRecorder
│   │       ├── markers.py      # MarkerService & control tag parsing
│   │       ├── prompts.py      # PromptManager & multilingual scripts
│   │       ├── tts.py          # TTSService (Cartesia/Sarvam/Azure)
│   │       ├── stt.py          # STTService (Sarvam/Groq Whisper & language detection)
│   │       ├── llm.py          # LLMService (multi-provider streaming & fallback)
│   │       ├── session_manager.py # VoiceSessionManager (VAD loop & state machine)
│   │       └── __init__.py
│   ├── prompts/              # System prompt templates
│   │   ├── inbound_prompt.txt   # System prompt for inbound calls
│   │   └── outbound_prompt.txt  # System prompt for outbound calls (Daffy)
│   └── tests/                # Automated pytest suite (86 unit & integration tests)
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx               # Root application component
│   │   ├── main.tsx              # React entry point
│   │   ├── types.ts              # TypeScript interfaces
│   │   ├── index.css             # Tailwind CSS & custom design system
│   │   ├── components/
│   │   │   ├── ui/                  # Reusable UI design system & table components
│   │   │   │   ├── TableComponents.tsx
│   │   │   │   └── index.ts
│   │   │   ├── TeleforceAgent.tsx   # Main agent control panel & SIP integration
│   │   │   ├── CallLogs.tsx         # Live & historical call logs
│   │   │   ├── CallHistory.tsx      # Call history table
│   │   │   ├── Metrics.tsx          # Performance metrics
│   │   │   ├── Reports.tsx          # Reporting & CSV export
│   │   │   ├── ScheduleTracker.tsx  # Meeting/demo scheduler
│   │   │   ├── ConversationModal.tsx # Conversation detail view
│   │   │   └── LiveSimulator.tsx    # Browser-based call simulator
│   │   └── utils/
│   │       └── excelParser.ts    # Excel and CSV contact importer
│   ├── package.json
│   ├── vite.config.ts
│   └── .env.example
│
└── .gitignore
```

---

## Prerequisites

Make sure you have the following installed:

- **Python 3.10+**
- **Node.js 18+** and **npm**
- **PostgreSQL 13+**
- A **Groq API key** — [console.groq.com](https://console.groq.com)
- An **Azure Speech Services** key — [portal.azure.com](https://portal.azure.com)

---

## Setup & Installation

### 1. Clone the repository

```bash
git clone https://github.com/infinitetechchennai/AI-Call-Agent.git
cd AI-Call-Agent
```

### 2. Backend Setup

```bash
cd backend

# Create and activate virtual environment
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy env template and fill in your keys
copy .env.example .env
```

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Copy env template
copy .env.example .env
```

---

## Environment Variables

### Backend — `backend/.env`

```env
# Groq LLM API
GROQ_API_KEY=your_groq_api_key_here

# Azure Speech Services
AZURE_SPEECH_KEY=your_azure_speech_key_here
AZURE_SPEECH_REGION=centralindia

# PostgreSQL Database
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_db_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=skyagent

# Optional: Full connection string (overrides individual fields above)
# DATABASE_URL=postgresql://user:password@localhost:5432/skyagent
```

### Frontend — `frontend/.env`

```env
# Backend API URL (default points to local backend)
VITE_API_URL=http://localhost:8000
```

---

## Running the Application

### Start the Backend

```bash
cd backend
uvicorn main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`  
API docs (Swagger): `http://localhost:8000/docs`

### Start the Frontend

```bash
cd frontend
npm run dev
```

The dashboard will be available at `http://localhost:5173`

---

## 🧪 Running Tests & Quality Checks

### Backend Tests (pytest)

```bash
cd backend
python -m pytest
```

Runs the 79 automated unit and integration tests covering:
- Audio WAV buffering & RIFF header manipulation
- Control marker extraction (`[END_CALL]`, `[MEETING_BOOKED]`, `[CALLBACK]`, `[LEAD]`)
- Multi-provider TTS pipelines (Cartesia, Sarvam, Azure)
- LLM provider dispatching & prompt script loading
- FastAPI REST integration & error handling
- Dual-track call audio recorder & noise filtering

### Frontend Typecheck & Build

```bash
cd frontend
npm run lint       # TypeScript strict type checking
npm run build      # Production bundle generation
```

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Health check + API key status |
| `GET` | `/api/calls` | Fetch call history |
| `GET` | `/api/leads` | Fetch captured leads |
| `GET` | `/api/meetings` | Fetch booked meetings |
| `GET` | `/api/contacts` | Fetch contact list |
| `POST` | `/api/contacts` | Add a new contact |
| `GET` | `/api/campaigns` | Fetch campaigns |
| `POST` | `/api/campaigns` | Create a campaign |
| `GET` | `/api/voice-config` | Get current voice/prompt config |
| `PUT` | `/api/voice-config` | Update voice/prompt config |
| `GET` | `/api/export/calls` | Export calls as CSV |
| `GET` | `/api/recordings/{filename}` | Stream a call recording |
| `WS` | `/ws` | WebSocket voice session |

---

## Dashboard Overview

| Section | Description |
|---|---|
| **Agent Control** | Start/stop the AI agent, configure voice settings |
| **Call Logs** | Live call feed with conversation transcripts |
| **Call History** | Full historical call log with search & filter |
| **Metrics** | KPIs: total calls, leads, meetings, success rate |
| **Schedule Tracker** | View upcoming demos and callbacks |
| **Reports** | Generate and export CSV reports |

---

## ⚠️ Important Notes

- **Never commit your `.env` file** — it contains sensitive API keys
- The `backend/venv/` directory is excluded from git — always run `pip install -r requirements.txt` after cloning
- The `frontend/node_modules/` directory is excluded — always run `npm install` after cloning
- Call `recordings/` and `logs/` are excluded from git as they may contain personal data

---

## License

Private — All rights reserved © Daffytel Technologies
