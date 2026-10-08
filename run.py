import os

import uvicorn
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8081"))
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, reload=True)