"""FastAPI 应用入口"""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# 日志配置：所有日志输出到 stdout（Docker 可捕获）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
# APScheduler 调试日志
logging.getLogger("apscheduler").setLevel(logging.DEBUG)

logger = logging.getLogger(__name__)

from src.db.database import init_db
from src.scheduler.jobs import start_scheduler

templates = Jinja2Templates(directory="src/web/templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("应用启动中...")
    init_db()
    scheduler = start_scheduler()
    app.state.scheduler = scheduler
    logger.info(f"调度器已启动，注册任务: {[j.id for j in scheduler.get_jobs()]}")
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
