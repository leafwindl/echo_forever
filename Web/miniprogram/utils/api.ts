import { appConfig } from './env';

export const BASE_URL = appConfig.apiBaseUrl;
export const USER_ID_STORAGE_KEY = 'echo_user_id';
export const ACCESS_TOKEN_STORAGE_KEY = 'echo_access_token';

export type MemoryStatus = 'active' | 'inactive' | 'deleted' | 'all';
export type ChatInputType = 'text' | 'voice';
export type PersonaReplyStyle = 'natural' | 'concise' | 'lively';
export type PersonaReplyLength = 'short' | 'balanced' | 'detailed';
export type PersonaSupportMode = 'comfort' | 'advice' | 'balanced';
export type PersonaProactivity = 'quiet' | 'balanced' | 'active';

export interface UserPersona {
  preferred_name?: string | null;
  reply_style: PersonaReplyStyle;
  reply_length: PersonaReplyLength;
  support_mode: PersonaSupportMode;
  proactivity: PersonaProactivity;
  avoid_topics: string[];
  about_user?: string | null;
  enabled: boolean;
  schema_version: number;
  is_customized: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface PersonaUpdateInput {
  preferred_name?: string | null;
  reply_style: PersonaReplyStyle;
  reply_length: PersonaReplyLength;
  support_mode: PersonaSupportMode;
  proactivity: PersonaProactivity;
  avoid_topics: string[];
  about_user?: string | null;
  enabled: boolean;
}

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
  phoneMode?: boolean;
}

export interface ChatSendResponse {
  reply: string;
  audioUrl?: string | null;
  audioUrls: string[];
}

export interface ChatStreamCallbacks {
  onDelta?(delta: string): void;
  onAudio?(audioUrl: string): void;
}

interface ChatSSEPayload {
  text?: string;
  url?: string;
  reply?: string;
  audio_url?: string | null;
  audio_urls?: string[];
  detail?: string;
  code?: string;
}

interface ChunkedRequestTask extends WechatMiniprogram.RequestTask {
  onChunkReceived(callback: (result: { data: ArrayBuffer }) => void): void;
}

class Utf8StreamDecoder {
  private remaining = 0;
  private codePoint = 0;

  decode(buffer: ArrayBuffer): string {
    const bytes = new Uint8Array(buffer);
    let output = '';
    for (const byte of bytes) {
      if (this.remaining === 0) {
        if (byte < 0x80) {
          output += String.fromCharCode(byte);
        } else if ((byte & 0xe0) === 0xc0) {
          this.remaining = 1;
          this.codePoint = byte & 0x1f;
        } else if ((byte & 0xf0) === 0xe0) {
          this.remaining = 2;
          this.codePoint = byte & 0x0f;
        } else if ((byte & 0xf8) === 0xf0) {
          this.remaining = 3;
          this.codePoint = byte & 0x07;
        } else {
          output += '\ufffd';
        }
        continue;
      }

      if ((byte & 0xc0) !== 0x80) {
        output += '\ufffd';
        this.remaining = 0;
        this.codePoint = 0;
        if (byte < 0x80) output += String.fromCharCode(byte);
        continue;
      }
      this.codePoint = (this.codePoint << 6) | (byte & 0x3f);
      this.remaining -= 1;
      if (this.remaining === 0) {
        output += String.fromCodePoint(this.codePoint);
        this.codePoint = 0;
      }
    }
    return output;
  }
}

class SSEChunkParser {
  private buffer = '';

  constructor(private readonly onEvent: (event: string, data: ChatSSEPayload) => void) {}

  push(chunk: string): void {
    this.buffer += chunk;
    let boundaryIndex = this.buffer.indexOf('\n\n');
    while (boundaryIndex >= 0) {
      const rawEvent = this.buffer.slice(0, boundaryIndex);
      this.buffer = this.buffer.slice(boundaryIndex + 2);
      this.parseEvent(rawEvent);
      boundaryIndex = this.buffer.indexOf('\n\n');
    }
  }

