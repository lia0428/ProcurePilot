# ProcurePilot — AI 智能采购 Agent

ProcurePilot 是一个基于 **GLM + LangGraph + FastAPI + SQLite + Streamlit** 开发的智能采购 Agent 项目。

用户只需通过自然语言描述采购需求，系统即可自动解析商品信息、查询库存、计算补货数量、筛选供应商、创建采购订单，并通过人工审批完成采购决策。

项目重点实现了 **Agent 工作流编排、Human-in-the-Loop（人工介入）、SQLite 数据持久化以及工作流中断恢复**。

## 一、项目功能

| 功能模块 | 实现内容 |
|---|---|
| 自然语言理解 | 使用 GLM 提取商品名称与目标库存 |
| 库存管理 | 查询库存并计算需要补货的数量 |
| 供应商比价 | 在库存充足的供应商中选择最低价方案 |
| 订单管理 | 使用 SQLite 创建、查询和更新采购订单 |
| 人工审批 | 使用 LangGraph `interrupt()` 暂停工作流 |
| 工作流恢复 | 使用 SQLite Checkpointer 持久化并恢复审批任务 |
| Web 界面 | 使用 Streamlit 实现采购操作与订单审批 |
| REST API | 使用 FastAPI 提供库存、供应商及订单接口 |
| 自动化测试 | 使用 pytest 验证核心业务逻辑与 Agent 工作流 |

## 二、系统架构

```text
用户输入自然语言采购需求
          |
          v
    Streamlit Web 界面
          |
          v
    GLM 采购意图解析
          |
          v
    LangGraph Agent
          |
          v
       库存查询
          |
          v
       补货计算
          |
          v
       供应商比价
          |
          v
       创建采购订单
          |
          v
    Human-in-the-Loop
       人工审批
          |
     +----+----+
     |         |
    批准      拒绝
     |         |
     +----+----+
          |
          v
    SQLite 更新订单状态
```

系统使用两个独立的 SQLite 数据库：

- `procurement.db`：存储商品、库存、供应商、采购订单及工作流线程映射。
- `langgraph_checkpoints.db`：存储 LangGraph 工作流检查点。

通过订单 ID 与 `thread_id` 的关联，系统可以在关闭并重新启动 Streamlit 后恢复未完成的审批任务。

## 三、技术栈

| 技术 | 用途 |
|---|---|
| Python | 项目开发语言 |
| GLM | 大语言模型，解析自然语言采购需求 |
| LangGraph | Agent 工作流编排、状态管理和人工审批 |
| FastAPI | RESTful API 开发 |
| Pydantic | 请求参数校验与结构化数据验证 |
| SQLite | 采购业务数据持久化 |
| LangGraph SQLite Checkpointer | 工作流检查点持久化 |
| Streamlit | Web 交互界面 |
| pytest | 自动化单元测试与集成测试 |
| Git | 代码版本管理 |

## 四、项目运行

### 1. 克隆项目

```bash
git clone <YOUR_REPOSITORY_URL>
cd ProcurePilot
```

### 2. 创建并激活虚拟环境

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. 安装项目依赖

```bash
python3 -m pip install -r requirements.txt
```

### 4. 配置环境变量

在项目根目录创建 `.env` 文件：

```env
GLM_API_KEY=your_api_key_here
GLM_MODEL=glm-4-flash
```

请将 API Key 和模型名称替换为实际配置。

### 5. 初始化数据库

```bash
python3 seed.py
python3 seed_suppliers.py
```

上述脚本用于初始化示例商品、库存及供应商数据。

### 6. 启动 Streamlit

```bash
python3 -m streamlit run streamlit_app.py
```

启动后，根据终端提示打开网页。

### 7. 启动 FastAPI（可选）

在另一个终端执行：

```bash
python3 -m uvicorn main:app --reload
```

API 文档地址：

http://127.0.0.1:8000/docs

## 五、使用示例

用户输入：

> 帮我把键盘库存补到30件。

假设当前键盘库存为8件，系统执行以下步骤：

1. GLM 解析采购需求，提取商品名称“键盘”和目标库存30件。
2. 查询 SQLite，获取当前库存8件。
3. 计算补货数量：30 − 8 = 22件。
4. 查询供应商，选择库存充足且价格最低的供应商。
5. 创建采购订单，初始状态为 `pending_approval`。
6. LangGraph 使用 `interrupt()` 暂停工作流，等待人工审批。
7. 用户通过 Streamlit 点击“批准订单”或“拒绝订单”。
8. 系统恢复工作流，将订单状态更新为 `approved` 或 `rejected`。

如果审批期间关闭网页，重新启动后仍可通过待审批订单列表恢复工作流。

## 六、自动化测试

项目使用 pytest 编写自动化测试。

运行：

```bash
python3 -m pytest -v
```

目前共有 **20个自动化测试，全部通过**。

测试覆盖：

- 库存查询及异常处理
- 采购请求参数验证
- 采购订单创建
- 重复待审批订单保护
- 订单批准与拒绝
- 非法状态流转
- LangGraph 工作流中断与恢复
- Agent 与 SQLite 的集成流程
- 库存充足时跳过采购

测试使用临时 SQLite 数据库和模拟 LLM 返回值，避免影响正式订单及消耗真实模型 API 调用额度。

## 七、项目技术亮点

### 1. 基于 LangGraph 的状态化 Agent 工作流

通过 LangGraph 将采购流程拆分为独立节点，实现采购需求解析、库存检查、供应商选择、订单创建与人工审批。

### 2. Human-in-the-Loop 人工审批

通过 `interrupt()` 和 `Command(resume=...)` 实现工作流暂停与恢复，避免 Agent 在未经人工确认的情况下直接完成采购决策。

### 3. 工作流持久化与跨重启恢复

通过 LangGraph SQLite Checkpointer 保存执行状态，并建立订单 ID 与 `thread_id` 的持久化关联，使未完成的审批任务能够在应用重启后恢复。

### 4. 业务数据与工作流状态分离

采购订单、库存和供应商数据由 SQLite 业务数据库管理；Agent 执行状态由 LangGraph Checkpointer 管理。

### 5. 业务规则与异常保护

实现重复待审批订单限制、供应商库存检查、请求参数校验及订单状态流转约束，提高系统可靠性。

## 八、当前版本范围

本项目为个人学习和求职展示用途的 MVP。

当前版本：

- 使用本地示例供应商数据，不直接连接真实采购平台。
- 支持采购订单创建、人工批准和拒绝。
- 审批成功不代表真实商品已购买或入库。
- 暂未实现真实支付、物流跟踪及外部供应商API对接。

## 九、后续优化方向

- 引入 RAG 供应商知识库
- 接入真实供应商API
- 增加采购成本分析与监控
- Docker 容器化部署
- 完善日志记录与Agent执行可观测性

---

**项目定位：** 基于大语言模型与LangGraph的智能采购工作流系统，重点展示AI应用开发、Agent编排、数据库设计、人工审批和工作流持久化能力。