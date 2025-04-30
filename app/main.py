import os
import uuid
from typing import Dict, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from .browser_controller import BrowserController

# Load environment variables
load_dotenv()

app = FastAPI(title="Browser Agent API")

# Configure CORS to allow frontend connections
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://the-ai-vantage.com", "https://aivantage.app", "http://localhost:3000"],  # Replace with your frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store active browser sessions
browser_sessions: Dict[str, BrowserController] = {}

class QueryRequest(BaseModel):
    user_id: str
    query: str
    model: Optional[str] = "gpt-4o"

class SessionRequest(BaseModel):
    user_id: str

@app.get("/")
async def root():
    return {"message": "Browser Agent API is running"}

@app.post("/api/browser/start")
async def start_browser(request: SessionRequest, background_tasks: BackgroundTasks):
    """
    Start a new browser session for a user
    """
    user_id = request.user_id
    
    # Check if session already exists
    if user_id in browser_sessions:
        return {"message": "Session already exists", "session_id": browser_sessions[user_id].session_id}
    
    # Create new browser controller
    browser_controller = BrowserController(user_id)
    browser_sessions[user_id] = browser_controller
    
    # Start session in background
    result = await browser_controller.start_session()
    
    if "error" in result:
        # If error occurred, remove the session
        del browser_sessions[user_id]
        raise HTTPException(status_code=500, detail=result["error"])
    
    return {
        "message": "Browser session started",
        "session_id": result["session_id"],
        "current_url": result["current_url"]
    }

@app.post("/api/browser/query")
async def process_query(request: QueryRequest):
    """
    Process a user query with the browser agent
    """
    user_id = request.user_id
    
    # Check if session exists
    if user_id not in browser_sessions:
        raise HTTPException(status_code=404, detail="No active browser session found")
    
    # Process the query
    result = await browser_sessions[user_id].process_query(request.query)
    
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result["error"])
    
    return {
        "response": result["aiResponse"],
        "current_url": result["current_url"],
        "steps": result.get("steps", [])
    }

@app.post("/api/browser/stop")
async def stop_browser(request: SessionRequest):
    """
    Stop a browser session
    """
    user_id = request.user_id
    
    # Check if session exists
    if user_id not in browser_sessions:
        return {"message": "No active session found"}
    
    # Stop the session
    await browser_sessions[user_id].stop_session()
    del browser_sessions[user_id]
    
    return {"message": "Browser session stopped"}

@app.websocket("/ws/browser/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """
    WebSocket endpoint for streaming browser screenshots
    """
    await websocket.accept()
    
    # Check if session exists
    if user_id not in browser_sessions:
        await websocket.send_json({"type": "error", "message": "No active browser session found"})
        await websocket.close()
        return
    
    # Stream browser screenshots
    browser_controller = browser_sessions[user_id]
    
    try:
        await browser_controller.stream_browser(websocket)
    except WebSocketDisconnect:
        print(f"WebSocket disconnected for user {user_id}")
    except Exception as e:
        print(f"Error in WebSocket: {str(e)}")
        await websocket.send_json({"type": "error", "message": str(e)})
    finally:
        # This doesn't close the browser session, just stops streaming
        browser_controller.streaming = False

@app.on_event("shutdown")
async def shutdown_event():
    """
    Cleanup all browser sessions on shutdown
    """
    for user_id, controller in list(browser_sessions.items()):
        await controller.stop_session()
    
    browser_sessions.clear() 