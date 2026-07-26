import {
  clearAdminChatContext,
  clearChatContext,
  ACCESS_TOKEN_STORAGE_KEY,
  getRuntimeSystemPrompt,
  login,
  sendMessage,
  updateRuntimeSystemPrompt,
  USER_ID_STORAGE_KEY,
} from '../../utils/api';
import { appConfig } from '../../utils/env';
import { playVoiceSegments, stopVoice } from './chat.audio';
import { createMessage, replaceMessageContent } from './chat.messages';
import type { ChatInputType } from '../../utils/api';
import type { Message, RequestInProgressError, SitCrop } from './chat.types';
import { recognizeVoice } from './chat.voice';
import { openVoiceStream } from './chat.voice-stream';
import type { VoiceStreamSession } from './chat.voice-stream';

let recorderManager: WechatMiniprogram.RecorderManager;

interface ActiveVoiceStream {
  opening: Promise<VoiceStreamSession>;
  session: VoiceStreamSession | null;
  bufferedFrames: ArrayBuffer[];
  bufferedBytes: number;
  canceled: boolean;
}

let activeVoiceStream: ActiveVoiceStream | null = null;
const STREAM_FRAME_BUFFER_MAX_BYTES = 1024 * 1024;

function cancelVoiceStreamState(state: ActiveVoiceStream): void {
  if (state.canceled) return;
  state.canceled = true;
  state.bufferedFrames = [];
  state.bufferedBytes = 0;
  state.session?.cancel();
  void state.opening.then((session) => session.cancel()).catch(() => undefined);
}

const CLIENT_ID_STORAGE_KEY = 'echo_client_id';
const DEFAULT_ECHO_MESSAGE = '嗨，我是 Echo，很开心认识你。你可以告诉我你希望我怎么称呼你吗？';
const TEMPORARY_ERROR_MESSAGE = '（抱歉，我暂时有点卡，请稍后再试）';

type PhoneStatus = 'idle' | 'recording' | 'recognizing' | 'thinking' | 'speaking';

interface ChatPageData {
  messages: Message[];
  inputText: string;
  phoneMode: boolean;
  phoneStatus: PhoneStatus;
  phoneStatusLabel: string;
  isLoggingIn: boolean;
  loginErrorText: string;
  isSending: boolean;
  lastMsgId: string;
  msgIdCounter: number;
  userId: string;
  isRecording: boolean;
  isRecordPressActive: boolean;
  shouldUploadVoice: boolean;
  chatExpanded: boolean;
  adminDebugEnabled: boolean;
  adminDebugVisible: boolean;
  adminPromptText: string;
  adminPromptSource: string;
  adminPromptLoading: boolean;
  sitCrop: SitCrop;
}

