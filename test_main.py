from fastapi.testclient import TestClient
from main import app
import pytest
import database
import sqlite3

client = TestClient(app)
#创建一个测试客户端，可以直接调用FastAPI接口，不需要另外启动Uvicorn服务器。

def test_home():
    response = client.get("/")
    assert response.status_code == 200
    #assert Python中的断言语句，用来检查实际结果是否符合预期(如果实际返回200，测试通过；否则测试失败)
    assert response.json()["message"] == "ProcurePilot API is running"


def test_inventory_not_found():
    response = client.get("/inventory/不存在的商品")
    assert response.status_code == 404
#lient.get(...)：模拟发送 GET 请求，查询名为“不存在的商品”的库存。
#response：保存接口返回的响应。
#assert response.status_code == 404：断言响应状态码必须为 404，表示商品不存在。

def test_invalid_purchase_request():
    response = client.post(
        "/purchase-orders",
        json={
            "product_name": "键盘",
            "target_stock": -5
        }
    )
    assert response.status_code == 422




@pytest.fixture#装饰器，用于定义一个测试夹具（fixture）
def test_db(tmp_path, monkeypatch):
    # 1. 创建临时数据库路径
    test_db_path = tmp_path / "test.db"

    # 2. 临时替换数据库路径
    monkeypatch.setattr(  #setattr()：将某个对象的属性值设置为指定值。
        database,
        "DB_PATH",
        test_db_path
        #临时将 database.DB_PATH 改为测试路径test_db_path
    )
    
    # 3. 初始化测试数据库的表结构
    database.init_db()

    # 4. 插入测试商品和库存
    conn = database.get_connection()

    try:
        cursor = conn.execute(
            "INSERT INTO products (name) VALUES (?)",
            ("键盘",)
        )

        product_id = cursor.lastrowid
        #cursor.lastrowid：获取最后插入行的ID，即商品ID。
        conn.execute(
            """
            INSERT INTO inventory (product_id, stock)
            VALUES (?, ?)
            """,
            (product_id, 8)
        )

        # 5. 插入测试供应商
        conn.execute(
            """
            INSERT INTO suppliers
                (product_id, name, price,
                 available_stock, lead_days)
            VALUES (?, ?, ?, ?, ?)
            """,
            (product_id, "测试供应商", 50.0, 100, 3)
        )

        conn.commit() # 将插入操作正式提交到数据库。如果不提交，关闭连接后通常不会保留未提交的修改。

    finally:
        conn.close()

    return test_db_path



def test_create_purchase_order(test_db):

    response = client.post(
        "/purchase-orders",
        json={
            "product_name": "键盘",
            "target_stock": 30
        }
    ) #发送POST请求，创建一个购买请求。

    # 验证HTTP状态码
    assert response.status_code == 201

    data = response.json()

    # 验证业务计算
    assert data["quantity"] == 22
    assert data["supplier_name"] == "测试供应商"
    assert data["total_price"] == 1100.0
    assert data["status"] == "pending_approval"

    # 验证订单确实保存到了测试数据库
    conn = database.get_connection()

    try:
        row = conn.execute(
            """
            SELECT quantity, status
            FROM purchase_orders
            WHERE id = ?
            """,
            (data["order_id"],)
        ).fetchone()

        assert row is not None
        assert row["quantity"] == 22
        assert row["status"] == "pending_approval"

    finally:
        conn.close()




def test_approve_purchase_order(test_db):
    # 1. 先创建一张待审批订单
    create_response = client.post(
        "/purchase-orders",
        json={
            "product_name": "键盘",
            "target_stock": 30
        }
    )

    assert create_response.status_code == 201

    order_id = create_response.json()["order_id"]

    # 2. 审批通过
    approve_response = client.patch(
        f"/purchase-orders/{order_id}/status",
        json={"status": "approved"}
    )

    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "approved"

    # 3. 查询订单，验证状态已保存到数据库
    get_response = client.get(
        f"/purchase-orders/{order_id}"
    )

    assert get_response.status_code == 200
    assert get_response.json()["status"] == "approved"




