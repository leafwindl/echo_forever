import { BASE_URL, getAuthHeader } from '../utils/api';

interface VoiceASRResponse {
  user_text?: string;
  detail?: string;
}

export function recognizeVoice(filePath: string): Promise<string> {
  return new Promise((resolve, reject) => {
    wx.uploadFile({
      url: `${BASE_URL}/voice/asr`,
      filePath,
      name: 'audio',
      header: getAuthHeader(),
      success: (result) => {
        let data: VoiceASRResponse = {};
        try {
          data = JSON.parse(result.data) as VoiceASRResponse;
        } catch (error) {
          void error;
        }
        if (result.statusCode === 200) {
          resolve(data.user_text || '');
          return;
        }
        reject({
          detail: data.detail || '语音识别失败',
          isUnauthorized: result.statusCode === 401,
          isRateLimited: result.statusCode === 429,
          isUploadTooLarge: result.statusCode === 413,
        });
      },
      fail: reject,
    });
  });
}