function getOrCreateClientId(): string {
  // 本地稳定匿名 ID 用于登录失败兜底，避免不同设备共用同一份记忆。
  const stored = wx.getStorageSync(CLIENT_ID_STORAGE_KEY);
  if (typeof stored === 'string' && stored) {
    return stored;
  }

  const clientId = `anon_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
  wx.setStorageSync(CLIENT_ID_STORAGE_KEY, clientId);
  return clientId;
}

Page({
  data: {
    messages: [] as Message[],
    inputText: '',
    phoneMode: false,
    phoneStatus: 'idle' as PhoneStatus,
    phoneStatusLabel: '按住说话',
    isLoggingIn: true,
    loginErrorText: '',
    isSending: false,
    lastMsgId: '',
    msgIdCounter: 0,
    userId: '',
    isRecording: false,
    isRecordPressActive: false,
    shouldUploadVoice: false,
    chatExpanded: false,
    adminDebugEnabled: appConfig.adminDebugEnabled,
    adminDebugVisible: false,
    adminPromptText: '',
    adminPromptSource: '',
    adminPromptLoading: false,
    sitCrop: {
      cropWidth: '750rpx',
      cropHeight: '500rpx',
      cropOffsetX: '0rpx',
      cropOffsetY: '0rpx',
      imageWidth: '800rpx',
      imageLeft: '-25rpx',
      imageTop: '-50rpx',
    },
  } as ChatPageData,

  onLoad() {
    const clientId = getOrCreateClientId();
    this.loginWithWechat(clientId);

    recorderManager = wx.getRecorderManager();
    this.initRecorderEvents();
  },

  onUnload() {
    this.cancelStreamingVoiceSession();
    if (this.data.isRecording) {
      this.setData({ shouldUploadVoice: false });
      recorderManager.stop();
    }
    stopVoice();
  },

  loginWithWechat(clientId: string) {
    this.setData({ isLoggingIn: true, loginErrorText: '', userId: '' });
    wx.login({
      success: async (res) => {
        if (!res.code) {
          this.handleLoginFailure('微信未返回登录凭证');
          return;
        }
        try {
          const result = await login(res.code, clientId);
          this.setData({
            userId: result.user_id,
            isLoggingIn: false,
            loginErrorText: '',
          });
          wx.setStorageSync(USER_ID_STORAGE_KEY, result.user_id);
          this.addMessage('echo', DEFAULT_ECHO_MESSAGE);
        } catch (error) {
          console.error('登录失败', error);
          this.handleLoginFailure('登录失败，请检查网络后重试');
        }
      },
      fail: () => this.handleLoginFailure('微信登录失败，请稍后重试'),
    });
  },

  handleLoginFailure(message: string) {
    wx.removeStorageSync(USER_ID_STORAGE_KEY);
    wx.removeStorageSync(ACCESS_TOKEN_STORAGE_KEY);
    this.setData({
      userId: '',
      isLoggingIn: false,
      loginErrorText: message,
    });
  },

  onRetryLogin() {
    if (this.data.isLoggingIn) return;
    this.loginWithWechat(getOrCreateClientId());
  },

  onToggleChatExpand() {
    this.setData({
      chatExpanded: !this.data.chatExpanded,
    });
  },

  onTogglePhoneMode() {
    if (!this.data.phoneMode && this.data.isSending) return;
    if (!this.data.userId) {
      wx.showToast({ title: '请先完成登录', icon: 'none' });
      return;
    }

    if (this.data.phoneMode) {
      this.cancelStreamingVoiceSession();
      if (this.data.isRecording) {
        this.setData({ shouldUploadVoice: false, isRecordPressActive: false });
        recorderManager.stop();
      }
      stopVoice();
      this.setData({
        phoneMode: false,
        phoneStatus: 'idle',
        phoneStatusLabel: '按住说话',
      });
      return;
    }

    this.setData({
      phoneMode: true,
      phoneStatus: 'idle',
      phoneStatusLabel: '按住说话',
    });
  },

  setPhoneStatus(status: PhoneStatus) {
    const statusLabels: Record<PhoneStatus, string> = {
      idle: '按住说话',
      recording: '松开发送',
      recognizing: '正在识别',
      thinking: 'Echo 正在思考',
      speaking: 'Echo 正在说话',
    };
    this.setData({ phoneStatus: status, phoneStatusLabel: statusLabels[status] });
  },

  initRecorderEvents() {
    recorderManager.onStart(() => {
      this.setData({ isRecording: true });
      if (!this.data.isRecordPressActive) {
        this.setData({ shouldUploadVoice: false });
        this.cancelStreamingVoiceSession();
        recorderManager.stop();
        return;
      }
      this.setPhoneStatus('recording');
      wx.vibrateShort({ type: 'light' });
    });

    recorderManager.onStop((res) => {
      const shouldUploadVoice = this.data.shouldUploadVoice;
      const streamState = activeVoiceStream;
      activeVoiceStream = null;
      this.setData({ isRecording: false, isRecordPressActive: false, shouldUploadVoice: false });
      wx.hideToast();

      if (shouldUploadVoice && streamState) {
        this.setPhoneStatus('recognizing');
        void this.handleStreamingVoice(streamState, res.tempFilePath || '');
      } else if (shouldUploadVoice && res.tempFilePath) {
        this.setPhoneStatus('recognizing');
        void this.handleVoiceFile(res.tempFilePath);
      } else if (shouldUploadVoice) {
        this.setPhoneStatus('idle');
        wx.showToast({ title: '录音失败', icon: 'none' });
      } else {
        if (streamState) cancelVoiceStreamState(streamState);
        this.setPhoneStatus('idle');
      }
    });

    recorderManager.onError((err) => {
      this.cancelStreamingVoiceSession();
      console.error('录音错误', err);
      this.setData({ isRecording: false, isRecordPressActive: false, shouldUploadVoice: false });
      this.setPhoneStatus('idle');
      wx.hideToast();
      wx.showToast({ title: '录音失败，请重试', icon: 'none' });
    });

    recorderManager.onFrameRecorded((res) => {
      const streamState = activeVoiceStream;
      if (!streamState || streamState.canceled) return;
      if (streamState.session) {
        streamState.session.sendFrame(res.frameBuffer);
        return;
      }
      if (
        streamState.bufferedBytes + res.frameBuffer.byteLength <=
        STREAM_FRAME_BUFFER_MAX_BYTES
      ) {
        streamState.bufferedFrames.push(res.frameBuffer);
        streamState.bufferedBytes += res.frameBuffer.byteLength;
      }
    });
  },

  onInput(e: WechatMiniprogram.Input) {
    this.setData({ inputText: e.detail.value });
  },

  onSend() {
    if (this.data.isSending) return;

    const text = this.data.inputText.trim();
    if (!text) return;

    this.setData({ inputText: '' });
    this.sendChatMessage(text, 'text');
  },

  async sendChatMessage(text: string, inputType: ChatInputType) {
    if (this.data.isSending) return;

    const userId = this.data.userId;
    if (!userId) {
      wx.showToast({ title: '请先完成登录', icon: 'none' });
      return;
    }
    const phoneReplyEnabled = this.data.phoneMode && inputType === 'voice';
    this.setData({ isSending: true });
    if (phoneReplyEnabled) {
      this.setPhoneStatus('thinking');
    }
    this.addMessage('user', text);
    const pendingMessageId = this.addTypingMessage();

    try {
      const response = await sendMessage(userId, text, {
        inputType,
        phoneMode: phoneReplyEnabled,
      });
      this.updateMessage(pendingMessageId, response.reply || '（我刚刚没组织好语言，可以再说一次吗？）');

      const audioUrls = response.audioUrls.length
        ? response.audioUrls
        : response.audioUrl
        ? [response.audioUrl]
        : [];
      if (phoneReplyEnabled && this.data.phoneMode && audioUrls.length) {
        this.setPhoneStatus('speaking');
        try {
          await playVoiceSegments(audioUrls, () => this.data.phoneMode);
        } catch (error) {
          console.error('电话模式播放失败', error);
          if (this.data.phoneMode) {
            wx.showToast({ title: '语音播放失败，仍可继续说话', icon: 'none' });
          }
        } finally {
          if (this.data.phoneMode) {
            this.setPhoneStatus('idle');
          }
        }
      }
    } catch (error) {
      console.error('发送消息失败', error);
      const requestError = error as RequestInProgressError;
      if (requestError.isUnauthorized) {
        this.handleLoginFailure('登录已失效，请重新登录');
      }
      this.updateMessage(
        pendingMessageId,
        requestError.isUnauthorized
          ? '（登录已失效，请重新登录后再试）'
          : requestError.isRequestInProgress || requestError.isRateLimited
          ? (requestError.detail || '上一条消息还在处理中，请稍后再试。')
          : TEMPORARY_ERROR_MESSAGE,
      );
    } finally {
      if (phoneReplyEnabled && this.data.phoneMode && this.data.phoneStatus !== 'idle') {
        this.setPhoneStatus('idle');
      }
      this.setData({ isSending: false });
    }
  },

  addMessage(sender: 'user' | 'echo', content: string, isTyping = false): number {
    const id = this.data.msgIdCounter + 1;
    const messages = [...this.data.messages, createMessage(id, sender, content, isTyping)];
    this.setData({
      messages,
      msgIdCounter: id,
      lastMsgId: `msg-${id}`,
    });
    return id;
  },

  addTypingMessage(): number {
    return this.addMessage('echo', '', true);
  },

  updateMessage(messageId: number, content: string) {
    this.setData({
      messages: replaceMessageContent(this.data.messages, messageId, content),
      lastMsgId: `msg-${messageId}`,
    });
  },

  onClearContext() {
    if (!this.data.userId || this.data.isSending) return;

    wx.showModal({
      title: '清除聊天上下文',
      content: '将删除服务器中的聊天记录和会话摘要，但不会删除长期记忆。',
      confirmText: '清除',
      confirmColor: '#E04F5F',
      success: async (modalResult) => {
        if (!modalResult.confirm) return;
        wx.showLoading({ title: '清除中...' });
        try {
          const result = await clearChatContext();
          wx.hideLoading();
          this.setData({ messages: [] });
          wx.showToast({
            title: `已清除${result.deletedMessages}条消息`,
            icon: 'none',
          });
        } catch (error) {
          const requestError = error as RequestInProgressError;
          if (requestError.isUnauthorized) {
            this.handleLoginFailure('登录已失效，请重新登录');
          }
          wx.hideLoading();
          wx.showToast({ title: '清除失败，请重试', icon: 'none' });
        }
      },
    });
  },

  onOpenMemoryPage() {
    if (!this.data.userId) {
      wx.showToast({ title: '请先完成登录', icon: 'none' });
      return;
    }
    wx.navigateTo({ url: '/pages/memory/memory' });
  },

  onOpenPersonaPage() {
    if (!this.data.userId) {
      wx.showToast({ title: '请先完成登录', icon: 'none' });
      return;
    }
    wx.navigateTo({ url: '/pages/persona/persona' });
  },

  async onOpenAdminDebug() {
    if (!appConfig.adminDebugToken) {
      wx.showToast({ title: '调试 token 未配置', icon: 'none' });
      return;
    }

    this.setData({
      adminDebugVisible: true,
      adminPromptLoading: true,
    });
    try {
      const result = await getRuntimeSystemPrompt();
      this.setData({
        adminPromptText: result.prompt,
        adminPromptSource: result.source,
      });
    } catch (error) {
      console.error('加载提示词失败', error);
      wx.showToast({ title: '加载提示词失败', icon: 'none' });
    } finally {
      this.setData({ adminPromptLoading: false });
    }
  },

  onCloseAdminDebug() {
    this.setData({ adminDebugVisible: false });
  },

  onAdminPromptInput(e: WechatMiniprogram.TextareaInput) {
    this.setData({ adminPromptText: e.detail.value });
  },

  async onSaveAdminPrompt() {
    const prompt = this.data.adminPromptText.trim();
    if (!prompt) {
      wx.showToast({ title: '提示词不能为空', icon: 'none' });
      return;
    }

    this.setData({ adminPromptLoading: true });
    try {
      const result = await updateRuntimeSystemPrompt(prompt);
      this.setData({
        adminPromptText: result.prompt,
        adminPromptSource: result.source,
      });
      wx.showToast({ title: '提示词已保存', icon: 'none' });
    } catch (error) {
      console.error('保存提示词失败', error);
      wx.showToast({ title: '保存提示词失败', icon: 'none' });
    } finally {
      this.setData({ adminPromptLoading: false });
    }
  },

  async onClearAdminChatContext() {
    const userId = this.data.userId;
    if (!userId) return;
    this.setData({ adminPromptLoading: true });
    try {
      const result = await clearAdminChatContext(userId);
      this.setData({ messages: [] });
      wx.showToast({
        title: `已清空${result.deletedMessages}条消息`,
        icon: 'none',
      });
    } catch (error) {
      console.error('清空聊天上下文失败', error);
      wx.showToast({ title: '清空失败', icon: 'none' });
    } finally {
      this.setData({ adminPromptLoading: false });
    }
  },

  async onStartRecord() {
    if (this.data.isSending) return;
    if (!this.data.userId) {
      wx.showToast({ title: '请先完成登录', icon: 'none' });
      return;
    }

    this.setData({ isRecordPressActive: true });
    const auth = await this.checkRecordAuth();
    if (!auth || !this.data.phoneMode || !this.data.isRecordPressActive) {
      this.setData({ isRecordPressActive: false });
      return;
    }

    this.setData({
      shouldUploadVoice: true,
    });

    const streamOpening = openVoiceStream((partialText) => {
      if (!partialText || !this.data.phoneMode || !this.data.isRecording) return;
      this.setData({ phoneStatusLabel: `正在听：${partialText.slice(-18)}` });
    });
    const streamState: ActiveVoiceStream = {
      opening: streamOpening,
      session: null,
      bufferedFrames: [],
      bufferedBytes: 0,
      canceled: false,
    };
    activeVoiceStream = streamState;
    void streamState.opening
      .then((session) => {
        if (streamState.canceled) {
          session.cancel();
          return;
        }
        streamState.session = session;
        for (const frame of streamState.bufferedFrames) {
          session.sendFrame(frame);
        }
        streamState.bufferedFrames = [];
        streamState.bufferedBytes = 0;
      })
      .catch((error) => {
        // Keep the existing full-file Tencent ASR path as an automatic fallback.
        console.warn('流式语音不可用，使用整段识别', error);
        streamState.bufferedFrames = [];
        streamState.bufferedBytes = 0;
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
    this.setData({ isRecordPressActive: false });
    if (!this.data.isRecording) {
      this.setData({ shouldUploadVoice: false });
      this.cancelStreamingVoiceSession();
      return;
    }
    recorderManager.stop();
  },

  onCancelRecord() {
    this.setData({ isRecordPressActive: false });
    this.setData({ shouldUploadVoice: false });
    this.cancelStreamingVoiceSession();
    if (!this.data.isRecording) return;
    recorderManager.stop();
  },

  cancelStreamingVoiceSession() {
    const streamState = activeVoiceStream;
    activeVoiceStream = null;
    if (streamState) cancelVoiceStreamState(streamState);
  },

  checkRecordAuth(): Promise<boolean> {
    return new Promise((resolve) => {
      wx.getSetting({
        success: (res) => {
          if (res.authSetting['scope.record']) {
            resolve(true);
            return;
          }

          wx.authorize({
            scope: 'scope.record',
            success: () => resolve(true),
            fail: () => {
              wx.showModal({
                title: '提示',
                content: '需要录音权限，请在设置中开启',
                success: () => wx.openSetting(),
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

      if (!userText) {
        this.setPhoneStatus('idle');
        wx.showToast({ title: '未听清，请重试', icon: 'none' });
        return;
      }

      if (!this.data.phoneMode) return;
      await this.sendChatMessage(userText, 'voice');
    } catch (error) {
      console.error('语音识别失败', error);
      this.setPhoneStatus('idle');
      const requestError = error as RequestInProgressError & {
        isUploadTooLarge?: boolean;
      };
      if (requestError.isUnauthorized) {
        this.handleLoginFailure('登录已失效，请重新登录');
      }
      wx.showToast({
        title: requestError.detail || '语音识别失败',
        icon: 'none',
      });
    }
  },

  async handleStreamingVoice(streamState: ActiveVoiceStream, fallbackFilePath: string) {
    try {
      const streamSession = streamState.session || (await streamState.opening);
      if (streamState.canceled) return;
      const userText = (await streamSession.finish()).trim();
      if (!userText) {
        throw new Error('未听清，请重说');
      }
      if (!this.data.phoneMode) return;
      await this.sendChatMessage(userText, 'voice');
    } catch (error) {
      console.warn('流式识别失败，尝试整段识别', error);
      cancelVoiceStreamState(streamState);
      if (fallbackFilePath && this.data.phoneMode) {
        await this.handleVoiceFile(fallbackFilePath);
        return;
      }
      this.setPhoneStatus('idle');
      wx.showToast({ title: '语音识别失败，请重试', icon: 'none' });
    }
  },
});
