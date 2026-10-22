# Assistant Persona

`assistant_persona` 保存由产品维护、不可被单个用户改写的 Echo 人格。

- `AssistantPersona` 定义稳定特点、表达原则和允许的自我披露。
- `ASSISTANT_PERSONA_VERSION` 选择版本，未知版本会拒绝启动或生成上下文。
- 用户交流偏好属于 `features/persona`，双方关系阶段属于 `features/relationship`。

当前默认版本为 `echo-persona-v2`：明确 AI 身份，女性人格，轻快好奇、傲娇甜软。人格包含行为规则与标明为虚构示范的口吻例子；例子不属于用户历史或长期记忆。原 `echo-persona-v1` 配置名兼容解析为 v2，避免旧环境配置恢复已经废弃的身份。

聊天分段、颜文字与表情包的落地说明见 [Echo 聊天 v2](../../../docs/echo-companion-chat-v2.md)。

