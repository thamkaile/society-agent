# Genesis: AI-Powered Startup Blueprint Studio

**Genesis** is an intelligent multi-agent system that simulates a team of business specialists to generate comprehensive startup blueprints. It combines market research, product design, financial analysis, and risk assessment into interactive, real-time debate sessions.

## 🎯 What This Project Does

Genesis takes a business idea and runs it through a panel of AI specialist agents:
- **Root Coordinator** — orchestrates the planning workflow
- **Product Manager** — defines MVP scope and customer focus
- **UX Researcher** — analyzes customer problems and personas
- **Business Analyst** — evaluates market opportunity and business models
- **Research Agent** — validates assumptions with external data
- **Technical Lead** — designs system architecture
- **Finance Analyst** — projects unit economics and runway
- **Marketing Strategist** — defines go-to-market strategy
- **Legal Advisor** — identifies compliance and regulatory risks
- **Risk & Compliance Officer** — assesses execution risks

The agents debate in rounds, reach consensus, and generate a **12-section blueprint** including market research, financial projections, technical architecture, implementation roadmap, and investor pitch.

---

## 🏗️ Project Structure

```
.
├── backend/                 # FastAPI REST API + AI engine
│   ├── main.py             # FastAPI app entry point
│   ├── cli.py              # Command-line interface for batch processing
│   ├── run_server.py       # Start local API server
│   ├── requirements.txt    # Python dependencies (pip)
│   ├── config/             # Model configuration (OpenRouter LLM settings)
│   ├── api/                # HTTP route handlers (chat, sessions)
│   ├── services/           # Business logic (session management)
│   ├── persistence/        # SQLite ORM models & repositories
│   ├── dynamic_engine/     # Core multi-agent orchestration engine
│   ├── .python_deps/       # Vendored Python dependencies (cp312)
│   └── README.md           # Backend setup instructions
│
├── frontend/               # React + Vite + GSAP animations
│   ├── App.jsx             # Route dispatcher
│   ├── index.html          # Entry point
│   ├── package.json        # Frontend dependencies (npm)
│   ├── vite.config.js      # Vite dev server & API proxy
│   ├── src/
│   │   ├── pages/          # LandingPage, Dashboard, BlueprintPage
│   │   ├── components/     # AgentStatus, DebateFeed, IdeaInput, etc.
│   │   ├── services/       # API client (streaming SSE, session CRUD)
│   │   ├── utils/          # Blueprint section mapping & helpers
│   │   └── index.css       # Design tokens (colors, fonts, spacing)
│   └── vite.config.js
│
├── tests/                  # Test suite
└── .gitignore
```

---

## 🚀 Getting Started (Local Download & Setup)

### Prerequisites

- **Python 3.12** (required for vendored cp312 binary wheels in `backend/.python_deps`)
- **Node.js 18+** (for frontend)
- **Git**
- **pip** (Python package manager)

### Step 1: Clone or Download the Repository

```bash
git clone https://github.com/ETHAN071104/Global_AI_Hackathon_Series_with_Qwen_Cloud.git
cd Global_AI_Hackathon_Series_with_Qwen_Cloud
```

Or download as ZIP and extract locally.

### Step 2: Set Up Environment Variables

Create a `.env` file in the `backend/` directory:

```bash
cd backend
touch .env  # or create .env manually on Windows
```

Add your OpenRouter API key:

```env
OPENROUTER_API_KEY=your_api_key_here
FRONTEND_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173
```

### Step 3: Install Backend Dependencies

```bash
cd backend

# Create a Python virtual environment (optional but recommended)
python -m venv venv

# Activate the virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 4: Start the Backend API Server

```bash
# From the backend/ directory
python run_server.py
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
```

Verify the backend is working:
```bash
# In another terminal
curl http://127.0.0.1:8000/api/health
```

Expected response: `{"status":"ok"}`

### Step 5: Install Frontend Dependencies

```bash
cd frontend
npm install
```

### Step 6: Start the Frontend Development Server

```bash
# From the frontend/ directory
npm run dev
```

You should see:
```
  VITE v5.3.1  ready in 123 ms

  ➜  Local:   http://localhost:5173/
  ➜  press h to show help
```

Open **`http://localhost:5173`** in your browser (or `http://localhost:3000` if configured).

---

## 📋 Backend Dependencies (requirements.txt)

**`requirements.txt`** contains:

