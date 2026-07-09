import type { ChatInputType } from '../../utils/api';

export interface Message {
  id: number;
  sender: 'user' | 'echo';
  content: string;
  isTyping?: boolean;
}

export type ChatMode = ChatInputType;

export interface SitCrop {
  cropWidth: string;
  cropHeight: string;
  cropOffsetX: string;
  cropOffsetY: string;
  imageWidth: string;
  imageLeft: string;
  imageTop: string;
}
