#这段代码使用 FastAPI 创建一个 Web API，让其他程序可以通过 HTTP 请求查询商品库存
from fastapi import FastAPI, HTTPException
#FastAPI 是一个用于构建 Web API 的 Python 框架，HTTPException 用于在请求处理过程中抛出 HTTP 异常
from database import (
    get_inventory_db,
    get_suppliers_db,
    calculate_restock_db,
    create_purchase_order_db,
    get_purchase_order_db,
    update_order_status_db
)
from pydantic import BaseModel, Field
from typing import Literal

app = FastAPI(title="ProcurePilot API")
# 创建一个 FastAPI 应用实例，并设置 API 的标题为 "ProcurePilot API",会显示在自动生成的文档页面上

@app.get("/")
def home():
    return {"message": "ProcurePilot API is running"}
#@app.get("/") 是一个装饰器，表示：收到对 / 路径的 GET 请求时，执行下面的 home() 函数

@app.get("/inventory/{product_name}")
def read_inventory(product_name: str):

    stock = get_inventory_db(product_name)

    if stock is None:
        raise HTTPException(
            status_code=404,
            detail="商品不存在"
        )

    return {
        "product_name": product_name,
        "stock": stock
    }
#@app.get("/inventory/{product_name}") 是一个装饰器，表示：收到对 /inventory/{product_name} 路径的 GET 请求时，执行下面的 read_inventory() 函数





class PurchaseRequest(BaseModel):
    product_name: str = Field(min_length=1)
    target_stock: int = Field(gt=0)
#  PurchaseRequest 是一个 Pydantic 模型类，用于验证采购请求的参数。BaseModel：定义数据结构，告诉FastAPI应该接收什么字段。Field()：设置字段的校验规则。min_length=1 表示至少一个字符，gt=0 表示必须大于0。

@app.post("/purchase-orders/validate")
def validate_purchase(request: PurchaseRequest):
    return {
        "message": "采购请求参数合法",
        "product_name": request.product_name,
        "target_stock": request.target_stock
    }
#@app.post()：声明POST接口，通常用于提交或创建数据



@app.get("/suppliers")
def read_suppliers(product_name: str):

    suppliers = get_suppliers_db(product_name)

    return {
        "product_name": product_name,
        "count": len(suppliers),
        "suppliers": suppliers
    }
#@app.get("/suppliers")：声明GET接口，通常用于获取数据



@app.post("/restock/calculate")
def calculate_restock(request: PurchaseRequest):

    result = calculate_restock_db(
        product_name=request.product_name,
        target_stock=request.target_stock
    )

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="商品不存在"
        )

    return result
#@app.post("/restock/calculate")：声明POST接口，通常用于提交或创建数据
# request: PurchaseRequest：接收并校验JSON请求体。
# calculate_restock_db(...)：调用刚才测试通过的数据库业务函数。
# HTTPException(404)：商品不存在时返回明确错误。
# return result：把Python字典自动转换为JSON响应。



@app.post("/purchase-orders", status_code=201) 
# status_code=201：表示资源创建成功，返回201状态码。
def create_purchase_order(request: PurchaseRequest):

    result = create_purchase_order_db(
        product_name=request.product_name,
        target_stock=request.target_stock
    )

    if "error" in result:
        error = result["error"]

        if error == "product_not_found":
            raise HTTPException(
                status_code=404,
                detail="商品不存在"
            )


        if error == "duplicate_pending_order":
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "该商品已有待审批采购订单",
                    "existing_order_id": result["existing_order_id"]
                }
            )


        if error == "no_restock_needed":
            raise HTTPException(
                status_code=409,
                detail="当前库存已达到目标，无需补货"
            )

        if error == "no_supplier_available":
            raise HTTPException(
                status_code=409,#HTTP 409表示请求与当前资源状态存在冲突
                detail="没有库存充足的供应商"
            )

        raise HTTPException(
            status_code=500,
            detail="未知的订单创建错误"
        )

    return result



@app.get("/purchase-orders/{order_id}")
def read_purchase_order(order_id: int):

    order = get_purchase_order_db(order_id)

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="采购订单不存在"
        )

    return order




class ApprovalRequest(BaseModel):
    status: Literal["approved", "rejected"]
#声明了一个 Pydantic 模型类 ApprovalRequest，用于验证审批请求的参数。status 字段只能是 "approved" 或 "rejected"。声明一个必填字段 status，类型为 Literal

@app.patch("/purchase-orders/{order_id}/status")
def update_order_status(
    order_id: int,
    request: ApprovalRequest
):
    result = update_order_status_db(
        order_id=order_id,
        new_status=request.status
    )

    if "error" in result:
        error = result["error"]

        if error == "order_not_found":
            raise HTTPException(
                status_code=404,
                detail="采购订单不存在"
            )

        if error == "already_processed":
            raise HTTPException(
                status_code=409,
                detail="该订单已经审批，不能重复操作"
            )

        raise HTTPException(
            status_code=422,
            detail="审批状态不合法"
        )

    return result
