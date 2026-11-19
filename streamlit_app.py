from langgraph.types import Command
import streamlit as st
from uuid import uuid4
from database import list_purchase_orders_db,save_order_workflow_db,get_order_workflow_db
from procurement_graph import create_graph


st.set_page_config(
    page_title="ProcurePilot",
    page_icon="🛒",
    layout="wide"
)

st.title("🛒 ProcurePilot")
st.caption("AI智能采购助手 · GLM + LangGraph + SQLite")

st.subheader("智能采购")

user_message = st.text_input(
    "请输入采购需求",
    placeholder="例如：帮我把键盘库存补到30件"
)

if st.button("开始采购分析", type="primary"):
    if not user_message.strip():
        st.warning("请先输入采购需求")
    else:
        with st.spinner("Agent正在分析采购需求..."):
            graph, conn = create_graph()

            try:
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

                if "__interrupt__" in result:
                    approval = result["__interrupt__"][0].value

                    st.success("采购订单已创建，等待人工审批")
                    save_order_workflow_db(
                        approval["order_id"],
                        thread_id
                    )
                    st.session_state["pending_thread_id"] = thread_id
                    st.session_state["pending_approval"] = approval

                    # st.write("### 采购订单")
                    # st.write(f"订单ID：{approval['order_id']}")
                    # st.write(f"商品：{approval['product_name']}")
                    # st.write(f"采购数量：{approval['quantity']}")
                    # st.write(f"供应商：{approval['supplier_name']}")
                    # st.write(f"总金额：¥{approval['total_price']}")

                else:
                    status = result.get("order_status")

                    if status == "already_pending":
                        st.warning(
                            f"该商品已有待审批订单："
                            f"{result.get('order_id')}"
                        )

                    elif status == "no_restock_needed":
                        st.info("库存充足，无需采购")

                    elif status == "no_supplier_available":
                        st.warning("没有库存充足的供应商")

                    else:
                        st.write(result)

            except Exception as exc:
                st.error(f"处理失败：{exc}")

            finally:
                conn.close()


# 展示本次会话中的待审批订单
if "pending_approval" in st.session_state:
    st.divider()
    st.subheader("待审批订单")

    approval = st.session_state["pending_approval"]

    st.write(f"订单ID：{approval['order_id']}")
    st.write(f"商品：{approval['product_name']}")
    st.write(f"采购数量：{approval['quantity']}")
    st.write(f"供应商：{approval['supplier_name']}")
    st.write(f"总金额：¥{approval['total_price']}")

    
    col1, col2 = st.columns(2)

    with col1:
        approve_clicked = st.button(
            "批准订单",
            type="primary",
            use_container_width=True
        )

    with col2:
        reject_clicked = st.button(
            "拒绝订单",
            use_container_width=True
        )

    if approve_clicked or reject_clicked:
        decision = (
            "approved" if approve_clicked else "rejected"
        )

        thread_id = st.session_state["pending_thread_id"]

        config = {
            "configurable": {
                "thread_id": thread_id
            }
        }

        graph, conn = create_graph()

        try:
            # 确认工作流确实处于暂停状态
            snapshot = graph.get_state(config)

            if not snapshot.next:
                st.warning("该工作流已结束或不存在待审批任务")
            else:
                result = graph.invoke(
                    Command(resume=decision),
                    config=config
                )

                if "__interrupt__" in result:
                    st.warning("工作流仍在等待人工处理")
                else:
                    st.success(
                        f"订单处理成功：{result['order_status']}"
                    )

                    st.session_state.pop(
                        "pending_approval", None
                    )
                    st.session_state.pop(
                        "pending_thread_id", None
                    )

                    st.rerun()

        except Exception as exc:
            st.error(f"审批失败：{exc}")

        finally:
            conn.close()


st.divider()
st.subheader("📋 采购订单记录")

orders = list_purchase_orders_db()

if orders:
    st.dataframe(
        orders,
        use_container_width=True,
        hide_index=True
    )
else:
    st.info("暂无采购订单")

st.subheader("🔄 恢复待审批订单")

pending_orders = [
    order for order in orders
    if order["status"] == "pending_approval"
]

if not pending_orders:
    st.info("目前没有待审批订单")
else:
    order_options = {
        f"订单 #{order['id']} · {order['product_name']}":
        order["id"]
        for order in pending_orders
    }

    selected_label = st.selectbox(
        "选择需要恢复的订单",
        options=list(order_options.keys())
    )

    if st.button("恢复审批"):
        order_id = order_options[selected_label]
        thread_id = get_order_workflow_db(order_id)

        if thread_id is None:
            st.warning(
                "该订单没有工作流映射，"
                "可能是在持久化功能上线前创建的"
            )
        else:
            graph, conn = create_graph()

            try:
                config = {
                    "configurable": {
                        "thread_id": thread_id
                    }
                }

                snapshot = graph.get_state(config)

                if not snapshot.next:
                    st.warning(
                        "该工作流不存在待恢复的任务"
                    )
                elif not snapshot.tasks or not snapshot.tasks[0].interrupts:
                    st.warning(
                        "该工作流当前没有待处理的审批中断"
                    )
                else:
                    approval = snapshot.tasks[0].interrupts[0].value

                    st.session_state["pending_thread_id"] = thread_id
                    st.session_state["pending_approval"] = approval

                    st.rerun()

            except Exception as exc:
                st.error(f"恢复失败：{exc}")

            finally:
                conn.close()