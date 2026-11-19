import os
from dotenv import load_dotenv
from openai import OpenAI
#本文件是我们之前创建的大模型API连接测试文件，主要用于验证Python能否成功调用智谱GLM
# 读取 .env 文件
load_dotenv()

# 获取环境变量
api_key = os.getenv("GLM_API_KEY")
model_name = os.getenv("GLM_MODEL")

if not api_key:
    raise ValueError("未找到GLM_API_KEY")

if not model_name:
    raise ValueError("未找到GLM_MODEL")

# 创建智谱客户端
client = OpenAI(
    api_key=api_key,
    base_url="https://open.bigmodel.cn/api/paas/v4/"
)

# 调用大模型
response = client.chat.completions.create(
    model=model_name,
    messages=[
        {
            "role": "system",
            "content": "你是一名专业的采购助手。"
        },
        {
            "role": "user",
            "content": "你好，请用一句话介绍自己。"
        }
    ]
)

print(response.choices[0].message.content)