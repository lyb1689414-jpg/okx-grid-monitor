# 编码规范

## Python 编码规范

### 命名约定
- 文件名: 小写 + 下划线 (snake_case) — `pair_engine.py`, `grid_config.yaml`
- 类名: 大驼峰 (PascalCase) — `GridConfig`, `OkxClient`
- 函数/变量: 小写 + 下划线 — `get_active_grids()`, `algo_id`
- 常量: 大写下划线 — `DB_URL`, `TZ`

### 模块职责
- `src/api/` — 只做 OKX API 调用封装，不含业务逻辑
- `src/core/` — 核心算法和业务规则，不操作 HTTP 也不操作数据库其本身
- `src/db/` — 数据模型和访问，`models.py` 只定义表结构，`repository.py` 封装所有查询
- `src/scheduler/` — 定时任务编排，调用 core 层完成业务
- `src/web/` — FastAPI 路由和模板，薄层，业务委托给 core/db

### 注释风格
- **不写解释型的注释**: 好的命名比注释更能说明意图
- **只在 WHY 处加注释**: 隐藏的约束、微妙的逻辑、已知的反直觉行为
- **函数不写多行 docstring**: 除非是公开 API，否则一行概括即可

### 错误处理
- API 调用层: 自动重试（3次，指数退避），抛出明确的异常
- 定时任务: 单个网格失败不阻断其他网格处理，错误记入 job_executions 表
- 前端: fetch 异常用 console.error 记录，不阻塞页面渲染

### 数据库
- 连接: 每次请求/任务独立创建 Session，结束时关闭
- 查询: 所有 SQL 操作集中在 `repository.py`
- 迁移: 本地开发用 `Base.metadata.create_all()` 自动建表（适合 SQLite），迁移到 PostgreSQL 时使用 Alembic

## 前端规范

### HTML/CSS/JS
- 单文件 `index.html`，包含 HTML + CSS + JS 全部
- CDN 引入 Bootstrap 5 和 ECharts，无本地依赖
- 数据刷新: 仪表盘汇总 + 网格列表 30 秒自动刷新；图表和表格手动刷新或按需加载
- 颜色语义: 绿色=盈利/正数，红色=亏损/负数，蓝色=中性数据

### API 调用模式
```javascript
async function fetchJSON(url) { ... }     // 统一错误处理
function refreshAll() { ... }             // 全量刷新入口
setInterval(() => { ... }, 30000);        // 定时轻量刷新
```

## Git 规范
- `.env` 不上传（含 API 密钥）
- `data/` 不上传（含数据库文件）
- `logs/` 不上传（运行时日志）
- 提交信息: 中文，动宾结构，如「实现配对计算引擎」

## 配置管理
- **密钥类**: `.env` 文件（pydantic-settings 读取），`.env.example` 作为模板
- **业务配置**: `config/grid_config.yaml`（网格列表、止盈比例等）
- **多环境**: 通过 `.env` 的 `DATABASE_URL` 区分本地/云端数据库
