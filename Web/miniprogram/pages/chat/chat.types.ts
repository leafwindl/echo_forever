export interface Message {
  id: number;
  sender: 'user' | 'echo';
  content: string;
  isTyping?: boolean;
}

export interface RequestInProgressError {
  isRequestInProgress?: boolean;
  isRateLimited?: boolean;
  isUnauthorized?: boolean;
  detail?: string;
}
