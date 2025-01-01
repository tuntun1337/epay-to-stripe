import hashlib
import os

import stripe
import requests
from fastapi import FastAPI, Request, HTTPException
from sqlmodel import SQLModel, Session, create_engine, select
from starlette.responses import RedirectResponse
from models import Order
from dotenv import load_dotenv

load_dotenv()

PID = os.getenv("PID")
KEY = os.getenv("KEY")
SIGN_TYPE = os.getenv("SIGN_TYPE")
CURRENCY = os.getenv("CURRENCY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")


DATABASE_URL = "sqlite:///./test.db"

PAYMENT_METHODS = {
    "wxpay":"wechat_pay",
    "alipay":"alipay",
    "qqpay":"card",
}



app = FastAPI()
stripe.api_key = KEY
engine = create_engine(DATABASE_URL, echo=False)


@app.on_event("startup")
def on_startup():
    # 创建数据库表
    SQLModel.metadata.create_all(engine)


def epay_sign(params: dict, key: str) -> str:
    """
    根据给定的参数字典和商户密钥 key，生成易支付签名（MD5 小写）。
    1. 将所有参数根据参数名 ASCII 升序排序（sign、sign_type、空值 不参与签名）。
    2. 将排序后的参数拼接成 a=b&c=d&... 格式（值不做URL编码）。
    3. 在末尾拼接上 KEY，执行 MD5 并返回结果的小写形式。

    :param params: 订单参数字典
    :param key: 易支付商户密钥
    :return: MD5签名字符串（小写）
    """

    # 1. 过滤掉 sign / sign_type / 以及值为空的参数
    filtered_params = {
        k: v for k, v in params.items()
        if k not in ["sign", "sign_type"] and v not in [None, ""]
    }

    # 2. 按照参数名ASCII码升序排序
    sorted_keys = sorted(filtered_params.keys())

    # 3. 拼接成 "a=b&c=d&..." 形式
    sign_str = "&".join(f"{k}={filtered_params[k]}" for k in sorted_keys)

    # 4. 末尾拼接上 key
    sign_str_with_key = f"{sign_str}{key}"

    # 5. 做MD5哈希并转成小写
    md5_obj = hashlib.md5(sign_str_with_key.encode("utf-8"))
    sign_result = md5_obj.hexdigest().lower()

    return sign_result


def get_real_time_rates() -> dict:
    url = "https://api.exchangerate-api.com/v4/latest/CNY"
    response = requests.get(url, timeout=10)
    data = response.json()
    return data["rates"]


def convert_cny_dynamic(amount: float, target_currency: str) -> float:
    rates = get_real_time_rates()
    rate = rates.get(target_currency.upper())
    if rate is None:
        raise ValueError(f"暂不支持的目标币种: {target_currency}")

    return amount * rate

@app.post("/submit.php")
async def epay_submit(request: Request):
    form = await request.form()

    pid = form.get("pid")
    out_trade_no = form.get("out_trade_no")
    money = form.get("money")
    pay_type = form.get("type")
    name = form.get("name")
    notify_url = form.get("notify_url")
    return_url = form.get("return_url")
    site_name = form.get("sitename")
    sign = form.get("sign")
    sign_type = form.get("sign_type")

    if pid != PID:
        raise HTTPException(status_code=400, detail="PID error")
    if not all([pid, out_trade_no, money, pay_type, name, notify_url, return_url,site_name, sign]):
        raise HTTPException(status_code=400, detail="Missing required parameters")

    params_for_sign = dict(form)
    if sign_type == "MD5":
        server_sign = epay_sign(params_for_sign, KEY)
        if sign.lower() != server_sign.lower():
            raise HTTPException(status_code=400, detail="Sign error")
    else:
        raise HTTPException(status_code=400, detail="Unsupported sign_type")

    with Session(engine) as db_sess:
        try:
            money_float = float(money)
        except:
            raise HTTPException(status_code=400, detail="Money format error")

        db_order = Order(
            pid=PID,
            out_trade_no=out_trade_no,
            money=money_float,
            name=name,
            pay_type=pay_type,
            notify_url=notify_url,
            return_url=return_url,
            status="INIT"
        )
        db_sess.add(db_order)
        db_sess.commit()
        db_sess.refresh(db_order)

    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=[PAYMENT_METHODS[pay_type]],
            payment_method_options={
                "wechat_pay": {
                    "client": "web"
                }
            },
            line_items=[{
                "price_data": {
                    "currency": CURRENCY,
                    "unit_amount": int(convert_cny_dynamic(money_float,CURRENCY) * 100),
                    "product_data": {
                        "name": name
                    },
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=return_url,
            cancel_url=return_url,
        )
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=str(e))

    with Session(engine) as db_sess:
        db_order = db_sess.exec(
            select(Order).where(Order.out_trade_no == out_trade_no)
        ).first()
        if db_order:
            db_order.stripe_session_id = checkout_session.id
            db_sess.add(db_order)
            db_sess.commit()

    return RedirectResponse(checkout_session.url, status_code=302)



@app.post("/webhook/stripe")
async def webhook_stripe(request: Request):

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=401, detail="Invalid signature")

    if event["type"] == "checkout.session.completed":
        session_obj = event["data"]["object"]
        session_id = session_obj["id"]

        with Session(engine) as db_sess:
            db_order = db_sess.exec(
                select(Order).where(Order.stripe_session_id == session_id)
            ).first()
            if db_order and db_order.status != "PAID":
                # 更新订单状态
                db_order.status = "PAID"
                db_sess.add(db_order)
                db_sess.commit()

                callback_data = {
                    "pid": db_order.pid,
                    "out_trade_no": db_order.out_trade_no,
                    "type": db_order.pay_type,
                    "trade_no": session_id,
                    "name": db_order.name,
                    "money": str(db_order.money),
                    "trade_status": "TRADE_SUCCESS",
                }

                sign_value = epay_sign(callback_data, KEY)
                callback_data["sign"] = sign_value
                callback_data["sign_type"] = "MD5"


                try:
                    resp = requests.post(db_order.notify_url, data=callback_data, timeout=10)
                except Exception as e:
                    pass

    # 返回 200 表示 Webhook 处理成功
    return {"status": "ok"}
