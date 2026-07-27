import {
  AffectionStyle,
  getPersona,
  PersonaProactivity,
  PersonaReplyLength,
  PersonaReplyStyle,
  PersonaSupportMode,
  RelationshipPace,
  resetPersona,
  resetRelationship,
  updatePersona,
  UserPreferences,
} from '../../utils/api';
import { clearSession } from '../../utils/session';

interface ChoiceOption<T extends string> {
  value: T;
  label: string;
  description: string;
}

interface PresetTopicOption {
  label: string;
  selected: boolean;
}

interface PersonaPageData {
  preferredName: string;
  replyStyle: PersonaReplyStyle;
  replyLength: PersonaReplyLength;
  supportMode: PersonaSupportMode;
  proactivity: PersonaProactivity;
  relationshipPace: RelationshipPace;
  affectionStyle: AffectionStyle;
  avoidTopics: string[];
  aboutUser: string;
  enabled: boolean;
  isCustomized: boolean;
  isLoading: boolean;
  isSaving: boolean;
  errorText: string;
  customTopic: string;
  replyStyleOptions: ChoiceOption<PersonaReplyStyle>[];
  replyLengthOptions: ChoiceOption<PersonaReplyLength>[];
  supportModeOptions: ChoiceOption<PersonaSupportMode>[];
  proactivityOptions: ChoiceOption<PersonaProactivity>[];
  relationshipPaceOptions: ChoiceOption<RelationshipPace>[];
  affectionStyleOptions: ChoiceOption<AffectionStyle>[];
  presetTopics: PresetTopicOption[];
  customAvoidTopics: string[];
}

interface PersonaApiError {
  detail?: string;
  isUnauthorized?: boolean;
}

const DEFAULT_DATA = {
  preferredName: '',
  replyStyle: 'natural' as PersonaReplyStyle,
  replyLength: 'balanced' as PersonaReplyLength,
  supportMode: 'balanced' as PersonaSupportMode,
  proactivity: 'balanced' as PersonaProactivity,
  relationshipPace: 'natural' as RelationshipPace,
  affectionStyle: 'contextual' as AffectionStyle,
  avoidTopics: [] as string[],
  aboutUser: '',
  enabled: true,
  isCustomized: false,
};

const PRESET_TOPIC_LABELS = ['医疗建议', '感情分析', '家庭话题'];

function buildTopicView(avoidTopics: string[]) {
  return {
    presetTopics: PRESET_TOPIC_LABELS.map((label) => ({
      label,
      selected: avoidTopics.includes(label),
    })),
    customAvoidTopics: avoidTopics.filter((topic) => !PRESET_TOPIC_LABELS.includes(topic)),
  };
}

