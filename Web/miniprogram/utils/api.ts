import { appConfig } from './env';

export const BASE_URL = appConfig.apiBaseUrl;
export const USER_ID_STORAGE_KEY = 'echo_user_id';
export const ACCESS_TOKEN_STORAGE_KEY = 'echo_access_token';

export type MemoryStatus = 'active' | 'inactive' | 'deleted' | 'all';
export type ChatInputType = 'text' | 'voice';

export interface MemoryItem {
  memory_id: string;
  memory_type: string;
  content: string;
  source_message_id?: number;
  confidence: number;
  importance: number;
  status: string;
  created_at?: string;
  updated_at?: string;
  expires_at?: string;
}

export interface SendMessageOptions {
  inputType?: ChatInputType;
  voiceReplyEnabled?: boolean;
}

export interface ChatSendResponse {
  reply: string;
  audioUrl?: string | null;
}

export interface RuntimePromptResponse {
  prompt: string;
  source: string;
}

export interface ClearChatContextResponse {
  deletedMessages: number;
  resetConversations: number;
}

export function clearChatContext(): Promise<ClearChatContextResponse> {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${BASE_URL}/chat/clear`,
      method: 'POST',
      header: getJsonHeader(),
      data: {},
      success: (res: any) => {
        const data = normalizeResponseData(res.data);
        if (res.statusCode === 200 && data) {
          resolve({
            deletedMessages: Number(data.deleted_messages || 0),
            resetConversations: Number(data.reset_conversations || 0),
          });
        } else if (res.statusCode === 401) {
          reject({ ...data, isUnauthorized: true });
        } else {
          reject(data);
        }
      },
      fail: (err) => reject(err),
    });
  });
}

export interface LoginResponse {
  user_id: string;
  access_token: string;
  token_type: string;
  expires_in: number;
}

interface MemoryListResponse {
  memories: MemoryItem[];
  count: number;
}

function normalizeResponseData(data: any): any {
  if (typeof data !== 'string') return data;

  try {
    return JSON.parse(data);
  } catch (error) {
    void error;
    return data;
  }
}

export function getStoredAccessToken(): string {
  const token = wx.getStorageSync(ACCESS_TOKEN_STORAGE_KEY);
  return typeof token === 'string' ? token : '';
}

export function getAuthHeader(): Record<string, string> {
  const token = getStoredAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function getJsonHeader(): Record<string, string> {
  return {
    'Content-Type': 'application/json',
    ...getAuthHeader(),
  };
}

function persistLoginSession(data: LoginResponse): void {
  wx.setStorageSync(USER_ID_STORAGE_KEY, data.user_id);
  wx.setStorageSync(ACCESS_TOKEN_STORAGE_KEY, data.access_token);
}

export function login(code: string, clientId: string): Promise<LoginResponse> {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${BASE_URL}/login`,
      method: 'POST',
      header: { 'Content-Type': 'application/json' },
      data: { code, client_id: clientId },
      success: (res: any) => {
        const data = normalizeResponseData(res.data);
        if (res.statusCode === 200 && data && data.user_id && data.access_token) {
          persistLoginSession(data);
          resolve(data);
        } else {
          reject(data);
        }
      },
      fail: (err) => reject(err),
    });
  });
}

