import json
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent / "data" / "inventory.json"
#Path(__file__).resolve().parent 表示当前Python文件所在的文件夹

# def load_inventory():
#     with open(DATA_FILE, "r", encoding="utf-8") as file:
#         return json.load(file)

#异常处理：万一不小心把json文件删了
def load_inventory():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            return json.load(file)

    except FileNotFoundError:
        print("错误：库存文件不存在")
        raise

    except json.JSONDecodeError:
        print("错误：库存文件不是有效的JSON")
        raise 
    #这里的 raise 表示：把捕获到的异常继续抛给调用者处理


# open(..., "r")：以只读模式打开文件。
# encoding="utf-8"：正确读取中文。
# with：操作结束后自动关闭文件。
# json.load(file)：把JSON文件中的数据转换成Python对象，这里是字典

def get_inventory(product_name):
    inventory_data = load_inventory()

    if inventory_data is None:
        return None

    return inventory_data.get(product_name)
#字典的 .get() 方法可以根据键查找对应的值。如果商品不存在，默认返回 None，不会因为找不到键而抛出 KeyError


def calculate_restock(product_name,target=30):
    stock=get_inventory(product_name)

    if stock is None:
        return None
    else:
        return max(0,target-stock)



def list_inventory():
    inventory_data = load_inventory()
    return inventory_data