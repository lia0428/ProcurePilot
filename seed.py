import json
from pathlib import Path

from database import get_connection, init_db


DATA_PATH = Path(__file__).resolve().parent / "data" / "inventory.json"


def seed_inventory():
    init_db()

    with open(DATA_PATH, "r", encoding="utf-8") as f:
        inventory_data = json.load(f)

    conn = get_connection()

    try:
        for product_name, stock in inventory_data.items():

            # 插入商品；已存在则忽略
            conn.execute(
                "INSERT OR IGNORE INTO products (name) VALUES (?)",
                (product_name,)
            )

            # 查询商品ID
            row = conn.execute(
                "SELECT id FROM products WHERE name = ?",
                (product_name,)
            ).fetchone()

            product_id = row["id"]

            # 插入或更新库存
            conn.execute(
                """
                INSERT INTO inventory (product_id, stock)
                VALUES (?, ?)
                ON CONFLICT(product_id)
                DO UPDATE SET stock = excluded.stock
                """,
                (product_id, stock)
            )

        conn.commit()
        print("库存数据导入成功！")

    finally:
        conn.close()


if __name__ == "__main__":
    seed_inventory()
