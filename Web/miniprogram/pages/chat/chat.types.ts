export interface Message {
  id: number;
  sender: 'user' | 'echo';
  content: string;
  isTyping?: boolean;
  stickerUrl?: string;
  sources?: Array<{ title: string; url: string }>;
}

export interface RequestInProgressError {
  isRequestInProgress?: boolean;
  isRateLimited?: boolean;
  isUnauthorized?: boolean;
  detail?: string;
}
