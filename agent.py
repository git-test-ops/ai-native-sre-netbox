import os
import json
import requests
from dotenv import load_dotenv
from openai import OpenAI

# 加载 .env 里的环境变量
load_dotenv()

# 1. 初始化 DeepSeek 客户端
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

# 2. NetBox 的 API 访问信息
NETBOX_URL = os.getenv("NETBOX_URL")
NETBOX_TOKEN = os.getenv("NETBOX_TOKEN")

HEADERS = {
    "Authorization": f"Token {NETBOX_TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json"
}

# 3. 定义工具
def check_site_health() -> str:
    """
    检查 NetBox 核心站点的健康状况
    """
    try:
        url = f"{NETBOX_URL}/api/dcim/sites/"
        res = requests.get(url, headers=HEADERS, timeout=5)
        res.raise_for_status()
        data = res.json()
        if data.get("count", 0) == 0:
            return "异常：NetBox 中没有任何站点记录！"
        return f"正常：当前系统中有 {data['count']} 个站点。"
    except Exception as e:
        return f"接口调用失败，异常信息：{str(e)}"

def add_site(name: str, slug: str, status: str = "active") -> str:
    """
    在 NetBox 中创建一个新站点。
    """
    try:
        url = f"{NETBOX_URL}/api/dcim/sites/"
        payload = {
            "name": name,
            "slug": slug,
            "status": status
        }
        res = requests.post(url, headers=HEADERS, json=payload, timeout=5)
        res.raise_for_status()
        return f"成功：站点 '{name}' 已创建。"
    except Exception as e:
        return f"接口调用失败，异常信息：{str(e)}"

# 注册工具给大模型
tools = [
    {
        "type": "function",
        "function": {
            "name": "check_site_health",
            "description": "检查当前系统中是否存在站点。"
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_site",
            "description": "创建一个新站点。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "站点的显示名称，例如 'Beijing-Datacenter'"},
                    "slug": {"type": "string", "description": "站点的唯一标识符，例如 'beijing-datacenter'"},
                },
                "required": ["name", "slug"]
            }
        }
    }
]

# ==========================================
# 4. Agent 核心循环
# ==========================================
def run_agent(user_prompt):
    print(f"\n[用户]: {user_prompt}")
    
    messages = [
        {"role": "system", "content": "你是一个自动化运维工具。你需要先检查系统状态，如果发现异常，请自动调用工具修复。"},
        {"role": "user", "content": user_prompt}
    ]

    while True:
        # 请求大模型
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
                
                print(f"  [Agent 思考中] 决定调用工具: {tool_name}，参数: {tool_args}")
                
                
                if tool_name == "check_site_health":
                    tool_result = check_site_health()
                elif tool_name == "add_site":
                    tool_result = add_site(**tool_args)
                else:
                    tool_result = "未知工具"
                
                print(f"  [工具返回结果]: {tool_result}")
                
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
    print("================ 场景 1：健康巡检 ================")
    run_agent("帮我检查一下系统现在有没有站点。")
    
    print("\n================ 场景 2：自动处置 ================")
    run_agent("发现站点缺失，请帮我自动补建一个名为 'bj-DC' 的站点。")