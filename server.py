import os
import uvicorn
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

if __name__ == "__main__":
    # Get host and port from environment or use defaults
    host = os.getenv("SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("SERVER_PORT", "3000"))
    
    # Start the FastAPI server (without reload for non-dev)
    uvicorn.run("app.main:app", host=host, port=port) 