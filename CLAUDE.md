# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

EduHive is a multi-agent tutoring system using LangGraph. Four specialized AI agents collaborate through a state machine to provide personalized learning experiences.

## Common Commands

```bash
# Install dependencies
uv sync

# Run development server
uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
pytest

# Build Docker image (for AWS Lambda deployment)
docker build -t tutor-agent .
./build-lambda-simple.sh   # alternative: zip-based Lambda packaging
```

## Architecture

### Agent Flow

```
User Message → router_check() → current_agent state → classification_agent
                                                       (assesses user needs)
                                                              ↓
                                                    transfer_to_agent()
                                                              ↓
                                ┌─────────────────────────────┼─────────────────────────────┐
                                ↓                             ↓                             ↓
                          teacher_agent               feynman_agent                   quiz_agent
                         (step-by-step)          (validates understanding)        (generates quizzes)
```

### Key Concepts

**State Management**: `TutorState` (extends `MessagesState`) in `core/graph.py` tracks `current_agent`. The `router_check()` function reads this to direct each incoming message to the right agent, bypassing `classification_agent` on subsequent turns.

**Agent Transfers**: Agents call `transfer_to_agent(agent_name)` from `tools/shared_tools.py`, which returns a LangGraph `Command` with `graph=Command.PARENT` to transition within the parent graph and updates `current_agent` in state.

**Graph Construction**: `build_graph(checkpointer)` in `core/graph.py` assembles the `StateGraph`. The checkpointer is injected at startup — `AsyncSqliteSaver` locally, `DynamoDBSaver` on Lambda.

**Checkpointing**: Session continuity requires passing `thread_id` in the graph config:
```python
config = {"configurable": {"thread_id": session_id}}
await graph.ainvoke({"messages": [HumanMessage(content=prompt)]}, config)
```

### Entry Points

- **Local/Docker**: `api/main.py` — FastAPI app with REST (`/chat`) and WebSocket (`/ws/{session_id}`) endpoints. Uses `AsyncSqliteSaver` backed by `memory.db`.
- **AWS Lambda (HTTP)**: `api/router.py` → `api/main.py` (via Mangum). `DEPLOYMENT_ENV=lambda` switches the lifespan to use `DynamoDBSaver`.
- **AWS Lambda (WebSocket)**: `api/router.py` → `api/websocket_handler.py` — stateless Lambda handler; DynamoDB stores `connectionId → sessionId` mappings via `api/dynamo_connections.py`.

The single Lambda function at `api/router.py` distinguishes HTTP vs WebSocket events by checking for `connectionId` in `requestContext`.

**Rate Limiting**: `auth/throttling.py` enforces 3 requests per 60 seconds per `session_id`. This is in-memory — effective locally and per-container on Lambda, not across Lambda instances.

### Tools

- `tools/shared_tools.py`: `transfer_to_agent` (agent routing), `web_search_tool` (Firecrawl)
- `tools/quiz_tools.py`: quiz generation helpers used by `quiz_agent`

All agents are built with `create_react_agent` from `langgraph.prebuilt`.

## Environment Variables

Required in `.env`:
- `OPENAI_API_KEY` — for GPT-4o
- `FIRECRAWL_API_KEY` — for web search tool

Lambda-only:
- `DEPLOYMENT_ENV=lambda` — switches checkpointer from SQLite to DynamoDB
- `AWS_REGION` — defaults to `us-west-2`
- `CHECKPOINTS_TABLE` — defaults to `eduhive-checkpoints`
- `WRITES_TABLE` — defaults to `eduhive-writes`
- `CONNECTIONS_TABLE` — defaults to `eduhive-connections` (WebSocket connection map)

## Known Stale Config

`langgraph.json` references `./main.py:graph` — this file was deleted and moved to `api/`. The LangGraph CLI (`langgraph dev`) won't work until `langgraph.json` is updated to point to `api/main.py` or a dedicated graph export.
