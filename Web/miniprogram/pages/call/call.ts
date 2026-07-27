import { getPersona, sendMessage } from '../../utils/api';
import { clearSession, ensureSession } from '../../utils/session';
import { playVoiceSegments, stopVoice } from '../../services/audio-player';
import { recognizeVoice } from '../../services/voice-asr';
import { openVoiceStream, VoiceStreamSession } from '../../services/voice-stream';

type CallStatus = 'connecting' | 'idle' | 'recording' | 'recognizing' | 'thinking' | 'speaking';

interface ActiveVoiceStream {
  opening: Promise<VoiceStreamSession>;
  session: VoiceStreamSession | null;
  bufferedFrames: ArrayBuffer[];
  bufferedBytes: number;
  canceled: boolean;
}

interface CallPageData {
  callActive: boolean;
  status: CallStatus;
  statusLabel: string;
  elapsedLabel: string;
  isReady: boolean;
  isSending: boolean;
  isRecording: boolean;
  isPressActive: boolean;
  shouldSendVoice: boolean;
  partialText: string;
  echoCaption: string;
}

interface CallPageController {
  data: CallPageData;
  setData(data: Partial<CallPageData>): void;
  setStatus(status: CallStatus): void;
  cancelVoiceStream(): void;
  handleStreamingVoice(stream: ActiveVoiceStream, fallbackFilePath: string): Promise<void>;
  handleVoiceFile(filePath: string): Promise<void>;
}

interface EchoRecorderManager extends WechatMiniprogram.RecorderManager {
  __echoCallEventsBound?: boolean;
  __echoCallPage?: CallPageController | null;
  __echoVoiceStream?: ActiveVoiceStream | null;
}

const STREAM_BUFFER_MAX_BYTES = 1024 * 1024;
const recorderManager = wx.getRecorderManager() as EchoRecorderManager;
let timerId: ReturnType<typeof setInterval> | null = null;
let callStartedAt = 0;

function cancelVoiceStream(stream: ActiveVoiceStream): void {
  if (stream.canceled) return;
  stream.canceled = true;
  stream.bufferedFrames = [];
  stream.bufferedBytes = 0;
  stream.session?.cancel();
  void stream.opening.then((session) => session.cancel()).catch(() => undefined);
}

function formatDuration(elapsedSeconds: number): string {
  const minutes = Math.floor(elapsedSeconds / 60).toString().padStart(2, '0');
  const seconds = Math.floor(elapsedSeconds % 60).toString().padStart(2, '0');
  return `${minutes}:${seconds}`;
}

