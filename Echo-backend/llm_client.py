import httpx
import logging
from config import settings

logger = logging.getLogger(__name__)
# 构造异步函数
async def request_llm(messages: list[dict]) -> str:
    """
    处理大模型请求，并返回回复文本
    
    Args:
        messages: 当前对话的消息列表（包含系统Prompt和历史消息）
        
    Returns:
        str: AI的回复内容
    """
    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
    # 请求头
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    # 构造请求体
    payload = {
        "model": settings.LLM_MODEL or "gpt-4o",
        "messages": messages,
        "temperature": settings.temperature,
        "max_tokens": settings.max_tokens, # 限制回复最大token长度
    }
    # 发送请求与处理响应
    try:
        # 使用AsyncClient发送POST请求，确保请求结束后自动释放连接
        # async with ... as client是创建一个上下文管理器，确保在请求完成后正确关闭连接，避免资源泄漏
        async with httpx.AsyncClient(timeout=settings.timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status() # 检查状态码
            data = response.json() # 解析JSON响应
            return data["choices"][0]["message"]["content"] # 提取第一条回复内容并返回，这个和OpenAI的API响应结构相关
    except httpx.HTTPStatusError as exc:
        logger.error(f"HTTPStatusError from LLM: {exc.response.text}")
        raise ValueError(f"大模型响应错误: {exc.response.status_code}")
    except Exception as exc:
        logger.error(f"Error requesting LLM: {exc}")
        raise ValueError("调用大模型服务失败")


# OpenAI的API响应结构如下：data是整个响应的字典
# {
#   "id": "chatcmpl-xxx",
#   "object": "chat.completion",
#   "created": 1234567890,
#   "model": "gpt-4o",
#   "choices": [
#     {
#       "index": 0,
#       "message": {
#         "role": "assistant",
#         "content": "你好！我是 Echo。"
#       },
#       "finish_reason": "stop"
#     }
#   ],
#   "usage": { ... }
# }