| Package | Version | Purpose |
|---------|---------|---------|
| `fastapi` | >=0.115,<1.0 | Web framework for REST API |
| `uvicorn[standard]` | >=0.30,<1.0 | ASGI application server |
| `SQLAlchemy` | >=2.0,<3.0 | ORM for database persistence |
| `pydantic` | >=2.0,<3.0 | Request/response validation |
| `python-dotenv` | >=1.0,<2.0 | Load environment variables from `.env` |
| `httpx` | >=0.27,<1.0 | HTTP client for API requests |
| `openai` | >=1.0,<2.0 | OpenAI/LLM API client |
| `tavily-python` | >=0.5,<1.0 | Search API for research agent |
| `camel-ai` | (latest) | Multi-agent orchestration framework |

**Install with:**
```bash
pip install -r backend/requirements.txt
```

---

## 📋 Frontend Dependencies (package.json)

**`package.json`** contains:

| Package | Version | Purpose |
|---------|---------|---------|
| `react` | ^18.3.1 | Component framework |
| `vite` | ^5.3.1 | Build tool & dev server |
| `@vitejs/plugin-react` | ^4.3.1 | React support for Vite |
| `lucide-react` | ^0.400.0 | Icon library |
| `react-icons` | ^5.6.0 | Supplementary icons |
| `gsap` | ^3.15.0 | Animation library |
| `@gsap/react` | ^2.1.2 | React bindings for GSAP |
| `three` | ^0.185.0 | 3D graphics library |
| `@react-three/fiber` | ^8.18.0 | React renderer for Three.js |
| `ogl` | ^1.0.11 | WebGL library |

**Install with:**
```bash
cd frontend && npm install
```

---

## 🎬 Quick Start Workflows

### Workflow 1: Create a New Startup Blueprint

**Terminal 1 (Backend):**
```bash
cd backend
python run_server.py
```

**Terminal 2 (Frontend):**
```bash
cd frontend
npm run dev
```

**Browser:**
1. Navigate to `http://localhost:5173`
2. Click **"New Idea"** on the landing page
3. Enter a business idea (e.g., "AI scheduling assistant for healthcare")
4. Click **"Start Simulation"**
5. Watch agents debate in real-time in the feed
6. Blueprint auto-generates as sections are finalized

### Workflow 2: Use CLI for Batch Processing

**Terminal (Backend):**
```bash
cd backend

# Create a new simulation
python cli.py new "AI-powered scheduling assistant for healthcare"

# Refine an existing session
python cli.py refine --chat-id=<uuid> "Add focus on HIPAA compliance"

# Inspect a session
python cli.py show --chat-id=<uuid>
```

---

## 🔧 Backend Architecture

### Core Components

**`main.py`** — FastAPI application  
- Sets up CORS for frontend origins (localhost:3000, localhost:5173)
- Registers two routers: `chat_router` and `session_router`
- Initializes SQLite database on startup

**`cli.py`** — Command-line interface  
- `python cli.py new "<idea>"` — start a new project
- `python cli.py refine --chat-id=<id> "<request>"` — refine an existing session
- `python cli.py show --chat-id=<id>` — inspect a saved session

**`dynamic_engine/engine.py`** — Multi-agent orchestrator  
- Orchestrates specialized agents through Root Coordinator
- Runs PM research planning, research validation, and round-table debate
- Streams real-time events to frontend via SSE

**`persistence/`** — SQLAlchemy models  
- `ChatSession` — session metadata (title, summary, timestamps)
- `ChatMessage` — individual messages with agent name, phase, metadata
- Repository pattern for transaction management

### API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/chat/stream` | Start/continue simulation (SSE stream) |
| GET | `/api/sessions` | List all saved sessions |
| GET | `/api/sessions/{chat_id}` | Fetch session + all messages |
| DELETE | `/api/sessions/{chat_id}` | Delete a session |
| GET | `/api/health` | Health check |

---

## 💻 Frontend Architecture

### Pages

**`LandingPage`** — Intro, tech stack showcase, proof metrics  
**`Dashboard`** — Chat interface, idea input, live agent feed  
**`BlueprintPage`** — Final blueprint with 12-section explorer  

### Core Services

**`api.js`** — HTTP client
- `streamSimulation({ message, chatId, onEvent, onError, onDone })` — stream SSE events
- `listSessions()` — fetch all sessions
- `getSession(chatId)` — load session with messages
- `deleteSession(chatId)` — remove a session

