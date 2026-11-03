# Echo 手机 Agent 实施计划

> 状态：草案 v0.1  
> 目标设备：闲置安卓手机 PJC110，Android 15（API 35），USB 调试已开启  
> 路线：先做 A（电脑端 ADB 原型），再做 B（手机端 Agent App）  
> 默认不 Root。

## 1. 目标与非目标

### 目标

让 Echo 能通过自然语言操作一台专门的安卓手机：

- 查看当前屏幕和界面结构
- 打开任意已安装应用
- 点击、长按、滑动、返回、Home、最近任务
- 输入文字、搜索、选择结果
- 读取通知和页面内容
- 执行多步骤任务，例如：
  - 打开网易云搜索并播放一首歌
  - 打开地图查路线
  - 打开微信找到联系人并进入聊天页
  - 打开设置修改一个选项
  - 读取当前页面的信息并汇报

### 非目标

- 不承诺操作所有应用。银行、支付、密码管理器、DRM 视频、部分游戏可能禁止截图或无障碍读取。
- 不绕过锁屏 PIN、指纹、人脸识别。
- 不在第一阶段 Root。
- 不先拿主力手机做实验。
- 不默认执行支付、删除、发消息、打电话等高风险操作。

## 2. 总体路线

```text
阶段 A：验证能力
Echo / DSH
  -> 电脑端 phone_lab
  -> ADB / WiFi ADB
  -> 闲置安卓手机
  -> UI 树 + 截图 + 输入操作

阶段 B：产品化
Echo 后端 mobile_agent
  -> WebSocket
  -> Echo Phone Agent（独立安卓 App）
  -> AccessibilityService + MediaProjection
  -> 手机上的应用
```

A 阶段只验证“看不看得懂、点不点得准、任务能不能完成”，不急着改现有产品。  
B 阶段再把能力收进 Echo，做配对、权限、审计和失败恢复。

## 3. 阶段 A：电脑端 ADB 原型

### A0. 手机和电脑准备

- [ ] 手机保持解锁，关闭自动锁屏或延长锁屏时间
- [ ] 开发者选项中开启 USB 调试
- [ ] USB 连接电脑，确认 `adb devices` 能看到设备
- [ ] 手机和电脑连接同一个 Wi-Fi，后续测试无线 ADB
- [ ] 手机关闭电池优化，避免前台服务被系统杀掉
- [ ] 准备一个测试用 Google/厂商账号，不登录主力账号
- [ ] 电脑安装 Android platform-tools、Python 3.11、scrcpy
- [ ] 准备 DeepSeek 或其他支持视觉的模型 API

当前设备：

```text
型号：PJC110
系统：Android 15（API 35）
连接：USB / ADB
```

### A1. 基线能力验证

不依赖大模型，先用 ADB 证明手机能被稳定控制：

- [ ] 截图：`adb exec-out screencap -p`
- [ ] 读取 UI 树：`adb shell uiautomator dump`
- [ ] 点击坐标
- [ ] 输入文字
- [ ] 返回、Home、最近任务
- [ ] 启动指定应用
- [ ] 获取当前前台应用
- [ ] 读取通知
- [ ] 息屏、亮屏、解锁状态判断

验收：以上命令都能重复执行，失败时能得到明确错误。

### A2. mobilerun 原型

