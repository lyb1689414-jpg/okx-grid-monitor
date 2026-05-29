"""FastAPI 应用入口"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.db.database import init_db
from src.scheduler.jobs import start_scheduler

templates = Jinja2Templates(directory="src/web/templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler = start_scheduler()
    yield
    scheduler.shutdown()


app = FastAPI(title="OKX 合约网格监控", lifespan=lifespan)

# 静态文件
import os
static_dir = os.path.join(os.path.dirname(__file__), "..", "..", "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir, exist_ok=True)

from src.web.routes import router
app.include_router(router)
