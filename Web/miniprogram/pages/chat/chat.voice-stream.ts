import { BASE_URL, getAuthHeader } from '../../utils/api';

interface StreamingASRMessage {
  type?: 'ready' | 'partial' | 'final' | 'error';
  text?: string;
  detail?: string;
}

export interface VoiceStreamSession {
  sendFrame(frame: ArrayBuffer): void;
  finish(): Promise<string>;
  cancel(): void;
}

function getStreamingASRUrl(): string {
  return `${BASE_URL.replace(/^http:/, 'ws:').replace(/^https:/, 'wss:')}/voice/asr/stream`;
}

export function openVoiceStream(
  onPartial: (text: string) => void,
): Promise<VoiceStreamSession> {
  return new Promise((resolve, reject) => {
    const socket = wx.connectSocket({
      url: getStreamingASRUrl(),
      header: getAuthHeader(),
    });
    let ready = false;
    let closed = false;
    let finishRequested = false;
    let finishResolve: ((text: string) => void) | null = null;
    let finishReject: ((error: Error) => void) | null = null;

    const readyTimeout = setTimeout(() => {
      if (ready) return;
      closed = true;
      socket.close({ code: 1000 });
      reject(new Error('流式语音服务连接超时'));
    }, 5000);

    const session: VoiceStreamSession = {
      sendFrame(frame: ArrayBuffer) {
        if (!ready || closed || finishRequested || !frame.byteLength) return;
        socket.send({ data: frame });
      },
      finish() {
        if (!ready || closed) {
          return Promise.reject(new Error('流式语音连接已关闭'));
        }
        finishRequested = true;
        return new Promise<string>((resolveFinal, rejectFinal) => {
          finishResolve = resolveFinal;
          finishReject = rejectFinal;
          socket.send({ data: JSON.stringify({ event: 'stop' }) });
        });
      },
      cancel() {
        if (closed) return;
        closed = true;
        if (ready) {
          socket.send({ data: JSON.stringify({ event: 'cancel' }) });
        }
        socket.close({ code: 1000 });
        finishReject?.(new Error('流式语音已取消'));
      },
    };

    socket.onMessage((event) => {
      if (typeof event.data !== 'string') return;
      let message: StreamingASRMessage;
      try {
        message = JSON.parse(event.data) as StreamingASRMessage;
      } catch (error) {
        void error;
        return;
      }

      if (message.type === 'ready') {
        ready = true;
        clearTimeout(readyTimeout);
        resolve(session);
        return;
      }
      if (message.type === 'partial') {
        onPartial((message.text || '').trim());
        return;
      }
      if (message.type === 'final') {
        const finalText = (message.text || '').trim();
        finishResolve?.(finalText);
        finishResolve = null;
        finishReject = null;
        return;
      }
      if (message.type === 'error') {
        finishReject?.(new Error(message.detail || '流式语音识别失败'));
      }
    });

    socket.onError(() => {
      clearTimeout(readyTimeout);
      const error = new Error('流式语音连接失败');
      if (!ready) {
        reject(error);
      } else {
        finishReject?.(error);
      }
    });

    socket.onClose(() => {
      clearTimeout(readyTimeout);
      closed = true;
      if (!ready) {
        reject(new Error('流式语音服务不可用'));
      } else if (finishRequested && finishReject) {
        finishReject(new Error('流式语音连接提前关闭'));
      }
    });
  });
}