def test_cannot_approve_twice(test_db):
    # 1. 创建订单
    response = client.post(
        "/purchase-orders",
        json={
            "product_name": "键盘",
            "target_stock": 30
        }
    )

    assert response.status_code == 201
    order_id = response.json()["order_id"]

    # 2. 第一次审批：应该成功
    first_response = client.patch(
        f"/purchase-orders/{order_id}/status",
        json={"status": "approved"}
    )

    assert first_response.status_code == 200

    # 3. 第二次审批：应该被拒绝
    second_response = client.patch(
        f"/purchase-orders/{order_id}/status",
        json={"status": "approved"}
    )

    assert second_response.status_code == 409

    # 4. 验证订单状态没有发生变化
    get_response = client.get(
        f"/purchase-orders/{order_id}"
    )

    assert get_response.status_code == 200
    assert get_response.json()["status"] == "approved"




def test_cannot_create_duplicate_order(test_db):
    # 1. 第一次创建订单
    first_response = client.post(
        "/purchase-orders",
        json={
            "product_name": "键盘",
            "target_stock": 30
        }
    )

    assert first_response.status_code == 201
    order_id = first_response.json()["order_id"]

    # 2. 再次创建同一商品的采购订单
    second_response = client.post(
        "/purchase-orders",
        json={
            "product_name": "键盘",
            "target_stock": 30
        }
    )

    # 3. 验证重复创建被拒绝
    assert second_response.status_code == 409
    assert (
        second_response.json()["detail"]["existing_order_id"]
        == order_id
    )

    # 4. 验证数据库中只有一张采购订单
    conn = database.get_connection()

    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM purchase_orders"
        ).fetchone()[0]

        assert count == 1

    finally:
        conn.close()




def test_database_prevents_duplicate_pending_orders(test_db):
    conn = database.get_connection()

    try:
        product_id = conn.execute(
            "SELECT id FROM products WHERE name = ?",
            ("键盘",)
        ).fetchone()["id"]

        # 第一张待审批订单
        conn.execute(
            """
            INSERT INTO purchase_orders
                (product_id, quantity, status)
            VALUES (?, ?, ?)
            """,
            (product_id, 10, "pending_approval")
        )

        # 第二张同商品待审批订单应被数据库拒绝
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO purchase_orders
                    (product_id, quantity, status)
                VALUES (?, ?, ?)
                """,
                (product_id, 20, "pending_approval")
            )
#with pytest.raises(sqlite3.IntegrityError):我们预期这段代码会抛出数据库完整性错误。如果数据库正确拒绝第二张订单，测试就通过
    finally:
        conn.rollback()
        conn.close()


def test_list_purchase_orders_db():
    from database import list_purchase_orders_db

    orders = list_purchase_orders_db()

    assert isinstance(orders, list)

    for order in orders:
        assert isinstance(order["id"], int)
        assert isinstance(order["product_name"], str)
        assert isinstance(order["quantity"], int)
        assert order["status"] in (
            "pending_approval",
            "approved",
            "rejected",
        )
        assert "created_at" in order
        #确保每个订单都包含一个创建时间字段


def test_reject_purchase_order(test_db):
    from database import (
        create_purchase_order_db,
        update_order_status_db,
        get_purchase_order_db,
    )

    # 创建一条待审批订单
    order = create_purchase_order_db("键盘", 30)
    order_id = order["order_id"]

    # 拒绝订单
    result = update_order_status_db(order_id, "rejected")

    assert result["status"] == "rejected"

    # 验证数据库中的状态确实更新
    saved_order = get_purchase_order_db(order_id)
    assert saved_order["status"] == "rejected"
    #再从数据库中查询订单，确保状态已经被更新为“rejected”。

def test_cannot_reject_approved_order(test_db):
    #测试已批准的订单不能再拒绝
    from database import (
        create_purchase_order_db,
        update_order_status_db,
    )

    order = create_purchase_order_db("键盘", 30)
    order_id = order["order_id"]

    # 先批准
    update_order_status_db(order_id, "approved")

    # 再尝试拒绝
    result = update_order_status_db(order_id, "rejected")

    assert result["error"] == "already_processed"


def test_order_not_found(test_db):
    from database import get_purchase_order_db

    result = get_purchase_order_db(999999)

    assert result is None


def test_invalid_order_status(test_db):
    from database import (
        create_purchase_order_db,
        update_order_status_db,
        get_purchase_order_db,
    )

    order = create_purchase_order_db("键盘", 30)
    order_id = order["order_id"]

    # 尝试设置不合法的状态
    result = update_order_status_db(order_id, "cancelled")

    assert result["error"] == "invalid_status"

    # 确保原状态没有被修改
    saved_order = get_purchase_order_db(order_id)
    assert saved_order["status"] == "pending_approval"