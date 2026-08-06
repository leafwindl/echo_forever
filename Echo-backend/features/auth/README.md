# Auth 模块

Auth 负责手机号验证码登录和内部用户会话。v1.0 不再保留微信登录、`openid` 或按请求传入 `user_id` 的兼容入口。

## 手机号登录流程

1. APP 生成并持久化设备 UUID，调用 `POST /login/phone`。
2. 后端规范化大陆手机号，按手机号、设备和 IP 做限流，创建一次性验证码 challenge。
3. 短信 provider 发送验证码；闭测环境可使用固定验证码配置，生产环境应切换真实短信 provider。
4. APP 调用 `POST /login/verify` 提交 request_id、手机号、验证码和设备 UUID。
5. 后端校验 challenge 的有效期、尝试次数、设备绑定和消费状态，创建或读取用户并签发 access token 与 refresh token。
6. APP 将 token 写入安全存储。后续 API 只从 Bearer token 解析当前 `user_id`。

## 会话维护

- access token 过期时，客户端通过 `POST /login/refresh` 轮换 refresh token。
- refresh token 复用、撤销或过期会使会话失效，客户端回到登录页。
- `POST /login/logout` 撤销当前设备的 refresh token。

## 数据

- `users`：内部用户和手机号。
- `sms_verification_challenges`：验证码 challenge，保存哈希，不保存明文验证码。
- `auth_refresh_tokens`：refresh token 哈希、token family、设备和撤销状态。

认证错误统一返回 `code/detail/request_id`，日志只记录脱敏后的 request_id 和错误类别。
