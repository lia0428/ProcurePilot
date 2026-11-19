
from uuid import uuid4

from langgraph.types import Command
from procurement_graph import graph


def main():
    user_message = input("请输入采购需求：").strip()

    config = {
        "configurable": {
            "thread_id": str(uuid4()) #为每次运行生成唯一的线程ID，确保工作流实例的隔离和独立性
        }
    }

    try:
        result = graph.invoke(
            {"user_message": user_message},
            config=config
        )

        # 判断是否遇到人工审批中断
        if "__interrupt__" in result:
            approval = result["__interrupt__"][0].value

            print("\n待审批采购订单")
            print(f"订单ID：{approval['order_id']}")
            print(f"商品：{approval['product_name']}")
            print(f"采购数量：{approval['quantity']}")
            print(f"供应商：{approval['supplier_name']}")
            print(f"总金额：¥{approval['total_price']}")

            choice = input("\n是否批准？(y/n)：").strip().lower()

            if choice not in ("y", "n"):
                print("未提交有效审批决定，订单保持待审批")
                return

            decision = "approved" if choice == "y" else "rejected"

            result = graph.invoke(
                Command(resume=decision),
                config=config
            )

        print("\n最终处理结果：")
        print(f"商品：{result.get('product_name')}")
        print(f"订单ID：{result.get('order_id', '无')}")
        print(f"订单状态：{result.get('order_status', '未知')}")

    except ValueError as exc:
        print(f"\n处理失败：{exc}")


if __name__ == "__main__":
    main()
