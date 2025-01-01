from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime

class Order(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    pid: int = Field(default=1)               # 易支付商户ID，固定为1
    out_trade_no: str                         # 易支付订单号（商户本地订单号）
    money: float                              # 订单金额
    name: str                                 # 商品名称
    pay_type: str                             # 支付类型（如 'alipay','wxpay' 等）
    notify_url: str                           # 异步通知地址（从易支付传入）
    return_url: str                           # 前台返回地址（从易支付传入）
    stripe_session_id: Optional[str] = None   # 对应Stripe的Checkout Session或PaymentIntent ID
    status: str = Field(default="INIT")       # 订单状态: INIT, PAID, etc.
    create_time: datetime = Field(default_factory=datetime.utcnow)
