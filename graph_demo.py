from intent_parser import parse_purchase_intent
from typing import TypedDict, NotRequired
from langgraph.graph import StateGraph, START, END
#StateGraph：用于构建状态图的类。START：表示状态图的起始节点。END：表示状态图的结束节点。
from database import calculate_restock_db,get_suppliers_db
from database import create_purchase_order_db

# 1. 定义状态

class ProcurementState(TypedDict):
    user_message: str # 用户输入的消息
    #NotRequired：表示这些字段可以不在初始输入中出现，由后面的节点逐步生成
    product_name: NotRequired[str]
    target_stock: NotRequired[int]
    message: NotRequired[str]
    current_stock: NotRequired[int]
    restock_quantity: NotRequired[int]
    supplier_name: NotRequired[str]
    unit_price: NotRequired[float]
    total_price: NotRequired[float]
    lead_days: NotRequired[int]
    order_id: NotRequired[int]
    order_status: NotRequired[str]


def parse_intent(state: ProcurementState): 
    #state：参数，接收工作流当前的状态字典
    intent = parse_purchase_intent(
        state["user_message"]
    )

    return {
        "product_name": intent.product_name,
        "target_stock": intent.target_stock
    }


# 2. 第一个节点：准备采购
def prepare_purchase(state: ProcurementState):
    return {
        "message": f"准备将{state['product_name']}库存补充至{state['target_stock']}件"
    }


# 3. 第二个节点：查询库存
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
    product_name = state["product_name"]
    quantity = state["restock_quantity"]

    # 无需补货时，不选择供应商
    if quantity == 0:
        return {
            "supplier_name": "",
            "unit_price": 0.0,
            "total_price": 0.0,
            "lead_days": 0
        }

    # 查询SQLite中的供应商
    suppliers = get_suppliers_db(product_name)

    # 筛选库存充足的供应商
    available = [
        s for s in suppliers
        if s["available_stock"] >= quantity
    ]

    if not available:
        return {
            "supplier_name": "",
            "unit_price": 0.0,
            "total_price": 0.0,
            "lead_days": 0,
            "order_status": "no_supplier_available"
        }

    # 选择价格最低的供应商
    best = min(
        available,
        key=lambda s: (s["price"], s["id"])
        #min() 不只能比较数字，也可以通过 key 指定比较规则key=lambda s: (s["price"], s["id"]) 表示按照供应商的价格进行排序，如果价格相同，则按照供应商ID排序。
    )

    return {
        "supplier_name": best["name"],
        "unit_price": best["price"],
        "total_price": round(best["price"] * quantity, 2),
        "lead_days": best["lead_days"]
    }



def create_order(state: ProcurementState):
    if state.get("order_status") == "no_supplier_available":
        return {
            "order_status": "no_supplier_available"
        }
    # 库存充足，不创建订单
    if state["restock_quantity"] == 0:
        return {
            "order_status": "no_restock_needed"
        }

    # 调用已有的SQLite订单创建函数
    result = create_purchase_order_db(
        state["product_name"],
        state["target_stock"]
    )

    # 处理数据库返回的业务错误
    if "error" in result:
        error = result["error"]

        if error == "duplicate_pending_order":
            return {
                "order_id": result["existing_order_id"],
                "order_status": "already_pending"
            }

        if error == "no_restock_needed":
            return {
                "order_status": "no_restock_needed"
            }

        if error == "no_supplier_available":
            return {
                "order_status": "no_supplier_available"
            }

        raise ValueError(f"创建订单失败：{error}")

    return {
        "order_id": result["order_id"],
        "order_status": result["status"]
    }


# 4. 构建工作流


builder = StateGraph(ProcurementState)

builder.add_node("parse_intent", parse_intent)
builder.add_node("prepare", prepare_purchase)
builder.add_node("check_inventory", check_inventory)
builder.add_node("select_supplier", select_supplier)
builder.add_node("create_order", create_order)

builder.add_edge(START, "parse_intent")
builder.add_edge("parse_intent", "prepare")
builder.add_edge("prepare", "check_inventory")
builder.add_edge("check_inventory", "select_supplier")
builder.add_edge("select_supplier", "create_order")
builder.add_edge("create_order", END)

graph = builder.compile()

#compile() 同样是方法。它返回一个可执行的工作流对象，保存到变量 graph

# 5. 执行工作流



def run_procurement(user_message: str):
    try:
        result = graph.invoke({
            "user_message": user_message
        })

        print("\n采购分析结果：")
        print(f"商品：{result['product_name']}")
        print(f"当前库存：{result['current_stock']}")
        print(f"目标库存：{result['target_stock']}")
        print(f"建议采购：{result['restock_quantity']}件")

        status = result["order_status"]

        if status == "pending_approval":
            print(f"推荐供应商：{result['supplier_name']}")
            print(f"预计总价：¥{result['total_price']}")
            print(f"订单ID：{result['order_id']}")
            print("订单状态：待人工审批")

        elif status == "already_pending":
            print(f"已有待审批订单：{result['order_id']}")
            print("已阻止重复创建")

        elif status == "no_restock_needed":
            print("库存充足，无需采购")

        elif status == "no_supplier_available":
            print("供应商库存不足，无法创建订单")

        return result

    except ValueError as exc:
        print(f"\n采购需求处理失败：{exc}")
        return None


if __name__ == "__main__":
    user_input = input("请输入采购需求：")
    run_procurement(user_input)
