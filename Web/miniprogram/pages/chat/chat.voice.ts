import { BASE_URL } from '../../utils/api';

interface VoiceASRResponse {
  user_text?: string;
}

export function recognizeVoice(filePath: string): Promise<string> {
  return new Promise((resolve, reject) => {
    wx.uploadFile({
      url: `${BASE_URL}/voice/asr`,
      filePath,
      name: 'audio',
      header: {
        'Content-Type': 'multipart/form-data',
      },
      success: (res) => {
        if (res.statusCode !== 200) {
          reject(res);
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
