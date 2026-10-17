"""
Root entrypoint for Hugging Face Spaces & Cloud Platforms.
Starts the FastAPI application on the configured PORT (default 7860 for HF Spaces).
"""

import os
import uvicorn
from backend.main import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
