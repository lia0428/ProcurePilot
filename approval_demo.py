
from typing import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import InMemorySaver
#InMemorySaver：用于在内存中保存工作流状态的类，适合演示和测试场景。对于生产环境，建议使用持久化存储方案，如数据库或文件系统。

# 1. 定义工作流状态
class ApprovalState(TypedDict):
    product_name: str
    quantity: int
    approved: bool


# 2. 人工审批节点
def request_approval(state: ApprovalState):
    decision = interrupt({
        "message": "请审批采购订单",
        "product_name": state["product_name"],
        "quantity": state["quantity"]
    })

    return {
        "approved": decision == "approved"
    }


# 3. 构建工作流
builder = StateGraph(ApprovalState)

builder.add_node("approval", request_approval)

builder.add_edge(START, "approval")
builder.add_edge("approval", END)

# 4. 配置状态保存器
graph = builder.compile(
    checkpointer=InMemorySaver()
    #InMemorySaver()：创建一个将工作流进度保存在内存中的对象
)

# 5. 为本次审批设置唯一线程ID
config = {  #嵌套字典
    "configurable": {
        "thread_id": "approval-demo-001"
    }
}

# 6. 第一次执行：遇到interrupt暂停
result = graph.invoke({
    "product_name": "键盘",
    "quantity": 22,
    "approved": False
}, config=config)

print("第一次执行结果：")
print(result)

# 7. 模拟人工审批
decision = input(
    "\n请输入审批结果（approved/rejected）："
).strip().lower()
#.strip()：去掉首尾空白。.lower()：转换为小写

if decision not in ("approved", "rejected"):
    print("无效审批结果，工作流保持暂停")
else:
    # 8. 从暂停位置恢复
    result = graph.invoke(
        Command(resume=decision),#Command(resume=decision)：创建一个命令对象，指示工作流从暂停位置恢复，并传入审批结果。
        config=config #相同的线程ID，确保恢复到正确的工作流实例
    )

    print("\n恢复后的执行结果：")
    print(result)
