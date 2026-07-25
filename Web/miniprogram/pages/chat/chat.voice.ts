import { BASE_URL, getAuthHeader } from '../../utils/api';

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
      success: (res) => {
        if (res.statusCode !== 200) {
          let detail = '语音识别失败';
          try {
            const data = JSON.parse(res.data) as VoiceASRResponse;
            detail = data.detail || detail;
          } catch (error) {
            void error;
          }
          reject({
            detail,
            statusCode: res.statusCode,
            isUnauthorized: res.statusCode === 401,
            isRateLimited: res.statusCode === 429,
            isUploadTooLarge: res.statusCode === 413,
          });
          return;
        }

        try {
          const data = JSON.parse(res.data) as VoiceASRResponse;
          resolve(data.user_text || '');
        } catch (error) {
          reject(error);
        }
      },
      fail: (err) => reject(err),
    });
  });
}
