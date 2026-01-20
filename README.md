# EduHive - AI-Powered Educational Tutor

<div align="center">

**A multi-agent educational platform that adapts to each learner's needs through specialized AI agents**

[![Python](https://img.shields.io/badge/Python-3.13+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.122+-green.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.6.6-orange.svg)](https://langchain-ai.github.io/langgraph/)

</div>

---

## 📚 Overview

EduHive is an intelligent tutoring system that leverages multiple specialized AI agents working together to provide personalized learning experiences. Each agent has a specific role in the educational process, ensuring learners receive the most appropriate teaching method for their needs.

### Key Features

- **🎯 Classification Agent**: Assesses learner knowledge, preferences, and learning style
- **👨‍🏫 Teacher Agent**: Provides structured, step-by-step explanations with confirmation checks
- **🧠 Feynman Agent**: Simplifies complex concepts using the Feynman technique
- **📝 Quiz Agent**: Generates research-based quizzes for knowledge assessment
- **💬 Real-time Communication**: WebSocket support for live chat interactions
- **🔄 Session Persistence**: SQLite-based checkpointing for conversation continuity
- **🌐 Web Research**: Integrated web search for up-to-date information
- **⚡ Rate Limiting**: Built-in throttling to manage API usage

## 🏗️ Architecture

The application is built on a multi-agent orchestration framework using LangGraph, where specialized agents collaborate through a state machine:

```
┌─────────────────────────────────────────────────────┐
│              Classification Agent                    │
│  (Assesses learner & routes to appropriate agent)   │
└──────────────┬──────────────────────────────────────┘
               │
       ┌───────┴────────┐
       │                │
┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐
│Teacher Agent│  │Feynman Agent│  │ Quiz Agent  │
│             │  │             │  │             │
│Structured   │  │Simplification│ │Assessment   │
│Teaching     │  │& Validation  │ │& Practice   │
└─────────────┘  └─────────────┘  └─────────────┘
```

### Technology Stack

- **Backend**: FastAPI (Python 3.13+)
- **Agent Framework**: LangGraph, LangChain
- **LLM**: OpenAI GPT-4o
- **Storage**: SQLite (conversation checkpointing)
- **Web Scraping**: Firecrawl API
- **Frontend**: Vanilla JavaScript, HTML/CSS
- **Deployment**: Docker, AWS Lambda (via Mangum)

## 🚀 Quick Start

### Prerequisites

- Python 3.13 or higher
- [uv](https://github.com/astral-sh/uv) package manager (recommended) or pip
- OpenAI API key
- Firecrawl API key (for web search functionality)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd tutor-agent
   ```

2. **Install dependencies**

   Using `uv` (recommended):
   ```bash
   uv sync
   ```

   Or using `pip`:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**

   Create a `.env` file in the root directory:
   ```env
   OPENAI_API_KEY=your_openai_api_key_here
   FIRECRAWL_API_KEY=your_firecrawl_api_key_here
   ```

4. **Initialize the database**

   The SQLite database (`memory.db`) will be created automatically on first run.

5. **Run the application**

   Using `uv`:
   ```bash
   uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
   ```

   Or using standard Python:
   ```bash
   uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
   ```

6. **Access the application**

   Open your browser and navigate to:
   ```
   http://localhost:8000
   ```

## 📖 API Documentation

### REST Endpoints

#### `GET /`
Serves the frontend web interface.

#### `GET /health`
Health check endpoint that verifies the API status and graph availability.

**Response:**
```json
{
  "status": "healthy",
  "graph_available": true,
  "checkpoint_available": true,
  "checkpoint_type": "sqlite"
}
```

#### `POST /chat`
Send a message to the tutor agent and receive a response.

**Request:**
```json
{
  "prompt": "I want to learn about quantum mechanics",
  "session_id": "optional-session-id-for-persistence"
}
```

**Response:**
```json
{
  "response": "Great! I'd be happy to help you learn...",
  "session_id": "generated-or-provided-session-id"
}
```

### WebSocket Endpoint

#### `WS /ws/{session_id}`
Real-time bidirectional communication channel for chat interactions.

**Query Parameters:**
- `client_id` (optional): Identifier for the client connection

**Message Format:**
- Client → Server: Plain text message
- Server → Client: Agent response as plain text

**Example Connection:**
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/your-session-id?client_id=your-client-id');
```

## 🔧 Configuration

### Environment Variables

| Variable                   | Description                               | Required |
| -------------------------- | ----------------------------------------- | -------- |
| `OPENAI_API_KEY`           | Your OpenAI API key for GPT-4o            | Yes      |
| `FIRECRAWL_API_KEY`        | Firecrawl API key for web search          | Yes      |
| `AWS_LAMBDA_FUNCTION_NAME` | Set automatically when deployed to Lambda | No       |

### Agent Configuration

Agents are configured in their respective files under `agents/`:
- Model: OpenAI GPT-4o (configurable)
- Tools: Each agent has access to specific tools for its role
- Prompt: Custom system prompts define agent behavior

## 📁 Project Structure

```
tutor-agent/
├── agents/                  # Agent implementations
│   ├── classification_agent.py
│   ├── feynman_agent.py
│   ├── quiz_agent.py
│   └── teacher_agent.py
├── api/                     # FastAPI application
│   ├── __init__.py
│   ├── main.py             # Main API routes and WebSocket
│   ├── models.py           # Pydantic request/response models
│   └── websocket_manager.py # WebSocket connection management
├── auth/                    # Authentication & rate limiting
│   └── throttling.py
├── core/                    # Core graph orchestration
│   ├── __init__.py
│   └── graph.py            # LangGraph state graph definition
├── tools/                   # Shared agent tools
│   ├── quiz_tools.py       # Quiz generation utilities
│   └── shared_tools.py     # Common tools (transfer, web search)
├── frontend/                # Web interface
│   ├── index.html
│   └── static/
│       ├── app.js          # Frontend JavaScript
│       └── styles.css      # Styling
├── .env                     # Environment variables (create this)
├── Dockerfile              # Docker container definition
├── langgraph.json          # LangGraph CLI configuration
├── pyproject.toml          # Project metadata and dependencies
├── requirements.txt        # Python dependencies
└── README.md               # This file
```

## 🧪 Development

### Running in Development Mode

```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

The `--reload` flag enables auto-reload on code changes.

### Running Tests

```bash
pytest
```

### Code Style

Follow PEP 8 guidelines for Python code. Consider using:
- `black` for code formatting
- `flake8` or `pylint` for linting
- `mypy` for type checking

## 🐳 Docker Deployment

### Build the Docker Image

```bash
docker build -t tutor-agent .
```

### Run the Container

```bash
docker run -p 8000:8000 \
  -e OPENAI_API_KEY=your_key \
  -e FIRECRAWL_API_KEY=your_key \
  tutor-agent
```

**Note**: The Dockerfile is configured for AWS Lambda deployment. For local Docker usage, you may need to modify the entrypoint.

## ☁️ AWS Lambda Deployment

The application is configured for serverless deployment on AWS Lambda using Mangum:

1. **Build the Lambda package**
   ```bash
   docker build -t tutor-agent .
   ```

2. **Create Lambda function** via AWS Console or CLI

3. **Configure environment variables** in Lambda settings:
   - `OPENAI_API_KEY`
   - `FIRECRAWL_API_KEY`

4. **Set handler**: `api.main.handler`

5. **Configure API Gateway** to route requests to the Lambda function

**Important**: For Lambda deployment, ensure the SQLite database path uses `/tmp/` directory (writable in Lambda environment).

## 🔒 Security Considerations

- **API Keys**: Never commit `.env` files or hardcode API keys
- **Rate Limiting**: Implemented to prevent abuse
- **Input Validation**: All inputs are validated using Pydantic models
- **SQL Injection**: SQLite queries use parameterized statements (handled by LangGraph)

## 🐛 Troubleshooting

### Common Issues

1. **"No module named 'api'"**
   - Ensure you're running from the project root directory
   - Check that all dependencies are installed

2. **"Graph not available" or checkpoint errors**
   - Verify `memory.db` is writable in the current directory
   - Check file permissions

3. **WebSocket connection fails**
   - Verify the session ID format
   - Check that the server is running and accessible

4. **OpenAI API errors**
   - Verify your API key is correct and has sufficient credits
   - Check API rate limits
