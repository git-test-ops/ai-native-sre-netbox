import os
import time
import json
import requests
import subprocess
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

# 加载 .env 里的环境变量
load_dotenv()

# 初始化 DeepSeek 客户端
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

# NetBox 的 API 访问信息
NETBOX_URL = os.getenv("NETBOX_URL")
NETBOX_TOKEN = os.getenv("NETBOX_TOKEN")
VM_IP = "192.168.72.130"  # 你的 Ubuntu 虚拟机 IP

HEADERS = {
    "Authorization": f"Token {NETBOX_TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json"
}


# 定义工具
def get_current_time() -> str:
    """获取当前时间"""
    return f"当前系统时间是：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

def check_netbox_api() -> str:
    """检查 NetBox 的 API 健康状况（应用层检查）。"""
    try:
        url = f"{NETBOX_URL}/api/dcim/sites/"
        res = requests.get(url, headers=HEADERS, timeout=5)
        res.raise_for_status()
        return f"正常：NetBox API 响应成功，当前系统有 {res.json().get('count', 0)} 个站点。"
    except Exception as e:
        return f"异常：NetBox API 请求失败！错误信息：{str(e)}"

def get_docker_logs() -> str:
    """获取 NetBox 容器最后 30 行日志（用于诊断）。"""
    try:
        cmd = ["ssh", f"root@{VM_IP}", "docker logs --tail 30 netbox-docker-release-netbox-1 2>&1"]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=10)
        return f"日志获取成功，最后30行内容如下：\n{result.stdout}"
    except Exception as e:
        return f"SSH 执行失败：{str(e)}"


def restart_netbox_container() -> str:
    try:
        # 1. 拉起容器
        cmd = ["ssh", f"root@{VM_IP}", f"cd /data/netbox-docker-release && docker compose up -d netbox"]
        # 同样修复编码问题
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=30)
        
        # 2. 就绪探针：最多探测 3 次，每次间隔 20 秒
        max_retries = 3
        wait_seconds = 20
        status_msg = f"处置成功：已执行容器拉起命令。"
        
        for i in range(max_retries):
            print(f"  [系统提示] 等待 {wait_seconds} 秒后，进行第 {i+1}/{max_retries} 次健康探测...")
            time.sleep(wait_seconds)
            
            probe_result = check_netbox_api()
            if "正常" in probe_result:
                status_msg += f" 服务已成功恢复（第 {i+1} 次探测通过）。"
                return status_msg
            else:
                status_msg += f"\n第 {i+1} 次探测失败：{probe_result}"
        
        return status_msg + f"\n共探测 {max_retries} 次均失败，服务可能启动异常。"
        
    except Exception as e:
        return f"SSH 执行失败：{str(e)}"

def send_feishu_notification(level: str, message: str) -> str:
    """发送飞书通知。level 为 'success' 或 'critical'。"""
    webhook_url = os.getenv("FEISHU_WEBHOOK_URL")
    if not webhook_url:
        return "未配置飞书 Webhook，跳过通知。"
    
    prefix = "✅ [SRE Agent 通知]" if level == "success" else "🚨 [高危告警-需人工介入]"
    
    payload = {
        "msg_type": "text",
        "content": {"text": f"{prefix}\n{message}"}
    }
    try:
        requests.post(webhook_url, json=payload, timeout=5)
        return "飞书通知发送成功。"
    except Exception as e:
        return f"飞书通知发送失败：{str(e)}"

# 注册工具给大模型
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取当前的日期和时间。只有当用户明确要求显示时间时，才调用此工具。"
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_netbox_api",
            "description": "检查 NetBox API 是否正常响应。"
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_docker_logs",
            "description": "通过 SSH 到宿主机，拉取 NetBox Docker 容器的最近 30 行运行日志。用于故障诊断。"
        }
    },
    {
        "type": "function",
        "function": {
            "name": "restart_netbox_container",
            "description": "通过 SSH 到宿主机，拉起或重启 NetBox 的 Docker 容器。用于服务假死等物理故障处置。"
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_feishu_notification",
            "description": "发送飞书通知。用于同步故障处置结果。level 为 'success' 表示已成功恢复，'critical' 表示高危告警/需人工介入。",
            "parameters": {
                "type": "object",
                "properties": {
                    "level": {
                        "type": "string",
                        "enum": ["success", "critical"],
                        "description": "通知级别。success 为成功恢复，critical 为高危告警/需人工介入"
                    },
                    "message": {
                        "type": "string",
                        "description": "发送的具体消息内容"
                    }
                },
                "required": ["level", "message"]
            }
        }
    }
]

# ==========================================
# Agent 核心循环
# ==========================================
def run_agent(user_prompt):
    print(f"\n[用户]: {user_prompt}")
    
    messages = [
        {"role": "system", "content": """你是一个高级 SRE 自动化运维机器人。
        你的目标：确保目标系统（NetBox）处于 100% 的健康状态。
        你有权自主决定调用哪些工具来完成任务。
        规则：
        1. 遇到异常时，先分析原因（如查询日志）。
        2. 如果是物理故障（如进程退出、容器假死），你可以自主使用工具进行处置（重启）。
        3. 处置后，必须再次检查以确认故障已修复。
        4. 【重要】：
        - 如果问题已成功解决（复检正常），请调用 send_feishu_notification，级别设为 success。
        - 如果问题未解决或超出了你的处理能力需要人工介入，请调用 send_feishu_notification，级别设为 critical。
        - 用户要求记录时间时，调用 get_current_time。"""},
        {"role": "user", "content": user_prompt}
    ]

    while True:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )

        message = response.choices[0].message
        messages.append(message)

        if message.tool_calls:
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)
                
                print(f"  [Agent 思考中] 决定调用工具: {tool_name}")
                
                if tool_name == "get_current_time":
                    tool_result = get_current_time()
                elif tool_name == "check_netbox_api":
                    tool_result = check_netbox_api()
                elif tool_name == "get_docker_logs":
                    tool_result = get_docker_logs()
                elif tool_name == "restart_netbox_container":
                    tool_result = restart_netbox_container()
                elif tool_name == "send_feishu_notification":
                    tool_result = send_feishu_notification(**tool_args)
                else:
                    tool_result = "未知工具"
                
                print(f"  [工具返回结果]: {tool_result[:200]}...\n")
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_name,
                    "content": tool_result
                })
        else:
            print(f"  [Agent 总结]: {message.content}")
            break


if __name__ == "__main__":
    print("================ NetBox SRE Agent 已启动 ================")
    print("输入你的指令（输入 'exit' 退出）：")
    
    while True:
        user_input = input("\n[你]: ")
        if user_input.lower() in ['exit', 'quit']:
            break
        if not user_input.strip():
            continue
        run_agent(user_input)