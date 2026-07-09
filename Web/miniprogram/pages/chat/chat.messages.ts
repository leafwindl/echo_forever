import type { Message } from './chat.types';

export function createMessage(
  id: number,
  sender: Message['sender'],
  content: string,
  isTyping = false,
): Message {
  return { id, sender, content, isTyping };
}

export function replaceMessageContent(
  messages: Message[],
  messageId: number,
  content: string,
): Message[] {
  return messages.map((message) => {
    if (message.id !== messageId) return message;
    return {
      ...message,
      content,
      isTyping: false,
    };
  });
}
