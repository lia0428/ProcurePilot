#这个文件负责启动新任务，以及恢复之前暂停的任务
from uuid import uuid4

from langgraph.types import Command
from procurement_graph import create_graph


def show_result(result):
    if "__interrupt__" in result:
        approval = result["__interrupt__"][0].value

        print("\n订单正在等待人工审批")
        print(f"订单ID：{approval['order_id']}")
        print(f"商品：{approval['product_name']}")
        print(f"数量：{approval['quantity']}")
        print(f"供应商：{approval['supplier_name']}")
        print(f"总金额：¥{approval['total_price']}")
    else:
        print("\n工作流执行完成")
        print(f"订单ID：{result.get('order_id', '无')}")
        print(f"订单状态：{result.get('order_status', '未知')}")


def main():
    graph, conn = create_graph()

    try:
        print("\n1. 创建新的采购任务")
        print("2. 恢复之前的审批任务")

        choice = input("请选择（1/2）：").strip()

        if choice == "1":
            user_message = input("请输入采购需求：")

            thread_id = str(uuid4())
            config = {
                "configurable": {
                    "thread_id": thread_id
                }
            }

            result = graph.invoke(
                {"user_message": user_message},
                config=config
            )

            show_result(result)

            if "__interrupt__" in result:
                print(f"\n请保存这个工作流ID：{thread_id}")
                print("现在可以关闭程序，稍后恢复审批。")

        elif choice == "2":
            thread_id = input("请输入工作流ID：").strip()

            config = {
                "configurable": {
                    "thread_id": thread_id
                }
            }

            snapshot = graph.get_state(config)
        # graph：之前创建的工作流对象。
        # get_state()：工作流对象的方法，读取保存的状态。
        # config：配置，通常包含 thread_id，用来指定查询哪一次任务。
        # snapshot：返回的状态快照对象，记录状态数据、下一步节点等信息
            if not snapshot.next:# next：是一个元组，表示工作流的下一步节点。如果为 None，说明工作流已经完成或没有待处理的任务。
                print("未找到正在等待审批的任务")
                return

            approval = snapshot.tasks[0].interrupts[0].value

            print("\n待审批订单")
            print(f"订单ID：{approval['order_id']}")
            print(f"商品：{approval['product_name']}")
            print(f"采购数量：{approval['quantity']}")
            print(f"供应商：{approval['supplier_name']}")
            print(f"总金额：¥{approval['total_price']}")

            decision = input(
                "\n是否批准？(y/n)："
            ).strip().lower()

            if decision not in ("y", "n"):
                print("无效输入，订单保持待审批")
                return

            result = graph.invoke(
                Command(
                    resume="approved" if decision == "y"
                    else "rejected"
                ),
                config=config
            )

            show_result(result)

        else:
            print("无效选项")

    except ValueError as exc:
        print(f"处理失败：{exc}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
