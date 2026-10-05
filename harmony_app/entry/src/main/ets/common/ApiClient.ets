import http from '@ohos.net.http';
import util from '@ohos.util';
import request from '@ohos.request';
import common from '@ohos.app.ability.common';
import { AppConfig } from './AppConfig';
import { ApiError, AuthSession } from '../model/ApiModels';

export class ApiClient {
  private readonly readSession: () => Promise<AuthSession | undefined>;
  private readonly saveSession: (session: AuthSession) => Promise<void>;
  private readonly clearSession: () => Promise<void>;
  private refreshInFlight?: Promise<boolean>;

  constructor(
    readSession: () => Promise<AuthSession | undefined>,
    saveSession: (session: AuthSession) => Promise<void>,
    clearSession: () => Promise<void>
  ) {
    this.readSession = readSession;
    this.saveSession = saveSession;
    this.clearSession = clearSession;
  }

  async get<T>(path: string, query?: Record<string, string>, authenticated: boolean = true): Promise<T> {
    return this.request<T>(http.RequestMethod.GET, path, undefined, query, authenticated);
  }

  async post<T>(path: string, body?: Record<string, Object>, authenticated: boolean = true): Promise<T> {
    return this.request<T>(http.RequestMethod.POST, path, body, undefined, authenticated);
  }

  async put<T>(path: string, body?: Record<string, Object>, authenticated: boolean = true): Promise<T> {
    return this.request<T>(http.RequestMethod.PUT, path, body, undefined, authenticated);
  }

  async patch<T>(path: string, body?: Record<string, Object>, authenticated: boolean = true): Promise<T> {
    return this.request<T>(http.RequestMethod.PATCH, path, body, undefined, authenticated);
  }

  async delete<T>(path: string, authenticated: boolean = true): Promise<T> {
    return this.request<T>(http.RequestMethod.DELETE, path, undefined, undefined, authenticated);
  }

  async uploadMultipart(
    context: common.BaseContext,
    path: string,
    fileUri: string,
    fileName: string,
    contentType: string,
    fields: Record<string, string>
  ): Promise<void> {
    const session = await this.readSession();
    const data: Array<request.RequestData> = [];
    Object.keys(fields).forEach((key: string) => {
      data.push({ name: key, value: fields[key] });
    });
    const headers: Record<string, string> = {
      'Accept': 'application/json',
      'X-Echo-Platform': AppConfig.appPlatform,
      'X-Echo-Version': AppConfig.appVersion
    };
    if (session?.accessToken) {
      headers['Authorization'] = `${session.tokenType || 'Bearer'} ${session.accessToken}`;
    }
    const config: request.UploadConfig = {
      url: this.buildUrl(path),
      header: headers,
      method: 'POST',
      files: [{
        uri: fileUri,
        filename: fileName,
        name: 'file',
        type: contentType
      }],
      data
    };
    const task = await request.uploadFile(context, config);
    await new Promise<void>((resolve, reject) => {
      task.on('complete', (states: Array<request.TaskState>) => {
        const state = states.length > 0 ? states[0] : undefined;
        if (state && state.responseCode >= 200 && state.responseCode < 300) {
          resolve();
        } else {
          reject(new Error(state?.message || `HTTP ${state?.responseCode ?? 0}`));
        }
      });
      task.on('fail', (states: Array<request.TaskState>) => {
        const state = states.length > 0 ? states[0] : undefined;
        reject(new Error(state?.message || '上传失败'));
      });
    });
  }

  async uploadMultipartResponse(
    path: string,
    fileUri: string,
    fileName: string,
    contentType: string,
    fields: Record<string, string>
  ): Promise<Record<string, Object>> {
    return this.uploadMultipartResponseAttempt(path, fileUri, fileName, contentType, fields, true);
  }

