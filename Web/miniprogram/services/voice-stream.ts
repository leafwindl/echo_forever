import { BASE_URL, getAuthHeader } from '../utils/api';

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
    const socket = wx.connectSocket({ url: getStreamingASRUrl(), header: getAuthHeader() });
    let ready = false;
    let closed = false;
    let finishRequested = false;
    let finishResolve: ((text: string) => void) | null = null;
    let finishReject: ((error: Error) => void) | null = null;
    let finishTimeout: ReturnType<typeof setTimeout> | null = null;

    const clearFinishTimeout = () => {
      if (finishTimeout === null) return;
      clearTimeout(finishTimeout);
      finishTimeout = null;
    };
    const readyTimeout = setTimeout(() => {
      if (ready) return;
      closed = true;
      socket.close({ code: 1000 });
      reject(new Error('流式语音服务连接超时'));
    }, 5000);

    const session: VoiceStreamSession = {
      sendFrame(frame) {
        if (ready && !closed && !finishRequested && frame.byteLength) socket.send({ data: frame });
      },
      finish() {
        if (!ready || closed) return Promise.reject(new Error('流式语音连接已关闭'));
        finishRequested = true;
        return new Promise<string>((resolveFinal, rejectFinal) => {
          finishResolve = resolveFinal;
          finishReject = rejectFinal;
          finishTimeout = setTimeout(() => {
            finishTimeout = null;
            finishReject?.(new Error('流式语音识别结果超时'));
            finishResolve = null;
            finishReject = null;
            socket.close({ code: 1000 });
          }, 15000);
          socket.send({ data: JSON.stringify({ event: 'stop' }) });
        });
      },
      cancel() {
        if (closed) return;
        closed = true;
        clearFinishTimeout();
        if (ready) socket.send({ data: JSON.stringify({ event: 'cancel' }) });
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
      } else if (message.type === 'partial') {
        onPartial((message.text || '').trim());
      } else if (message.type === 'final') {
        clearFinishTimeout();
        finishResolve?.((message.text || '').trim());
        finishResolve = null;
        finishReject = null;
      } else if (message.type === 'error') {
        clearFinishTimeout();
        finishReject?.(new Error(message.detail || '流式语音识别失败'));
      }
    });
    socket.onError(() => {
      clearTimeout(readyTimeout);
      clearFinishTimeout();
      const error = new Error('流式语音连接失败');
      ready ? finishReject?.(error) : reject(error);
    });
    socket.onClose(() => {
      clearTimeout(readyTimeout);
      clearFinishTimeout();
      closed = true;
      if (!ready) reject(new Error('流式语音服务不可用'));
      else if (finishRequested && finishReject) finishReject(new Error('流式语音连接提前关闭'));
    });
  });
}
