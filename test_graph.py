from typing import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import InMemorySaver


class ApprovalState(TypedDict):
    order_id: int
    status: str


def request_approval(state: ApprovalState):
    decision = interrupt({
        "order_id": state["order_id"],
        "message": "请审批采购订单"
    })

    return {"status": decision}


def build_test_graph():
    builder = StateGraph(ApprovalState)
    #调用 StateGraph 类，创建工作流构建器对象，保存到变量 builder。ApprovalState 是前面定义的状态类型，描述工作流中传递的数据结构

    builder.add_node("request_approval", request_approval)
    builder.add_edge(START, "request_approval")
    builder.add_edge("request_approval", END)

    return builder.compile(
        checkpointer=InMemorySaver()
    )
#InMemorySaver()：创建一个在内存中保存工作流进度的对象。
#builder.compile(...)：编译出可执行的工作流，并配置保存器

def test_graph_interrupt():
    graph = build_test_graph()

    config = {
        "configurable": {
            "thread_id": "test-interrupt"
        }
    }

    result = graph.invoke(
        {"order_id": 1, "status": "pending_approval"},
        config=config
    )

    assert "__interrupt__" in result

    approval = result["__interrupt__"][0].value

    assert approval["order_id"] == 1


def test_graph_resume_approved():
    graph = build_test_graph()

    config = {
        "configurable": {
            "thread_id": "test-approved"
        }
    }

    graph.invoke(
        {"order_id": 2, "status": "pending_approval"},
        config=config
    )

    result = graph.invoke(
        Command(resume="approved"),
        config=config
    )

    assert result["status"] == "approved"


def test_graph_resume_rejected():
    graph = build_test_graph()

    config = {
        "configurable": {
            "thread_id": "test-rejected"
        }
    }

    graph.invoke(
        {"order_id": 3, "status": "pending_approval"},
        config=config
    )

    result = graph.invoke(
        Command(resume="rejected"),
        config=config
    )

    assert result["status"] == "rejected"