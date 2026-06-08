# Echo v0.2 第七阶段测试文档
> 阶段：记忆管理前端
> 目标：验证小程序端可以查看、删除和清空 Echo 的长期记忆，并能和后端记忆管理接口正确联动

***

## 1. 本阶段交付范围

本阶段完成以下能力：

- 聊天页新增“记忆管理”入口
- 新增小程序页面 `pages/memory/memory`
- 前端封装 `/memory/list`、`DELETE /memory/{memory_id}`、`/memory/clear`
- 登录成功或降级登录时，把 `user_id` 写入本地缓存
- 记忆页读取本地 `user_id` 后加载长期记忆
- 支持“使用中 / 已删除”切换
- 支持删除单条 active 长期记忆
- 支持清空当前用户 active 长期记忆

本阶段不做：

- 向量库管理
- 记忆编辑
- 恢复已删除记忆
- 前端聊天记录管理

***

## 2. 关键代码路径

### 2.1 入口

```text
pages/chat/chat.wxml
  -> 记忆管理
  -> pages/chat/chat.ts:onOpenMemoryPage()
  -> wx.navigateTo('/pages/memory/memory')
```

### 2.2 用户身份

```text
pages/chat/chat.ts
  -> login()
  -> wx.setStorageSync(USER_ID_STORAGE_KEY, user_id)

pages/memory/memory.ts
  -> wx.getStorageSync(USER_ID_STORAGE_KEY)
  -> listMemories(user_id)
```

### 2.3 记忆接口

```text
utils/api.ts
  -> listMemories()
  -> deleteMemory()
  -> clearMemories()
```

***

## 3. 测试用例

### 用例 1：聊天页能进入记忆管理

**操作**

1. 打开聊天页
2. 点击底部“记忆管理”

**预期**

- 小程序进入 `pages/memory/memory`
- 顶部标题为“记忆管理”

### 用例 2：登录后记忆页能拿到 user_id

**操作**

1. 打开聊天页等待登录完成
2. 进入记忆管理页

**预期**

- 本地缓存存在 `echo_user_id`
- 记忆页不会显示“请先返回聊天页完成登录”
- 记忆页会请求 `/memory/list`

### 用例 3：查看使用中的长期记忆

**操作**

后端已有 active 记忆后，进入记忆管理页。

**预期**

- 默认选中“使用中”
- 页面展示 active 记忆列表
- 每条记忆展示类型、内容、重要度、置信度、更新时间
- 每条 active 记忆右侧显示“删除”

### 用例 4：删除单条记忆

**操作**

1. 在“使用中”列表点击某条记忆的“删除”
2. 弹窗确认删除

**预期**

- 前端调用 `DELETE /memory/{memory_id}?user_id=xxx`
- 删除成功后显示“已删除”
- 当前列表刷新
- 被删除记忆不再出现在“使用中”

### 用例 5：查看已删除记忆

**操作**

1. 删除一条记忆
2. 切换到“已删除”

**预期**

- 前端调用 `/memory/list?status=deleted`
- 被删除记忆出现在“已删除”列表
- 已删除列表不显示“删除”按钮

### 用例 6：清空长期记忆

**操作**

1. 在“使用中”列表点击“清空”
2. 弹窗确认清空

**预期**

- 前端调用 `POST /memory/clear`
- 成功后显示清空数量
- “使用中”列表刷新为空
- “已删除”列表能看到被清空的记忆

### 用例 7：无记忆空状态

**操作**

使用一个没有长期记忆的用户进入记忆管理页。

**预期**

- “使用中”显示“暂无使用中的长期记忆”
- “已删除”显示“暂无已删除的长期记忆”
- “清空”按钮不可用

### 用例 8：接口失败提示

**操作**

断开后端或让 `/memory/list` 返回错误。

**预期**

- 页面显示“记忆加载失败”
- 删除失败时显示“删除失败”
- 清空失败时显示“清空失败”

***

## 4. 代码层验收

### 4.1 app.json 注册页面

```bash
rg "pages/memory/memory" Web/miniprogram/app.json
```

预期：

- 能看到记忆管理页面已注册

### 4.2 API 封装存在

```bash
rg "listMemories|deleteMemory|clearMemories|USER_ID_STORAGE_KEY" Web/miniprogram/utils/api.ts
```

预期：

- 能看到三个记忆管理请求函数和本地 user_id key

### 4.3 聊天页入口存在

```bash
rg "onOpenMemoryPage|记忆管理|USER_ID_STORAGE_KEY" Web/miniprogram/pages/chat
```

预期：

- 聊天页能写入 user_id，并能导航到记忆管理页

### 4.4 记忆页文件存在

```bash
rg "listMemories|deleteMemory|clearMemories|使用中|已删除" Web/miniprogram/pages/memory
```

预期：

- 记忆页能加载、删除、清空长期记忆

***

## 5. 本阶段通过标准

第七阶段验收通过需要同时满足：

- 聊天页可以进入记忆管理页
- 记忆页能读取当前用户 `user_id`
- 记忆页能展示 active 长期记忆
- 单条删除后，active 列表刷新且不再展示该记忆
- 切换“已删除”后能看到 deleted 记忆
- 清空长期记忆后，active 列表为空
- 所有操作都只作用于当前 `user_id`

***

## 6. 后续阶段入口

第七阶段完成后，可以进入下一阶段：

```text
embedding 和向量检索
```

下一阶段会为 `user_memories.content` 生成 embedding，并让当前消息召回更相关的长期记忆。
