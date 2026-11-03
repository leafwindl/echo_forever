# phone_lab

A 阶段用的 Android ADB 手机控制实验工具。只依赖 Python 标准库和 adb，不进入生产后端。

## 前置

```powershell
adb devices
```

手机需要已解锁、开发者选项和 USB 调试已开启。首次使用请确认屏幕不是锁屏页。

## 命令

```powershell
python -m phone_lab devices
python -m phone_lab current
python -m phone_lab screenshot
python -m phone_lab ui --contains 设置
python -m phone_lab observe --screenshot
python -m phone_lab tap 540 1200
python -m phone_lab tap-text 设置
python -m phone_lab key back
python -m phone_lab launch com.android.settings
python -m phone_lab text hello
python -m phone_lab task "打开设置，告诉我当前安卓版本" --steps 8
```

`--serial` 或 `ECHO_ANDROID_SERIAL` 用于多设备环境。`ECHO_ADB` 可以覆盖 adb 路径。

`task` 通过 `mobilerun` 的 DeepSeek provider 执行，需要本机环境变量 `DEEPSEEK_API_KEY`；不要把密钥写进仓库或日志。也可以设置 `ECHO_MOBILERUN` 指向 mobilerun 可执行文件。

## 当前边界

- A1 只保证 ASCII 文字输入；中文输入交给 mobilerun / uiautomator2。
- 截图和 UI 树是实验产物，不进入生产审计。
- A 阶段结束后这套工具可以保留为实验工具，不直接作为 B 阶段的生产实现。