Page({
  data: {
    ...DEFAULT_DATA,
    isLoading: true,
    isSaving: false,
    errorText: '',
    customTopic: '',
    replyStyleOptions: [
      { value: 'natural', label: '自然', description: '像朋友一样' },
      { value: 'concise', label: '简洁', description: '重点先说' },
      { value: 'lively', label: '活泼', description: '轻松不过火' },
    ],
    replyLengthOptions: [
      { value: 'short', label: '短一些', description: '通常 1–2 句' },
      { value: 'balanced', label: '适中', description: '按内容调整' },
      { value: 'detailed', label: '详细', description: '结论后补充' },
    ],
    supportModeOptions: [
      { value: 'comfort', label: '先陪伴', description: '先理解感受' },
      { value: 'balanced', label: '平衡', description: '理解与建议兼顾' },
      { value: 'advice', label: '多建议', description: '优先给下一步' },
    ],
    proactivityOptions: [
      { value: 'quiet', label: '安静', description: '少追问' },
      { value: 'balanced', label: '适中', description: '需要时追问' },
      { value: 'active', label: '主动', description: '适当延伸话题' },
    ],
    relationshipPaceOptions: [
      { value: 'slow', label: '慢一些', description: '多相处一阵' },
      { value: 'natural', label: '自然', description: '跟随互动' },
      { value: 'open', label: '开放', description: '可以快一点' },
    ],
    affectionStyleOptions: [
      { value: 'restrained', label: '克制', description: '保持分寸' },
      { value: 'contextual', label: '看语境', description: '合适时表达' },
      { value: 'expressive', label: '更有温度', description: '更明显地在意' },
    ],
    ...buildTopicView([]),
  } as PersonaPageData,

  onLoad() {
    this.loadPersona();
  },

  applyPersona(persona: UserPreferences) {
    this.setData({
      preferredName: persona.preferred_name || '',
      replyStyle: persona.reply_style,
      replyLength: persona.reply_length,
      supportMode: persona.support_mode,
      proactivity: persona.proactivity,
      relationshipPace: persona.relationship_pace,
      affectionStyle: persona.affection_style,
      avoidTopics: Array.isArray(persona.avoid_topics) ? persona.avoid_topics : [],
      ...buildTopicView(Array.isArray(persona.avoid_topics) ? persona.avoid_topics : []),
      aboutUser: persona.about_user || '',
      enabled: persona.enabled,
      isCustomized: persona.is_customized,
      isLoading: false,
      errorText: '',
    });
  },

  async loadPersona() {
    this.setData({ isLoading: true, errorText: '' });
    try {
      this.applyPersona(await getPersona());
    } catch (error) {
      this.handleApiError(error, '个性化设置加载失败');
    }
  },

  handleApiError(error: unknown, fallbackMessage: string) {
    const apiError = error as PersonaApiError;
    console.error(fallbackMessage, error);
    if (apiError.isUnauthorized) {
      clearSession();
      wx.reLaunch({ url: '/pages/onboarding/onboarding' });
      return;
    }
    this.setData({
      isLoading: false,
      isSaving: false,
      errorText: fallbackMessage,
    });
  },

  onEnabledChange(e: WechatMiniprogram.SwitchChange) {
    this.setData({ enabled: e.detail.value });
  },

  onPreferredNameInput(e: WechatMiniprogram.Input) {
    this.setData({ preferredName: e.detail.value });
  },

  onAboutUserInput(e: WechatMiniprogram.TextareaInput) {
    this.setData({ aboutUser: e.detail.value });
  },

  onCustomTopicInput(e: WechatMiniprogram.Input) {
    this.setData({ customTopic: e.detail.value });
  },

  onSelectChoice(e: WechatMiniprogram.TouchEvent) {
    const field = String(e.currentTarget.dataset.field || '');
    const value = String(e.currentTarget.dataset.value || '');
    if (field === 'replyStyle') {
      this.setData({ replyStyle: value as PersonaReplyStyle });
    } else if (field === 'replyLength') {
      this.setData({ replyLength: value as PersonaReplyLength });
    } else if (field === 'supportMode') {
      this.setData({ supportMode: value as PersonaSupportMode });
    } else if (field === 'proactivity') {
      this.setData({ proactivity: value as PersonaProactivity });
    } else if (field === 'relationshipPace') {
      this.setData({ relationshipPace: value as RelationshipPace });
    } else if (field === 'affectionStyle') {
      this.setData({ affectionStyle: value as AffectionStyle });
    }
  },

  onToggleTopic(e: WechatMiniprogram.TouchEvent) {
    const topic = String(e.currentTarget.dataset.topic || '').trim();
    if (!topic) return;

    const existingIndex = this.data.avoidTopics.indexOf(topic);
    if (existingIndex >= 0) {
      const avoidTopics = this.data.avoidTopics.filter((item) => item !== topic);
      this.setData({ avoidTopics, ...buildTopicView(avoidTopics) });
      return;
    }
    this.addTopic(topic);
  },

  onAddCustomTopic() {
    const topic = this.data.customTopic.trim();
    if (!topic) return;
    if (this.addTopic(topic)) {
      this.setData({ customTopic: '' });
    }
  },

  addTopic(topic: string): boolean {
    if (topic.length > 40) {
      wx.showToast({ title: '单个话题最多 40 个字', icon: 'none' });
      return false;
    }
    if (this.data.avoidTopics.includes(topic)) {
      wx.showToast({ title: '这个话题已经添加', icon: 'none' });
      return false;
    }
    if (this.data.avoidTopics.length >= 5) {
      wx.showToast({ title: '最多添加 5 个话题', icon: 'none' });
      return false;
    }
    const avoidTopics = [...this.data.avoidTopics, topic];
    this.setData({ avoidTopics, ...buildTopicView(avoidTopics) });
    return true;
  },

  async onSave() {
    if (this.data.isSaving) return;
    this.setData({ isSaving: true, errorText: '' });
    try {
      const persona = await updatePersona({
        preferred_name: this.data.preferredName.trim() || null,
        reply_style: this.data.replyStyle,
        reply_length: this.data.replyLength,
        support_mode: this.data.supportMode,
        proactivity: this.data.proactivity,
        relationship_pace: this.data.relationshipPace,
        affection_style: this.data.affectionStyle,
        avoid_topics: this.data.avoidTopics,
        about_user: this.data.aboutUser.trim() || null,
        enabled: this.data.enabled,
      });
      this.applyPersona(persona);
      this.setData({ isSaving: false });
      wx.showToast({ title: '设置已保存', icon: 'success' });
    } catch (error) {
      this.handleApiError(error, '保存失败，请稍后重试');
    }
  },

  onReset() {
    if (this.data.isSaving) return;
    wx.showModal({
      title: '恢复默认设置',
      content: '只会重置这里的个性化偏好，不会删除长期记忆或聊天记录。',
      confirmText: '恢复默认',
      confirmColor: '#E04F5F',
      success: async (result) => {
        if (!result.confirm) return;
        this.setData({ isSaving: true, errorText: '' });
        try {
          const persona = await resetPersona();
          this.applyPersona(persona);
          this.setData({ customTopic: '', isSaving: false });
          wx.showToast({ title: '已恢复默认', icon: 'success' });
        } catch (error) {
          this.handleApiError(error, '恢复默认失败，请稍后重试');
        }
      },
    });
  },

  onResetRelationship() {
    if (this.data.isSaving) return;
    wx.showModal({
      title: '重置关系进度',
      content: 'Echo 会从初识阶段重新建立熟悉感。个性化设置、长期记忆和聊天记录不会被删除。',
      confirmText: '确认重置',
      confirmColor: '#E04F5F',
      success: async (result) => {
        if (!result.confirm) return;
        this.setData({ isSaving: true, errorText: '' });
        try {
          await resetRelationship();
          this.setData({ isSaving: false });
          wx.showToast({ title: '关系进度已重置', icon: 'success' });
        } catch (error) {
          this.handleApiError(error, '关系进度重置失败');
        }
      },
    });
  },
});
