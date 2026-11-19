import os   #python自带的os模块，用于处理文件和目录
import json
from dotenv import load_dotenv #  用于从.env文件加载环境变量
from openai import OpenAI #  从 openai 库中导入 OpenAI 客户端类，后续可以用它创建客户端，与 OpenAI API 通信
from inventory import get_inventory, calculate_restock, list_inventory
from orders import (
    create_purchase_order,
    get_purchase_order,
    list_purchase_orders,
    update_order_status
)

tool_registry = {
    "get_inventory": get_inventory,
    "calculate_restock": calculate_restock,
    "list_inventory": list_inventory,
    "create_purchase_order": create_purchase_order,
    "get_purchase_order": get_purchase_order,
    "list_purchase_orders": list_purchase_orders,
    "update_order_status": update_order_status
}
#tool_registry 字典，将工具名称映射到对应的函数,左边的 "get_inventory" 是字符串，右边的 get_inventory 是Python函数对象
load_dotenv()

client = OpenAI(
    api_key=os.getenv("GLM_API_KEY"),
    base_url="https://open.bigmodel.cn/api/paas/v4/"
)
#OpenAI(...)：创建一个 API 客户端，保存到变量 client。虽然使用的是 OpenAI 的 Python 库，但可以通过 base_url 连接兼容该接口的其他服务
model_name = os.getenv("GLM_MODEL")

# 1. 告诉大模型有哪些工具

tools = [
    {
        "type": "function",  # 工具类型，function 表示函数工具
        "function": {
            "name": "get_inventory",
            "description": "查询指定商品的当前库存数量",
            "parameters": {  #定义函数接收的参数格式
                "type": "object",  #参数是一组键值对
                "properties": {
                    "product_name": {
                        "type": "string",
                        "description": "需要查询的商品名称"
                    }
                }, #properties 字段定义了函数的参数，每个参数是一个键值对，键是参数名，值是参数类型和描述
                "required": ["product_name"]  # product_name 是必填参数
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_restock",
            "description": "计算指定商品需要补货多少件",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name": {
                        "type": "string",
                        "description": "商品名称"
                    },
                    "target": {
                        "type": "integer",
                        "description": "目标库存数量，默认30件"
                    }
                },
                "required": ["product_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_inventory",
            "description": "查询所有商品的库存信息",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "create_purchase_order",
            "description": "创建待审批的采购订单，并保存到本地文件。仅在用户明确要求创建或保存采购订单时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name": {
                        "type": "string",
                        "description": "需要采购的商品名称"
                    },
                    "target": {
                        "type": "integer",
                        "description": "目标库存数量，默认30件"
                    }
                },
                "required": ["product_name"]
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "get_purchase_order",
            "description": "根据订单编号查询已经创建的采购订单详情，不创建或修改订单",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "需要查询的采购订单编号"
                    }
                },
                "required": ["order_id"]
            }
        }
    },


    {
        "type": "function",
        "function": {
            "name": "list_purchase_orders",
            "description": "查询采购订单列表，可查询全部订单或根据审批状态筛选，不会修改订单",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": [
                            "pending_approval",
                            "approved",
                            "rejected"
                        ],
                        "description": "可选的订单状态筛选条件；不提供则返回全部订单"
                    }
                },
                "required": []
            }
        }
    },


    {
        "type": "function",
        "function": {
            "name": "update_order_status",
            "description": "根据用户明确的审批指令，批准或拒绝已有的待审批订单。该工具会修改订单文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "订单编号"
                    },
                    "new_status": {
                        "type": "string",
                        "enum": ["approved", "rejected"],
                        "description": "审批结果：批准或拒绝"
                    }
                },
                "required": ["order_id", "new_status"]
            }
        }
    }


]


# 2. 用户输入

# 保存对话历史
#系统提示词
messages = [
    {
        "role": "system",
        "content": """
你是ProcurePilot企业采购助手。

你有三个库存工具：
1. get_inventory：查询单个商品库存。
2. calculate_restock：计算单个商品补货数量。
3. list_inventory：查询所有商品库存。
4. create_purchase_order：创建并保存待审批采购订单。
5. get_purchase_order：根据订单编号查询已有采购订单。
6. update_order_status：批准或拒绝待审批采购订单。
7. list_purchase_orders：查询采购订单列表，可按审批状态筛选。

规则：
- 涉及库存数据时，必须使用工具，不得编造数据。
- 只查询库存时，优先使用get_inventory。
- 询问补货数量时，使用calculate_restock。
- 查询所有商品时，使用list_inventory。
- 默认目标库存为30件。
- 用户修改目标库存时，沿用上一轮商品。
- 用户只更换商品时，沿用上一轮目标库存。
- 不要擅自增加用户未要求的采购任务。
- 只有用户明确要求创建采购订单时，才能调用create_purchase_order。
- 查询库存、计算补货、提供建议时，不得创建订单。
- 创建的订单状态为pending_approval，表示等待审批。
- 不得声称订单已经审批通过、完成付款或实际采购。
- 用户查询订单时，使用get_purchase_order。
- 查询订单不会创建新订单。
- 如果用户没有提供订单编号，不要编造编号。
- 不得声称待审批订单已经完成采购。
- 只有用户明确要求批准或拒绝指定订单时，才能调用审批工具。
- 不能自行决定是否批准订单。
- 不能把库存不足理解成自动批准采购。
- 如果用户取消确认，必须告知订单未修改。
- 审批通过不代表已经付款、发货或完成采购。
- 查询全部订单时，调用list_purchase_orders，不传status。
- 查询待审批订单时，status为pending_approval。
- 查询已批准订单时，status为approved。
- 查询已拒绝订单时，status为rejected。
- 如果返回空列表，说明没有符合条件的订单。
- 查询订单不会创建订单，也不会修改审批状态。
"""
    }
]



