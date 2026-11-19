
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "procurement.db"


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH) #  连接到DB_PATH指定的SQLite数据库文件，如果文件不存在则会自动创建
    conn.row_factory = sqlite3.Row #让后续查询返回的每一行支持通过列名读取数据，也仍然支持索引读取
    conn.execute("PRAGMA foreign_keys = ON") #  启用外键约束，确保数据库的引用完整性

    return conn


def init_db():
    conn = get_connection()

    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS inventory (
                product_id INTEGER PRIMARY KEY,
                stock INTEGER NOT NULL DEFAULT 0
                    CHECK (stock >= 0),
                FOREIGN KEY (product_id)
                    REFERENCES products(id)
            );

            CREATE TABLE IF NOT EXISTS suppliers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                price REAL NOT NULL CHECK (price >= 0),
                available_stock INTEGER NOT NULL
                    CHECK (available_stock >= 0),
                lead_days INTEGER NOT NULL
                    CHECK (lead_days >= 0),
                FOREIGN KEY (product_id)
                    REFERENCES products(id)
            );

            CREATE TABLE IF NOT EXISTS purchase_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                supplier_id INTEGER,
                quantity INTEGER NOT NULL
                    CHECK (quantity > 0),
                status TEXT NOT NULL DEFAULT 'pending_approval'
                    CHECK (status IN (
                        'pending_approval',
                        'approved',
                        'rejected'
                    )),
                created_at TEXT NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id)
                    REFERENCES products(id),
                FOREIGN KEY (supplier_id)
                    REFERENCES suppliers(id)
            );


            CREATE UNIQUE INDEX IF NOT EXISTS
                idx_one_pending_order_per_product
            ON purchase_orders(product_id)
            WHERE status = 'pending_approval';

       
        """)

        conn.commit()
    finally:
        conn.close()

#CREATE UNIQUE INDEX：创建唯一索引，限制索引中的值不能重复。
#IF NOT EXISTS：如果同名索引已存在，就跳过创建。
#idx_one_pending_order_per_product：索引名称，用来说明它的用途。

def get_inventory_db(product_name: str):
    conn = get_connection()

    try:
        row = conn.execute(
            """
            SELECT p.name, i.stock
            FROM products AS p
            JOIN inventory AS i
                ON p.id = i.product_id
            WHERE p.name = ?
            """,
            (product_name,)
        ).fetchone()

        if row is None:
            return None

        return row["stock"]

    finally:
        conn.close()



def get_suppliers_db(product_name: str):
    conn = get_connection()

    try:
        rows = conn.execute(
            """
            SELECT
                s.id,
                s.name,
                s.price,
                s.available_stock,
                s.lead_days
            FROM suppliers AS s
            JOIN products AS p
                ON s.product_id = p.id
            WHERE p.name = ?
            ORDER BY s.price ASC
            """,
            (product_name,)
        ).fetchall()

        return [dict(row) for row in rows]

    finally:
        conn.close()


def calculate_restock_db(product_name: str, target_stock: int):
    if target_stock <= 0:
        raise ValueError("目标库存必须大于0")

    # 从SQLite读取当前库存
    current_stock = get_inventory_db(product_name)

    if current_stock is None:
        return None

    # 计算需要采购的数量
    quantity = max(0, target_stock - current_stock)

    return {
        "product_name": product_name,
        "current_stock": current_stock,
        "target_stock": target_stock,
        "restock_quantity": quantity,
        "need_restock": quantity > 0
    }



def create_purchase_order_db(product_name: str, target_stock: int):
    if target_stock <= 0:
        raise ValueError("目标库存必须大于0")

    conn = get_connection()

    try:
        # 1. 查询商品及当前库存
        product = conn.execute(
            """
            SELECT p.id, i.stock
            FROM products AS p
            JOIN inventory AS i ON p.id = i.product_id
            WHERE p.name = ?
            """,
            (product_name,)
        ).fetchone()

        if product is None:
            return {"error": "product_not_found"}


        
        # 检查该商品是否已有待审批订单
        existing_order = conn.execute(
            """
            SELECT id
            FROM purchase_orders
            WHERE product_id = ?
              AND status = 'pending_approval'
            LIMIT 1
            """,
            (product["id"],)
        ).fetchone()

        if existing_order is not None:
            return {
                "error": "duplicate_pending_order",
                "existing_order_id": existing_order["id"]
            }


        # 2. 计算补货量
        quantity = max(0, target_stock - product["stock"])

        if quantity == 0:
            return {"error": "no_restock_needed"}

        # 3. 选择可供库存充足、单价最低的供应商
        supplier = conn.execute(
            """
            SELECT id, name, price, available_stock, lead_days
            FROM suppliers
            WHERE product_id = ?
              AND available_stock >= ?
            ORDER BY price ASC, id ASC
            LIMIT 1
            """,
            (product["id"], quantity)
        ).fetchone() #按价格从低到高排序；价格相同则按ID排序，最后只取一条记录

        if supplier is None:
            return {"error": "no_supplier_available"}

        # 4. 创建待审批订单
        
        try:
            cursor = conn.execute(
                """
                INSERT INTO purchase_orders
                    (product_id, supplier_id, quantity, status)
                VALUES (?, ?, ?, ?)
                """,
                (
                    product["id"],
                    supplier["id"],
                    quantity,
                    "pending_approval"
                )
            )

            conn.commit()

        except sqlite3.IntegrityError:
            conn.rollback()

            # 检查是否由重复待审批订单引起
            existing = conn.execute(
                """
                SELECT id
                FROM purchase_orders
                WHERE product_id = ?
                  AND status = 'pending_approval'
                LIMIT 1
                """,
                (product["id"],)
            ).fetchone()

            if existing is not None:
                return {
                    "error": "duplicate_pending_order",
                    "existing_order_id": existing["id"]
                }

            # 其他数据库完整性错误不能误报为重复订单
            raise

        return {
            "order_id": cursor.lastrowid,
            "product_name": product_name,
            "supplier_name": supplier["name"],
            "quantity": quantity,
            "unit_price": supplier["price"],
            "total_price": round(quantity * supplier["price"], 2),
            "lead_days": supplier["lead_days"],
            "status": "pending_approval"
        }

    finally:
        conn.close()



def get_purchase_order_db(order_id: int):
    conn = get_connection()

    try:
        row = conn.execute(
            """
            SELECT
                po.id AS order_id,
                p.name AS product_name,
                s.name AS supplier_name,
                po.quantity,
                po.status,
                po.created_at
            FROM purchase_orders AS po
            JOIN products AS p
                ON po.product_id = p.id
            LEFT JOIN suppliers AS s
                ON po.supplier_id = s.id
            WHERE po.id = ?
            """,
            (order_id,)
        ).fetchone()
        #使用 LEFT JOIN，是因为 purchase_orders.supplier_id 允许为空。即使订单没有关联供应商，也能查询到订单本身，只是 supplier_name 会返回 null
        if row is None:
            return None

        return dict(row)

    finally:
        conn.close()



def update_order_status_db(order_id: int, new_status: str):

    if new_status not in ("approved", "rejected"):
        return {"error": "invalid_status"}

    conn = get_connection()

    try:
        # 1. 查询订单当前状态
        order = conn.execute(
            """
            SELECT id, status
            FROM purchase_orders
            WHERE id = ?
            """,
            (order_id,)
        ).fetchone()

        if order is None:
            return {"error": "order_not_found"}

        # 2. 只允许待审批订单改变状态
        if order["status"] != "pending_approval":
            return {"error": "already_processed"}

        # 3. 更新订单状态
        cursor = conn.execute(
            """
            UPDATE purchase_orders
            SET status = ?
            WHERE id = ? AND status = 'pending_approval'
            """,
            (new_status, order_id)
        )

        if cursor.rowcount != 1:
            conn.rollback()
            return {"error": "already_processed"}

        conn.commit()

        return {
            "order_id": order_id,
            "status": new_status,
            "message": "订单审批完成"
        }

    finally:
        conn.close()


def list_purchase_orders_db():
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT
                po.id,
                p.name AS product_name,
                s.name AS supplier_name,
                po.quantity,
                po.status,
                po.created_at
            FROM purchase_orders AS po
            JOIN products AS p ON po.product_id = p.id
            LEFT JOIN suppliers AS s ON po.supplier_id = s.id
            ORDER BY po.id DESC
        """).fetchall()

        return [dict(row) for row in rows]
    finally:
        conn.close()


