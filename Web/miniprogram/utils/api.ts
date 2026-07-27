import { appConfig } from './env';

export const BASE_URL = appConfig.apiBaseUrl;
export const USER_ID_STORAGE_KEY = 'echo_user_id';
export const ACCESS_TOKEN_STORAGE_KEY = 'echo_access_token';

export type MemoryStatus = 'active' | 'inactive' | 'deleted' | 'all';
export type ConversationMode = 'chat' | 'call';
export type PersonaReplyStyle = 'natural' | 'concise' | 'lively';
export type PersonaReplyLength = 'short' | 'balanced' | 'detailed';
export type PersonaSupportMode = 'comfort' | 'advice' | 'balanced';
export type PersonaProactivity = 'quiet' | 'balanced' | 'active';
export type RelationshipPace = 'slow' | 'natural' | 'open';
export type AffectionStyle = 'restrained' | 'contextual' | 'expressive';

export interface UserPreferences {
  preferred_name?: string | null;
  reply_style: PersonaReplyStyle;
  reply_length: PersonaReplyLength;
  support_mode: PersonaSupportMode;
  proactivity: PersonaProactivity;
  avoid_topics: string[];
  about_user?: string | null;
  relationship_pace: RelationshipPace;
  affection_style: AffectionStyle;
  enabled: boolean;
  schema_version: number;
  is_customized: boolean;
  onboarding_completed: boolean;
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
  relationship_pace: RelationshipPace;
  affection_style: AffectionStyle;
  enabled: boolean;
}

export interface RelationshipState {
  stage: 'new' | 'familiar' | 'trusted' | 'close';
  stage_label: string;
  interaction_turns: number;
  active_days: number;
  affection_permission: 'unknown' | 'restrained' | 'welcomed';
  schema_version: number;
  created_at?: string | null;
  updated_at?: string | null;
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

export interface ChatSendResponse {
  reply: string;
  audioUrls: string[];
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
  message: string,
  mode: ConversationMode = 'chat',
): Promise<ChatSendResponse> {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${BASE_URL}/chat/send`,
      method: 'POST',
      header: getJsonHeader(),
      data: {
        message,
        mode,
      },
      success: (res: any) => {
        const data = normalizeResponseData(res.data);
        if (res.statusCode === 200 && data && data.reply) {
          resolve({
            reply: data.reply,
            audioUrls: Array.isArray(data.audio_urls)
              ? data.audio_urls.filter((url: unknown) => typeof url === 'string' && url)
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

export function listMemories(
  status: MemoryStatus = 'active',
  limit = 100,
): Promise<MemoryListResponse> {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${BASE_URL}/memory/list`,
      method: 'GET',
      header: getJsonHeader(),
      data: { status, limit },
      success: (res: any) => {
        const data = normalizeResponseData(res.data);
        if (res.statusCode === 200 && data && Array.isArray(data.memories)) {
          resolve({
            memories: data.memories,
            count: typeof data.count === 'number' ? data.count : data.memories.length,
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

export function deleteMemory(memoryId: string): Promise<void> {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${BASE_URL}/memory/${encodeURIComponent(memoryId)}`,
      method: 'DELETE',
      header: getJsonHeader(),
      success: (res: any) => {
        const data = normalizeResponseData(res.data);
        if (res.statusCode === 200 && data && data.status === 'deleted') {
          resolve();
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

export function clearMemories(): Promise<{ cleared_count: number }> {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${BASE_URL}/memory/clear`,
      method: 'POST',
      header: getJsonHeader(),
      data: {},
      success: (res: any) => {
        const data = normalizeResponseData(res.data);
        if (res.statusCode === 200 && data && typeof data.cleared_count === 'number') {
          resolve(data);
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

function requestPersona(
  method: 'GET' | 'PUT' | 'POST',
  path: string,
  data: PersonaUpdateInput | Record<string, never>,
): Promise<UserPreferences> {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${BASE_URL}${path}`,
      method,
      header: getJsonHeader(),
      data,
      success: (res: any) => {
        const responseData = normalizeResponseData(res.data);
        if (res.statusCode === 200 && responseData && typeof responseData.enabled === 'boolean') {
          resolve(responseData as UserPreferences);
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

export function getPersona(): Promise<UserPreferences> {
  return requestPersona('GET', '/persona/me', {});
}

export function updatePersona(input: PersonaUpdateInput): Promise<UserPreferences> {
  return requestPersona('PUT', '/persona/me', input);
}

export function resetPersona(): Promise<UserPreferences> {
  return requestPersona('POST', '/persona/me/reset', {});
}

function requestRelationship(method: 'GET' | 'POST', path: string): Promise<RelationshipState> {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${BASE_URL}${path}`,
      method,
      header: getJsonHeader(),
      data: {},
      success: (res: any) => {
        const data = normalizeResponseData(res.data);
        if (res.statusCode === 200 && data && typeof data.stage === 'string') {
          resolve(data as RelationshipState);
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

export function getRelationship(): Promise<RelationshipState> {
  return requestRelationship('GET', '/relationship/me');
}

export function resetRelationship(): Promise<RelationshipState> {
  return requestRelationship('POST', '/relationship/me/reset');
}
