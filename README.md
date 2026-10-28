# AI Native Agent

基于大模型 Tool Calling 能力构建的自动化运维Agent。

## 项目背景
本项目以 `netbox-docker` 作为数据源和分析对象，构建了一个具备**感知异常 -> 底层诊断 -> 物理处置 -> 结果通知**完整闭环能力的 AI Agent。它不仅能在应用层发现服务不可用，还能穿透到基础设施层拉取日志，并在必要时自动执行物理重启。

## 核心特性
- **跨层级巡检**：同时支持应用层（NetBox API）与基础设施层（Docker 容器）的健康检查。
- **自主诊断**：当 API 异常时，Agent 会自主通过 SSH 进入宿主机拉取底层日志进行分析。
- **智能处置与探针**：发现容器假死或退出时，Agent 可自主执行 `docker compose up -d` 进行拉起，并内置了就绪探针（轮询 3 次，每次间隔 20s）等待服务恢复。
- **分级告警通知**：集成飞书自定义机器人。若自动修复成功则发送 `success` 通知；若处置失败需人工介入，则发送 `critical` 级别高危告警。

## 架构与闭环流程
1. **环境**：Windows (Agent 运行端，也可运行在 Linux 机器中) + VMware Ubuntu (NetBox 宿主机)
2. **执行流程**：
   - 接受指令 -> 调用 API 检查服务状态。
   - 发现异常 -> 通过 SSH 获取 Docker 容器日志进行诊断。
   - 定位为假死/宕机 -> 通过 SSH 执行重启命令拉起容器。
   - 触发就绪探针 -> 轮询检测 API 直到恢复正常。
   - 判定最终结果 -> 调用飞书机器人同步 `success` 或 `critical` 告警。
   - 汇总生成巡检报告。

## 技术栈与工具
- **大模型**：DeepSeek (兼容 OpenAI 接口)
- **交互层**：Python `openai` SDK, `requests`
- **宿主控制**：`subprocess` 调用本地 SSH 免密执行
- **注册的工具 (Tools)**：
  - `check_netbox_api`：检查 NetBox API 是否存活。
  - `get_docker_logs`：通过 SSH 获取容器日志。
  - `restart_netbox_container`：通过 SSH 拉起容器并执行就绪探针。
  - `send_feishu_notification`：发送飞书群消息通知。
  - `get_current_time`：获取系统当前时间。

## 环境准备与运行

### 1. 安装依赖
pip install openai requests python-dotenv

### 2. 配置环境变量
在项目根目录创建 .env 文件，并填入以下配置：
DEEPSEEK_API_KEY=你的DeepSeek密钥
NETBOX_URL=http://你的虚拟机IP:8000
NETBOX_TOKEN=你的NetBox_Token
FEISHU_WEBHOOK_URL=你的飞书机器人Webhook地址

### 3. 运行测试
启动 Agent 程序：
python agent.py

然后在终端提示符中输入巡检指令：
> 帮我巡检下 NetBox 服务的状态。若存在问题，自行分析处理。将结果同步到飞书群里，记得带上巡检时间。