# Echo 手机 Agent A 阶段记录

> 日期：2026-11-03  
> 设备：PJC110，Android 15（API 35），USB ADB  
> 结论：A 阶段通过，可以进入 B 阶段；但 Portal 无障碍服务在这台 ColorOS 上出现故障，A 阶段实际使用 mobilerun 的 ADB 路径。

## A0 环境

- ADB 在线，设备序列号已确认
- 屏幕尺寸：1080 × 2412
- 屏幕保持唤醒
- 手机和电脑在同一 Wi-Fi
- 手机已解锁，桌面可用
- Android SDK platform-tools 可用

## A1 ADB 基线

| 能力 | 结果 | 说明 |
| --- | --- | --- |
| 截图 | 通过 | `phone_lab screenshot` 输出 PNG |
| UI 树 | 通过 | `phone_lab ui` 可读取文本、描述、resource-id、bounds |
| 坐标点击 | 通过 | `phone_lab tap` |
| 点击文字/描述 | 通过 | `phone_lab tap-text 设置` 打开了设置 |
| ASCII 输入 | 通过 | 在夸克搜索框输入 `hello`，出现搜索联想 |
| 启动应用 | 通过 | `phone_lab launch` |
| 当前前台 Activity | 通过 | `phone_lab current` |
| Home/Back | 通过 | `phone_lab key` |
| 中文输入 | 未通过基线 | ADB `input text` 不稳定；交给 mobilerun / uiautomator2 |
| 锁屏状态 | 已知限制 | 锁屏时暂停，不能绕过 PIN |

`phone_lab` 位于仓库根目录，只依赖 Python 标准库和 adb。

## A2 mobilerun 验证

使用：

- mobilerun `0.7.4`
- DeepSeek provider
- 模型 `deepseek-v4-flash`
- ADB 连接（Portal 的无障碍服务在这台 ColorOS 上报告“此服务出现故障”，未作为 A 阶段依赖）

### 测试结果

| # | 任务 | 结果 | 备注 |
| --- | --- | --- | --- |
| 1 | 打开设置，查看安卓版本 | 通过 | 返回 Android 15 / ColorOS 15 |
| 2 | 计算 23 × 17 | 通过 | 结果 391 |
| 3 | 夸克搜索 DeepSeek，读第一条结果 | 通过 | 第一条为 DeepSeek 官网 |
| 4 | 文件管理器进入 Download，列出内容 | 通过 | 能读取文件夹和文件列表 |
| 5 | 下拉通知栏，读取前三条通知 | 通过 | 能区分应用和通知内容，未点击通知 |
| 6 | 网易云搜索《晴天》并播放 | 部分通过 | 播放器打开并显示 00:09 / 04:30，但有 VIP 弹窗；确认播放状态时超过步数上限，不计为完全通过 |
| 7 | 回桌面 → 最近任务 → 回桌面 | 部分通过 | 动作都执行了，但确认页面稳定时超过步数上限 |
| 8 | 清空计算器，计算 8 + 9 | 通过 | 结果 17 |

保守计分：**6 / 8 完全通过**，达到计划的 6/8 决策门槛。

### 失败原因

- 主要是 Agent 的步数预算，不是 ADB 控制失败
- 网易云出现 VIP 付费弹窗，播放确认被打断
- 模型会在最后反复确认页面状态，消耗剩余步数
- 后续应提高默认步数或让 Agent 在关键状态确认后立即结束

## A3 phone_lab 薄封装

已提供：

- `observe()`：屏幕尺寸、当前 Activity、UI 节点、可选截图
- `act`：点击、按文字点击、输入、按键、滑动能力
- `launch()`：按包名启动应用
- `task()`：调用 mobilerun 执行自然语言任务

CLI：

```powershell
python -m phone_lab observe --screenshot
python -m phone_lab tap-text 设置
python -m phone_lab task "打开设置，告诉我当前安卓版本" --steps 8
```

`task` 需要本机 `DEEPSEEK_API_KEY` 环境变量，密钥不进入仓库。

## A4 决策

- [x] 8 个任务完成
- [x] 6/8 完全通过
- [x] 普通应用 UI 树可读
- [x] 文件、通知、浏览器、计算器、设置可操作
- [x] 失败原因已记录
- [x] 已明确部分应用/状态需要视觉或更长步数

结论：进入 B 阶段。  
A 阶段保留为实验台，不直接成为生产实现。

## 已知限制

- Portal 无障碍服务在 ColorOS 15 上启用后仍报告故障；B 阶段必须自己验证 AccessibilityService 生命周期。
- 中文输入不能依赖 ADB `input text`；B 阶段应使用无障碍 `ACTION_SET_TEXT` 或输入法方案。
- 网易云等应用有会员/广告弹窗，自动化任务需要能识别并跳过。
- 通知和文件内容可能包含隐私，A 阶段只记录结构和结果，不落库。
