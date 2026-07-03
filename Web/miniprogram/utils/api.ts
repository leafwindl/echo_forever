// utils/api.ts
import { appConfig } from './env';

export const BASE_URL = appConfig.apiBaseUrl;
export const USER_ID_STORAGE_KEY = 'echo_user_id';

export type MemoryStatus = 'active' | 'inactive' | 'deleted' | 'all';

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

interface MemoryListResponse {
  memories: MemoryItem[];
  count: number;
}

function normalizeResponseData(data: any): any {
  // 某些代理或调试环境可能把 JSON 当字符串返回，先尝试解析一次。
  if (typeof data === 'string') {
    try {
      return JSON.parse(data);
    } catch (e) {
      return data;
    }
  }
  return data;
}

// 前后端通信接口封装层
export function login(code: string, clientId: string): Promise<{ user_id: string }> { //将微信登陆获取的code发送给后端获取openid
  // Promise是用于处理异步操作的对象，代表未来会完成的任务。
  return new Promise((resolve, reject) => { 
    wx.request({
      url: `${BASE_URL}/login`,
      method: 'POST',
      header: { 'Content-Type': 'application/json' }, //请求头
      // client_id 是本地开发兜底身份：后端没有微信密钥时，用它生成稳定 dev 用户。
      data: { code, client_id: clientId },
      success: (res: any) => { //请求成功时的回调函数
        if (res.statusCode === 200 && res.data.user_id) {
          resolve(res.data);
        } else {
          reject(res.data);
        }
      },
      fail: (err) => reject(err),
    });
  });
}

//发送消息给后端
export function sendMessage(userId: string, message: string): Promise<string> {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${BASE_URL}/chat/send`,
      method: 'POST',
      header: { 'Content-Type': 'application/json' },
      data: { user_id: userId, message },
      success: (res: any) => {
        if (res.statusCode === 200 && res.data.reply) {
          resolve(res.data.reply);
        } else {
          reject(res.data);
        }
      },
      fail: (err) => reject(err),
    });
  });
}

export function listMemories(userId: string, status: MemoryStatus = 'active', limit = 100): Promise<MemoryListResponse> {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${BASE_URL}/memory/list`,
      method: 'GET',
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
      header: {
        'Content-Type': 'application/json',
      },
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
