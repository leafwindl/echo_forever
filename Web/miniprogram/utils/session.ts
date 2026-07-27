import {
  ACCESS_TOKEN_STORAGE_KEY,
  getStoredAccessToken,
  login,
  LoginResponse,
  USER_ID_STORAGE_KEY,
} from './api';

const CLIENT_ID_STORAGE_KEY = 'echo_client_id';

function getOrCreateClientId(): string {
  const stored = wx.getStorageSync(CLIENT_ID_STORAGE_KEY);
  if (typeof stored === 'string' && stored) return stored;

  const clientId = `client_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
  wx.setStorageSync(CLIENT_ID_STORAGE_KEY, clientId);
  return clientId;
}

function requestWechatCode(): Promise<string> {
  return new Promise((resolve, reject) => {
    wx.login({
      success: (result) => {
        if (result.code) {
          resolve(result.code);
        } else {
          reject(new Error('微信未返回登录凭证'));
        }
      },
      fail: reject,
    });
  });
}

export function clearSession(): void {
  wx.removeStorageSync(USER_ID_STORAGE_KEY);
  wx.removeStorageSync(ACCESS_TOKEN_STORAGE_KEY);
}

export function getStoredUserId(): string {
  const userId = wx.getStorageSync(USER_ID_STORAGE_KEY);
  return typeof userId === 'string' ? userId : '';
}

export async function ensureSession(forceLogin = false): Promise<LoginResponse> {
  if (!forceLogin) {
    const userId = getStoredUserId();
    const accessToken = getStoredAccessToken();
    if (userId && accessToken) {
      return {
        user_id: userId,
        access_token: accessToken,
        token_type: 'bearer',
        expires_in: 0,
      };
    }
  }

  clearSession();
  const code = await requestWechatCode();
  return login(code, getOrCreateClientId());
}