  private async uploadMultipartResponseAttempt(
    path: string,
    fileUri: string,
    fileName: string,
    contentType: string,
    fields: Record<string, string>,
    retryOnUnauthorized: boolean
  ): Promise<Record<string, Object>> {
    const session = await this.readSession();
    const formData: Array<http.MultiFormData> = [];
    Object.keys(fields).forEach((key: string) => {
      formData.push({
        name: key,
        contentType: 'text/plain',
        data: fields[key]
      });
    });
    formData.push({
      name: 'file',
      contentType,
      remoteFileName: fileName,
      filePath: fileUri
    });

    const headers: Record<string, string> = {
      'Accept': 'application/json',
      'Content-Type': 'multipart/form-data',
      'X-Echo-Platform': AppConfig.appPlatform,
      'X-Echo-Version': AppConfig.appVersion
    };
    if (session?.accessToken) {
      headers['Authorization'] = `${session.tokenType || 'Bearer'} ${session.accessToken}`;
    }

    const client = http.createHttp();
    try {
      const options: http.HttpRequestOptions = {
        method: http.RequestMethod.POST,
        header: headers,
        multiFormDataList: formData,
        connectTimeout: 10000,
        readTimeout: 60000
      };
      console.info(`[EchoUpload] POST ${this.buildUrl(path)} file=${fileUri} name=${fileName} type=${contentType}`);
      const response = await client.request(this.buildUrl(path), options);
      const raw = this.responseToString(response.result);
      console.info(`[EchoUpload] HTTP ${response.responseCode} body=${raw.substring(0, 1000)}`);
      if (response.responseCode === 401) {
        if (retryOnUnauthorized && await this.refreshSession()) {
          return this.uploadMultipartResponseAttempt(
            path, fileUri, fileName, contentType, fields, false
          );
        }
        await this.clearSession();
        throw new ApiError({
          status: 401,
          code: 'AUTH_ACCESS_INVALID',
          detail: '鐧诲綍鐘舵€佸凡澶辨晥锛岃閲嶆柊鐧诲綍',
          requestId: ''
        });
      }
      if (response.responseCode < 200 || response.responseCode >= 300) {
        throw this.toApiError(response.responseCode, raw);
      }
      if (raw.length === 0) return {};
      return JSON.parse(raw) as Record<string, Object>;
    } catch (error) {
      console.error(`[EchoUpload] request failed: ${String(error)}`);
      if (error instanceof Error) {
        throw error;
      }
      throw new Error(String(error));
    } finally {
      client.destroy();
    }
  }

  async openSse(
    path: string,
    afterMessageId: number,
    onEvent: (eventName: string, data: Record<string, Object>) => void
  ): Promise<void> {
    const session = await this.readSession();
    const client = http.createHttp();
    const sseQuery: Record<string, string> = {};
    sseQuery.after_message_id = String(afterMessageId);
    const sseOptions: http.HttpRequestOptions = {
        method: http.RequestMethod.GET,
        header: {
          'Accept': 'text/event-stream',
          'Authorization': `${session?.tokenType || 'Bearer'} ${session?.accessToken || ''}`
        } as Record<string, string>,
        connectTimeout: 10000,
        readTimeout: 0
    };
    await new Promise<void>((resolve, reject) => {
      let buffer = '';
      let settled = false;
      const decoder = util.TextDecoder.create('utf-8');
      const finish = (error?: Error): void => {
        if (settled) return;
        settled = true;
        client.off('dataReceive');
        client.off('dataEnd');
        client.destroy();
        if (error) reject(error);
        else resolve();
      };
      const consume = (): void => {
        // SSE frames are separated by a blank line. Keep the final partial
        // frame because a network chunk can end in the middle of a frame.
        const blocks = buffer.split(/\r?\n\r?\n/);
        buffer = blocks.pop() ?? '';
        blocks.forEach((block: string) => this.parseSse(block, onEvent));
      };
      client.on('dataReceive', (chunk: ArrayBuffer) => {
        const text = decoder.decodeToString(new Uint8Array(chunk), { stream: true });
        if (text.length > 0) {
          buffer += text;
          console.info(`[EchoSSE] data=${text.length}`);
          consume();
        }
      });
      client.on('dataEnd', () => {
        const tail = decoder.decodeToString(new Uint8Array(0), { stream: false });
        if (tail.length > 0) buffer += tail;
        consume();
        finish();
      });
      client.requestInStream(this.buildUrl(path, sseQuery), sseOptions, (error: Object, code: number) => {
        if (error) {
          console.error(`[EchoSSE] request failed: ${String(error)}`);
          finish(new Error(String(error)));
        } else if (code < 200 || code >= 300) {
          console.error(`[EchoSSE] HTTP ${code}`);
          finish(new Error(`HTTP ${code}`));
        } else {
          console.info(`[EchoSSE] connected HTTP ${code}, after=${afterMessageId}`);
        }
      });
    });
  }

  private async request<T>(
    method: http.RequestMethod,
    path: string,
    body?: Record<string, Object>,
    query?: Record<string, string>,
    authenticated: boolean = true,
    retryOnUnauthorized: boolean = true
  ): Promise<T> {
    const client = http.createHttp();
    try {
      const url = this.buildUrl(path, query);
      const headers: Record<string, string> = {};
      headers['Accept'] = 'application/json';
      headers['Content-Type'] = 'application/json';
      headers['X-Echo-Platform'] = AppConfig.appPlatform;
      headers['X-Echo-Version'] = AppConfig.appVersion;
      if (authenticated) {
        const session = await this.readSession();
        if (session?.accessToken) {
          headers['Authorization'] = `${session.tokenType || 'Bearer'} ${session.accessToken}`;
        }
      }
      const options: http.HttpRequestOptions = {
        method,
        header: headers,
        extraData: body === undefined ? undefined : JSON.stringify(body),
        connectTimeout: 10000,
        readTimeout: 60000
      };
      const response = await client.request(url, options);
      if (response.responseCode === 401 && authenticated) {
        if (retryOnUnauthorized) {
          const session = await this.readSession();
          const currentAuthorization = `${session?.tokenType || 'Bearer'} ${session?.accessToken || ''}`;
          // Another request may already have rotated the token while this one was in flight.
          const refreshed = session?.accessToken && currentAuthorization !== headers['Authorization']
            ? true
            : await this.refreshSession();
          if (refreshed) {
            return this.request<T>(method, path, body, query, authenticated, false);
          }
        } else {
          await this.clearSession();
        }
        throw new ApiError({
          status: 401,
          code: 'AUTH_ACCESS_INVALID',
          detail: '登录状态已失效，请重新登录',
          requestId: ''
        });
      }
      if (response.responseCode < 200 || response.responseCode >= 300) {
        throw this.toApiError(response.responseCode, String(response.result));
      }
      if (response.result === '' || response.result === undefined) {
        const emptyResult: Record<string, Object> = {};
        return emptyResult as T;
      }
      return JSON.parse(String(response.result)) as T;
    } finally {
      client.destroy();
    }
  }

