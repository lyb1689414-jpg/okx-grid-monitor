"""启动入口"""
import os
import uvicorn

if __name__ == "__main__":
    is_dev = os.environ.get("ENV", "prod") == "dev"
    uvicorn.run(
        "src.web.app:app",
        host="0.0.0.0",
        port=8000,
        reload=is_dev,
        log_level="info",
    )