def init_workflow_mapping_db():
    #创建一个新的表 order_workflows，用于存储采购订单与工作流线程ID的映射关系。这个表有两个字段：order_id 和 thread_id，其中 order_id 是主键，thread_id 是唯一且不能为空的文本字段。order_id 还作为外键引用了 purchase_orders 表的 id 字段，确保每个订单都对应一个有效的工作流线程。
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS order_workflows (
                order_id INTEGER PRIMARY KEY,
                thread_id TEXT NOT NULL UNIQUE,
                FOREIGN KEY (order_id)
                    REFERENCES purchase_orders(id)
            )
        """)
        conn.commit()
    finally:
        conn.close()
#order_id INTEGER PRIMARY KEY：表示 order_id 为整数，是主键不能重复，唯一标识每一条记录。
#thread_id TEXT NOT NULL UNIQUE：表示 线程ID thread_id 为文本类型，不能为空，并且在表中必须唯一。
#FOREIGN KEY (order_id) REFERENCES purchase_orders(id)：表示 order_id 是一个外键，引用 purchase_orders 表的 id 列，确保 order_workflows 表中的 order_id 必须在 purchase_orders 表中存在。

def save_order_workflow_db(order_id, thread_id):
    #接收订单编号和线程 ID，先确保映射表存在
    init_workflow_mapping_db()

    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO order_workflows (order_id, thread_id)
            VALUES (?, ?)
            ON CONFLICT(order_id)
            DO UPDATE SET thread_id = excluded.thread_id
        """, (order_id, thread_id))
        conn.commit()
    finally:
        conn.close()
#ON CONFLICT(order_id) DO UPDATE SET thread_id = excluded.thread_id：表示如果插入时 order_id 已经存在，则更新该记录的 thread_id 为新值，而不是插入新记录。这确保了每个订单只能对应一个线程 ID，避免重复映射。excluded.thread_id指的是本次原本准备插入的新 thread_id

def get_order_workflow_db(order_id):#根据订单编号查询对应的线程 ID
    #确保映射表存在
    init_workflow_mapping_db()

    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT thread_id
            FROM order_workflows
            WHERE order_id = ?
        """, (order_id,)).fetchone()

        return row["thread_id"] if row else None
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"数据库初始化成功：{DB_PATH}")
