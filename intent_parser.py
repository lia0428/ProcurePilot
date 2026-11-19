import json #模块，将JSON字符串转换为Python对象，或者将Python对象转换为JSON字符串
import os #模块，用于处理操作系统相关的功能，如读取环境变量

from dotenv import load_dotenv #函数，加载.env文件中的环境变量到系统环境中
from openai import OpenAI #类，提供与OpenAI API交互的功能，包括发送请求和接收响应
from pydantic import BaseModel, Field, ValidationError
#BaseModel：用于定义数据模型的基类，提供数据验证和序列化功能。Field：用于定义模型字段的属性的函数，如类型、默认值和验证规则。ValidationError：当数据验证失败时抛出的异常类。

# 1. 加载环境变量
load_dotenv()

client = OpenAI(
    api_key=os.getenv("GLM_API_KEY"),
    base_url="https://open.bigmodel.cn/api/paas/v4/"
)
#加载.env文件中的环境变量，并使用OpenAI类创建一个客户端对象，用于与OpenAI API进行交互。api_key：OpenAI API的密钥，用于身份验证。base_url：OpenAI API的基本URL，用于指定API的访问地址。

MODEL = os.getenv("GLM_MODEL", "glm-4-flash")
#读取模型名称；如果环境变量中没有 GLM_MODEL，就使用默认字符串 "glm-4-flash"

# 2. 定义结构化数据格式
class PurchaseIntent(BaseModel):
    product_name: str = Field(min_length=1)
    target_stock: int = Field(gt=0) #gt：大于，gt=0表示目标库存必须大于0
#定义一个名为 PurchaseIntent 的类，继承 BaseModel，因此具备 Pydantic 的数据校验能力

# 3. 解析自然语言
def parse_purchase_intent(user_message: str) -> PurchaseIntent:
#user_message: str：表示预期传入字符串。-> PurchaseIntent：表示预期返回 PurchaseIntent 对象
    response = client.chat.completions.create(
#调用客户端的 create() 方法，实际发送请求，并把完整响应保存到 response
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是采购需求解析助手。"
                    "从用户输入中提取商品名称和目标库存。"
                    "只返回JSON对象，不要输出Markdown。"
                    '格式：{"product_name":"键盘","target_stock":30}。'
                    "如果用户没有明确给出商品名称或目标库存，"
                    "返回空对象 {}，不要猜测。"
                )
            },
            {
                "role": "user",
                "content": user_message
            }
        ],
        temperature=0#temperature=0：表示生成的文本将更加确定性，减少随机性。
    )

    content = response.choices[0].message.content
    #从第一条响应中提取消息内容，保存到 content 变量中
    if not content:
        raise ValueError("GLM没有返回有效内容")

    try:
        data = json.loads(content)
        return PurchaseIntent.model_validate(data)
    #model_validate() 方法用于验证数据是否符合 PurchaseIntent 模型的定义，并返回一个 PurchaseIntent 实例

    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(
            f"无法解析采购需求，请明确提供商品名称和目标库存：{exc}"
        ) from exc


# 4. 本地测试
if __name__ == "__main__":
    user_input = "帮我把键盘库存补到30件"

    intent = parse_purchase_intent(user_input)

    print("商品名称：", intent.product_name)
    print("目标库存：", intent.target_stock)