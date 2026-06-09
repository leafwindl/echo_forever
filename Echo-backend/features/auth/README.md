# Auth 模块

## 1. 业务目标

负责用户登录与内部 `user_id` 生成。真实微信环境下用 `wx.login()` 的 code 换取 openid；本地开发环境未配置微信密钥时，使用 `client_id` 生成稳定 dev 用户。

## 2. 核心业务流程

1. 接收登录请求，读取微信临时 code 和可选的本地设备标识。
2. 校验 code 是否为空；无效请求直接返回登录失败。
3. 判断当前环境是否配置了微信密钥。
4. 生产环境下，用 code 向微信换取 openid。
5. 本地开发环境下，用设备标识或 code 生成稳定的开发 openid。
6. 将 openid 转换为内部 `user_id`，避免业务数据直接暴露微信身份。
7. 写入或更新用户记录。
8. 返回内部 `user_id` 给前端，后续所有用户数据都按该 ID 隔离。

## 3. 对外契约

### HTTP API

- `POST /login`
  - Request: `LoginRequest`
  - Response: `LoginResponse`

### 发布的事件

- 当前无已落地事件。

### 依赖的其它模块接口

- 用户仓储：写入或更新用户记录。
- 配置服务：读取微信登录密钥和请求超时时间。

## 4. 数据库表

- `users`

## 5. 关键配置项

- `WECHAT_APPID`
- `WECHAT_SECRET`
- `TIMEOUT`

## 6. 注意事项

- 不要在业务表中直接使用 openid，必须转换为内部 `user_id`。
- 开发环境 dev 用户用于本地调试，生产环境应配置微信密钥。
- 登录失败统一抛出 `AuthError`，由 Interface 映射为 HTTP 错误。
