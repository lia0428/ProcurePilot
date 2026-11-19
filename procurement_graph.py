
from typing import TypedDict, NotRequired

from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
import sqlite3
from pathlib import Path
from langgraph.checkpoint.sqlite import SqliteSaver
# SqliteSaver：用于将工作流状态保存到SQLite数据库的类，适合演示和测试场景。对于生产环境，建议使用更强大的数据库系统，如PostgreSQL或MySQL。
from intent_parser import parse_purchase_intent
from database import (
    calculate_restock_db,
    get_suppliers_db,
    create_purchase_order_db,
    update_order_status_db
)


class ProcurementState(TypedDict):
    user_message: str
    product_name: NotRequired[str]
    target_stock: NotRequired[int]
    current_stock: NotRequired[int]
    restock_quantity: NotRequired[int]
    supplier_name: NotRequired[str]
    total_price: NotRequired[float]
    order_id: NotRequired[int]
    order_status: NotRequired[str]


def parse_intent(state: ProcurementState):
    intent = parse_purchase_intent(state["user_message"])
    return {
        "product_name": intent.product_name,
        "target_stock": intent.target_stock
    }


def check_inventory(state: ProcurementState):
    result = calculate_restock_db(
        state["product_name"],
        state["target_stock"]
    )
    if result is None:
        raise ValueError("商品不存在")

    return {
        "current_stock": result["current_stock"],
        "restock_quantity": result["restock_quantity"]
    }


def select_supplier(state: ProcurementState):
    quantity = state["restock_quantity"]

    if quantity == 0:
        return {"supplier_name": "", "total_price": 0.0}

    suppliers = get_suppliers_db(state["product_name"])
    available = [
        s for s in suppliers
        if s["available_stock"] >= quantity
    ]

    if not available:
        return {
            "supplier_name": "",
            "total_price": 0.0,
            "order_status": "no_supplier_available"
        }

    best = min(available, key=lambda s: (s["price"], s["id"]))

    return {
        "supplier_name": best["name"],
        "total_price": round(best["price"] * quantity, 2)
    }


def create_order(state: ProcurementState):
    if state.get("order_status") == "no_supplier_available":
        return {}

    if state["restock_quantity"] == 0:
        return {"order_status": "no_restock_needed"}

    result = create_purchase_order_db(
        state["product_name"],
        state["target_stock"]
    )

    if "error" in result:
        if result["error"] == "duplicate_pending_order":
            return {
                "order_id": result["existing_order_id"],
                "order_status": "already_pending"
            }
        return {"order_status": result["error"]}

    return {
        "order_id": result["order_id"],
        "order_status": result["status"],
        "supplier_name": result["supplier_name"],
        "total_price": result["total_price"]
    }


def request_approval(state: ProcurementState):
    if state.get("order_status") != "pending_approval":
        return {}

    decision = interrupt({
        "order_id": state["order_id"],
        "product_name": state["product_name"],
        "quantity": state["restock_quantity"],
        "supplier_name": state["supplier_name"],
        "total_price": state["total_price"],
        "message": "请确认是否批准该采购订单"
    })

    if decision not in ("approved", "rejected"):
        raise ValueError("无效的审批结果")

    result = update_order_status_db(
        state["order_id"],
        decision
    )

    if "error" in result:
        raise ValueError(f"审批失败：{result['error']}")

    return {"order_status": decision}


builder = StateGraph(ProcurementState)

builder.add_node("parse_intent", parse_intent)
builder.add_node("check_inventory", check_inventory)
builder.add_node("select_supplier", select_supplier)
builder.add_node("create_order", create_order)
builder.add_node("request_approval", request_approval)

builder.add_edge(START, "parse_intent")
builder.add_edge("parse_intent", "check_inventory")
builder.add_edge("check_inventory", "select_supplier")
builder.add_edge("select_supplier", "create_order")
builder.add_edge("create_order", "request_approval")
builder.add_edge("request_approval", END)

CHECKPOINT_PATH = (
    Path(__file__).resolve().parent
    / "data"
    / "langgraph_checkpoints.db"
)

CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)


def create_graph():
    conn = sqlite3.connect(
        CHECKPOINT_PATH,
        check_same_thread=False #允许这个连接被创建它的线程之外的其他线程使用，方便工作流在不同线程中执行数据库操作
    )

    checkpointer = SqliteSaver(conn)
    #SqliteSaver 是类，`SqliteSaver(conn)` 创建一个对象，使用 conn 连接的数据库保存工作流检查点
    checkpointer.setup()#调用保存器的 setup() 方法，确保数据库中存在必要的表和结构，以便保存工作流状态

    graph = builder.compile(checkpointer=checkpointer)
#调用 builder 的 compile() 方法，把之前定义的节点和边编译成可执行工作流，并指定使用这个保存器
    return graph, conn
