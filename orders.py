import json
from pathlib import Path
from datetime import datetime
from uuid import uuid4 # 生成唯一ID

from inventory import get_inventory


ORDER_FILE = Path(__file__).resolve().parent / "data" / "orders.json" #  定义订单文件路径


def create_purchase_order(product_name, target=30):

    # 1. 校验商品名称
    if not isinstance(product_name, str) or not product_name.strip():
        return {"error": "商品名称不能为空"}

    product_name = product_name.strip()

    # 2. 校验目标库存
    if type(target) is not int or target < 0:
        return {"error": "目标库存必须是非负整数"}

    # 3. 查询真实库存
    stock = get_inventory(product_name)

    if stock is None:
        return {"error": "商品不存在"}

    # 4. 计算补货数量
    quantity = max(0, target - stock)

    if quantity == 0:
        return {"error": "当前库存已达到目标，无需采购"}

    # 5. 构建采购订单
    order = {
        "order_id": uuid4().hex[:12], #  生成唯一的订单ID，取UUID的前12位字符
        "product_name": product_name,
        "current_stock": stock,
        "target_stock": target,
        "quantity": quantity,
        "status": "pending_approval",
        "created_at": datetime.now().isoformat(timespec="seconds") #  订单创建时间，使用ISO格式，精确到秒
    }

    # 6. 读取已有订单
    ORDER_FILE.parent.mkdir(parents=True, exist_ok=True) 
    #  ORDER_FILE是订单文件的路径，ORDER_FILE.parent是订单文件所在的目录。mkdir()表示创建目录，parents=True表示如果父目录不存在也一并创建，exist_ok=True表示如果目录已存在则不报错。

    if ORDER_FILE.exists():
        with open(ORDER_FILE, "r", encoding="utf-8") as f:
            orders = json.load(f)
    else:
        orders = [] #  如果文件不存在，则初始化一个空列表

    if not isinstance(orders, list):
        return {"error": "订单文件格式错误"}

    # 7. 保存新订单
    orders.append(order)

    with open(ORDER_FILE, "w", encoding="utf-8") as f: #  以写入模式打开订单文件，如果文件不存在则创建新文件，使用UTF-8编码，存在则覆盖原文件
        json.dump(orders, f, ensure_ascii=False, indent=2)
    #  保存订单列表到文件，ensure_ascii=False表示不转义非ASCII字符，indent=2表示缩进2个空格
    return order


def get_purchase_order(order_id):

    # 1. 检查订单编号
    if not isinstance(order_id, str) or not order_id.strip():
        return {"error": "订单编号不能为空"}

    # 2. 检查订单文件是否存在
    if not ORDER_FILE.exists():
        return {"error": "订单文件不存在"}

    # 3. 读取订单列表
    try:
        with open(ORDER_FILE, "r", encoding="utf-8") as f:
            orders = json.load(f)

    except (OSError, json.JSONDecodeError):
        return {"error": "订单文件读取失败"}

    # 4. 检查数据格式
    if not isinstance(orders, list):
        return {"error": "订单文件格式错误"}

    # 5. 遍历订单列表，查找指定订单
    for order in orders:
        if isinstance(order, dict) and order.get("order_id") == order_id.strip():
            return order

    # 6. 未找到订单
    return {"error": "订单不存在"}


def list_purchase_orders(status=None): 
    #  status参数用于筛选订单状态，默认为None，表示不筛选

    # 1. 校验筛选状态
    valid_statuses = [
        "pending_approval",
        "approved",
        "rejected"
    ]

    if status is not None and status not in valid_statuses:
        return {"error": "订单状态不合法"}

    # 2. 如果没有订单文件，返回空列表
    if not ORDER_FILE.exists():
        return []

    # 3. 读取订单文件
    try:
        with open(ORDER_FILE, "r", encoding="utf-8") as f:
            orders = json.load(f)

    except (OSError, json.JSONDecodeError):
        return {"error": "订单文件读取失败"}

    # 4. 检查数据格式
    if not isinstance(orders, list):
        return {"error": "订单文件格式错误"}

    # 5. 如果没有指定状态，返回全部订单
    if status is None:
        return orders

    # 6. 根据状态筛选订单
    filtered_orders = []

    for order in orders:
        if isinstance(order, dict) and order.get("status") == status:
            filtered_orders.append(order)

    return filtered_orders


def update_order_status(order_id, new_status):

    # 1. 校验订单编号
    if not isinstance(order_id, str) or not order_id.strip():
        return {"error": "订单编号不能为空"}

    order_id = order_id.strip()

    # 2. 校验目标状态
    if new_status not in ["approved", "rejected"]:
        return {"error": "只能批准或拒绝订单"}

    # 3. 检查订单文件
    if not ORDER_FILE.exists():
        return {"error": "订单文件不存在"}

    # 4. 读取已有订单
    try:
        with open(ORDER_FILE, "r", encoding="utf-8") as f:
            orders = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"error": "订单文件读取失败"}

    if not isinstance(orders, list):
        return {"error": "订单文件格式错误"}

    # 5. 查找订单
    for order in orders:

        if not isinstance(order, dict):
            continue #如果订单不是字典类型，则跳过本轮循环，继续查找下一个订单。

        if order.get("order_id") != order_id:
            continue

        # 只允许待审批订单变更状态
        if order.get("status") != "pending_approval":
            return {"error": "该订单已处理，不能重复审批"}

        # 更新订单状态
        order["status"] = new_status
        order["reviewed_at"] = datetime.now().isoformat(
            timespec="seconds"
        )

        # 保存整个订单列表
        with open(ORDER_FILE, "w", encoding="utf-8") as f:
            json.dump(orders, f, ensure_ascii=False, indent=2)

        return order

    return {"error": "订单不存在"}




if __name__ == "__main__":

    print("全部订单：")
    print(list_purchase_orders())

    print("\n待审批订单：")
    print(list_purchase_orders("pending_approval"))

    print("\n已批准订单：")
    print(list_purchase_orders("approved"))

    print("\n已拒绝订单：")
    print(list_purchase_orders("rejected"))

    print("\n非法状态测试：")
    print(list_purchase_orders("finished"))
