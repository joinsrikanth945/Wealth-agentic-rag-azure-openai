# Adapted from Enterprise IT Support Agentic RAG Copilot by Bappy Ahmed (Apache-2.0).
# Modified by Sreekanth Dara, 2026.
import os

import uvicorn
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8081"))
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, reload=True)