### UI Components

**`IdeaInput`** — Text input for new ideas  
**`DebateFeed`** — Live streaming of agent messages  
**`AgentStatus`** — Shows current phase and active agent  
**`SessionSidebar`** — List and switch between saved sessions  
**`BlueprintExplorer`** — Browse and export 12-section blueprint  

### Styling

- **Design tokens** in `src/index.css` — colors, fonts, shadows, spacing
- **Lucide React** — SVG icons (Sparkles, FileText, Users, etc.)
- **GSAP** — timeline animations and scroll effects
- **Three.js** — 3D WebGL canvas for architecture diagram

---

## 🛠️ Configuration

### Backend Config

**Set up `.env` file in `backend/`:**

```env
OPENROUTER_API_KEY=sk-or-xxxxxxxxxxxxxxxxxxxxxxxx
FRONTEND_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173
DYNAMIC_ENGINE_DEBUG_RESEARCH=0
```

**`backend/config/models.json`** — LLM provider & model selection

```json
{
  "version": "1",
  "default_model_id": "default",
  "models": {
    "default": {
      "provider": "openrouter",
      "platform": "openai_compatible",
      "model_type": "openrouter/owl-alpha",
      "api_url": "https://openrouter.ai/api/v1",
      "context_window": 200000,
      "suppress_unknown_context_warning": true
    }
  }
}
```

### Frontend Config

**`frontend/vite.config.js`** — dev server settings

```javascript
server: {
  port: 3000,
  host: true,
  proxy: {
    '/api': {
      target: 'http://127.0.0.1:8000',
      changeOrigin: true
    }
  }
}
```

Override with **`VITE_API_BASE_URL`** for production deployments.

---

## 📊 Data Flow

```
User Input (Frontend)
    ↓
POST /api/chat/stream (with message, optional chat_id)
    ↓
FastAPI Routes (Backend)
    ↓
DynamicStreamingEngine
    ├─ Session Load (if existing) or Create
    ├─ Root Coordinator Orchestration
    ├─ PM Planning & Research Planning
    ├─ Research Agent Validation
    ├─ Specialist Selection (Finance, Technical, Legal, etc.)
    ├─ Round-Table Debate (iterative consensus)
    └─ Blueprint Generation
    ↓
Real-time SSE Events (Streaming Response)
    ↓
Frontend (React Dashboard)
    ├─ DebateFeed displays events
    ├─ AgentStatus shows active agent
    ├─ Blueprint sections auto-populate
    └─ Store session in sidebar
    ↓
SQLite Persistence (Backend)
    └─ Save session + all messages
```

---

## 🧪 Testing

Run tests from the `tests/` directory:

```bash
cd tests
pytest .
```

Or with coverage:

```bash
pytest --cov=../backend .
```

---

## 🔐 Environment Variables Reference

| Variable | Purpose | Example | Required |
|----------|---------|---------|----------|
| `OPENROUTER_API_KEY` | API key for OpenRouter LLM | `sk-or-...` | ✅ Yes |
| `FRONTEND_CORS_ORIGINS` | Comma-separated CORS origins | `http://localhost:3000,...` | ❌ No (has defaults) |
| `VITE_API_BASE_URL` | Frontend API base URL | `http://localhost:8000` | ❌ No (auto-proxy in dev) |
| `DYNAMIC_ENGINE_DEBUG_RESEARCH` | Enable debug logging | `0` or `1` | ❌ No |
| `BROWSER_SESSION_COOKIE_SAMESITE` | Override browser identity cookie SameSite policy | `none`, `lax`, `strict` | ❌ No |
| `BROWSER_SESSION_COOKIE_SECURE` | Override Secure flag for the browser identity cookie | `true` | ❌ No |
| `BROWSER_SESSION_COOKIE_DOMAIN` | Optional shared parent domain for same-site deployments | `.your-domain.com` | ❌ No |

### Browser Session Recovery

The browser cookie stores only an opaque `browser_session_id`. Chat messages, blueprint sections, research briefs, reports, and run events are stored in SQLite and scoped to that browser identity. If SQLite is recreated while a browser still has an old cookie, the backend automatically issues a fresh browser identity instead of requiring manual cookie deletion.

