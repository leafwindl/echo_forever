import {
  clearAdminChatContext,
  getRuntimeSystemPrompt,
  login,
  sendMessage,
  updateRuntimeSystemPrompt,
  USER_ID_STORAGE_KEY,
} from '../../utils/api';
import { appConfig } from '../../utils/env';
import { playVoice } from './chat.audio';
import { createMessage, replaceMessageContent } from './chat.messages';
import type { ChatMode, Message, SitCrop } from './chat.types';
import { recognizeVoice } from './chat.voice';

let recorderManager: WechatMiniprogram.RecorderManager;

const CLIENT_ID_STORAGE_KEY = 'echo_client_id';
const VOICE_REPLY_STORAGE_KEY = 'echo_voice_reply_enabled';
const DEFAULT_ECHO_MESSAGE = '嗨，我是 Echo，很开心认识你。你可以告诉我你希望我怎么称呼你吗？';
const FALLBACK_ECHO_MESSAGE = '嗨，我是 Echo，很高兴认识你～';
const TEMPORARY_ERROR_MESSAGE = '（抱歉，我暂时有点卡，请稍后再试）';

interface ChatPageData {
  messages: Message[];
  inputText: string;
  inputMode: ChatMode;
  voiceReplyEnabled: boolean;
  lastMsgId: string;
  msgIdCounter: number;
  userId: string;
  isRecording: boolean;
  recordStartTime: number;
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

function getInitialVoiceReplyEnabled(): boolean {
  const stored = wx.getStorageSync(VOICE_REPLY_STORAGE_KEY);
  return stored === true;
}

Page({
  data: {
    messages: [] as Message[],
    inputText: '',
    inputMode: 'text' as ChatMode,
    voiceReplyEnabled: getInitialVoiceReplyEnabled(),
    lastMsgId: '',
    msgIdCounter: 0,
    userId: '',
    isRecording: false,
    recordStartTime: 0,
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

  loginWithWechat(clientId: string) {
    wx.login({
      success: async (res) => {
        try {
          const result = await login(res.code, clientId);
          this.setData({ userId: result.user_id });
          wx.setStorageSync(USER_ID_STORAGE_KEY, result.user_id);
          this.addMessage('echo', DEFAULT_ECHO_MESSAGE);
        } catch (error) {
          console.error('登录失败', error);
          this.useFallbackUser(clientId);
        }
      },
      fail: () => this.useFallbackUser(clientId),
    });
  },

  useFallbackUser(clientId: string) {
    this.setData({ userId: clientId });
    wx.setStorageSync(USER_ID_STORAGE_KEY, clientId);
    this.addMessage('echo', FALLBACK_ECHO_MESSAGE);
  },

  onToggleChatExpand() {
    this.setData({
      chatExpanded: !this.data.chatExpanded,
    });
  },

  onToggleInputMode() {
    this.setData({
      inputMode: this.data.inputMode === 'text' ? 'voice' : 'text',
    });
  },

  onToggleVoiceReply() {
    const nextVoiceReplyEnabled = !this.data.voiceReplyEnabled;
    this.setData({ voiceReplyEnabled: nextVoiceReplyEnabled });
    wx.setStorageSync(VOICE_REPLY_STORAGE_KEY, nextVoiceReplyEnabled);
  },

  initRecorderEvents() {
    recorderManager.onStart(() => {
      this.setData({ isRecording: true });
      wx.showToast({ title: '录音中... 松开结束', icon: 'none', duration: 60000 });
    });

    recorderManager.onStop((res) => {
      const shouldUploadVoice = this.data.shouldUploadVoice;
      this.setData({ isRecording: false, shouldUploadVoice: false });
      wx.hideToast();

      if (shouldUploadVoice && res.tempFilePath) {
        this.handleVoiceFile(res.tempFilePath);
      } else if (shouldUploadVoice) {
        wx.showToast({ title: '录音失败', icon: 'none' });
      }
    });

    recorderManager.onError((err) => {
      console.error('录音错误', err);
      this.setData({ isRecording: false, shouldUploadVoice: false });
      wx.hideToast();
      wx.showToast({ title: '录音失败，请重试', icon: 'none' });
    });
  },

  onInput(e: WechatMiniprogram.Input) {
    this.setData({ inputText: e.detail.value });
  },

  onSend() {
    const text = this.data.inputText.trim();
    if (!text) return;

    this.setData({ inputText: '' });
    this.sendChatMessage(text, 'text');
  },

  async sendChatMessage(text: string, inputMode: ChatMode) {
    const userId = this.data.userId || getOrCreateClientId();
    this.addMessage('user', text);
    const pendingMessageId = this.addTypingMessage();

    try {
      const response = await sendMessage(userId, text, {
        inputType: inputMode,
        voiceReplyEnabled: this.data.voiceReplyEnabled,
      });
      this.updateMessage(pendingMessageId, response.reply || '（我刚刚没组织好语言，可以再说一次吗？）');

      if (this.data.voiceReplyEnabled && response.audioUrl) {
        playVoice(response.audioUrl);
      }
    } catch (error) {
      console.error('发送消息失败', error);
      this.updateMessage(pendingMessageId, TEMPORARY_ERROR_MESSAGE);
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
    this.setData({ messages: [] });
    wx.showToast({ title: '上下文已清除', icon: 'none' });
  },

  onOpenMemoryPage() {
    wx.navigateTo({ url: '/pages/memory/memory' });
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
    const userId = this.data.userId || getOrCreateClientId();
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
    const auth = await this.checkRecordAuth();
    if (!auth) return;

    this.setData({
      shouldUploadVoice: true,
      recordStartTime: Date.now(),
    });

    recorderManager.start({
      duration: 60000,
      sampleRate: 16000,
      numberOfChannels: 1,
      format: 'mp3',
    });
  },

  onStopRecord() {
    if (!this.data.isRecording) return;
    recorderManager.stop();
  },

  onCancelRecord() {
    if (!this.data.isRecording) return;
    this.setData({ shouldUploadVoice: false });
    recorderManager.stop();
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
      });
    });
  },

  async handleVoiceFile(filePath: string) {
    wx.showLoading({ title: '识别中...' });
    try {
      const userText = (await recognizeVoice(filePath)).trim();
      wx.hideLoading();

      if (!userText) {
        wx.showToast({ title: '未听清，请重试', icon: 'none' });
        return;
      }

      await this.sendChatMessage(userText, 'voice');
    } catch (error) {
      wx.hideLoading();
      console.error('语音识别失败', error);
      wx.showToast({ title: '语音识别失败', icon: 'none' });
    }
  },
});