export function sendMessage(
  userId: string,
  message: string,
  options: SendMessageOptions = {},
): Promise<ChatSendResponse> {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${BASE_URL}/chat/send`,
      method: 'POST',
      header: getJsonHeader(),
      data: {
        user_id: userId,
        message,
        input_type: options.inputType || 'text',
        voice_reply_enabled: Boolean(options.voiceReplyEnabled),
      },
      success: (res: any) => {
        const data = normalizeResponseData(res.data);
        if (res.statusCode === 200 && data && data.reply) {
          resolve({
            reply: data.reply,
            audioUrl: data.audio_url || null,
          });
        } else if (res.statusCode === 409) {
          reject({ ...data, isRequestInProgress: true });
        } else if (res.statusCode === 429) {
          reject({ ...data, isRateLimited: true });
        } else if (res.statusCode === 401) {
          reject({ ...data, isUnauthorized: true });
        } else {
          reject(data);
        }
      },
      fail: (err) => reject(err),
    });
  });
}

export function listMemories(
  userId: string,
  status: MemoryStatus = 'active',
  limit = 100,
): Promise<MemoryListResponse> {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${BASE_URL}/memory/list`,
      method: 'GET',
      header: getJsonHeader(),
      data: { user_id: userId, status, limit },
      success: (res: any) => {
        const data = normalizeResponseData(res.data);
        if (res.statusCode === 200 && data && Array.isArray(data.memories)) {
          resolve({
            memories: data.memories,
            count: typeof data.count === 'number' ? data.count : data.memories.length,
          });
        } else {
          reject(data);
        }
      },
      fail: (err) => reject(err),
    });
  });
}

export function deleteMemory(userId: string, memoryId: string): Promise<void> {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${BASE_URL}/memory/${encodeURIComponent(memoryId)}?user_id=${encodeURIComponent(userId)}`,
      method: 'DELETE',
      header: getJsonHeader(),
      success: (res: any) => {
        const data = normalizeResponseData(res.data);
        if (res.statusCode === 200 && data && data.status === 'deleted') {
          resolve();
        } else {
          reject(data);
        }
      },
      fail: (err) => reject(err),
    });
  });
}

export function clearMemories(userId: string): Promise<{ cleared_count: number }> {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${BASE_URL}/memory/clear`,
      method: 'POST',
      header: getJsonHeader(),
      data: { user_id: userId },
      success: (res: any) => {
        const data = normalizeResponseData(res.data);
        if (res.statusCode === 200 && data && typeof data.cleared_count === 'number') {
          resolve(data);
        } else {
          reject(data);
        }
      },
      fail: (err) => reject(err),
    });
  });
}

function getAdminDebugHeader(): Record<string, string> {
  return {
    ...getJsonHeader(),
    'X-Admin-Debug-Token': appConfig.adminDebugToken,
  };
}

export function getRuntimeSystemPrompt(): Promise<RuntimePromptResponse> {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${BASE_URL}/admin/debug/prompt`,
      method: 'GET',
      header: getAdminDebugHeader(),
      success: (res: any) => {
        const data = normalizeResponseData(res.data);
        if (res.statusCode === 200 && data && typeof data.prompt === 'string') {
          resolve({
            prompt: data.prompt,
            source: String(data.source || ''),
          });
        } else {
          reject(data);
        }
      },
      fail: (err) => reject(err),
    });
  });
}

export function updateRuntimeSystemPrompt(prompt: string): Promise<RuntimePromptResponse> {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${BASE_URL}/admin/debug/prompt`,
      method: 'PUT',
      header: getAdminDebugHeader(),
      data: { prompt },
      success: (res: any) => {
        const data = normalizeResponseData(res.data);
        if (res.statusCode === 200 && data && typeof data.prompt === 'string') {
          resolve({
            prompt: data.prompt,
            source: String(data.source || ''),
          });
        } else {
          reject(data);
        }
      },
      fail: (err) => reject(err),
    });
  });
}

export function clearAdminChatContext(userId: string): Promise<ClearChatContextResponse> {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${BASE_URL}/admin/debug/chat/clear`,
      method: 'POST',
      header: getAdminDebugHeader(),
      data: { user_id: userId },
      success: (res: any) => {
        const data = normalizeResponseData(res.data);
        if (res.statusCode === 200 && data) {
          resolve({
            deletedMessages: Number(data.deleted_messages || 0),
            resetConversations: Number(data.reset_conversations || 0),
          });
        } else {
          reject(data);
        }
      },
      fail: (err) => reject(err),
    });
  });
}