def execute_tool(tool_name, args):

    # 1. 查找工具
    function = tool_registry.get(tool_name) 
    #tool_registry.get(...)：从工具注册表中查找工具对应的函数，保存到变量 function

    if function is None:
        return {"error": f"未知工具：{tool_name}"}

    # 2. 检查参数是否为字典
    if not isinstance(args, dict): 
        #isinstance(...)：检查 args 是否是字典类型
        return {"error": "工具参数必须是字典"}

    # 3. 检查商品名称
    if tool_name in ["get_inventory", "calculate_restock", "create_purchase_order"]:
        product_name = args.get("product_name")
        #get(...)：从字典 args 中获取键 "product_name" 对应的值，如果键不存在，则返回 None。
        if not isinstance(product_name, str) or not product_name.strip():
            return {"error": "product_name必须是非空字符串"}
        #.strip()：去掉字符串首尾的空白字符，确保商品名称不只是空格。
    # 4. 检查目标库存
    if tool_name == ["calculate_restock", "create_purchase_order"]:
        target = args.get("target", 30)

        if type(target) is not int or target < 0:
            return {"error": "target必须是非负整数"}

    # 5. 检查订单编号
    if tool_name == "get_purchase_order":
        order_id = args.get("order_id")

        if not isinstance(order_id, str) or not order_id.strip():
            return {"error": "order_id必须是非空字符串"}

    #6. 检查审批状态
    if tool_name == "list_purchase_orders":
        status = args.get("status")

        valid_statuses = [
            "pending_approval",
            "approved",
            "rejected"
        ]

        if status is not None and status not in valid_statuses:
            return {"error": "订单状态不合法"}


    # 7. 执行工具
    try:
        result = function(**args)
        return result

    except TypeError as e:
        return {"error": f"工具参数错误：{e}"}

    except Exception as e:
        return {"error": f"工具执行失败：{type(e).__name__}"}



def chat(user_input):
    messages.append({
        "role": "user",
        "content": user_input
    }) #messages：一个列表，用来保存对话中的消息。
#.append(...)：在列表末尾添加一条新消息。
#"role": "user"：标记这条消息来自用户。
#"content": user_input：消息内容是变量 user_input 保存的文字

    max_steps = 10

    for step in range(max_steps):
        response = client.chat.completions.create(#client.chat.completions.create(...)：调用 OpenAI API 的 chat.completions.create 方法，生成回复。
            model=model_name,
            messages=messages,
            tools=tools,
            tool_choice="auto" #tool_choice：指定工具选择策略，auto 表示让模型自动选择工具。
        )

        assistant_message = response.choices[0].message
        #取出返回结果中的第一个元素，即模型生成的回复消息，保存到变量 assistant_message 中。
        messages.append(assistant_message)

        # 没有工具调用，说明模型给出了最终回答
        if not assistant_message.tool_calls:
            return assistant_message.content

        # 执行本轮请求的所有工具
        for tool_call in assistant_message.tool_calls:
            tool_name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)
            #arguments:模型生成的JSON格式参数文本
            print(f"\n第{step + 1}轮调用工具：{tool_name}")
            print("工具参数：", args)

            
            if tool_name == "update_order_status":

                # 检查工具参数
                if not isinstance(args, dict):
                    result = {"error": "审批参数格式错误"}

                elif not isinstance(args.get("order_id"), str) or not args["order_id"].strip():
                    result = {"error": "订单编号不能为空"}

                elif args.get("new_status") not in ["approved", "rejected"]:
                    result = {"error": "审批状态不合法"}

                else:
                    # 用户确认前不执行修改
                    print("\n即将修改订单状态：")
                    print("订单编号：", args["order_id"])
                    print("目标状态：", args["new_status"])

                    confirmation = input("确认执行审批？(yes/no)：").strip().lower()

                    if confirmation == "yes":
                        result = execute_tool(tool_name, args)
                    else:
                        result = {"error": "用户取消审批，订单未修改"}

            else:
                result = execute_tool(tool_name, args)


            print("工具执行结果：", result)

            messages.append({
                "role": "tool", #标记这条消息来自工具。
                "tool_call_id": tool_call.id, #对应模型之前生成的工具调用 ID，确保模型可以将工具结果与之前的调用关联起来。
                "content": json.dumps(
                    result,
                    ensure_ascii=False #让中文保留原样显示，而不是被转义为 Unicode 编码
                ) #json.dumps(...)：将 Python 对象转换为 JSON 字符串。
            })

    raise RuntimeError("工具调用轮数超过上限，任务未完成")
    #如果模型在指定轮数内没有给出最终回答，程序会抛出 RuntimeError 异常，提示工具调用轮数超过上限，任务未完成。

# 程序入口
if __name__ == "__main__": 
    print("ProcurePilot采购助手已启动！") #在终端打印启动提示
    print("输入 exit 退出程序。")

    while True: #进入一个无限循环，等待用户输入。直到遇到break
        user_input = input("\n你：").strip()
        #换行显示“你”，然后等待用户输入。strip()：去掉输入字符串的首尾空白字符。
        if user_input.lower() == "exit":
            print("采购助手已退出。")
            break

        if not user_input:
            continue #如果用户输入为空字符串，则跳过本轮循环，继续等待下一次输入。

        try:
            answer = chat(user_input)
            print("\nAgent：", answer)
        except Exception as e: #e保存了异常对象，包含错误信息和类型
            print("运行出错：", e)
            messages[:] = messages[:1]
            #messages[:] = messages[:1]：将 messages 列表重置为只保留第一条消息，即系统提示词。
