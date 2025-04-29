# Browser Agent Backend

A Python backend service that integrates Browserbase and browser-use to provide AI-powered browser automation.

## Features

- Remote browser sessions using Browserbase
- AI-powered browser automation with browser-use
- WebSocket streaming of browser screenshots
- REST API for browser control

## Setup

1. Create a Python virtual environment:

```bash
# Using venv
python -m venv venv

# Activate the environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Install Playwright browsers:

```bash
playwright install
```

4. Create a `.env` file with your API keys (see `.env.example` for reference):

```
BROWSERBASE_API_KEY=your_browserbase_api_key
BROWSERBASE_PROJECT_ID=your_browserbase_project_id
OPENAI_API_KEY=your_openai_api_key
```

5. Start the server:

```bash
python server.py
```

The server will start on http://localhost:8000 by default.

## API Endpoints

- `POST /api/browser/start`: Start a new browser session
- `POST /api/browser/query`: Process a query with the browser agent
- `POST /api/browser/stop`: Stop a browser session
- `WebSocket /ws/browser/{user_id}`: Stream browser screenshots

## Usage with Frontend

The backend is designed to work with the RemoteBrowser component in the frontend.

## Dependencies

- FastAPI: Web framework
- Browserbase: Remote browser provider
- browser-use: AI browser automation
- LangChain: AI framework
- Playwright: Browser automation 