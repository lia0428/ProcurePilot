import pytest #模块，提供测试功能
import database #项目模块
import procurement_graph #项目模块

from langgraph.types import Command #类，创建恢复工作流的命令
from langgraph.checkpoint.memory import InMemorySaver
#类，在内存中保存工作流进度

#以 @ 开头的这种写法叫装饰器，它写在函数前面，给下面的函数增加用途或行为
#这里的意思是告诉 pytest：下面这个函数是“测试准备函数”，测试需要它时，先运行它准备环境
@pytest.fixture
def agent_graph(tmp_path, monkeypatch):
    #tmp_path：pytest 提供的临时目录对象，用于存放测试文件或数据库，测试结束后会自动清理
    #monkeypatch：pytest 提供的模块，用于修改模块或函数的行为，测试结束后会自动恢复(一个可以临时修改属性、并在测试结束后恢复的工具对象)

    # 1. 使用临时数据库，不影响真实订单
    monkeypatch.setattr( #setattr: set attribute，设置属性值
        database,#要修改的对象
        "DB_PATH",#要修改的属性
        tmp_path / "test_procurement.db"#新的值
    )

    database.init_db()

    conn = database.get_connection()
    try:
        cursor = conn.execute( 
        #execute: 执行SQL语句，返回一个游标对象
            "INSERT INTO products (name) VALUES (?)",
            ("键盘",)
        )
        product_id = cursor.lastrowid#是数据库根据表结构自动分配编号，`cursor.lastrowid` 负责读取这个编号

        conn.execute(
            "INSERT INTO inventory (product_id, stock) VALUES (?, ?)",
            (product_id, 8)
        )

        conn.execute("""
            INSERT INTO suppliers
            (product_id, name, price, available_stock, lead_days)
            VALUES (?, ?, ?, ?, ?)
        """, (product_id, "测试供应商", 50.0, 100, 3))

        conn.commit()
    finally:
        conn.close()

    # 2. 模拟GLM解析结果，不实际调用API
    class FakeIntent:
        product_name = "键盘"
        target_stock = 30

    monkeypatch.setattr(
        procurement_graph,#项目模块
        "parse_purchase_intent",#项目模块中的函数
        lambda message: FakeIntent()
        #lambda表达式，定义一个匿名函数，参数是 message，返回值是 FakeIntent 类的实例
    )

    # 3. 使用内存检查点运行真实采购节点
    graph = procurement_graph.builder.compile(
        checkpointer=InMemorySaver()
    )
    #使用真实采购工作流的构建器，但将进度保存在内存中，而不是数据库中
    return graph


def test_agent_creates_pending_order(agent_graph):
    config = {"configurable": {"thread_id": "create-test"}}
    #config：配置字典，包含一个可配置的 thread_id，用于标识工作流的执行线程（给本次执行指定线程 ID，用于关联工作流进度）
    result = agent_graph.invoke(
        {"user_message": "帮我把键盘库存补到30件"},
        config=config
    )

    assert "__interrupt__" in result#检查结果中是否包含中断信息

    approval = result["__interrupt__"][0].value
    #获取中断记录集合，取第一条中断记录，读取该记录携带的数据
    assert approval["product_name"] == "键盘"
    assert approval["quantity"] == 22
    assert approval["total_price"] == 1100.0

    saved = database.get_purchase_order_db(approval["order_id"])
    assert saved["status"] == "pending_approval"


def test_agent_approval_updates_database(agent_graph):
    config = {"configurable": {"thread_id": "approve-test"}}

    result = agent_graph.invoke(
        {"user_message": "采购键盘"},
        config=config
    )
    order_id = result["__interrupt__"][0].value["order_id"]

    resumed = agent_graph.invoke(
        Command(resume="approved"),
        config=config
    )

    assert resumed["order_status"] == "approved"
    assert database.get_purchase_order_db(order_id)["status"] == "approved"


def test_agent_rejection_updates_database(agent_graph):
    config = {"configurable": {"thread_id": "reject-test"}}

    result = agent_graph.invoke(
        {"user_message": "采购键盘"},
        config=config
    )
    order_id = result["__interrupt__"][0].value["order_id"]

    resumed = agent_graph.invoke(
        Command(resume="rejected"),
        config=config
    )

    assert resumed["order_status"] == "rejected"
    assert database.get_purchase_order_db(order_id)["status"] == "rejected"


def test_agent_skips_order_when_stock_sufficient(
    agent_graph, monkeypatch
):
    class FakeIntent:
        product_name = "键盘"
        target_stock = 5

    monkeypatch.setattr(
        procurement_graph,
        "parse_purchase_intent",
        lambda message: FakeIntent()
    )

    config = {"configurable": {"thread_id": "no-restock-test"}}

    result = agent_graph.invoke(
        {"user_message": "键盘库存保持5件"},
        config=config
    )

    assert "__interrupt__" not in result
    assert result["order_status"] == "no_restock_needed"
    assert database.list_purchase_orders_db() == []