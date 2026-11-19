from database import get_connection

# 模拟供应商数据
SUPPLIERS = [
    ("键盘", "华南科技", 65.0, 100, 2),
    ("键盘", "智联办公", 58.0, 50, 5),
    ("键盘", "极速数码", 72.0, 200, 1),
    ("鼠标", "华南科技", 35.0, 120, 3),
    ("鼠标", "智联办公", 30.0, 80, 4),
    ("显示器", "极速数码", 899.0, 20, 3),
    ("耳机", "华南科技", 120.0, 60, 2),
]


def seed_suppliers():
    conn = get_connection()

    try:
        for name, supplier, price, stock, days in SUPPLIERS:

            # 根据商品名称查找商品ID
            product = conn.execute(
                "SELECT id FROM products WHERE name = ?",
                (name,)
            ).fetchone()

            if product is None:
                raise ValueError(f"商品不存在：{name}")

            product_id = product["id"]

            # 已有同名供应商报价则更新，避免重复插入
            existing = conn.execute(
                """
                SELECT id FROM suppliers
                WHERE product_id = ? AND name = ?
                """,
                (product_id, supplier)
            ).fetchone()

            if existing:
                conn.execute(
                    """
                    UPDATE suppliers
                    SET price = ?, available_stock = ?, lead_days = ?
                    WHERE id = ?
                    """,
                    (price, stock, days, existing["id"])
                )
            else:
                conn.execute(
                    """
                    INSERT INTO suppliers
                    (product_id, name, price, available_stock, lead_days)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (product_id, supplier, price, stock, days)
                )

        conn.commit()
        print("供应商数据导入成功！")

    finally:
        conn.close()


if __name__ == "__main__":
    seed_suppliers()