优先用 [droidrun/mobilerun](https://github.com/droidrun/mobilerun) 验证，不自己先造一套 Agent。

```text
安装 mobilerun
  -> 配置模型提供方
  -> 安装或连接 Portal
  -> 执行自然语言任务
```

测试任务：

1. 打开设置，告诉我当前安卓版本
2. 打开计算器，计算 23 × 17
3. 打开网易云，搜索“晴天”并尝试播放
4. 打开浏览器，搜索一个关键词并返回第一条结果
5. 打开文件管理器，找到 Download 目录
6. 返回桌面，再打开最近使用的应用
7. 读取当前页面的通知并总结
8. 连续执行三步操作后回到桌面

记录：

| 指标 | 说明 |
| --- | --- |
| 成功率 | 8 个任务成功几个 |
| 平均耗时 | 从下达到完成 |
| 步数 | 每个任务实际点击/输入次数 |
| 失败原因 | UI 树缺失、视觉误判、权限、超时、应用限制 |
| 截图可用性 | 是否黑屏、是否被 FLAG_SECURE 拦截 |
| 恢复能力 | 点错后能不能回到正确页面 |

### A3. 自建 phone_lab 薄封装

mobilerun 只用于验证，不直接成为 Echo 的生产依赖。  
A 阶段做一个很薄的本地封装：

```text
phone_lab/
  observe()   当前前台应用 + UI 树 + 截图
  act()       点击/输入/滑动/返回/Home
  launch()    启动应用
  task()      交给模型做多步规划
```

先作为命令行工具，不接生产后端。  
目标是固定接口形状，方便 B 阶段复用。

### A4. 和 Echo 的临时连接

- [ ] 提供一个本地 CLI：`phone_lab run "打开设置并..."` 
- [ ] DSH 或 Echo 可以通过命令行调用
- [ ] 输出结构化结果：成功/失败、当前应用、截图路径、执行步骤
- [ ] 不把临时截图写进长期存储

### A5. A 阶段决策门

进入 B 阶段前必须满足：

- [ ] 8 个测试任务至少成功 6 个
- [ ] 能稳定读取大多数普通应用的 UI 树
- [ ] 没有 UI 树的应用能用截图 + 坐标完成
- [ ] 点击和输入成功率可接受
- [ ] 失败后能安全停止，不会无限循环
- [ ] 明确列出无法操作的应用类型

如果达不到，先继续优化 A，不急着开发 App。

## 4. 阶段 B：Echo Phone Agent

### B0. 产品边界

- 独立 App，包名建议 `cn.echoaiforever.phone_agent`
- 只安装在专门的闲置手机上
- 不把无障碍权限塞进现有 Echo 聊天 App
- 现有 Echo / 电脑端负责下指令和展示，不直接执行手机操作
- 默认不 Root；Shizuku 作为可选增强

### B1. 手机端 App

#### 权限与系统能力

- [ ] `AccessibilityService`
  - 读取 UI 树
  - 点击、长按、滑动、滚动
  - 设置文本、返回、Home、最近任务
- [ ] `MediaProjection`
  - 用户授权后截图
  - 处理没有无障碍节点的界面
- [ ] `NotificationListenerService`
  - 读取通知标题、正文、应用来源
- [ ] 前台服务
  - WebSocket 长连接
  - 心跳、断线重连
  - 常驻通知和紧急停止
- [ ] `PackageManager`
  - 列出应用
  - 通过启动 Intent 打开任意应用
- [ ] 必要的系统 Intent
  - 相机、相册、设置、文件、浏览器
- [ ] 可选：Shizuku
  - 系统级操作
  - 不默认开启

#### App 内页面

- [ ] 首次启动引导：说明权限用途
- [ ] 无障碍服务开启引导
- [ ] 截图授权引导
- [ ] 配对页面：二维码或配对码
- [ ] 在线状态、当前任务、最近操作
- [ ] 暂停/恢复、紧急停止
- [ ] 权限状态和故障排查

#### 通信协议

建议消息类型：

```text
hello              手机上线、能力上报
heartbeat          心跳
observe            请求当前界面
observe_result     UI 树 + 截图 + 前台应用
action             点击/输入/滑动/返回/启动应用
action_result      成功/失败/耗时
task               多步任务
task_progress      当前步骤
stop               紧急停止
```

### B2. 后端模块

- [ ] 新增 `mobile_agent` 业务模块
- [ ] 设备配对和一次性令牌
- [ ] WebSocket 连接管理
- [ ] 设备在线状态
- [ ] 任务队列和超时
- [ ] 操作审计
- [ ] 截图临时存储和清理
- [ ] Agent 工具：
  - `phone_status`
  - `phone_observe`
  - `phone_launch_app`
  - `phone_action`
  - `phone_run_task`
- [ ] 高风险操作确认策略
- [ ] 设备不在线、权限缺失、锁屏时返回明确错误

### B3. Agent 执行循环

```text
观察：当前应用 + UI 树 + 截图
  -> 规划：下一步只做一个小动作
  -> 校验：动作是否在当前页面可执行
  -> 执行：点击/输入/滑动/启动
  -> 观察：确认页面变化
  -> 成功或重试
```

约束：

- 单任务最大步数，例如 20 步
- 单步超时，例如 20 秒
- 连续两次相同动作无变化就停止
- 遇到密码、支付、删除、隐私页面立即暂停
- 截图只在任务期间保留，任务结束后清理

### B4. 安全策略

默认需要确认：

- 支付、转账、下单
- 删除数据、卸载应用
- 发送消息、发邮件、拨打电话
- 修改密码、权限、账号
- 读取银行、密码管理器等敏感页面

默认禁止：

- 自动输入支付密码
- 自动通过生物识别
- 绕过锁屏
- 在用户不知情时持续录屏

### B5. 测试与验收

- [ ] 真机安装和覆盖升级
- [ ] 配对、解绑、重新配对
- [ ] 断网、重连、后端重启
- [ ] 息屏、锁屏、解锁后的恢复
- [ ] 无障碍服务被系统关闭后的提示
- [ ] 截图授权被拒绝后的降级
- [ ] 普通应用：设置、计算器、浏览器、网易云、地图
- [ ] 无 UI 树应用：截图坐标点击
- [ ] 通知读取
- [ ] 多步任务
- [ ] 紧急停止
- [ ] 审计日志
- [ ] 敏感页面阻断

## 5. 里程碑

| 阶段 | 交付物 | 验收标准 | 预计 |
| --- | --- | --- | --- |
| M0 | 手机和 ADB 环境 | `adb devices` 稳定看到设备 | 0.5 天 |
| M1 | ADB 基线脚本 | 截图、UI 树、点击、输入、返回可重复 | 1 天 |
| M2 | mobilerun 跑通 | 完成 3 个自然语言任务 | 1-2 天 |
| M3 | phone_lab 薄封装 | `observe/act/launch/task` 四个接口可用 | 1-2 天 |
| M4 | A 阶段评估 | 8 个任务至少 6 个成功，形成失败清单 | 1 天 |
| M5 | Phone Agent 骨架 | 安装、配对、上线、截图、UI 树 | 3-5 天 |
| M6 | 基础动作 | 启动应用、点击、输入、滑动、返回 | 3-5 天 |
| M7 | Agent 闭环 | 多步任务、失败恢复、停止 | 1-2 周 |
| M8 | 安全与审计 | 敏感操作确认、审计、截图清理 | 3-5 天 |
| M9 | 真机验收 | 任务矩阵通过，可日常试用 | 3-5 天 |

时间只是开发量估算，不是承诺日期。

## 6. A/B 两阶段的分工

| 能力 | A 阶段 | B 阶段 |
| --- | --- | --- |
| 手机连接 | USB / WiFi ADB | App + WebSocket |
| 截图 | ADB / scrcpy | MediaProjection |
| UI 树 | uiautomator | AccessibilityService |
| 点击输入 | ADB input | Accessibility |
| 模型规划 | mobilerun / 本地脚本 | 后端 Agent |
| 配对鉴权 | 无 | 设备令牌 |
| 审计 | 本地日志 | 后端审计 |
| 产品入口 | CLI | Echo / DSH |
| 是否需要电脑 | 需要 | 不需要 |

## 7. 风险清单

| 风险 | 影响 | 应对 |
| --- | --- | --- |
| 应用禁止截图 | 视觉模式失效 | UI 树优先；敏感应用直接跳过 |
| 无无障碍节点 | 点击不到元素 | 截图 + 坐标 + 视觉模型 |
| 系统杀前台服务 | 连接中断 | 前台服务、电池白名单、重连 |
| 模型误点 | 进入错误页面 | 每步确认、最大步数、连续无变化停止 |
| 锁屏/密码 | 无法继续 | 明确暂停，要求用户解锁 |
| 网络延迟 | 任务慢 | 本地预判、减少截图、压缩 |
| 隐私泄露 | 截图/通知含敏感信息 | 临时存储、脱敏、任务结束删除 |
| 自动化被检测 | 应用限制 | 不强绕；必要时人工接管 |
| 权限过大 | 手机被滥用 | 专用机、配对令牌、审计、紧急停止 |

## 8. 需要确认的产品决策

1. 是否接受使用独立 App，而不是把功能塞进现有 Echo App？
2. 手机是否长期保持解锁/亮屏，还是允许锁屏后暂停？
3. 哪些应用属于“默认禁止自动操作”：
   - 银行/支付
   - 密码管理器
   - 微信/QQ 发消息
   - 电话/短信
4. 是否允许使用 Shizuku 作为可选增强？
5. A 阶段的任务成功率门槛是否按 6/8 执行？

## 9. 参考资料

- [droidrun/mobilerun](https://github.com/droidrun/mobilerun)：LLM 驱动的 Android/iOS Agent，UI 树 + 截图，支持 ADB 和 Portal
- [ForrestGump618/mobile-agent](https://github.com/ForrestGump618/mobile-agent)：原生 Kotlin Agent，无障碍 + Shizuku + 策略门，适合参考 B 阶段架构
- [miqian-nomad/YinyueMobile](https://github.com/miqian-nomad/YinyueMobile)：安卓端本地 LLM + 无障碍操控
- [pedro-rivas/android-puppeteer-mcp](https://github.com/pedro-rivas/android-puppeteer-mcp)：MCP + uiautomator2 + scrcpy，适合电脑端原型
- [openatx/uiautomator2](https://github.com/openatx/uiautomator2)：成熟的 ADB UI 自动化库
- [Genymobile/scrcpy](https://github.com/Genymobile/scrcpy)：安卓投屏和控制
- [RikkaApps/Shizuku](https://github.com/RikkaApps/Shizuku)：不 Root 使用部分系统 API
- [google-research/android_world](https://github.com/google-research/android_world)：手机 Agent 评测环境