For Vercel frontend + Railway backend deployments, set `FRONTEND_CORS_ORIGINS` to the exact Vercel origin and keep the production cookie default of `SameSite=None; Secure`. For a same-site custom domain or Alibaba Cloud ECS deployment behind one parent domain, set `BROWSER_SESSION_COOKIE_SAMESITE=lax` and `BROWSER_SESSION_COOKIE_SECURE=true`.

---

## 🚀 Deployment

### Deploy Backend (Docker)

**Dockerfile:**
```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY backend/ .

RUN pip install --no-cache-dir -r requirements.txt

ENV OPENROUTER_API_KEY=your_key_here
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Build & run:**
```bash
docker build -t genesis-backend .
docker run -e OPENROUTER_API_KEY=your_key -p 8000:8000 genesis-backend
```

### Deploy Frontend (Vercel / Netlify)

**Build:**
```bash
cd frontend
npm run build    # → dist/
```

**Deploy `dist/` folder to:**
- **Vercel**: `vercel deploy dist/`
- **Netlify**: Drag `dist/` to Netlify UI

**Set environment variable:**
```
VITE_API_BASE_URL=https://api.your-domain.com
```

---

## 🆘 Troubleshooting

### Backend won't start
```bash
# Check Python version
python --version          # Should be 3.12+

# Check API key is set
echo $OPENROUTER_API_KEY  # Should not be empty

# Verify port 8000 is available
netstat -an | grep 8000   # Should be empty
```

**Solution:**
- Install Python 3.12 if missing
- Add `OPENROUTER_API_KEY` to `.env` file
- Change port in `run_server.py` if 8000 is in use

### Frontend can't reach backend
```bash
# Check backend is running
curl http://127.0.0.1:8000/api/health

# Check Vite proxy in vite.config.js
cat frontend/vite.config.js | grep proxy
```

**Solution:**
- Ensure backend is running on port 8000
- Check CORS headers: `curl -i -H "Origin: http://localhost:5173" http://127.0.0.1:8000/api/health`
- Verify `.env` file has correct `FRONTEND_CORS_ORIGINS`

### Animations are choppy
- Try disabling hardware acceleration: DevTools → Settings → Rendering → uncheck "Use hardware acceleration"
- Update GSAP: `npm update gsap @gsap/react`

### Database errors
```bash
# Reset database (deletes all sessions)
rm backend/chat_sessions.db

# Restart backend
python backend/run_server.py
```

### Dependencies fail to install
```bash
# Upgrade pip first
pip install --upgrade pip

# Try installing again with verbose output
pip install -r backend/requirements.txt -v

# On Windows with Python 3.12, ensure you have VC++ build tools
# Download: https://visualstudio.microsoft.com/visual-cpp-build-tools/
```

---

## 📚 Key Files Reference

- **Backend entry:** `backend/main.py`
- **CLI tool:** `backend/cli.py`
- **Dependencies:** `backend/requirements.txt`
- **Frontend entry:** `frontend/src/main.jsx`
- **Frontend config:** `frontend/vite.config.js`
- **Frontend deps:** `frontend/package.json`
- **API client:** `frontend/src/services/api.js`
- **Blueprint sections:** `frontend/src/utils/blueprintSections.js`
- **Database models:** `backend/persistence/models.py`
- **LLM config:** `backend/config/models.json`

---

## 🤝 Contributing

1. Create a feature branch: `git checkout -b feature/your-feature`
2. Make changes and test locally
3. Commit: `git commit -am "Add feature"`
4. Push: `git push origin feature/your-feature`
5. Open a pull request

---

## 📝 License

This project is part of the **Global AI Hackathon Series with Qwen Cloud**.

---

## 💡 Key Takeaways

- **Multi-Agent Debate** — 10 specialized AI agents collaborate to build comprehensive business plans
- **Real-Time Streaming** — Watch the agents reason and reach consensus in real-time
- **Persistent Sessions** — Save, resume, and refine blueprints indefinitely
- **Production-Ready UI** — Smooth animations, responsive design, beautiful visualizations
- **Extensible Architecture** — Easily add new agents, sections, or LLM providers
- **Local Development** — Run fully locally with Python, Node.js, and a free API key

---

## 🆘 Support

For issues, feature requests, or questions:
1. Check existing issues on GitHub
2. Create a detailed bug report with logs
3. Include reproduction steps and environment info (Python version, Node version, OS)

---

**Happy hacking! 🎉**
