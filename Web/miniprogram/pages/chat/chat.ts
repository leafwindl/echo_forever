import { clearChatContext, getPersona, sendMessage } from '../../utils/api';
import { clearSession, ensureSession } from '../../utils/session';
import { createMessage, replaceMessageContent } from './chat.messages';
import type { Message, RequestInProgressError } from './chat.types';

interface ChatPageData {
  messages: Message[];
  inputText: string;
  displayName: string;
  isReady: boolean;
  isBootstrapping: boolean;
  isSending: boolean;
  errorText: string;
  lastMsgId: string;
  msgIdCounter: number;
}

const TEMPORARY_ERROR_MESSAGE = '（我刚刚有点卡住了，等一下再和我说一次好吗？）';

Page({
  data: {
    messages: [] as Message[],
    inputText: '',
    displayName: '',
    isReady: false,
    isBootstrapping: true,
    isSending: false,
    errorText: '',
    lastMsgId: '',
    msgIdCounter: 0,
  } as ChatPageData,

  onLoad() {
    void this.bootstrap();
  },

  onShow() {
    if (this.data.isReady) void this.refreshPreferences();
  },

  async bootstrap(forceLogin = false) {
    this.setData({ isBootstrapping: true, errorText: '' });
    try {
      await ensureSession(forceLogin);
      const preferences = await getPersona();
      if (!preferences.onboarding_completed) {
        wx.reLaunch({ url: '/pages/onboarding/onboarding' });
        return;
      }

      const displayName = (preferences.preferred_name || '').trim();
      this.setData({
        displayName,
        isReady: true,
        isBootstrapping: false,
        errorText: '',
      });
      if (!this.data.messages.length) {
        const greeting = displayName
          ? `嗨，${displayName}。我在呢，今天想聊点什么？`
          : '嗨，我在呢。今天想聊点什么？';
        this.addMessage('echo', greeting);
      }
    } catch (error) {
      const requestError = error as RequestInProgressError;
      if (requestError.isUnauthorized && !forceLogin) {
        clearSession();
        await this.bootstrap(true);
        return;
      }
      console.error('聊天页初始化失败', error);
      this.setData({
        isReady: false,
        isBootstrapping: false,
        errorText: requestError.detail || '暂时无法连接 Echo，请稍后重试',
      });
    }
  },

  async refreshPreferences() {
    try {
      const preferences = await getPersona();
      if (!preferences.onboarding_completed) {
        wx.reLaunch({ url: '/pages/onboarding/onboarding' });
        return;
      }
      this.setData({ displayName: (preferences.preferred_name || '').trim() });
    } catch (error) {
      const requestError = error as RequestInProgressError;
      if (requestError.isUnauthorized) this.expireSession();
    }
  },

  onRetry() {
    if (this.data.isBootstrapping) return;
    void this.bootstrap(true);
  },

  onInput(event: WechatMiniprogram.Input) {
    this.setData({ inputText: event.detail.value });
  },

  onSend() {
    if (!this.data.isReady || this.data.isSending) return;
    const text = this.data.inputText.trim();
    if (!text) return;
    this.setData({ inputText: '' });
    void this.sendChatMessage(text);
  },

  async sendChatMessage(text: string) {
    this.setData({ isSending: true });
    this.addMessage('user', text);
    const pendingMessageId = this.addMessage('echo', '', true);

    try {
      const response = await sendMessage(text, 'chat');
      this.updateMessage(
        pendingMessageId,
        response.reply || '（我刚刚没组织好语言，可以再说一次吗？）',
      );
    } catch (error) {
      console.error('发送消息失败', error);
      const requestError = error as RequestInProgressError;
      if (requestError.isUnauthorized) {
        this.updateMessage(pendingMessageId, '（登录已失效，正在重新连接。）');
        this.expireSession();
      } else {
        this.updateMessage(
          pendingMessageId,
          requestError.isRequestInProgress || requestError.isRateLimited
            ? requestError.detail || '上一条消息还在处理中，请稍后再试。'
            : TEMPORARY_ERROR_MESSAGE,
        );
      }
    } finally {
      this.setData({ isSending: false });
    }
  },

  addMessage(sender: Message['sender'], content: string, isTyping = false): number {
    const id = this.data.msgIdCounter + 1;
    this.setData({
      messages: [...this.data.messages, createMessage(id, sender, content, isTyping)],
      msgIdCounter: id,
      lastMsgId: `msg-${id}`,
    });
    return id;
  },

  updateMessage(messageId: number, content: string) {
    this.setData({
      messages: replaceMessageContent(this.data.messages, messageId, content),
      lastMsgId: `msg-${messageId}`,
    });
  },

  onOpenCall() {
    if (!this.data.isReady || this.data.isSending) return;
    wx.navigateTo({ url: '/pages/call/call' });
  },

  onOpenTools() {
    if (!this.data.isReady) return;
    wx.showActionSheet({
      itemList: ['个性化设置', '记忆管理', '清除聊天上下文'],
      success: (result) => {
        if (result.tapIndex === 0) wx.navigateTo({ url: '/pages/persona/persona' });
        if (result.tapIndex === 1) wx.navigateTo({ url: '/pages/memory/memory' });
        if (result.tapIndex === 2) this.confirmClearContext();
      },
    });
  },

  confirmClearContext() {
    if (this.data.isSending) return;
    wx.showModal({
      title: '清除聊天上下文',
      content: '会清除聊天记录和会话摘要，长期记忆仍会保留。',
      confirmText: '清除',
      confirmColor: '#d95762',
      success: (result) => {
        if (result.confirm) void this.clearContext();
      },
    });
  },

  async clearContext() {
    wx.showLoading({ title: '清除中' });
    try {
      await clearChatContext();
      wx.hideLoading();
      this.setData({ messages: [], msgIdCounter: 0, lastMsgId: '' });
      const greeting = this.data.displayName
        ? `好啦，${this.data.displayName}。我们重新聊。`
        : '好啦，我们重新聊。';
      this.addMessage('echo', greeting);
      wx.showToast({ title: '已清除', icon: 'success' });
    } catch (error) {
      wx.hideLoading();
      const requestError = error as RequestInProgressError;
      if (requestError.isUnauthorized) this.expireSession();
      else wx.showToast({ title: '清除失败，请重试', icon: 'none' });
    }
  },

  expireSession() {
    clearSession();
    this.setData({ isReady: false });
    wx.reLaunch({ url: '/pages/onboarding/onboarding' });
  },
});