  private parseEvent(rawEvent: string): void {
    let eventName = 'message';
    const dataLines: string[] = [];
    for (const rawLine of rawEvent.split('\n')) {
      const line = rawLine.endsWith('\r') ? rawLine.slice(0, -1) : rawLine;
      if (line.startsWith('event:')) eventName = line.slice(6).trim();
      if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart());
    }
    if (!dataLines.length) return;
    try {
      this.onEvent(eventName, JSON.parse(dataLines.join('\n')) as ChatSSEPayload);
    } catch (error) {
      console.warn('忽略无法解析的流式消息', error);
    }
  }
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
        voice_reply_enabled: Boolean(options.phoneMode),
      },
      success: (res: any) => {
        const data = normalizeResponseData(res.data);
        if (res.statusCode === 200 && data && data.reply) {
          resolve({
            reply: data.reply,
            audioUrl: data.audio_url || null,
            audioUrls: Array.isArray(data.audio_urls)
              ? data.audio_urls.filter((url: unknown) => typeof url === 'string' && url)
              : data.audio_url
              ? [data.audio_url]
              : [],
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

export function sendMessageStream(
  userId: string,
  message: string,
  options: SendMessageOptions = {},
  callbacks: ChatStreamCallbacks = {},
): Promise<ChatSendResponse> {
  return new Promise((resolve, reject) => {
    let settled = false;
    let finalReply = '';
    const streamedAudioUrls: string[] = [];
    const decoder = new Utf8StreamDecoder();

    const settleResolve = (result: ChatSendResponse) => {
      if (settled) return;
      settled = true;
      resolve(result);
    };
    const settleReject = (error: any) => {
      if (settled) return;
      settled = true;
      reject(error);
    };

    const parser = new SSEChunkParser((event, data) => {
      if (event === 'delta' && data.text) {
        finalReply += data.text;
        callbacks.onDelta?.(data.text);
        return;
      }
      if (event === 'audio' && data.url) {
        streamedAudioUrls.push(data.url);
        callbacks.onAudio?.(data.url);
        return;
      }
      if (event === 'error') {
        settleReject({
          ...data,
          isRequestInProgress: data.code === 'request_in_progress',
        });
        return;
      }
      if (event === 'done') {
        const audioUrls = Array.isArray(data.audio_urls)
          ? data.audio_urls.filter((url): url is string => typeof url === 'string' && Boolean(url))
          : streamedAudioUrls;
        settleResolve({
          reply: data.reply || finalReply,
          audioUrl: data.audio_url || audioUrls[0] || null,
          audioUrls,
        });
      }
    });

    const requestTask = (wx.request as any)({
      url: `${BASE_URL}/chat/stream`,
      method: 'POST',
      header: {
        ...getJsonHeader(),
        Accept: 'text/event-stream',
      },
      data: {
        user_id: userId,
        message,
        input_type: options.inputType || 'text',
        voice_reply_enabled: Boolean(options.phoneMode),
      },
      enableChunked: true,
      responseType: 'arraybuffer',
      timeout: 90000,
      success: (res: any) => {
        if (settled) return;
        if (res.statusCode === 401) {
          settleReject({ isUnauthorized: true, detail: '登录已失效' });
        } else if (res.statusCode === 429) {
          settleReject({ isRateLimited: true, detail: '消息发送过于频繁，请稍后再试' });
        } else if (res.statusCode !== 200) {
          settleReject(normalizeResponseData(res.data));
        } else {
          settleReject({ detail: '流式回复提前结束' });
        }
      },
      fail: (error: any) => settleReject(error),
    }) as ChunkedRequestTask;

    if (typeof requestTask.onChunkReceived !== 'function') {
      requestTask.abort();
      settleReject({ detail: '当前微信版本不支持流式回复', isStreamingUnsupported: true });
      return;
    }
    requestTask.onChunkReceived((result) => {
      parser.push(decoder.decode(result.data));
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

function requestPersona(
  method: 'GET' | 'PUT' | 'POST',
  path: string,
  data: PersonaUpdateInput | Record<string, never>,
): Promise<UserPersona> {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${BASE_URL}${path}`,
      method,
      header: getJsonHeader(),
      data,
      success: (res: any) => {
        const responseData = normalizeResponseData(res.data);
        if (res.statusCode === 200 && responseData && typeof responseData.enabled === 'boolean') {
          resolve(responseData as UserPersona);
        } else if (res.statusCode === 401) {
          reject({ ...responseData, isUnauthorized: true });
        } else {
          reject(responseData);
        }
      },
      fail: (err) => reject(err),
    });
  });
}

export function getPersona(): Promise<UserPersona> {
  return requestPersona('GET', '/persona/me', {});
}

export function updatePersona(input: PersonaUpdateInput): Promise<UserPersona> {
  return requestPersona('PUT', '/persona/me', input);
}

export function resetPersona(): Promise<UserPersona> {
  return requestPersona('POST', '/persona/me/reset', {});
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