Page({
  data: {
    callActive: true,
    status: 'connecting' as CallStatus,
    statusLabel: '正在连接',
    elapsedLabel: '00:00',
    isReady: false,
    isSending: false,
    isRecording: false,
    isPressActive: false,
    shouldSendVoice: false,
    partialText: '',
    echoCaption: '',
  } as CallPageData,

  onLoad() {
    recorderManager.__echoCallPage = this as unknown as CallPageController;
    if (recorderManager.__echoVoiceStream) cancelVoiceStream(recorderManager.__echoVoiceStream);
    recorderManager.__echoVoiceStream = null;
    this.bindRecorderEvents();
    wx.setKeepScreenOn({ keepScreenOn: true });
    void this.connectCall();
  },

  onUnload() {
    this.endCallResources();
  },

  async connectCall() {
    try {
      await ensureSession();
      const preferences = await getPersona();
      if (!preferences.onboarding_completed) {
        wx.redirectTo({ url: '/pages/onboarding/onboarding' });
        return;
      }
      callStartedAt = Date.now();
      timerId = setInterval(() => {
        this.setData({ elapsedLabel: formatDuration((Date.now() - callStartedAt) / 1000) });
      }, 1000);
      this.setData({ isReady: true });
      this.setStatus('idle');
    } catch (error) {
      console.error('电话连接失败', error);
      clearSession();
      wx.showToast({ title: '登录已失效，请重新进入', icon: 'none' });
      setTimeout(() => wx.redirectTo({ url: '/pages/onboarding/onboarding' }), 800);
    }
  },

  setStatus(status: CallStatus) {
    const labels: Record<CallStatus, string> = {
      connecting: '正在连接',
      idle: '按住下方按钮说话',
      recording: '正在听你说',
      recognizing: '正在听清内容',
      thinking: 'Echo 正在想',
      speaking: 'Echo 正在说话',
    };
    this.setData({ status, statusLabel: labels[status] });
  },

  bindRecorderEvents() {
    if (recorderManager.__echoCallEventsBound) return;
    recorderManager.__echoCallEventsBound = true;

    recorderManager.onStart(() => {
      const page = recorderManager.__echoCallPage;
      if (!page) return;
      page.setData({ isRecording: true });
      if (!page.data.isPressActive) {
        page.setData({ shouldSendVoice: false });
        page.cancelVoiceStream();
        recorderManager.stop();
        return;
      }
      page.setStatus('recording');
      wx.vibrateShort({ type: 'light' });
    });

    recorderManager.onFrameRecorded((result) => {
      const stream = recorderManager.__echoVoiceStream;
      if (!stream || stream.canceled) return;
      if (stream.session) {
        stream.session.sendFrame(result.frameBuffer);
      } else if (stream.bufferedBytes + result.frameBuffer.byteLength <= STREAM_BUFFER_MAX_BYTES) {
        stream.bufferedFrames.push(result.frameBuffer);
        stream.bufferedBytes += result.frameBuffer.byteLength;
      }
    });

    recorderManager.onStop((result) => {
      const page = recorderManager.__echoCallPage;
      if (!page) return;
      const shouldSendVoice = page.data.shouldSendVoice;
      const stream = recorderManager.__echoVoiceStream || null;
      recorderManager.__echoVoiceStream = null;
      page.setData({
        isRecording: false,
        isPressActive: false,
        shouldSendVoice: false,
        partialText: '',
      });

      if (shouldSendVoice && stream) {
        page.setStatus('recognizing');
        void page.handleStreamingVoice(stream, result.tempFilePath || '');
      } else if (shouldSendVoice && result.tempFilePath) {
        page.setStatus('recognizing');
        void page.handleVoiceFile(result.tempFilePath);
      } else {
        if (stream) cancelVoiceStream(stream);
        page.setStatus('idle');
      }
    });

    recorderManager.onError((error) => {
      const page = recorderManager.__echoCallPage;
      if (!page) return;
      console.error('电话录音失败', error);
      page.cancelVoiceStream();
      page.setData({ isRecording: false, isPressActive: false, shouldSendVoice: false });
      page.setStatus('idle');
      wx.showToast({ title: '没录到声音，请重试', icon: 'none' });
    });
  },

  async onStartRecord() {
    if (!this.data.isReady || this.data.isSending || this.data.isRecording) return;
    stopVoice();
    this.setData({ isPressActive: true, shouldSendVoice: true, echoCaption: '' });
    const authorized = await this.checkRecordAuth();
    if (!authorized || !this.data.isPressActive) {
      this.setData({ isPressActive: false, shouldSendVoice: false });
      return;
    }

    const opening = openVoiceStream((partialText) => {
      if (partialText && this.data.isRecording) this.setData({ partialText });
    });
    const stream: ActiveVoiceStream = {
      opening,
      session: null,
      bufferedFrames: [],
      bufferedBytes: 0,
      canceled: false,
    };
    recorderManager.__echoVoiceStream = stream;
    void opening
      .then((session) => {
        if (stream.canceled) {
          session.cancel();
          return;
        }
        stream.session = session;
        stream.bufferedFrames.forEach((frame) => session.sendFrame(frame));
        stream.bufferedFrames = [];
        stream.bufferedBytes = 0;
      })
      .catch((error) => {
        console.warn('流式识别不可用，将使用整段识别', error);
        stream.bufferedFrames = [];
        stream.bufferedBytes = 0;
      });

    recorderManager.start({
      duration: 60000,
      sampleRate: 16000,
      numberOfChannels: 1,
      format: 'mp3',
      frameSize: 4,
    });
  },

  onStopRecord() {
    this.setData({ isPressActive: false });
    if (this.data.isRecording) recorderManager.stop();
    else {
      this.setData({ shouldSendVoice: false });
      this.cancelVoiceStream();
    }
  },

  onCancelRecord() {
    this.setData({ isPressActive: false, shouldSendVoice: false });
    this.cancelVoiceStream();
    if (this.data.isRecording) recorderManager.stop();
  },

  cancelVoiceStream() {
    const stream = recorderManager.__echoVoiceStream || null;
    recorderManager.__echoVoiceStream = null;
    if (stream) cancelVoiceStream(stream);
  },

  checkRecordAuth(): Promise<boolean> {
    return new Promise((resolve) => {
      wx.getSetting({
        success: (settings) => {
          if (settings.authSetting['scope.record']) {
            resolve(true);
            return;
          }
          wx.authorize({
            scope: 'scope.record',
            success: () => resolve(true),
            fail: () => {
              wx.showModal({
                title: '需要麦克风权限',
                content: '请在设置中允许录音，才能和 Echo 通话。',
                success: (result) => {
                  if (result.confirm) wx.openSetting();
                },
              });
              resolve(false);
            },
          });
        },
        fail: () => resolve(false),
      });
    });
  },

  async handleVoiceFile(filePath: string) {
    try {
      const userText = (await recognizeVoice(filePath)).trim();
      if (!userText) throw new Error('没有识别到内容');
      await this.requestEchoReply(userText);
    } catch (error) {
      this.handleVoiceError(error);
    }
  },

  async handleStreamingVoice(stream: ActiveVoiceStream, fallbackFilePath: string) {
    try {
      const session = stream.session || (await stream.opening);
      if (stream.canceled) return;
      const userText = (await session.finish()).trim();
      if (!userText) throw new Error('没有识别到内容');
      await this.requestEchoReply(userText);
    } catch (error) {
      console.warn('流式识别失败，尝试整段识别', error);
      cancelVoiceStream(stream);
      if (fallbackFilePath) {
        await this.handleVoiceFile(fallbackFilePath);
      } else {
        this.handleVoiceError(error);
      }
    }
  },

  async requestEchoReply(userText: string) {
    this.setData({ isSending: true, partialText: '' });
    this.setStatus('thinking');
    try {
      const response = await sendMessage(userText, 'call');
      if (!this.data.callActive) return;
      this.setData({ echoCaption: response.reply });
      if (!response.audioUrls.length) throw new Error('语音生成失败');
      this.setStatus('speaking');
      await playVoiceSegments(response.audioUrls, () => this.data.callActive);
      if (this.data.callActive) this.setStatus('idle');
    } catch (error) {
      this.handleVoiceError(error);
    } finally {
      this.setData({ isSending: false });
    }
  },

  handleVoiceError(error: unknown) {
    const requestError = error as { detail?: string; isUnauthorized?: boolean };
    console.error('电话对话失败', error);
    if (requestError.isUnauthorized) {
      clearSession();
      this.endCallResources();
      wx.redirectTo({ url: '/pages/onboarding/onboarding' });
      return;
    }
    this.setStatus('idle');
    wx.showToast({ title: requestError.detail || '刚刚没听清，请再说一次', icon: 'none' });
  },

  onHangup() {
    this.setData({ callActive: false });
    this.endCallResources();
    wx.navigateBack({ delta: 1 });
  },

  endCallResources() {
    if (timerId !== null) {
      clearInterval(timerId);
      timerId = null;
    }
    this.cancelVoiceStream();
    if (this.data.isRecording) {
      this.setData({ shouldSendVoice: false, isPressActive: false });
      recorderManager.stop();
    }
    stopVoice();
    wx.setKeepScreenOn({ keepScreenOn: false });
    if (recorderManager.__echoCallPage === (this as unknown as CallPageController)) {
      recorderManager.__echoCallPage = null;
    }
  },
});
