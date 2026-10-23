# Echo 开发约束

开始后端开发、重构、修复、清理、提示词调整或测试前，必须先阅读 [Echo 后端架构与代码规范](doc/Echo%20后端架构与代码规范.md)。这是后续开发的统一规范，用户当前明确要求优先。

- 只新增有当前消费者的实现、接口、配置和提示资产，不建未来占位 feature、路由、空注册或备用门面。
- 保留用户修改；删除前检查入口、任务、脚本和消费者，不误删 Protocol、测试 fake 或运维工具。
- Interface 不写 SQL，Domain/Application 不依赖具体基础设施，跨 feature 通过稳定 API、实际端口或事件协作。
- 共享提示机制位于 `Echo-backend/shared/prompting/`，不得反向导入业务 feature。内容分身份角色、规则约束、上下文注入、工具描述、示例、输出格式六类；资产须与真实加载链同一变更接入。
- 当前尚无完整六类资产注册和按需选择引擎，不得声称已具备，也不预建空目录。
- 修改后运行 `python -B scripts/check_architecture.py` 和相关后端测试；影响客户端时执行适用的 Flutter/Harmony 检查。DB、模型、设备验收和 skip 如实报告。
- 不删除失败测试、弱化权限或新增空壳掩盖问题；不得扩大 feature 依赖环。
- 手机开发更新默认走 USB：鸿蒙使用 `harmony_app/scripts/install-usb.ps1` 同签名覆盖安装并核对版本；Android 使用对应 adb 覆盖流程。不自动卸载、清数据或改签名来绕过覆盖失败。
