import {
  getPersona,
  PersonaReplyStyle,
  PersonaSupportMode,
  RelationshipPace,
  updatePersona,
} from '../../utils/api';
import { clearSession, ensureSession } from '../../utils/session';

interface OnboardingError {
  detail?: string;
  isUnauthorized?: boolean;
}

Page({
  data: {
    isLoading: true,
    isSaving: false,
    errorText: '',
    preferredName: '',
    replyStyle: 'natural' as PersonaReplyStyle,
    supportMode: 'balanced' as PersonaSupportMode,
    relationshipPace: 'natural' as RelationshipPace,
    aboutUser: '',
    replyStyleOptions: [
      { value: 'natural', label: '自然', description: '像朋友一样平实' },
      { value: 'concise', label: '简洁', description: '少铺垫，说重点' },
      { value: 'lively', label: '活泼', description: '轻松一点' },
    ],
    supportModeOptions: [
      { value: 'comfort', label: '先陪我', description: '先听感受' },
      { value: 'balanced', label: '看情况', description: '理解和建议平衡' },
      { value: 'advice', label: '给建议', description: '更快说下一步' },
    ],
    relationshipPaceOptions: [
      { value: 'slow', label: '慢慢熟悉', description: '多相处一阵' },
      { value: 'natural', label: '自然发展', description: '跟随互动' },
      { value: 'open', label: '容易熟络', description: '可以快一点' },
    ],
  },

  onLoad() {
    void this.bootstrap();
  },

  async bootstrap(forceLogin = false) {
    this.setData({ isLoading: true, errorText: '' });
    try {
      await ensureSession(forceLogin);
      const preferences = await getPersona();
      if (preferences.onboarding_completed) {
        this.enterEcho();
        return;
      }
      this.setData({ isLoading: false });
    } catch (error) {
      const apiError = error as OnboardingError;
      if (apiError.isUnauthorized && !forceLogin) {
        clearSession();
        await this.bootstrap(true);
        return;
      }
      console.error('首次引导初始化失败', error);
      this.setData({
        isLoading: false,
        errorText: apiError.detail || '暂时无法连接 Echo，请检查网络后重试',
      });
    }
  },

  onRetry() {
    if (this.data.isLoading) return;
    void this.bootstrap(true);
  },

  onNameInput(event: WechatMiniprogram.Input) {
    this.setData({ preferredName: event.detail.value });
  },

  onAboutInput(event: WechatMiniprogram.TextareaInput) {
    this.setData({ aboutUser: event.detail.value });
  },

  onSelect(event: WechatMiniprogram.TouchEvent) {
    const field = String(event.currentTarget.dataset.field || '');
    const value = String(event.currentTarget.dataset.value || '');
    if (field === 'replyStyle') this.setData({ replyStyle: value as PersonaReplyStyle });
    if (field === 'supportMode') this.setData({ supportMode: value as PersonaSupportMode });
    if (field === 'relationshipPace') {
      this.setData({ relationshipPace: value as RelationshipPace });
    }
  },

  async onComplete() {
    if (this.data.isSaving) return;
    const preferredName = this.data.preferredName.trim();
    if (!preferredName) {
      wx.showToast({ title: '先告诉 Echo 怎么称呼你', icon: 'none' });
      return;
    }

    this.setData({ isSaving: true, errorText: '' });
    try {
      await updatePersona({
        preferred_name: preferredName,
        reply_style: this.data.replyStyle,
        reply_length: 'balanced',
        support_mode: this.data.supportMode,
        proactivity: 'balanced',
        avoid_topics: [],
        about_user: this.data.aboutUser.trim() || null,
        relationship_pace: this.data.relationshipPace,
        affection_style: 'contextual',
        enabled: true,
      });
      this.enterEcho();
    } catch (error) {
      const apiError = error as OnboardingError;
      if (apiError.isUnauthorized) clearSession();
      console.error('首次个性化保存失败', error);
      this.setData({
        isSaving: false,
        errorText: apiError.detail || '保存失败，请稍后再试',
      });
    }
  },

  enterEcho() {
    wx.redirectTo({ url: '/pages/chat/chat' });
  },
});
