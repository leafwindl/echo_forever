# Assistant Persona

`assistant_persona` 保存由产品维护、不可被单个用户改写的 Echo 人格。

- `AssistantPersona` 定义稳定特点、表达原则和允许的自我披露。
- `ASSISTANT_PERSONA_VERSION` 选择版本，未知版本会拒绝启动或生成上下文。
- 用户交流偏好属于 `features/persona`，双方关系阶段属于 `features/relationship`。

当前默认版本为 `echo-persona-v3`：以情感陪伴为核心，平等、有主见、傲娇甜软；情绪随互动变化，轻松文字聊天主动使用贴切颜文字，也允许安静认真地回应。产品定位不重复展开人格。人格包含标明为虚构示范的口吻例子，例子不属于用户历史或长期记忆。原 `echo-persona-v1/v2` 配置名解析为当前 v3，避免部署旧配置恢复已退役内容。

允许表达当前交流里的喜爱、开心、害羞和不同意见；真实性边界针对人类身份、现实身体、离线经历等事实，不压制正常的角色化情绪。聊天和主动聊天的自然语言交付指引使用中文；`role`、`tools`、工具名和状态值保留协议原名。

聊天分段、颜文字与表情包的落地说明见 [Echo 聊天 v2](../../../docs/echo-companion-chat-v2.md)。

