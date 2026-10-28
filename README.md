# AI Native SRE Agent (NetBox)

基于大模型 Tool Calling（工具调用）能力构建的自动化运维 SRE Agent。

## 项目简介
本项目以 `netbox-docker` 作为数据源和分析对象，通过接入大语言模型（DeepSeek），构建一个具备感知、诊断和处置闭环能力的 AI Agent。

## 当前进度
- [√] 完成 NetBox 环境的 Docker 部署
- [√] 接入 DeepSeek API，实现基础的 Tool Calling 闭环
- [√] 实现工具：`check_site_health`（健康巡检）、`add_site`（自动创建站点）
- [ ] 实现跨机器 SSH 诊断（拉取 Docker 日志）
- [ ] 实现自动处置动作（重启 Docker 容器）

## 环境准备
1. 安装依赖：
   ```bash
   pip install openai requests python-dotenv