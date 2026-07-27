# Relationship

`relationship` 维护用户与 Echo 之间逐步发展的交流熟悉度。

- 阶段：`new`、`familiar`、`trusted`、`close`。
- 阶段由确定性规则计算；消息量不能绕过活跃天数门槛。
- 用户边界会立即收紧亲近表达，但不会自动清空整段关系。
- `relationship_events` 只记录结构化事件，不复制聊天正文。
- `GET /relationship/me` 返回非游戏化摘要，`POST /relationship/me/reset` 重置关系进度。

