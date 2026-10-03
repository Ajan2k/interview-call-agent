# 🤖 TalentAI — Autonomous AI Interview Agent Platform

> An end-to-end autonomous AI-powered technical and behavioral interview platform. It ingests candidate resumes, extracts experience profiles, analyzes target job descriptions, autonomously creates personalized technical and behavioral questions, conducts real-time conversational phone interviews, and delivers comprehensive AI evaluation scorecards.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Autonomous Interview Workflow](#autonomous-interview-workflow)
- [Tech Stack](#tech-stack)
- [Project Architecture](#project-architecture)
- [Prerequisites](#prerequisites)
- [Setup & Installation](#setup--installation)
- [Environment Variables](#environment-variables)
- [Running the Application](#running-the-application)
- [API Reference](#api-reference)
- [Testing & Quality Verification](#testing--quality-verification)

---

## Overview

**TalentAI Interview Agent** transforms traditional recruiting by automating the preliminary screening process:

1. **Candidate Dossier Ingestion** — Upload PDF or DOCX candidate resumes alongside the target Job Description (JD), candidate name, phone number, and position.
2. **Autonomous Question Formulation** — The LLM analyzes the candidate's resume and compares it against the JD to autonomously generate **up to 10 personalized technical questions** focused on skills, architectural decisions, and gap areas, paired with **5 fixed behavioral questions** using the STAR methodology (Situation, Task, Action, Result).
3. **Voice Screening Execution** — The voice engine initiates or receives the candidate's call via SIP/WebRTC, conducts an empathetic, natural screening interview, manages speaking turn-taking, and records candidate responses.
4. **Automated AI Scorecard & Evaluation** — At the conclusion of the interview, the AI generates a multi-dimensional evaluation scorecard: overall score (0-100), hire/reject recommendation, technical/behavioral/communication ratings, key strengths, areas for improvement, and a hiring manager summary.

---

## Key Features

- 📄 **Resume Parsing (PDF & DOCX)** — Robust document extraction using `pypdf` and `python-docx` with fallback text parsing.
- 🎯 **Autonomous Question Generation** — Up to 10 tailored technical questions based directly on the intersection of candidate resume projects and JD requirements.
- 💬 **5 Fixed Behavioral Questions** — Pre-configured STAR-framework behavioral questions editable directly in the UI or settings.
- 🎙️ **Real-Time Voice Conversational Engine** — Sub-500ms audio pipeline with Azure Speech (TTS/STT), Groq LLaMA models, and SIP.js WebRTC audio bridge.
- 🌐 **Multilingual Voice Capabilities** — Fluent conversational support across English, Tamil, Hindi, Telugu, Kannada, and Malayalam.
- 📊 **Automated AI Scorecard & Dossier** — Instant evaluation of interview transcripts against target JD competencies.
- 💼 **Recruiter Pipeline Dashboard** — Sleek React + Tailwind UI for managing candidates, reviewing roadmaps, initiating calls, and inspecting scorecards.

---

## Autonomous Interview Workflow

```
Candidate Upload (PDF/DOCX Resume + JD + Role)
                 │
                 ▼
Document Parsing (`document_parser.py`)
                 │
                 ▼
Autonomous Question Generation (`interview_service.py`)
  ├── 5 Fixed Behavioral Questions (STAR Method)
  └── Up to 10 Personalized Technical Questions (Resume + JD)
                 │
                 ▼
Candidate Interview Call (SIP / WebRTC / Phone)
  ├── Warm greeting & confirmation
  ├── Structured, conversational Q&A
  └── Real-time streaming voice loop
                 │
                 ▼
Automated AI Scorecard Generation
  ├── Overall Score (0-100) & Hire/Consider/Reject Recommendation
  ├── Technical (0-100), Behavioral (0-100), Communication (0-100)
  ├── Strengths & Improvement Areas
  └── Executive Summary
```

---

## Tech Stack

### Backend
| Technology | Purpose |
|---|---|
| **FastAPI** | High-performance async REST & WebSocket server |
| **Groq API (LLaMA)** | High-speed LLM inference for question generation, dialogue & evaluation |
| **Azure Speech Services** | Neural Text-to-Speech (TTS) & Speech-to-Text (STT) |
| **pypdf & python-docx** | Document extraction for resumes |
| **PostgreSQL** | Primary persistence store with JSON fallback |
| **Pydantic v2** | Data schema validation and serialization |

### Frontend
| Technology | Purpose |
|---|---|
| **React 19** | Modern UI framework |
| **Vite** | Build tool & HMR dev server |
| **TypeScript** | End-to-end type safety |
| **Tailwind CSS v4** | Clean design system |
| **SIP.js** | VoIP/SIP protocol integration |
| **Lucide React** | Icons |

---

## Project Architecture

```
AI-Call-Agent/
├── backend/
│   ├── main.py                  # FastAPI application entry point
│   ├── requirements.txt         # Python dependencies (includes pypdf, python-docx)
│   ├── core/                    # Core configuration and logging
│   │   ├── config.py            # Pydantic BaseSettings, SecretStr, PostgresDsn
│   │   └── logging.py           # Structured logging and request filtering
│   ├── models/                  # Domain entities
│   │   ├── candidate.py         # Candidate, Question, Scorecard models
│   │   ├── contact.py           # Contact entity
│   │   ├── campaign.py          # Campaign entity
│   │   ├── call.py              # Call records
│   │   └── voice_config.py      # Voice configuration entity
│   ├── schemas/                 # Pydantic request/response schemas
│   │   ├── candidate.py         # CandidateCreate, ScorecardSchema, QuestionSchema
│   │   ├── contact.py
│   │   └── ...
│   ├── services/                # Business services & repositories
│   │   ├── document_parser.py   # PDF & DOCX text extraction
│   │   ├── interview_service.py # Autonomous question generation & evaluation
│   │   ├── candidate_repository.py # Candidate database persistence
│   │   ├── database_manager.py  # PostgreSQL manager
│   │   └── voice/               # Modular Voice AI engine
│   │       ├── session_manager.py # Voice state machine & candidate session binding
│   │       ├── prompts.py       # Candidate interview prompt generator
│   │       ├── llm.py           # Multi-provider LLM streaming
│   │       ├── tts.py           # Azure / Sarvam / Cartesia TTS
│   │       └── stt.py           # Whisper / Azure STT
│   ├── routes/                  # API routers
│   │   ├── candidates.py        # /api/candidates endpoints (CRUD, upload, evaluate)
│   │   ├── voice.py             # WebSocket audio stream (/api/voice/teleforce_stream)
│   │   ├── voice_config.py      # /api/voice-config
│   │   └── ...
│   └── tests/                   # Pytest test suite (95 passing tests)
│
└── frontend/
    ├── src/
    │   ├── App.tsx              # Main dashboard with Candidate Pipeline navigation
    │   ├── types.ts             # TypeScript definitions (Candidate, Scorecard, Question)
    │   ├── components/
    │   │   ├── CandidateManager.tsx # Candidate cards, resume dropzone, scorecards & roadmap
    │   │   ├── TeleforceAgent.tsx   # Live call keypad, WebRTC audio bridge & live badge
    │   │   ├── Metrics.tsx
    │   │   ├── CallLogs.tsx
    │   │   ├── CallHistory.tsx
    │   │   ├── Reports.tsx
    │   │   └── ScheduleTracker.tsx
    │   └── utils/
    └── package.json
```

---

## Prerequisites

- **Python 3.10+**
- **Node.js 18+** and **npm**
- **PostgreSQL 13+** (optional; in-memory / JSON fallback operates automatically if database is unavailable)
- **Groq API Key** — [console.groq.com](https://console.groq.com)
- **Azure Speech Services Key** — [portal.azure.com](https://portal.azure.com)

---

## Setup & Installation

### 1. Backend Setup

```bash
cd backend

# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate       # Windows
# source venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Create .env from template
copy .env.example .env
```

### 2. Frontend Setup

```bash
cd frontend
npm install
copy .env.example .env
```

---

## Environment Variables

### Backend (`backend/.env`)

```env
# Groq LLM API
GROQ_API_KEY=your_groq_api_key_here

# Azure Speech Services (TTS & STT)
AZURE_SPEECH_KEY=your_azure_speech_key_here
AZURE_SPEECH_REGION=centralindia

# PostgreSQL Database (Optional)
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_db_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=skyagent
```

---

## Running the Application

### Start the Backend Server

```bash
cd backend
venv\Scripts\activate
uvicorn main:app --reload --port 8000
```

- API Base: `http://localhost:8000`
- Interactive Swagger Documentation: `http://localhost:8000/docs`

### Start the Frontend Dev Server

```bash
cd frontend
npm run dev
```

- Dashboard: `http://localhost:5173`

---

## API Reference

### Candidate & Interview Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/candidates` | Create candidate with multipart form (Resume PDF/DOCX, name, phone, position, JD) |
| `GET` | `/api/candidates` | List all candidates in pipeline with interview status & scores |
| `GET` | `/api/candidates/{id}` | Get candidate dossier, questions roadmap, and scorecard |
| `PUT` | `/api/candidates/{id}/questions` | Update or customize the candidate's interview questions |
| `POST` | `/api/candidates/{id}/evaluate` | Trigger AI evaluation and scorecard generation |
| `DELETE` | `/api/candidates/{id}` | Remove candidate from pipeline |
| `GET` | `/api/candidates/behavioral-defaults` | Get standard 5 STAR behavioral questions |

### Voice & Call Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `WS` | `/api/voice/teleforce_stream` | Bi-directional WebSocket audio bridge for live interview calls |
| `GET` | `/api/voice-config` | Retrieve current interviewer persona and prompt configuration |
| `POST` | `/api/voice-config` | Update interviewer persona and prompt configuration |
| `GET` | `/api/health` | System health check and API key verification |

---

## Testing & Quality Verification

Run the comprehensive pytest test suite (covers candidate parsing, autonomous question generation, scorecards, audio processing, markers, and REST endpoints):

```bash
cd backend
python -m pytest
```

Build the frontend bundle to ensure strict TypeScript validation:

```bash
cd frontend
npm run build
```
