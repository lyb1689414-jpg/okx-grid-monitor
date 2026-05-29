# CLAUDE.md — 欧易合约网格自动监控项目指引

## 项目简介
欧易（OKX）合约网格自动监控系统。监控多个合约网格策略，每日 23:59 自动统计配对数据，每日 00:00 自动修改止盈金额。Python 后端 + HTML/ECharts 前端。

## 标准文件索引

| 文件 | 说明 |
|------|------|
| [docs/requirements.md](docs/requirements.md) | 功能需求文档 — 核心功能、可并行实现功能、约束条件 |
| [docs/architecture.md](docs/architecture.md) | 技术架构设计 — 技术栈、目录结构、数据流、关键设计决策 |
| [docs/database-design.md](docs/database-design.md) | 数据库设计 — 6张表结构、字段说明、ER关系 |
| [docs/api-design.md](docs/api-design.md) | API 设计规范 — 后端端点、OKX API 调用清单、认证方式 |
| [docs/coding-standards.md](docs/coding-standards.md) | 编码规范 — 命名约定、模块职责、错误处理、前端/配置规范 |
| [docs/implementation-plan.md](docs/implementation-plan.md) | 实施步骤 — 已完成/待完成清单、执行命令 |
| [devlog/TEMPLATE.md](devlog/TEMPLATE.md) | 开发日志模板 |
| [devlog/](devlog/) | 开发日志目录（按日期命名：YYYY-MM-DD.md） |

## 工作约定

### 沟通语言
- 所有沟通和思考过程使用中文
- 代码中的命名使用英文

### 开发流程
1. 每次开始开发前，先查看 `docs/implementation-plan.md` 了解当前进度
2. 开发完成后，在 `devlog/` 中创建或更新当天的日志文件（`YYYY-MM-DD.md`）
3. 每天结束前在日志中记录：已完成事项、遇到的问题、明日计划
4. 重大架构变更需要同步更新 `docs/` 下对应的标准文件

### 代码规范
- 遵循 `docs/coding-standards.md` 中的约定
- 不写解释型注释，只在 WHY 处加注释
- 不引入过度抽象，三行类似的代码好过一个过早的封装
- 编辑已有文件优先于新建文件

### 测试约定
- 先在模拟盘（OKX_FLAG=1）测试所有涉及交易的 API
- 涉及资金的操作必须先在模拟盘验证

### 关键文件路径
- 启动入口: `run.py`
- 配置文件: `config/settings.py`（读取 `.env`）、`config/grid_config.yaml`（网格列表）
- API 客户端: `src/api/client.py`（HMAC 签名、限频、重试）
- 核心算法: `src/core/pair_engine.py`（配对识别）
- 前端页面: `src/web/templates/index.html`
- 数据库: `data/okx_grid.db`（SQLite，已 gitignore）

## 环境信息
- Python: Anaconda Python 3.11.5（路径: `E:\anaconda3\python`）
- SQLAlchemy: 1.4.39（使用传统 Column 定义，非 2.0 的 Mapped/mapped_column）
- 启动命令: `python run.py`
- 访问地址: `http://localhost:8000`