  private async refreshSession(): Promise<boolean> {
    if (!this.refreshInFlight) this.refreshInFlight = this.tryRefresh();
    try {
      return await this.refreshInFlight;
    } finally {
      this.refreshInFlight = undefined;
    }
  }

  private async tryRefresh(): Promise<boolean> {
    const session = await this.readSession();
    if (!session?.refreshToken || !session.deviceId) {
      await this.clearSession();
      return false;
    }
    const client = http.createHttp();
    try {
      const refreshHeaders: Record<string, string> = {};
      refreshHeaders['Content-Type'] = 'application/json';
      refreshHeaders['Accept'] = 'application/json';
      const options: http.HttpRequestOptions = {
        method: http.RequestMethod.POST,
        header: refreshHeaders,
        extraData: JSON.stringify({
          refresh_token: session.refreshToken,
          device_id: session.deviceId
        }),
        connectTimeout: 10000,
        readTimeout: 30000
      };
      const response = await client.request(`${AppConfig.baseUrl}/login/refresh`, options);
      if (response.responseCode < 200 || response.responseCode >= 300) {
        await this.clearSession();
        return false;
      }
      const result = JSON.parse(String(response.result)) as Record<string, Object>;
      session.accessToken = String(result.access_token ?? '');
      session.refreshToken = String(result.refresh_token ?? '');
      session.tokenType = String(result.token_type ?? 'bearer');
      session.accessExpiresAt = String(result.expires_in ?? '');
      session.refreshExpiresAt = String(result.refresh_expires_in ?? '');
      await this.saveSession(session);
      return true;
    } catch (_) {
      await this.clearSession();
      return false;
    } finally {
      client.destroy();
    }
  }

  private toApiError(status: number, raw: string): ApiError {
    let code = '';
    let detail = '';
    let requestId = '';
    try {
      const parsed = JSON.parse(raw) as Record<string, Object>;
      code = String(parsed.code ?? '');
      detail = String(parsed.detail ?? '');
      requestId = String(parsed.request_id ?? '');
      if (Array.isArray(parsed.detail)) {
        detail = '请求字段不合法';
      }
    } catch (_) {
      detail = raw;
    }
    if (!detail) {
      detail = status === 422 ? '请求字段不合法' : `HTTP ${status}`;
    }
    return new ApiError({ status, code, detail, requestId });
  }

  private responseToString(result: string | Object | ArrayBuffer): string {
    if (typeof result === 'string') return result;
    if (result instanceof ArrayBuffer) {
      return util.TextDecoder.create('utf-8').decodeToString(new Uint8Array(result));
    }
    return JSON.stringify(result);
  }

  private buildUrl(path: string, query?: Record<string, string>): string {
    const cleanPath = path.startsWith('/') ? path : `/${path}`;
    const params = query === undefined
      ? ''
      : `?${Object.keys(query).map((key) => `${encodeURIComponent(key)}=${encodeURIComponent(query[key])}`).join('&')}`;
    return `${AppConfig.baseUrl}${cleanPath}${params}`;
  }

  private parseSse(raw: string, onEvent: (eventName: string, data: Record<string, Object>) => void): void {
    let eventName = '';
    let dataLines: string[] = [];
    for (const line of raw.split(/\r?\n/)) {
      if (line.startsWith('event:')) {
        eventName = line.substring(6).trim();
      } else if (line.startsWith('data:')) {
        dataLines.push(line.substring(5).trim());
      }
    }
    if (eventName && dataLines.length > 0) {
      try {
        const data = JSON.parse(dataLines.join('\n')) as Record<string, Object>;
        console.info(`[EchoSSE] event=${eventName}`);
        onEvent(eventName, data);
      } catch (error) {
        console.error(`[EchoSSE] invalid event=${eventName}: ${String(error)}`);
      }
    }
  }
}
