export interface Message {
  id: number;
  sender: 'user' | 'echo';
  content: string;
  isTyping?: boolean;
}

export interface SitCrop {
  cropWidth: string;
  cropHeight: string;
  cropOffsetX: string;
  cropOffsetY: string;
  imageWidth: string;
  imageLeft: string;
  imageTop: string;
}

export interface RequestInProgressError {
  isRequestInProgress?: boolean;
  isRateLimited?: boolean;
  isUnauthorized?: boolean;
  detail?: string;
}
