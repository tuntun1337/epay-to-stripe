# EPay-to-Stripe 兼容层

这是一个将 [易支付](https://www.epay.com/) 接口映射到 [Stripe](https://stripe.com/) 的简单兼容层，方便已有易支付对接的项目无缝迁移或代理到 Stripe。

## 功能

- 模拟易支付的 `/submit.php` 端点创建订单  
- 使用 Stripe Checkout 完成实际支付  
- 通过 `/webhook/stripe` 接收 Stripe Webhook 回调，更新订单状态并调用原易支付风格的 `notify_url` 回调

## 付款方式映射

项目中使用下述字典将易支付提交的 `type` 参数映射到 Stripe 的 `payment_method_types` 参数：

```python
PAYMENT_METHODS = {
    "wxpay":"wechat_pay",  # 易支付 wxpay 映射为 Stripe 的 WeChat Pay
    "alipay":"alipay",     # 易支付 alipay 映射为 Stripe 的 Alipay
    "qqpay":"card",        # 易支付 qqpay 暂无法直接对应 Stripe，因此以 card 做占位
}
```

例如，当表单 `type=wxpay` 时，系统会在 Stripe Checkout 中启用 `wechat_pay` 作为实际支付方式。

## 快速开始

1. **克隆仓库：**
   ```bash
   git clone https://github.com/tuntun1337/epay-to-stripe.git
   cd epay-to-stripe
   ```

2. **安装依赖：**
   ```bash
   pip install --no-cache-dir -r requirements.txt
   ```

3. **配置 `.env`**：

   `cp env.example .env`，并填写以下内容：

   ```env
   # 别动
   PID=1
   # 你的stripe密钥，和易支付密钥相同
   KEY=sk_test_xxxxx
   # 别动
   SIGN_TYPE=MD5
   # 你Stripe账号的主要货币
   CURRENCY=gbp
   # 你的Stripe webhook密钥
   STRIPE_WEBHOOK_SECRET=whsec_xxxxx
   ```

4. **运行服务：**
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```

5. **测试：**  
   向 `/submit.php` 发送易支付格式的表单请求，若校验通过，将自动跳转至 Stripe Checkout 页面。

## Docker 部署

```bash
docker build -t epay2stripe .
docker run -d --name epay2stripe -p 8000:8000 --env-file .env epay2stripe
```

## 配置易支付

支付网关：`https://YOURDOMAIN/submit.php` (部分程序不需要填写submit.php，比如异次元发卡)

商户ID(PID)：`1`

密钥(KEY)：`你的Stripe密钥`

## 许可证

本项目采用 [MIT License](./LICENSE)。欢迎提交 Issue 或 Pull Request。  