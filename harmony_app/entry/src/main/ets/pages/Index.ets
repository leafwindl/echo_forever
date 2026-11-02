import promptAction from '@ohos.promptAction';
import common from '@ohos.app.ability.common';
import photoAccessHelper from '@ohos.file.photoAccessHelper';
import dataSharePredicates from '@ohos.data.dataSharePredicates';
import fs from '@ohos.file.fs';
import { ApiClient } from '../common/ApiClient';
import { AppConfig, normalizeMainlandPhone } from '../common/AppConfig';
import { SecureStore } from '../common/SecureStore';
import { EchoRepository, messageFromJson } from '../data/EchoRepository';
import { StudyFocusMedia } from '../data/StudyFocusMedia';
import {
  ApiError,
  AuthSession,
  ChatMessage,
  ChatSchedule,
  DailyLetter,
  MemoryListResult,
  MemoryRecord,
  PersonaProfile,
  PresenceSnapshot,
  PresenceThought,
  ProactiveChatPreferences,
  RelationshipProposal,
  RelationshipState,
  StickerItem
} from '../model/ApiModels';
import { HarmonyNotifications } from '../platform/HarmonyNotifications';
import { HarmonyPush } from '../platform/HarmonyPush';
import { NotificationsPage } from './NotificationsPage';
import { DevicesPage } from './DevicesPage';
import { UpdatePanel } from './UpdatePanel';
import {
  relationshipDirectionLabel,
  relationshipModeLabel,
  relationshipStageLabel,
  relationshipTypeLabel
} from '../model/Relationship';

interface HarmonyFocusSession {
  sessionId: string;
  activityType: string;
  shortGoal: string;
  plannedDurationSeconds: number;
  startedAt: number;
  activeStartedAt?: number;
  elapsedSeconds: number;
  status: string;
  endedAt?: number;
}

interface PersonaDraftPatch {
  preferredName?: string;
  replyStyle?: string;
  replyLength?: string;
  supportMode?: string;
  proactivity?: string;
  avoidTopics?: string[];
  aboutUser?: string;
  relationshipPace?: string;
  affectionStyle?: string;
  enabled?: boolean;
}

interface PersonaChoice {
  value: string;
  label: string;
}

interface ProactivePreferencesPatch {
  enabled?: boolean;
  allowEchoScheduling?: boolean;
  allowSpontaneousChat?: boolean;
  timezone?: string;
  quietStart?: string;
  quietEnd?: string;
  explicitReminderQuietPolicy?: string;
  notificationPreview?: boolean;
}

const HARMONY_FOCUS_ACTIVITIES: string[] = ['背单词', '刷题', '看课', '阅读', '其他'];
const PERSONA_REPLY_STYLES: PersonaChoice[] = [
  { value: 'natural', label: '自然' },
  { value: 'concise', label: '简洁' },
  { value: 'lively', label: '活泼' }
];
const PERSONA_REPLY_LENGTHS: PersonaChoice[] = [
  { value: 'short', label: '短一些' },
  { value: 'balanced', label: '适中' },
  { value: 'detailed', label: '详细' }
];
const PERSONA_SUPPORT_MODES: PersonaChoice[] = [
  { value: 'comfort', label: '先陪伴' },
  { value: 'advice', label: '给建议' },
  { value: 'balanced', label: '平衡' }
];
const PERSONA_PROACTIVITY: PersonaChoice[] = [
  { value: 'quiet', label: '安静' },
  { value: 'balanced', label: '适中' },
  { value: 'active', label: '主动' }
];
const PERSONA_RELATIONSHIP_PACES: PersonaChoice[] = [
  { value: 'slow', label: '慢慢来' },
  { value: 'natural', label: '自然' },
  { value: 'open', label: '开放' }
];
const RELATIONSHIP_MODES: PersonaChoice[] = [
  { value: 'friend', label: '朋友' },
  { value: 'ai_partner', label: 'AI 恋人' }
];
const PERSONA_AFFECTION_STYLES: PersonaChoice[] = [
  { value: 'restrained', label: '克制' },
  { value: 'contextual', label: '看语境' },
  { value: 'expressive', label: '更有温度' }
];
const PERSONA_PRESET_TOPICS: string[] = ['医疗建议', '情感分析', '家庭话题'];

@Entry
@Component
struct Index {
  @State private page: string = 'chat';
  @State private loggedIn: boolean = false;
  @State private initializing: boolean = true;
  @State private chatLoadError: string = '';
  @State private phone: string = '';
  @State private code: string = '';
  @State private verificationId: string = '';
  @State private messages: ChatMessage[] = [];
  @State private input: string = '';
  @State private memories: MemoryRecord[] = [];
  @State private memoryTab: string = 'active';
  @State private memoryCount: number = 0;
  @State private memoryError: string = '';
  @State private memoryDeletingId: string = '';
  @State private memoryConfirmAction: string = '';
  @State private memoryConfirmId: string = '';
  @State private letters: DailyLetter[] = [];
  @State private selectedLetter: DailyLetter = {
    letterId: '',
    localDate: '',
    timezone: '',
    title: '',
    body: '',
    mood: '',
    isRead: true,
    imageUrl: ''
  };
  @State private letterDetailOpen: boolean = false;
  @State private stickers: StickerItem[] = [];
  @State private stickerPickerOpen: boolean = false;
  @State private stickerUploadOpen: boolean = false;
  @State private stickerUploadUri: string = '';
  @State private stickerUploadFilePath: string = '';
  @State private stickerUploadName: string = '';
  @State private stickerUploadType: string = 'image/jpeg';
  @State private uploadDescription: string = '';
  @State private uploadTags: string = '';
  @State private stickerSaving: boolean = false;
  @State private schedules: ChatSchedule[] = [];
  @State private proactivePreferences: ProactiveChatPreferences = {
    enabled: false,
    allowEchoScheduling: true,
    allowSpontaneousChat: false,
    timezone: 'Asia/Shanghai',
    quietStart: '22:30',
    quietEnd: '08:00',
    explicitReminderQuietPolicy: 'defer',
    notificationPreview: false,
    pauseIndefinite: false
  };
  @State private proactiveError: string = '';
  @State private proactiveSaving: boolean = false;
  @State private proactiveTimeDialog: boolean = false;
  @State private quietStartDraft: string = '22:30';
  @State private quietEndDraft: string = '08:00';
  @State private tasksReturnPage: string = 'chat';
  @State private scheduleConfirmId: string = '';
  @State private focusSession: HarmonyFocusSession | undefined = undefined;
  @State private focusResult: HarmonyFocusSession | undefined = undefined;
  @State private focusHistory: HarmonyFocusSession[] = [];
  @State private focusDurationSeconds: number = 25 * 60;
  @State private focusActivityType: string = '背单词';
  @State private focusShortGoal: string = '';
  @State private focusCustomDuration: boolean = false;
  @State private focusCustomMinutes: string = '30';
  @State private focusBusy: boolean = false;
  @State private focusNow: number = Date.now();
  @State private focusHistoryOpen: boolean = false;
  @State private focusVideoFailed: boolean = false;
  @StorageProp('pushEpoch') @Watch('onPushEpoch') private pushEpoch: number = 0;
  @StorageProp('foregroundEpoch') @Watch('onForegroundEpoch') private foregroundEpoch: number = 0;
  @State private personaName: string = '';
  @State private personaProfile: PersonaProfile = {
    preferredName: '',
    replyStyle: 'natural',
    replyLength: 'balanced',
    supportMode: 'balanced',
    proactivity: 'balanced',
    avoidTopics: [],
    aboutUser: '',
    relationshipPace: 'natural',
    affectionStyle: 'contextual',
    enabled: true,
    onboardingCompleted: false
  };
  @State private relationshipState: RelationshipState | undefined = undefined;
  @State private relationshipModeSaving: boolean = false;
  @State private pendingRelationshipProposal: RelationshipProposal | undefined = undefined;
  @State private proposalDialogVisible: boolean = false;
  private proposalShownId: string = '';
  @State private personaError: string = '';
  @State private personaSaving: boolean = false;
  @State private personaCustomTopic: string = '';
  @State private personaConfirmAction: string = '';
  @State private presence: PresenceSnapshot | undefined = undefined;
  @State private presenceError: string = '';
  @State private loading: boolean = false;
  @State private statusText: string = '';
  @State private onboarding: boolean = false;
  @State private onboardingName: string = '';
  @State private chatExpanded: boolean = false;
  @State private menuOpen: boolean = false;
  @State private updateOpen: boolean = false;
  @State private updateLocked: boolean = false;
  private deviceBackHandler?: () => void;
  @State private clearingContext: boolean = false;
  @State private eventConnected: boolean = false;
  @State private echoTyping: boolean = false;
  @State private sending: boolean = false;
  @State private unreadLetters: number = 0;
  @State private nextBeforeId: number = 0;
  @State private hasMoreHistory: boolean = false;
  @State private greetingOverride: string = '';
  private eventGeneration: number = 0;
  private chatScroller: Scroller = new Scroller();
  // Reply groups arrive as one SSE event, but Android reveals their messages
  // in sequence using the server-provided presentation delays.
  private revealGeneration: number = 0;
  private revealChain: Promise<void> = Promise.resolve();
  private activeRevealGroups: number = 0;
  private serverTyping: boolean = false;
  private pendingRevealIds: Set<number> = new Set<number>();
  private focusTimer: number | undefined = undefined;
  private pushRegistrationInFlight: boolean = false;
  private foregroundRecoveryInFlight: boolean = false;

  private store: SecureStore = new SecureStore();
  private repository?: EchoRepository;
  private notifications: HarmonyNotifications = new HarmonyNotifications();
  private focusVideoController: VideoController = new VideoController();
  private focusMedia: StudyFocusMedia = new StudyFocusMedia();

  async aboutToAppear(): Promise<void> {
    try {
      const context = getContext(this) as common.UIAbilityContext;
      await this.store.initialize(context);
      const raw = await this.store.get('session');
      if (raw) {
        let session: AuthSession | undefined;
        try {
          session = JSON.parse(raw) as AuthSession;
        } catch (_) {
          await this.store.remove('session');
        }
        if (session?.accessToken) {
          this.configureRepository(session);
          this.loggedIn = true;
          await this.restoreSession();
        }
      }
    } catch (error) {
      this.statusText = this.describeError(error);
    } finally {
      this.initializing = false;
    }
  }

  aboutToDisappear(): void {
    this.focusStopTimer();
    this.focusVideoStop();
    void this.focusMedia.dispose();
  }

  onBackPress(): boolean {
    if (this.updateOpen) {
      if (!this.updateLocked) this.updateOpen = false;
      return true;
    }
    if (this.menuOpen) { this.menuOpen = false; return true; }
    if (this.page === 'devices' && this.deviceBackHandler) { this.deviceBackHandler(); return true; }
    if (this.page !== 'chat') { this.navigate('chat'); return true; }
    return false;
  }

  private async restoreSession(): Promise<void> {
    if (!this.repository) return;
    try {
      const persona = await this.repository.getPersonaProfile();
      this.personaName = persona.preferredName;
      this.onboardingName = persona.preferredName;
      this.onboarding = !persona.onboardingCompleted;
    } catch (error) {
      this.statusText = this.describeError(error);
      this.onboarding = false;
    }
    // A profile failure must not skip history, and the long-lived SSE stream must not block startup.
    if (this.loggedIn && !this.onboarding) {
          this.page = 'chat';
          await this.loadChat();
          void this.registerHarmonyPushToken();
          if (this.loggedIn) void this.startEvents();
    }
  }

  private configureRepository(session: AuthSession): void {
    this.repository = new EchoRepository(new ApiClient(
      async () => session,
      async (next) => this.store.set('session', JSON.stringify(next)),
      async () => {
        await this.store.remove('session');
        this.loggedIn = false;
      }
    ));
  }

  private async requestCode(): Promise<void> {
    if (!this.phone.trim()) {
      this.toast('请输入手机号');
      return;
    }
    let normalizedPhone: string;
    try {
      normalizedPhone = normalizeMainlandPhone(this.phone);
    } catch (error) {
      this.toast(String(error));
      return;
    }
    this.loading = true;
    try {
      const response = await this.repositoryOrCreate().requestPhoneCode(
        normalizedPhone,
        await this.getDeviceId()
      );
      this.verificationId = String(response.request_id ?? '');
      this.code = '';
      this.statusText = '验证码已发送，请输入 123456';
    } catch (error) {
      this.statusText = `发送失败：${this.describeError(error)}`;
    } finally {
      this.loading = false;
    }
  }

  private async verify(): Promise<void> {
    if (!this.phone.trim() || !this.code.trim()) {
      this.toast('请输入手机号和验证码');
      return;
    }
    let normalizedPhone: string;
    try {
      normalizedPhone = normalizeMainlandPhone(this.phone);
    } catch (error) {
      this.toast(String(error));
      return;
    }
    if (!/^\d{6}$/.test(this.code.trim())) {
      this.toast('请输入 6 位数字验证码');
      return;
    }
    this.loading = true;
    try {
      const deviceId = await this.getDeviceId();
      const session = await this.repositoryOrCreate().verifyCode(
        normalizedPhone,
        this.code.trim(),
        this.verificationId,
        deviceId
      );
      await this.store.set('session', JSON.stringify(session));
      this.configureRepository(session);
      this.loggedIn = true;
      await this.restoreSession();
      void this.registerHarmonyPushToken();
      this.page = this.onboarding ? 'onboarding' : 'chat';
    } catch (error) {
      this.statusText = `登录失败：${this.describeError(error)}`;
    } finally {
      this.loading = false;
    }
  }

  private describeError(error: Object): string {
    if (error instanceof ApiError) {
      const suffix = error.requestId ? `（请求号 ${error.requestId}）` : '';
      return `${error.detail}${suffix}`;
    }
    return String(error);
  }

  private repositoryOrCreate(): EchoRepository {
    if (this.repository) return this.repository;
    return new EchoRepository(new ApiClient(
      async () => undefined,
      async () => {},
      async () => {}
    ));
  }

  private async getDeviceId(): Promise<string> {
    let id = await this.store.get('device_id');
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(id)) {
      id = this.createUuid();
      await this.store.set('device_id', id);
    }
    return id;
  }

  private async registerHarmonyPushToken(): Promise<void> {
    if (!this.repository || !this.loggedIn || this.pushRegistrationInFlight) return;
    this.pushRegistrationInFlight = true;
    try {
      const context = getContext(this) as common.UIAbilityContext;
      await HarmonyPush.initialize(context);
      for (let attempt = 0; attempt < 6; attempt++) {
        const clientId = HarmonyPush.getClientId();
        if (clientId.length > 0) {
          try {
            await this.repository.registerPushToken(await this.getDeviceId(), clientId);
            AppStorage.setOrCreate('pushStatus', 'registered');
          } catch (error) {
            AppStorage.setOrCreate('pushStatus', 'registration_failed');
            AppStorage.setOrCreate('pushError', this.describeError(error));
          }
          return;
        }
        await new Promise<void>((resolve) => setTimeout(resolve, 1000));
      }
      if (HarmonyPush.getClientId().length === 0) {
        AppStorage.setOrCreate('pushStatus', 'unconfigured');
      }
    } finally {
      this.pushRegistrationInFlight = false;
    }
  }

  private onPushEpoch(): void {
    // The SDK can return the CID after the initial login attempt. Retry when
    // the callback updates AppStorage instead of giving up after six seconds.
    if (this.loggedIn && HarmonyPush.getClientId().length > 0) {
      void this.registerHarmonyPushToken();
    }
  }

  private onForegroundEpoch(): void {
    // HarmonyOS may suspend the SSE socket while the ability is in the
    // background. Rehydrate durable chat state and restart the stream when
    // the ability becomes visible again.
    void this.recoverAfterForeground();
  }

  private async recoverAfterForeground(): Promise<void> {
    if (!this.loggedIn || this.initializing || this.onboarding || !this.repository) return;
    if (this.foregroundRecoveryInFlight) return;
    this.foregroundRecoveryInFlight = true;
    try {
      const context = getContext(this) as common.UIAbilityContext;
      await HarmonyPush.initialize(context);
      await this.loadChat();
      if (this.loggedIn && !this.onboarding && this.repository) {
        void this.registerHarmonyPushToken();
        // Invalidate callbacks and retry timers belonging to the suspended
        // stream before creating the replacement connection.
        this.eventGeneration += 1;
        void this.startEvents();
      }
    } catch (error) {
      this.statusText = `鍥炲埌鍓嶅彴鍚屾澶辫触锛?{this.describeError(error)}`;
    } finally {
      this.foregroundRecoveryInFlight = false;
    }
  }

  private createUuid(): string {
    const chars = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx';
    let result = '';
    for (const char of chars) {
      if (char === 'x' || char === 'y') {
        const value = Math.floor(Math.random() * 16);
        result += (char === 'x' ? value : (value & 0x3) | 0x8).toString(16);
      } else {
        result += char;
      }
    }
    return result;
  }

  private async createMessageId(): Promise<string> {
    const chars = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx';
    let result = '';
    for (const char of chars) {
      if (char === 'x' || char === 'y') {
        const value = Math.floor(Math.random() * 16);
        result += (char === 'x' ? value : (value & 0x3) | 0x8).toString(16);
      } else {
        result += char;
      }
    }
    return result;
  }

  private async loadChat(): Promise<void> {
    if (!this.repository) return;
    this.loading = true;
    this.chatLoadError = '';
    try {
      const result = await this.repository.getChatHistory();
      const items: Record<string, Object>[] = [];
      if (Array.isArray(result.items)) {
        result.items.forEach((item: Object) => {
          if (item instanceof Object) {
            items.push(item as Record<string, Object>);
          }
        });
      }
      this.messages = items.length > 0
        ? items.map(messageFromJson)
        : [this.greetingOverride ? this.restartGreetingMessage() : this.greetingMessage()];
      if (this.messages.length > 0) {
        this.nextBeforeId = Number(result.next_before_id ?? this.messages[0].id) || 0;
        this.hasMoreHistory = result.has_more === true || items.length >= 10;
      }
      this.scrollChatToBottom();
    } catch (error) {
      this.chatLoadError = `聊天加载失败：${this.describeError(error)}`;
    } finally {
      this.loading = false;
    }
  }

  private async send(): Promise<void> {
    const text = this.input.trim();
    if (!text || !this.repository) return;
    this.input = '';
    const clientMessageId = await this.createMessageId();
    const localMessage: ChatMessage = {
      id: -Date.now(),
      messageType: 'text',
      role: 'user',
      content: text,
      createdAt: new Date().toISOString(),
      clientMessageId,
      // Show the user's message as sent immediately; only failures need a state label.
      status: 'sent'
    };
    this.greetingOverride = '';
    this.messages = this.messages.length === 1 && this.messages[0].id === 0
      ? [localMessage]
      : this.messages.concat([localMessage]);
    // The Android client shows the optimistic message immediately and keeps a
    // lightweight typing indicator while the accepted turn is being processed.
    this.echoTyping = true;
    this.scrollChatToBottom();
    this.sending = true;
    try {
      const accepted = await this.repository.sendMessage(text, clientMessageId);
      const acceptedMessage = accepted.message;
      if (acceptedMessage instanceof Object) {
        this.mergeMessages([messageFromJson(acceptedMessage as Record<string, Object>)]);
      }
      // The SSE stream is the fast path. Query the durable history in the
      // background as a recovery path for stream buffering or reconnects.
      const acceptedId = acceptedMessage instanceof Object
        ? Number((acceptedMessage as Record<string, Object>).message_id ?? 0)
        : 0;
      void this.recoverReplyAfterSend(acceptedId);
    } catch (error) {
      this.messages = this.messages.map((message: ChatMessage) => {
        if (message.clientMessageId !== clientMessageId) return message;
        return {
          id: message.id,
          messageType: message.messageType,
          role: message.role,
          content: message.content,
          createdAt: message.createdAt,
          clientMessageId: message.clientMessageId,
          status: 'failed',
          sources: message.sources,
          stickerUrl: message.stickerUrl
        } as ChatMessage;
      });
      this.echoTyping = false;
      this.statusText = `发送失败：${this.describeError(error)}`;
    } finally {
      this.sending = false;
    }
  }

  private async sendSticker(sticker: StickerItem): Promise<void> {
    if (!this.repository || sticker.stickerId.length === 0) return;
    const clientMessageId = await this.createMessageId();
    const localMessage: ChatMessage = {
      id: -Date.now(),
      messageType: 'sticker',
      role: 'user',
      content: '',
      createdAt: new Date().toISOString(),
      clientMessageId,
      status: 'sent',
      stickerUrl: sticker.imageUrl
    };
    this.greetingOverride = '';
    this.messages = this.messages.length === 1 && this.messages[0].id === 0
      ? [localMessage]
      : this.messages.concat([localMessage]);
    this.stickerPickerOpen = false;
    this.echoTyping = true;
    this.scrollChatToBottom();
    try {
      const accepted = await this.repository.sendSticker(sticker.stickerId, clientMessageId);
      const acceptedMessage = accepted.message;
      if (acceptedMessage instanceof Object) {
        this.mergeMessages([messageFromJson(acceptedMessage as Record<string, Object>)]);
      }
      const acceptedId = acceptedMessage instanceof Object
        ? Number((acceptedMessage as Record<string, Object>).message_id ?? 0)
        : 0;
      void this.recoverReplyAfterSend(acceptedId);
    } catch (error) {
      this.messages = this.messages.map((message: ChatMessage) => {
        if (message.clientMessageId !== clientMessageId) return message;
        return {
          id: message.id,
          messageType: message.messageType,
          role: message.role,
          content: message.content,
          createdAt: message.createdAt,
          clientMessageId: message.clientMessageId,
          status: 'failed',
          sources: message.sources,
          stickerUrl: message.stickerUrl
        } as ChatMessage;
      });
      this.echoTyping = false;
      this.statusText = `发送失败：${this.describeError(error)}`;
    }
  }

  private async recoverReplyAfterSend(afterId: number): Promise<void> {
    if (!this.repository || afterId <= 0) return;
    const delays = [700, 1800, 3500, 6000];
    for (const delay of delays) {
      await new Promise<void>((resolve) => setTimeout(resolve, delay));
      if (!this.repository) return;
      try {
        const result = await this.repository.getChatHistory(undefined, afterId);
        const incoming: ChatMessage[] = [];
        if (Array.isArray(result.items)) {
          result.items.forEach((item: Object) => {
            if (item instanceof Object) incoming.push(messageFromJson(item as Record<string, Object>));
          });
        }
        if (incoming.length > 0) {
          this.enqueueMessages(incoming, []);
          return;
        }
      } catch (_) {
        // The SSE connection or its next retry remains the primary path.
      }
    }
    this.echoTyping = false;
  }

  private async loadOlder(): Promise<void> {
    if (!this.repository || !this.hasMoreHistory || this.nextBeforeId <= 0 || this.loading) return;
    this.loading = true;
    try {
      const result = await this.repository.getChatHistory(this.nextBeforeId);
      const items: Record<string, Object>[] = [];
      if (Array.isArray(result.items)) {
        result.items.forEach((item: Object) => {
          if (item instanceof Object) items.push(item as Record<string, Object>);
        });
      }
      const existing = new Set<number>(this.messages.map((item) => item.id));
      const older = items.map(messageFromJson).filter((item) => !existing.has(item.id));
      this.messages = older.concat(this.messages);
      this.nextBeforeId = Number(result.next_before_id ?? (older.length > 0 ? older[0].id : 0)) || 0;
      this.hasMoreHistory = result.has_more === true || items.length >= 10;
    } catch (error) {
      this.statusText = `历史消息加载失败：${this.describeError(error)}`;
    } finally {
      this.loading = false;
    }
  }

  private async startEvents(): Promise<void> {
    if (!this.repository) return;
    const generation = ++this.eventGeneration;
    this.eventConnected = false;
    try {
      await this.repository.subscribeChat(this.latestMessageId(), (eventName, data) => {
        if (generation !== this.eventGeneration) return;
        if (eventName !== 'chat.heartbeat') this.eventConnected = true;
        if (eventName === 'chat.ready') {
          this.serverTyping = data.echo_typing === true;
          this.echoTyping = this.serverTyping || this.activeRevealGroups > 0;
        }
        if (eventName === 'chat.typing.started') {
          this.serverTyping = true;
          this.echoTyping = true;
        }
        if (eventName === 'chat.typing.stopped') {
          this.serverTyping = false;
          this.echoTyping = this.activeRevealGroups > 0;
        }
        if (eventName === 'chat.sync') {
          const incoming: Object[] = Array.isArray(data.messages) ? data.messages as Object[] : [];
          const parsed: ChatMessage[] = [];
          incoming.forEach((item: Object) => {
            if (item instanceof Object) parsed.push(messageFromJson(item as Record<string, Object>));
          });
          this.mergeMessages(parsed);
        }
        if (eventName === 'chat.delivery.created') {
          const incoming: Object[] = Array.isArray(data.messages) ? data.messages as Object[] : [];
          const parsed: ChatMessage[] = [];
          incoming.forEach((item: Object) => {
            if (item instanceof Object) parsed.push(messageFromJson(item as Record<string, Object>));
          });
          this.enqueueMessages(parsed, this.deliveryDelays(data));
          void this.refreshPendingProposal(true);
        }
        if (eventName === 'chat.turn.failed') {
          this.serverTyping = false;
          this.echoTyping = false;
          this.statusText = 'Echo 回复失败，请稍后重试';
        }
      });
      if (generation === this.eventGeneration) {
        this.eventConnected = false;
        setTimeout(() => {
          if (generation === this.eventGeneration) void this.startEvents();
        }, 500);
      }
    } catch (_) {
      if (generation !== this.eventGeneration) return;
      this.eventConnected = false;
      setTimeout(() => {
        if (generation === this.eventGeneration) void this.startEvents();
      }, 3000);
    }
  }

  private latestMessageId(): number {
    return this.messages.reduce((maximum, item) => Math.max(maximum, item.id), 0);
  }

  private cancelRevealQueue(): void {
    this.revealGeneration += 1;
    this.pendingRevealIds.clear();
    this.activeRevealGroups = 0;
    this.echoTyping = this.serverTyping;
  }

  private deliveryDelays(data: Record<string, Object>): number[] {
    const presentation = data.presentation;
    if (!(presentation instanceof Object)) return [];
    const values = (presentation as Record<string, Object>).message_delays_ms;
    if (!Array.isArray(values)) return [];
    return values.map((value: Object) => Math.max(0, Math.min(2500, Number(value) || 0)));
  }

  private enqueueMessages(incoming: ChatMessage[], delays: number[]): void {
    if (incoming.length === 0) return;
    const fresh: ChatMessage[] = [];
    incoming.forEach((message: ChatMessage) => {
      const duplicateInView = this.messages.some((existing: ChatMessage) =>
        (message.clientMessageId !== undefined && message.clientMessageId.length > 0 &&
          existing.clientMessageId === message.clientMessageId) ||
        (message.id > 0 && existing.id === message.id)
      );
      const duplicateInQueue = message.id > 0 && this.pendingRevealIds.has(message.id);
      if (!duplicateInView && !duplicateInQueue) {
        fresh.push(message);
        if (message.id > 0) this.pendingRevealIds.add(message.id);
      }
    });
    if (fresh.length === 0) return;

    const generation = this.revealGeneration;
    this.activeRevealGroups += 1;
    this.echoTyping = true;
    this.revealChain = this.revealChain
      .catch(() => {})
      .then(() => this.revealMessages(fresh, delays, generation));
  }

  private async revealMessages(
    incoming: ChatMessage[],
    delays: number[],
    generation: number
  ): Promise<void> {
    try {
      for (let index = 0; index < incoming.length; index += 1) {
        if (generation !== this.revealGeneration) return;
        const delay = delays.length > index
          ? delays[index]
          : (index === 0 ? 0 : 1000);
        if (delay > 0) {
          await new Promise<void>((resolve) => setTimeout(resolve, delay));
        }
        if (generation !== this.revealGeneration) return;
        this.mergeMessages([incoming[index]]);
        if (incoming[index].id > 0) this.pendingRevealIds.delete(incoming[index].id);
      }
    } finally {
      this.activeRevealGroups = Math.max(0, this.activeRevealGroups - 1);
      this.echoTyping = this.serverTyping || this.activeRevealGroups > 0;
    }
  }

  private greetingMessage(): ChatMessage {
    return {
      id: 0,
      messageType: 'text',
      role: 'assistant',
      content: this.personaName.trim().length > 0
        ? `嗨，${this.personaName.trim()}。我在呢，今天想聊点什么？`
        : '嗨，我在呢。今天想聊点什么？',
      createdAt: ''
    };
  }

  private restartGreetingMessage(): ChatMessage {
    return {
      id: 0,
      messageType: 'text',
      role: 'assistant',
      content: this.personaName.trim().length > 0
        ? `好啦，${this.personaName.trim()}。我们重新聊。`
        : '好啦，我们重新聊。',
      createdAt: ''
    };
  }

  private mergeMessages(incoming: ChatMessage[]): void {
    const current = this.messages.slice();
    incoming.forEach((message: ChatMessage) => {
      const index = current.findIndex((existing: ChatMessage) =>
        (message.clientMessageId !== undefined && message.clientMessageId.length > 0 &&
          existing.clientMessageId === message.clientMessageId) ||
        (message.id > 0 && existing.id === message.id)
      );
      if (index >= 0) current[index] = message;
      else current.push(message);
    });
      this.messages = current.filter((message: ChatMessage, index: number) =>
      index === current.findIndex((other: ChatMessage) =>
        message.id > 0 && other.id === message.id
      ) || message.id <= 0
      ).sort((left: ChatMessage, right: ChatMessage) => {
      if (left.createdAt && right.createdAt) {
        const byTime = left.createdAt.localeCompare(right.createdAt);
        if (byTime !== 0) return byTime;
      }
      return left.id - right.id;
      });
    if (incoming.length > 0) this.greetingOverride = '';
    if (incoming.length > 0) this.scrollChatToBottom();
  }

  private scrollChatToBottom(): void {
    setTimeout(() => {
      try {
        const lastIndex = this.messages.length + (this.echoTyping ? 0 : -1);
        if (lastIndex >= 0) this.chatScroller.scrollToIndex(lastIndex, false);
        this.chatScroller.scrollEdge(Edge.Bottom, { velocity: 0 });
      } catch (_) {
        // The list may not have been laid out yet.
      }
    }, 140);
  }

  private async completeOnboarding(): Promise<void> {
    const name = this.onboardingName.trim();
    if (!name || !this.repository) {
      this.toast('请填写称呼');
      return;
    }
    this.loading = true;
    try {
      const data: Record<string, Object> = {};
      data.preferred_name = name;
      await this.repository.updatePersona(data);
      this.personaName = name;
      this.onboarding = false;
      this.page = 'chat';
      await this.loadChat();
      void this.startEvents();
    } catch (error) {
      this.statusText = `保存失败：${this.describeError(error)}`;
    } finally {
      this.loading = false;
    }
  }

  private updatePersonaDraft(patch: PersonaDraftPatch): void {
    const current = this.personaProfile;
    this.personaProfile = {
      preferredName: patch.preferredName === undefined ? current.preferredName : patch.preferredName,
      replyStyle: patch.replyStyle === undefined ? current.replyStyle : patch.replyStyle,
      replyLength: patch.replyLength === undefined ? current.replyLength : patch.replyLength,
      supportMode: patch.supportMode === undefined ? current.supportMode : patch.supportMode,
      proactivity: patch.proactivity === undefined ? current.proactivity : patch.proactivity,
      avoidTopics: patch.avoidTopics === undefined ? current.avoidTopics : patch.avoidTopics,
      aboutUser: patch.aboutUser === undefined ? current.aboutUser : patch.aboutUser,
      relationshipPace: patch.relationshipPace === undefined ? current.relationshipPace : patch.relationshipPace,
      affectionStyle: patch.affectionStyle === undefined ? current.affectionStyle : patch.affectionStyle,
      enabled: patch.enabled === undefined ? current.enabled : patch.enabled,
      onboardingCompleted: current.onboardingCompleted
    };
    this.personaName = this.personaProfile.preferredName;
  }

  private personaTopicSelected(topic: string): boolean {
    return this.personaProfile.avoidTopics.includes(topic);
  }

  private togglePersonaTopic(topic: string): void {
    const topics = this.personaProfile.avoidTopics.slice();
    const index = topics.indexOf(topic);
    if (index >= 0) {
      topics.splice(index, 1);
    } else {
      if (topics.length >= 5) {
        this.toast('最多添加 5 个话题');
        return;
      }
      topics.push(topic);
    }
    this.updatePersonaDraft({ avoidTopics: topics });
  }

  private addPersonaTopic(): void {
    const topic = this.personaCustomTopic.trim();
    if (topic.length === 0) return;
    if (topic.length > 40) {
      this.toast('单个话题最多 40 个字');
      return;
    }
    if (this.personaProfile.avoidTopics.some((item: string) => item.toLowerCase() === topic.toLowerCase())) {
      this.toast('这个话题已经添加过了');
      return;
    }
    if (this.personaProfile.avoidTopics.length >= 5) {
      this.toast('最多添加 5 个话题');
      return;
    }
    const topics = this.personaProfile.avoidTopics.slice();
    topics.push(topic);
    this.updatePersonaDraft({ avoidTopics: topics });
    this.personaCustomTopic = '';
  }

  private removePersonaTopic(topic: string): void {
    this.updatePersonaDraft({
      avoidTopics: this.personaProfile.avoidTopics.filter((item: string) => item !== topic)
    });
  }

  private personaPayload(): Record<string, Object> {
    const payload: Record<string, Object> = {};
    payload.preferred_name = this.personaProfile.preferredName.trim();
    payload.reply_style = this.personaProfile.replyStyle;
    payload.reply_length = this.personaProfile.replyLength;
    payload.support_mode = this.personaProfile.supportMode;
    payload.proactivity = this.personaProfile.proactivity;
    payload.avoid_topics = this.personaProfile.avoidTopics as Object;
    payload.about_user = this.personaProfile.aboutUser.trim();
    payload.relationship_pace = this.personaProfile.relationshipPace;
    payload.affection_style = this.personaProfile.affectionStyle;
    payload.enabled = this.personaProfile.enabled;
    return payload;
  }

  private async savePersona(): Promise<void> {
    if (!this.repository || this.personaSaving) return;
    const name = this.personaProfile.preferredName.trim();
    const aboutUser = this.personaProfile.aboutUser.trim();
    if (name.length > 40) {
      this.toast('称呼最多 40 个字');
      return;
    }
    if (aboutUser.length > 300) {
      this.toast('关于你最多 300 个字');
      return;
    }
    if (this.personaProfile.avoidTopics.length > 5 ||
      this.personaProfile.avoidTopics.some((item: string) => item.length > 40)) {
      this.toast('请检查避免话题的数量和长度');
      return;
    }
    this.personaSaving = true;
    this.personaError = '';
    try {
      const response = await this.repository.updatePersona(this.personaPayload());
      const profile: PersonaProfile = {
        preferredName: String(response.preferred_name ?? name),
        replyStyle: String(response.reply_style ?? this.personaProfile.replyStyle),
        replyLength: String(response.reply_length ?? this.personaProfile.replyLength),
        supportMode: String(response.support_mode ?? this.personaProfile.supportMode),
        proactivity: String(response.proactivity ?? this.personaProfile.proactivity),
        avoidTopics: Array.isArray(response.avoid_topics)
          ? (response.avoid_topics as Object[]).map((item: Object) => String(item))
          : this.personaProfile.avoidTopics,
        aboutUser: String(response.about_user ?? aboutUser),
        relationshipPace: String(response.relationship_pace ?? this.personaProfile.relationshipPace),
        affectionStyle: String(response.affection_style ?? this.personaProfile.affectionStyle),
        enabled: response.enabled === undefined ? this.personaProfile.enabled : response.enabled === true,
        onboardingCompleted: response.onboarding_completed === true || this.personaProfile.onboardingCompleted
      };
      this.personaProfile = profile;
      this.personaName = profile.preferredName;
      this.toast('设置已保存');
    } catch (error) {
      this.personaError = `保存失败：${this.describeError(error)}`;
      this.statusText = this.personaError;
    } finally {
      this.personaSaving = false;
    }
  }

  private async resetPersonaSettings(): Promise<void> {
    if (!this.repository || this.personaSaving) return;
    this.personaConfirmAction = '';
    this.personaSaving = true;
    this.personaError = '';
    try {
      this.personaProfile = await this.repository.resetPersona();
      this.personaName = this.personaProfile.preferredName;
      this.toast('已恢复默认设置');
    } catch (error) {
      this.personaError = `恢复失败：${this.describeError(error)}`;
      this.statusText = this.personaError;
    } finally {
      this.personaSaving = false;
    }
  }

  private async updateRelationshipMode(mode: string): Promise<void> {
    if (!this.repository || this.relationshipModeSaving || this.personaSaving ||
      this.relationshipState?.relationshipMode === mode) return;
    this.relationshipModeSaving = true;
    this.personaError = '';
    try {
      this.relationshipState = await this.repository.updateRelationshipMode(mode);
      this.toast(`已切换为${relationshipModeLabel(mode)}`);
    } catch (error) {
      this.personaError = `相处方式保存失败：${this.describeError(error)}`;
      this.toast(this.personaError);
    } finally {
      this.relationshipModeSaving = false;
    }
  }

  private async resetRelationshipProgress(): Promise<void> {
    if (!this.repository || this.personaSaving || this.relationshipModeSaving) return;
    this.personaConfirmAction = '';
    this.personaSaving = true;
    this.personaError = '';
    try {
      await this.repository.resetCompanionship();
      this.relationshipState = await this.repository.getRelationship();
      this.pendingRelationshipProposal = undefined;
      this.proposalDialogVisible = false;
      this.proposalShownId = '';
      this.cancelRevealQueue();
      this.greetingOverride = 'restart';
      this.messages = [this.restartGreetingMessage()];
      this.nextBeforeId = 0;
      this.hasMoreHistory = false;
      this.toast('已重新开始，账号和设备保留');
    } catch (error) {
      this.personaError = `重置失败：${this.describeError(error)}`;
      this.statusText = this.personaError;
    } finally {
      this.personaSaving = false;
    }
  }

  private async refreshPendingProposal(showDialog: boolean): Promise<void> {
    if (!this.repository) return;
    try {
      const state = await this.repository.getRelationship();
      this.relationshipState = state;
      const proposal = state.pendingProposal;
      this.pendingRelationshipProposal = proposal;
      if (proposal === undefined) {
        this.proposalDialogVisible = false;
        this.proposalShownId = '';
        return;
      }
      if (showDialog && proposal.proposalId !== this.proposalShownId) {
        this.proposalShownId = proposal.proposalId;
        this.proposalDialogVisible = true;
      }
    } catch (_) {
      // A relationship refresh failure must not interrupt chat delivery.
    }
  }

  private async acceptRelationshipProposal(): Promise<void> {
    const proposal = this.pendingRelationshipProposal;
    if (!this.repository || proposal === undefined || this.relationshipModeSaving) return;
    this.relationshipModeSaving = true;
    try {
      this.relationshipState = await this.repository.acceptRelationshipProposal(proposal.proposalId);
      this.pendingRelationshipProposal = undefined;
      this.proposalDialogVisible = false;
      this.proposalShownId = '';
      this.toast(`关系已更新为${relationshipTypeLabel(this.relationshipState.relationshipType)}`);
    } catch (error) {
      this.toast(`确认失败：${this.describeError(error)}`);
    } finally {
      this.relationshipModeSaving = false;
    }
  }

  private async deferRelationshipProposal(): Promise<void> {
    const proposal = this.pendingRelationshipProposal;
    if (!this.repository || proposal === undefined) {
      this.proposalDialogVisible = false;
      return;
    }
    try {
      await this.repository.deferRelationshipProposal(proposal.proposalId);
      this.pendingRelationshipProposal = undefined;
      this.proposalDialogVisible = false;
      this.proposalShownId = '';
      this.toast('好，那就先这样，我不催你');
    } catch (error) {
      this.toast(`稍后再试：${this.describeError(error)}`);
    }
  }

  private async loadPageData(): Promise<void> {
    if (!this.repository) return;
    this.loading = true;
    try {
      if (this.page === 'memory') {
        this.memoryError = '';
        const result: MemoryListResult = await this.repository.listMemories(this.memoryTab);
        this.memories = result.memories;
        this.memoryCount = result.count;
      }
      if (this.page === 'letters') this.letters = await this.repository.listLetters();
      if (this.page === 'letters') this.unreadLetters = this.letters.filter((item) => !item.isRead).length;
      if (this.page === 'stickers') this.stickers = await this.repository.listStickers();
      if (this.page === 'proactive' || this.page === 'tasks') {
        this.proactiveError = '';
        if (this.page === 'proactive') {
          this.proactivePreferences = await this.repository.getProactivePreferences();
        }
        this.schedules = await this.repository.listSchedules();
      }
      if (this.page === 'persona') {
        this.personaError = '';
        const persona = await this.repository.getPersonaProfile();
        this.personaProfile = persona;
        this.personaName = persona.preferredName;
        this.relationshipState = await this.repository.getRelationship();
      }
      if (this.page === 'presence') {
        this.presenceError = '';
        this.presence = await this.repository.getPresence();
      }
    } catch (error) {
      this.statusText = `加载失败：${this.describeError(error)}`;
      if (this.page === 'memory') this.memoryError = this.describeError(error);
      if (this.page === 'proactive' || this.page === 'tasks') {
        this.proactiveError = this.describeError(error);
      }
      if (this.page === 'persona') this.personaError = this.statusText;
      if (this.page === 'presence') this.presenceError = this.statusText;
    } finally {
      this.loading = false;
    }
  }

  private proactivePreferencePayload(value: ProactiveChatPreferences): Record<string, Object> {
    const payload: Record<string, Object> = {};
    payload.enabled = value.enabled;
    payload.allow_echo_scheduling = value.allowEchoScheduling;
    payload.allow_spontaneous_chat = value.allowSpontaneousChat;
    payload.timezone = value.timezone;
    payload.quiet_start = value.quietStart;
    payload.quiet_end = value.quietEnd;
    payload.explicit_reminder_quiet_policy = value.explicitReminderQuietPolicy;
    payload.notification_preview = value.notificationPreview;
    return payload;
  }

  private applyProactivePatch(patch: ProactivePreferencesPatch): ProactiveChatPreferences {
    const current = this.proactivePreferences;
    return {
      enabled: patch.enabled === undefined ? current.enabled : patch.enabled,
      allowEchoScheduling: patch.allowEchoScheduling === undefined
        ? current.allowEchoScheduling
        : patch.allowEchoScheduling,
      allowSpontaneousChat: patch.allowSpontaneousChat === undefined
        ? current.allowSpontaneousChat
        : patch.allowSpontaneousChat,
      timezone: patch.timezone === undefined ? current.timezone : patch.timezone,
      quietStart: patch.quietStart === undefined ? current.quietStart : patch.quietStart,
      quietEnd: patch.quietEnd === undefined ? current.quietEnd : patch.quietEnd,
      explicitReminderQuietPolicy: patch.explicitReminderQuietPolicy === undefined
        ? current.explicitReminderQuietPolicy
        : patch.explicitReminderQuietPolicy,
      notificationPreview: patch.notificationPreview === undefined
        ? current.notificationPreview
        : patch.notificationPreview,
      pausedUntil: current.pausedUntil,
      pauseIndefinite: current.pauseIndefinite
    };
  }

  private async saveProactivePreferences(patch: ProactivePreferencesPatch): Promise<void> {
    if (!this.repository || this.proactiveSaving) return;
    const previous = this.proactivePreferences;
    const next = this.applyProactivePatch(patch);
    this.proactivePreferences = next;
    this.proactiveSaving = true;
    this.proactiveError = '';
    try {
      this.proactivePreferences = await this.repository.updateProactivePreferences(
        this.proactivePreferencePayload(next)
      );
    } catch (error) {
      this.proactivePreferences = previous;
      this.proactiveError = `保存失败：${this.describeError(error)}`;
    } finally {
      this.proactiveSaving = false;
    }
  }

  private async pauseProactiveContact(): Promise<void> {
    if (!this.repository || this.proactiveSaving) return;
    this.proactiveSaving = true;
    this.proactiveError = '';
    try {
      this.proactivePreferences = await this.repository.pauseProactive(2);
      this.toast('接下来两天不主动找你');
    } catch (error) {
      this.proactiveError = `暂停失败：${this.describeError(error)}`;
    } finally {
      this.proactiveSaving = false;
    }
  }

  private async resumeProactiveContact(): Promise<void> {
    if (!this.repository || this.proactiveSaving) return;
    this.proactiveSaving = true;
    this.proactiveError = '';
    try {
      this.proactivePreferences = await this.repository.resumeProactive();
      this.toast('好，我可以再自然找你聊天了');
    } catch (error) {
      this.proactiveError = `恢复失败：${this.describeError(error)}`;
    } finally {
      this.proactiveSaving = false;
    }
  }

  private openQuietHours(): void {
    this.quietStartDraft = this.proactivePreferences.quietStart;
    this.quietEndDraft = this.proactivePreferences.quietEnd;
    this.proactiveTimeDialog = true;
  }

  private validClock(value: string): boolean {
    if (!/^\d{2}:\d{2}$/.test(value)) return false;
    const hour = Number(value.substring(0, 2));
    const minute = Number(value.substring(3, 5));
    return hour >= 0 && hour <= 23 && minute >= 0 && minute <= 59;
  }

  private async saveQuietHours(): Promise<void> {
    const start = this.quietStartDraft.trim();
    const end = this.quietEndDraft.trim();
    if (!this.validClock(start) || !this.validClock(end)) {
      this.toast('请输入有效时间，格式为 HH:mm');
      return;
    }
    this.proactiveTimeDialog = false;
    await this.saveProactivePreferences({ quietStart: start, quietEnd: end });
  }

  private scheduleDisplayLabel(schedule: ChatSchedule): string {
    const label = schedule.userVisibleLabel.trim();
    return label.length > 0 ? label : schedule.intent;
  }

  private scheduleTypeLabel(value: string): string {
    if (value === 'daily') return '每天';
    if (value === 'weekly') return '每周';
    return '一次性';
  }

  private scheduleDateLabel(value: string): string {
    if (value.length === 0) return '时间待定';
    const timestamp = Date.parse(value);
    if (!Number.isFinite(timestamp)) return value;
    const date = new Date(timestamp);
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hour = String(date.getHours()).padStart(2, '0');
    const minute = String(date.getMinutes()).padStart(2, '0');
    return `${date.getFullYear()}-${month}-${day} ${hour}:${minute}`;
  }

  private scheduleStatusLabel(value: string): string {
    if (value === 'active') return '进行中';
    if (value === 'paused') return '已暂停';
    if (value === 'cancelled') return '已取消';
    return value.length > 0 ? value : '未知';
  }

  private openScheduledTasks(): void {
    this.tasksReturnPage = 'proactive';
    this.navigate('tasks');
  }

  private async toggleSchedule(schedule: ChatSchedule): Promise<void> {
    if (!this.repository || this.proactiveSaving) return;
    this.proactiveSaving = true;
    this.proactiveError = '';
    try {
      await this.repository.updateSchedule(
        schedule.scheduleId,
        schedule.status === 'active' ? 'paused' : 'active'
      );
      this.schedules = await this.repository.listSchedules();
    } catch (error) {
      this.proactiveError = `任务更新失败：${this.describeError(error)}`;
    } finally {
      this.proactiveSaving = false;
    }
  }

  private requestDeleteSchedule(scheduleId: string): void {
    if (this.proactiveSaving) return;
    this.scheduleConfirmId = scheduleId;
  }

  private async confirmDeleteSchedule(): Promise<void> {
    const scheduleId = this.scheduleConfirmId;
    this.scheduleConfirmId = '';
    if (!this.repository || scheduleId.length === 0) return;
    this.proactiveSaving = true;
    this.proactiveError = '';
    try {
      await this.repository.deleteSchedule(scheduleId);
      this.schedules = this.schedules.filter((item: ChatSchedule) => item.scheduleId !== scheduleId);
    } catch (error) {
      this.proactiveError = `任务删除失败：${this.describeError(error)}`;
    } finally {
      this.proactiveSaving = false;
    }
  }

  private focusNumber(value: Object | undefined, fallback: number = 0): number {
    if (value === undefined || value === null) return fallback;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  private focusTimestamp(value: Object | undefined): number | undefined {
    if (value === undefined || value === null) return undefined;
    const numeric = Number(value);
    if (Number.isFinite(numeric) && numeric > 0) return numeric;
    const parsed = Date.parse(String(value));
    return Number.isFinite(parsed) ? parsed : undefined;
  }

  private focusFromJson(value: Record<string, Object>): HarmonyFocusSession {
    const startedAt = this.focusTimestamp(value.started_at) ?? Date.now();
    return {
      sessionId: String(value.session_id ?? ''),
      activityType: String(value.activity_type ?? '其他'),
      shortGoal: String(value.short_goal ?? ''),
      plannedDurationSeconds: Math.max(
        60,
        this.focusNumber(value.planned_duration_seconds, 25 * 60)
      ),
      startedAt,
      activeStartedAt: this.focusTimestamp(value.active_started_at),
      elapsedSeconds: Math.max(0, this.focusNumber(value.elapsed_seconds)),
      status: String(value.status ?? 'paused'),
      endedAt: this.focusTimestamp(value.ended_at)
    };
  }

  private focusElapsed(session: HarmonyFocusSession, now: number): number {
    let elapsed = Math.max(0, session.elapsedSeconds);
    if (session.status === 'running' && session.activeStartedAt !== undefined) {
      elapsed += Math.max(0, Math.floor((now - session.activeStartedAt) / 1000));
    }
    return Math.min(session.plannedDurationSeconds, elapsed);
  }

  private focusRemaining(session: HarmonyFocusSession, now: number): number {
    return Math.max(0, session.plannedDurationSeconds - this.focusElapsed(session, now));
  }

  private async loadFocusState(): Promise<void> {
    let history: HarmonyFocusSession[] = [];
    const rawHistory = await this.store.get('study_focus.history');
    if (rawHistory.length > 0) {
      try {
        const parsed = JSON.parse(rawHistory) as Object;
        if (Array.isArray(parsed)) {
          parsed.forEach((item: Object) => {
            if (item instanceof Object) {
              const session = this.focusFromJson(item as Record<string, Object>);
              if (session.sessionId.length > 0) history.push(session);
            }
          });
        }
      } catch (_) {
        await this.store.remove('study_focus.history');
      }
    }
    this.focusHistory = history;
    this.focusResult = undefined;
    const rawActive = await this.store.get('study_focus.active');
    if (rawActive.length === 0) {
      this.focusSession = undefined;
      this.focusStopTimer();
      return;
    }
    try {
      const parsed = JSON.parse(rawActive) as Record<string, Object>;
      const active = this.focusFromJson(parsed);
      const now = Date.now();
      if (active.status === 'running' && this.focusRemaining(active, now) <= 0) {
        const finished: HarmonyFocusSession = {
          sessionId: active.sessionId,
          activityType: active.activityType,
          shortGoal: active.shortGoal,
          plannedDurationSeconds: active.plannedDurationSeconds,
          startedAt: active.startedAt,
          elapsedSeconds: active.plannedDurationSeconds,
          status: 'completed',
          endedAt: now
        };
        await this.store.remove('study_focus.active');
        await this.focusAppendHistory(finished);
        this.focusHistory = [finished].concat(history);
        this.focusSession = undefined;
        this.focusResult = finished;
        void this.focusSyncUpdate(finished);
      } else {
        this.focusSession = active;
        this.focusEnsureTimer();
        if (active.status === 'running') void this.focusPlayAudio();
      }
    } catch (_) {
      await this.store.remove('study_focus.active');
      this.focusSession = undefined;
      this.focusStopTimer();
    }
  }

  private async focusSaveActive(session: HarmonyFocusSession): Promise<void> {
    await this.store.set('study_focus.active', JSON.stringify(session));
    void this.focusUpdateReminder(session);
  }

  private async focusUpdateReminder(session?: HarmonyFocusSession): Promise<void> {
    try {
      const context = getContext(this) as common.UIAbilityContext;
      if (session?.status === 'running') {
        const end = Date.now() + this.focusRemaining(session, Date.now()) * 1000;
        await this.notifications.schedule(context, end);
      } else {
        await this.notifications.cancel(context);
      }
    } catch (error) {
      console.warn(`[EchoStudy] local reminder unavailable: ${String(error)}`);
    }
  }

  private async focusAppendHistory(session: HarmonyFocusSession): Promise<void> {
    const history = this.focusHistory.filter(
      (item: HarmonyFocusSession) => item.sessionId !== session.sessionId
    );
    history.unshift(session);
    this.focusHistory = history.slice(0, 90);
    await this.store.set('study_focus.history', JSON.stringify(this.focusHistory));
  }

  private focusEnsureTimer(): void {
    if (this.focusTimer !== undefined) return;
    this.focusTimer = setInterval(() => this.focusTick(), 1000);
  }

  private focusStopTimer(): void {
    if (this.focusTimer !== undefined) {
      clearInterval(this.focusTimer);
      this.focusTimer = undefined;
    }
  }

  private focusTick(): void {
    this.focusNow = Date.now();
    const session = this.focusSession;
    if (session === undefined || session.status !== 'running') return;
    if (this.focusRemaining(session, this.focusNow) <= 0 && !this.focusBusy) {
      void this.focusFinish(false);
    }
  }

  private async focusStart(): Promise<void> {
    if (this.focusSession !== undefined || this.focusBusy) return;
    let duration = this.focusCustomDuration
      ? Number(this.focusCustomMinutes.trim())
      : this.focusDurationSeconds / 60;
    if (!Number.isFinite(duration) || duration < 1 || duration > 180) {
      this.toast('请输入 1 到 180 分钟');
      return;
    }
    duration = Math.floor(duration);
    this.focusDurationSeconds = duration * 60;
    const now = Date.now();
    const session: HarmonyFocusSession = {
      sessionId: this.createUuid(),
      activityType: this.focusActivityType,
      shortGoal: this.focusShortGoal.trim().substring(0, 80),
      plannedDurationSeconds: this.focusDurationSeconds,
      startedAt: now,
      activeStartedAt: now,
      elapsedSeconds: 0,
      status: 'running'
    };
    this.focusBusy = true;
    try {
      await this.focusSaveActive(session);
      this.focusSession = session;
      this.focusResult = undefined;
      this.focusNow = now;
      this.focusEnsureTimer();
      this.focusBusy = false;
      void this.focusPlayAudio();
      this.focusVideoStart();
      void this.focusSyncCreate(session);
    } catch (error) {
      this.focusBusy = false;
      this.statusText = `学习启动失败：${this.describeError(error)}`;
    }
  }

  private async focusPause(): Promise<void> {
    const current = this.focusSession;
    if (current === undefined || current.status !== 'running' || this.focusBusy) return;
    const now = Date.now();
    const paused: HarmonyFocusSession = {
      sessionId: current.sessionId,
      activityType: current.activityType,
      shortGoal: current.shortGoal,
      plannedDurationSeconds: current.plannedDurationSeconds,
      startedAt: current.startedAt,
      elapsedSeconds: this.focusElapsed(current, now),
      status: 'paused'
    };
    this.focusBusy = true;
    try {
      await this.focusSaveActive(paused);
      this.focusSession = paused;
      this.focusNow = now;
      this.focusBusy = false;
      void this.focusMedia.pause();
      this.focusVideoPause();
      void this.focusSyncUpdate(paused);
    } catch (error) {
      this.focusBusy = false;
      this.statusText = `暂停失败：${this.describeError(error)}`;
    }
  }

  private async focusResume(): Promise<void> {
    const current = this.focusSession;
    if (current === undefined || current.status !== 'paused' || this.focusBusy) return;
    const now = Date.now();
    const resumed: HarmonyFocusSession = {
      sessionId: current.sessionId,
      activityType: current.activityType,
      shortGoal: current.shortGoal,
      plannedDurationSeconds: current.plannedDurationSeconds,
      startedAt: current.startedAt,
      activeStartedAt: now,
      elapsedSeconds: current.elapsedSeconds,
      status: 'running'
    };
    this.focusBusy = true;
    try {
      await this.focusSaveActive(resumed);
      this.focusSession = resumed;
      this.focusNow = now;
      this.focusEnsureTimer();
      this.focusBusy = false;
      void this.focusPlayAudio();
      this.focusVideoStart();
      void this.focusSyncUpdate(resumed);
    } catch (error) {
      this.focusBusy = false;
      this.statusText = `继续失败：${this.describeError(error)}`;
    }
  }

  private async focusFinish(early: boolean = true): Promise<void> {
    const current = this.focusSession;
    if (current === undefined || this.focusBusy) return;
    const now = Date.now();
    const finished: HarmonyFocusSession = {
      sessionId: current.sessionId,
      activityType: current.activityType,
      shortGoal: current.shortGoal,
      plannedDurationSeconds: current.plannedDurationSeconds,
      startedAt: current.startedAt,
      elapsedSeconds: this.focusElapsed(current, now),
      status: early ? 'ended_early' : 'completed',
      endedAt: now
    };
    this.focusBusy = true;
    try {
      await this.store.remove('study_focus.active');
      await this.focusAppendHistory(finished);
      this.focusSession = undefined;
      this.focusResult = finished;
      this.focusNow = now;
      this.focusBusy = false;
      this.focusStopTimer();
      void this.focusUpdateReminder();
      void this.focusMedia.stop();
      this.focusVideoStop();
      void this.focusSyncUpdate(finished);
    } catch (error) {
      this.focusBusy = false;
      this.statusText = `结束学习失败：${this.describeError(error)}`;
    }
  }

  private async focusSyncCreate(session: HarmonyFocusSession): Promise<void> {
    if (!this.repository) return;
    const request: Record<string, Object> = {};
    request.session_id = session.sessionId;
    request.activity_type = session.activityType;
    request.short_goal = session.shortGoal;
    request.planned_duration_seconds = session.plannedDurationSeconds;
    request.started_at = new Date(session.startedAt).toISOString();
    request.timezone = 'Asia/Shanghai';
    try {
      await this.repository.createFocusSession(request);
    } catch (_) {
      // Local state remains authoritative while the device is offline.
    }
  }

  private async focusSyncUpdate(session: HarmonyFocusSession): Promise<void> {
    if (!this.repository) return;
    const request: Record<string, Object> = {};
    request.status = session.status;
    request.actual_duration_seconds = session.elapsedSeconds;
    request.occurred_at = new Date(session.endedAt ?? Date.now()).toISOString();
    try {
      await this.repository.updateFocusSession(session.sessionId, request);
    } catch (_) {
      // The next screen entry can still use the locally saved history.
    }
  }

  private focusDismissResult(): void {
    this.focusResult = undefined;
  }

  private focusFormatTime(seconds: number): string {
    const safeSeconds = Math.max(0, Math.floor(seconds));
    const minutes = Math.floor(safeSeconds / 60);
    const remainder = safeSeconds % 60;
    return `${String(minutes).padStart(2, '0')}:${String(remainder).padStart(2, '0')}`;
  }

  private focusFormatMinutes(seconds: number): string {
    const safeSeconds = Math.max(0, Math.floor(seconds));
    const minutes = Math.floor(safeSeconds / 60);
    const remainder = safeSeconds % 60;
    return remainder === 0 ? `${minutes} 分钟` : `${minutes} 分 ${String(remainder).padStart(2, '0')} 秒`;
  }

  private focusFormatDate(timestamp: number | undefined): string {
    if (timestamp === undefined) return '';
    const date = new Date(timestamp);
    return `${date.getMonth() + 1}/${date.getDate()}`;
  }

  private focusTodaySeconds(): number {
    const today = new Date();
    return this.focusHistory
      .filter((session: HarmonyFocusSession) => {
        if (session.endedAt === undefined) return false;
        const date = new Date(session.endedAt);
        return date.getFullYear() === today.getFullYear() &&
          date.getMonth() === today.getMonth() &&
          date.getDate() === today.getDate();
      })
      .reduce((sum: number, session: HarmonyFocusSession) => sum + session.elapsedSeconds, 0);
  }

  private parseStickerTagsLegacy(value: string): string[] {
    const result: string[] = [];
    value.split(/[,，\s]+/).forEach((item: string) => {
      const tag = item.trim();
      if (tag.length > 0 && !result.includes(tag)) result.push(tag);
    });
    return result;
  }

  private async chooseStickerImageLegacy(): Promise<void> {
    try {
      const picker = new photoAccessHelper.PhotoViewPicker();
      const result = await picker.select({
        MIMEType: photoAccessHelper.PhotoViewMIMETypes.IMAGE_TYPE,
        maxSelectNumber: 1
      });
      if (!result.photoUris || result.photoUris.length === 0) return;
      const uri = result.photoUris[0];
      const name = decodeURIComponent(uri.substring(uri.lastIndexOf('/') + 1)) || 'sticker.jpg';
      const lower = name.toLowerCase();
      const type = lower.endsWith('.png')
        ? 'image/png'
        : lower.endsWith('.gif')
          ? 'image/gif'
          : lower.endsWith('.webp')
            ? 'image/webp'
            : 'image/jpeg';
      this.stickerUploadUri = uri;
      this.stickerUploadName = name;
      this.stickerUploadType = type;
      this.uploadDescription = '';
      this.uploadTags = '';
      this.stickerUploadOpen = true;
    } catch (error) {
      this.toast(`无法打开相册：${String(error)}`);
    }
  }

  private async saveStickerLegacy(): Promise<void> {
    const description = this.uploadDescription.trim();
    const tags = this.parseStickerTagsLegacy(this.uploadTags);
    if (this.stickerUploadFilePath.length === 0) {
      this.toast('请先选择图片');
      return;
    }
    if (description.length === 0 || description.length > 300) {
      this.toast('请填写 300 字以内的表情包描述');
      return;
    }
    if (tags.length === 0 || this.uploadTags.length > 300) {
      this.toast('请填写 300 字以内的语义标签');
      return;
    }
    this.stickerSaving = true;
    try {
      await this.repository?.uploadSticker(
        this.stickerUploadFilePath,
        this.stickerUploadName,
        this.stickerUploadType,
        description,
        tags
      );
      this.stickerUploadOpen = false;
      await this.loadPageData();
      this.toast('表情包已保存');
    } catch (error) {
      this.statusText = `上传失败：${this.describeError(error)}`;
      this.toast(this.statusText);
    } finally {
      if (this.stickerUploadFilePath.length > 0) {
        try {
          await fs.unlink(this.stickerUploadFilePath);
        } catch (_) {
          console.warn(`[EchoUpload] failed to remove cache file ${this.stickerUploadFilePath}`);
        }
        this.stickerUploadFilePath = '';
      }
      this.stickerSaving = false;
    }
  }

  private stickerCanDeleteLegacy(sticker: StickerItem): boolean {
    return sticker.ownerType === 'user' || sticker.source === 'uploaded';
  }

  private async deleteStickerLegacy(sticker: StickerItem): Promise<void> {
    if (!this.repository || !this.stickerCanDeleteLegacy(sticker)) return;
    try {
      await this.repository.deleteSticker(sticker.stickerId);
      this.stickers = this.stickers.filter((item: StickerItem) =>
        item.stickerId !== sticker.stickerId);
      this.toast('表情包已删除');
    } catch (error) {
      this.statusText = `删除失败：${this.describeError(error)}`;
    }
  }

  @Builder
  private studyFocusPage(): void {
    Column() {
      Row() {
        this.iconButton($r('app.media.arrow_back_outline'), () => this.navigate('chat'))
        Text('一起学习')
          .fontSize(18)
          .fontWeight(FontWeight.Bold)
          .fontColor(Color.White)
          .layoutWeight(1)
          .margin({ left: 4 })
        if (this.focusSession === undefined && this.focusResult === undefined) {
          Button() {
            Text('◷')
              .fontSize(24)
              .fontColor(Color.White)
          }
            .width(48)
            .height(48)
            .backgroundColor(Color.Transparent)
            .onClick(() => this.focusHistoryOpen = true)
        } else {
          Blank().width(48)
        }
      }
      .width('100%')
      .height(56)
      .padding({ left: 8, right: 8 })
      .backgroundColor('#000000')

      Stack() {
        if (this.focusVideoFailed) {
          Image($r('app.media.echo_idle'))
            .width('100%')
            .height('100%')
            .objectFit(ImageFit.Contain)
            .backgroundColor('#121212')
        } else {
          Video({
            src: $rawfile('echo_study.mp4'),
            controller: this.focusVideoController
          })
            .width('100%')
            .height('100%')
            .objectFit(ImageFit.Cover)
            .muted(true)
            .autoPlay(true)
            .controls(false)
            .loop(true)
            .onError(() => {
              this.focusVideoFailed = true;
            })
        }
        if (this.focusSession !== undefined) {
          this.focusRunningView()
        } else if (this.focusResult !== undefined) {
          this.focusResultView()
        } else {
          this.focusSetupView()
        }
        if (this.focusHistoryOpen) {
          this.focusHistoryView()
        }
      }
      .layoutWeight(1)
      .width('100%')
    }
    .width('100%')
    .height('100%')
    .backgroundColor('#000000')
  }

  @Builder
  private focusSetupView(): void {
    Column() {
      Blank().layoutWeight(1)
      Column({ space: 10 }) {
        Text('专注时长')
          .fontSize(16)
          .fontWeight(FontWeight.Bold)
          .fontColor(Color.White)
          .width('100%')
        Row({ space: 8 }) {
          Button('25 分钟')
            .layoutWeight(1)
            .height(42)
            .fontColor(Color.White)
            .backgroundColor(!this.focusCustomDuration && this.focusDurationSeconds === 25 * 60
              ? '#6E61AF' : '#66000000')
            .border({ width: 1, color: '#99FFFFFF' })
            .onClick(() => {
              this.focusCustomDuration = false;
              this.focusDurationSeconds = 25 * 60;
            })
          Button('50 分钟')
            .layoutWeight(1)
            .height(42)
            .fontColor(Color.White)
            .backgroundColor(!this.focusCustomDuration && this.focusDurationSeconds === 50 * 60
              ? '#6E61AF' : '#66000000')
            .border({ width: 1, color: '#99FFFFFF' })
            .onClick(() => {
              this.focusCustomDuration = false;
              this.focusDurationSeconds = 50 * 60;
            })
          Button('自定义')
            .layoutWeight(1)
            .height(42)
            .fontColor(Color.White)
            .backgroundColor(this.focusCustomDuration ? '#6E61AF' : '#66000000')
            .border({ width: 1, color: '#99FFFFFF' })
            .onClick(() => this.focusCustomDuration = true)
        }
        .width('100%')

        if (this.focusCustomDuration) {
          TextInput({ placeholder: '输入分钟数（1-180）', text: this.focusCustomMinutes })
            .type(InputType.Number)
            .maxLength(3)
            .height(44)
            .fontColor(Color.White)
            .backgroundColor('#CCFFFFFF')
            .borderRadius(6)
            .onChange((value: string) => this.focusCustomMinutes = value)
        }

        Text('学习内容')
          .fontSize(16)
          .fontWeight(FontWeight.Bold)
          .fontColor(Color.White)
          .width('100%')
          .margin({ top: 8 })
        Row({ space: 8 }) {
          ForEach(HARMONY_FOCUS_ACTIVITIES, (activity: string) => {
            Button(activity)
              .height(36)
              .fontSize(13)
              .fontColor(Color.White)
              .backgroundColor(this.focusActivityType === activity ? '#6E61AF' : '#66000000')
              .border({ width: 1, color: '#99FFFFFF' })
              .onClick(() => this.focusActivityType = activity)
          }, (activity: string) => activity)
        }
        .width('100%')

        TextInput({ placeholder: '短目标（可选）', text: this.focusShortGoal })
          .maxLength(80)
          .height(44)
          .fontColor('#202124')
          .backgroundColor('#EFFFFFFF')
          .borderRadius(6)
          .onChange((value: string) => this.focusShortGoal = value)

        Button(`开始 ${this.focusCustomDuration ? this.focusCustomMinutes : String(this.focusDurationSeconds / 60)} 分钟`)
          .width('100%')
          .height(46)
          .fontSize(16)
          .fontColor(Color.White)
          .backgroundColor('#6E61AF')
          .enabled(!this.focusBusy)
          .onClick(() => void this.focusStart())

        Text(`今天已学习 ${this.focusFormatMinutes(this.focusTodaySeconds())}`)
          .fontSize(14)
          .fontColor('#CCFFFFFF')
          .width('100%')
      }
      .width('100%')
      .padding({ left: 20, right: 20, top: 18, bottom: 26 })
      .backgroundColor('#B8000000')
    }
    .width('100%')
    .height('100%')
    .justifyContent(FlexAlign.End)
  }

  @Builder
  private focusRunningView(): void {
    if (this.focusSession !== undefined) {
      Column() {
        Blank().layoutWeight(1)
        Column({ space: 12 }) {
          Text(this.focusSession.shortGoal.length === 0
            ? this.focusSession.activityType
            : `${this.focusSession.activityType} · ${this.focusSession.shortGoal}`)
            .fontSize(16)
            .fontWeight(FontWeight.Medium)
            .fontColor('#EFFFFFFF')
            .maxLines(2)
            .textAlign(TextAlign.Center)
            .width('100%')
          Text(this.focusFormatTime(this.focusRemaining(this.focusSession, this.focusNow)))
            .fontSize(58)
            .fontWeight(FontWeight.Bold)
            .fontColor(Color.White)
            .width('100%')
            .textAlign(TextAlign.Center)
          Row() {
            Row()
              .width(`${Math.max(0, Math.min(1, this.focusElapsed(this.focusSession, this.focusNow) / this.focusSession.plannedDurationSeconds) * 100)}%`)
              .height(7)
              .borderRadius(4)
              .backgroundColor(Color.White)
          }
            .width('100%')
            .height(7)
            .borderRadius(4)
            .backgroundColor('#55FFFFFF')
          Row({ space: 12 }) {
            Button(this.focusSession.status === 'paused' ? '继续' : '暂停')
              .layoutWeight(1)
              .height(44)
              .fontColor(Color.White)
              .backgroundColor('#6E61AF')
              .enabled(!this.focusBusy)
              .onClick(() => {
                if (this.focusSession !== undefined && this.focusSession.status === 'paused') {
                  void this.focusResume();
                } else {
                  void this.focusPause();
                }
              })
            Button('结束本轮')
              .layoutWeight(1)
              .height(44)
              .fontColor(Color.White)
              .backgroundColor('#66000000')
              .border({ width: 1, color: '#B3FFFFFF' })
              .enabled(!this.focusBusy)
              .onClick(() => void this.focusFinish(true))
          }
          .width('100%')
        }
        .width('100%')
        .padding({ left: 20, right: 20, top: 24, bottom: 30 })
        .backgroundColor('#99000000')
      }
      .width('100%')
      .height('100%')
      .justifyContent(FlexAlign.End)
    } else {
      Blank()
        .width('100%')
        .height('100%')
    }
  }

  @Builder
  private focusResultView(): void {
    if (this.focusResult !== undefined) {
      Column({ space: 12 }) {
        Blank().layoutWeight(1)
        Column({ space: 12 }) {
          Text(this.focusResult.status === 'completed' ? '✓' : 'Ⅱ')
            .fontSize(52)
            .fontColor(Color.White)
            .width('100%')
            .textAlign(TextAlign.Center)
          Text(this.focusResult.status === 'completed' ? '这一轮完成了' : '这一轮提前结束')
            .fontSize(24)
            .fontWeight(FontWeight.Bold)
            .fontColor(Color.White)
            .width('100%')
            .textAlign(TextAlign.Center)
          Text(`实际学习 ${this.focusFormatMinutes(this.focusResult.elapsedSeconds)} · ${this.focusResult.activityType}`)
            .fontSize(15)
            .fontColor('#D9FFFFFF')
            .width('100%')
            .textAlign(TextAlign.Center)
          if (this.focusResult.shortGoal.length > 0) {
            Text(this.focusResult.shortGoal)
              .fontSize(15)
              .fontColor('#D9FFFFFF')
              .width('100%')
              .textAlign(TextAlign.Center)
          }
          Button('再来一轮')
            .width('100%')
            .height(46)
            .fontColor(Color.White)
            .backgroundColor('#6E61AF')
            .onClick(() => this.focusDismissResult())
          Button('结束学习')
            .width('100%')
            .height(46)
            .fontColor(Color.White)
            .backgroundColor('#66000000')
            .border({ width: 1, color: '#B3FFFFFF' })
            .onClick(() => {
              this.focusDismissResult();
              this.navigate('chat');
            })
        }
        .width('100%')
        .padding({ left: 20, right: 20, top: 26, bottom: 32 })
        .backgroundColor('#99000000')
      }
      .width('100%')
      .height('100%')
      .justifyContent(FlexAlign.End)
    } else {
      Blank()
        .width('100%')
        .height('100%')
    }
  }

  @Builder
  private focusHistoryView(): void {
    Stack() {
      Column()
        .width('100%')
        .height('100%')
        .backgroundColor('#99000000')
        .onClick(() => this.focusHistoryOpen = false)
      Column() {
        Row() {
          Text('学习记录')
            .fontSize(20)
            .fontWeight(FontWeight.Bold)
            .fontColor('#262331')
            .layoutWeight(1)
          this.iconButton($r('app.media.arrow_back_outline'), () => this.focusHistoryOpen = false)
        }
        .width('100%')
        .height(58)
        .padding({ left: 18, right: 8 })
        if (this.focusHistory.length === 0) {
          Column({ space: 10 }) {
            Text('还没有学习记录').fontSize(17).fontColor('#49454F')
            Text('完成一轮学习后会显示在这里').fontSize(14).fontColor('#6F6A78')
          }
          .layoutWeight(1)
          .width('100%')
          .justifyContent(FlexAlign.Center)
        } else {
          List({ space: 1 }) {
            ForEach(this.focusHistory, (session: HarmonyFocusSession) => {
              ListItem() {
                Row({ space: 12 }) {
                  Text(session.status === 'completed' ? '✓' : '■')
                    .fontSize(20)
                    .fontColor(session.status === 'completed' ? '#6E61AF' : '#6F6A78')
                    .width(24)
                  Column({ space: 4 }) {
                    Text(session.shortGoal.length === 0
                      ? session.activityType
                      : `${session.activityType} · ${session.shortGoal}`)
                      .fontSize(16)
                      .fontColor('#262331')
                      .maxLines(1)
                      .textOverflow({ overflow: TextOverflow.Ellipsis })
                      .width('100%')
                    Text(`${this.focusFormatMinutes(session.elapsedSeconds)}${session.endedAt === undefined ? '' : ` · ${this.focusFormatDate(session.endedAt)}`}`)
                      .fontSize(13)
                      .fontColor('#6F6A78')
                  }
                  .layoutWeight(1)
                }
                .width('100%')
                .padding({ left: 16, right: 16, top: 12, bottom: 12 })
                .backgroundColor('#FFFFFF')
              }
            }, (session: HarmonyFocusSession) => session.sessionId)
          }
          .layoutWeight(1)
          .width('100%')
        }
      }
      .width('92%')
      .height('78%')
      .backgroundColor('#FFFBFE')
      .borderRadius(16)
    }
    .width('100%')
    .height('100%')
    .zIndex(30)
  }

  private navigate(page: string): void {
    if (this.page === 'study' && page !== 'study') {
      this.focusVideoStop();
      void this.focusMedia.stop();
    }
    this.page = page;
    this.menuOpen = false;
    if (page === 'chat') {
      void this.loadChat();
    } else if (page === 'study') {
      void this.loadFocusState();
    } else {
      void this.loadPageData();
    }
  }

  private focusVideoStart(): void {
    try {
      this.focusVideoController.start();
    } catch (_) {
      // The video is optional and must not block the focus timer.
    }
  }

  private focusVideoPause(): void {
    try {
      this.focusVideoController.pause();
    } catch (_) {
      // The video is optional and must not block the focus timer.
    }
  }

  private focusVideoStop(): void {
    try {
      this.focusVideoController.stop();
    } catch (_) {
      // The video is optional and must not block the focus timer.
    }
  }

  private async focusPlayAudio(): Promise<void> {
    try {
      const context = getContext(this) as common.UIAbilityContext;
      await this.focusMedia.play(context);
    } catch (error) {
      this.statusText = '学习背景音播放失败，请检查媒体音量后重试';
      console.warn(`[EchoStudy] audio setup unavailable: ${String(error)}`);
    }
  }

  private letterDate(letter: DailyLetter): string {
    if (letter.localDate.length > 0) return letter.localDate;
    if (letter.publishAt !== undefined && letter.publishAt.length >= 10) {
      return letter.publishAt.substring(0, 10);
    }
    return '';
  }

  private letterPreview(letter: DailyLetter): string {
    return letter.body.replace(/\s+/g, ' ').trim();
  }

  private async switchMemoryTab(status: string): Promise<void> {
    if (this.memoryTab === status && !this.loading) return;
    this.memoryTab = status;
    this.memories = [];
    this.memoryCount = 0;
    await this.loadPageData();
  }

  private memoryTypeLabel(value: string): string {
    switch (value) {
      case 'profile':
        return '资料';
      case 'preference':
        return '偏好';
      case 'relationship':
        return '关系';
      case 'goal':
        return '目标';
      case 'event':
        return '事件';
      case 'boundary':
        return '边界';
      default:
        return value.length > 0 ? value : '未知';
    }
  }

  private memoryStatusLabel(value: string): string {
    if (value === 'active') return '有效';
    if (value === 'deleted') return '已删除';
    if (value === 'inactive') return '停用';
    return value.length > 0 ? value : '未知';
  }

  private memoryConfidenceLabel(value: number): string {
    return `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`;
  }

  private memoryUpdatedLabel(value?: string): string {
    if (value === undefined || value.length === 0) return '更新时间未知';
    const timestamp: number = Date.parse(value);
    if (!Number.isFinite(timestamp)) return value;
    const date = new Date(timestamp);
    const month: string = String(date.getMonth() + 1).padStart(2, '0');
    const day: string = String(date.getDate()).padStart(2, '0');
    const hour: string = String(date.getHours()).padStart(2, '0');
    const minute: string = String(date.getMinutes()).padStart(2, '0');
    return `${month}-${day} ${hour}:${minute}`;
  }

  private requestDeleteMemory(memoryId: string): void {
    this.memoryConfirmAction = 'delete';
    this.memoryConfirmId = memoryId;
  }

  private requestClearMemories(): void {
    if (this.memoryTab !== 'active' || this.memories.length === 0 || this.loading) return;
    this.memoryConfirmAction = 'clear';
    this.memoryConfirmId = '';
  }

  private async confirmMemoryAction(): Promise<void> {
    const action: string = this.memoryConfirmAction;
    const memoryId: string = this.memoryConfirmId;
    this.memoryConfirmAction = '';
    this.memoryConfirmId = '';
    if (!this.repository) return;
    if (action === 'delete' && memoryId.length > 0) {
      this.memoryDeletingId = memoryId;
      this.memoryError = '';
      try {
        await this.repository.deleteMemory(memoryId);
        await this.loadPageData();
      } catch (error) {
        this.memoryError = `删除失败：${this.describeError(error)}`;
      } finally {
        this.memoryDeletingId = '';
      }
    } else if (action === 'clear') {
      this.loading = true;
      this.memoryError = '';
      try {
        await this.repository.clearMemories();
        this.memoryTab = 'active';
        await this.loadPageData();
      } catch (error) {
        this.memoryError = `清空失败：${this.describeError(error)}`;
        this.loading = false;
      }
    }
  }

  @Builder
  private iconButton(resource: Resource, action: () => void): void {
    Button() {
      Image(resource)
        .width(26)
        .height(26)
    }
      .width(48)
      .height(48)
      .backgroundColor(Color.Transparent)
      .onClick(action)
  }

  @Builder
  private lettersPage(): void {
    Stack() {
      Column() {
        Row() {
          this.iconButton($r('app.media.arrow_back_outline'), () => this.navigate('chat'))
          Text(`Echo 来信${this.unreadLetters > 0 ? ` (${this.unreadLetters})` : ''}`)
            .fontSize(22)
            .fontWeight(FontWeight.Bold)
            .fontColor('#262331')
            .layoutWeight(1)
            .margin({ left: 4 })
          this.iconButton($r('app.media.refresh_outline'), () => this.loadPageData())
        }
        .width('100%')
        .height(64)
        .padding({ left: 10, right: 10 })
        .backgroundColor('#F8F7FC')

        if (this.loading && this.letters.length === 0) {
          Column() {
            Text('正在取回来信').fontSize(16).fontColor('#6F6A78')
          }
          .layoutWeight(1)
          .width('100%')
          .justifyContent(FlexAlign.Center)
        } else if (this.letters.length === 0) {
          Column({ space: 10 }) {
            Image($r('app.media.mail_outline')).width(44).height(44)
            Text('今天还没有新信').fontSize(18).fontColor('#49454F')
            Text('我们聊过的事，会在这里慢慢沉淀下来。')
              .fontSize(14)
              .fontColor('#6F6A78')
              .textAlign(TextAlign.Center)
          }
          .layoutWeight(1)
          .width('100%')
          .padding(32)
          .justifyContent(FlexAlign.Center)
        } else {
          List({ space: 12 }) {
            ForEach(this.letters, (letter: DailyLetter) => {
              ListItem() {
                this.letterCard(letter)
              }
              .onClick(() => this.openLetter(letter))
            }, (letter: DailyLetter) => letter.letterId)
          }
          .layoutWeight(1)
          .width('100%')
          .padding({ left: 16, right: 16, top: 16, bottom: 24 })
        }
      }
      .width('100%')
      .height('100%')
      if (this.letterDetailOpen) {
        this.letterDetail()
      }
    }
    .width('100%')
    .height('100%')
  }

  @Builder
  private letterCard(letter: DailyLetter): void {
    Column({ space: 8 }) {
      Text(this.letterDate(letter))
        .fontSize(13)
        .fontColor('#6F6A78')
        .maxLines(1)
      Text(letter.title)
        .fontSize(18)
        .fontWeight(FontWeight.Medium)
        .fontColor('#262331')
        .maxLines(1)
      if (letter.imageUrl.length > 0) {
        Image(letter.imageUrl)
          .width('100%')
          .height(120)
          .objectFit(ImageFit.Cover)
          .borderRadius(8)
      }
      Text(this.letterPreview(letter))
        .fontSize(15)
        .lineHeight(22)
        .fontColor('#49454F')
        .maxLines(2)
    }
    .width('100%')
    .padding(16)
    .backgroundColor(letter.isRead ? '#FFFFFF' : '#F5F0FF')
    .border({
      width: letter.isRead ? 1 : 1.4,
      color: letter.isRead ? '#E3E0E8' : '#6750A4'
    })
    .borderRadius(8)
    .alignItems(HorizontalAlign.Start)
  }

  private async openLetter(letter: DailyLetter): Promise<void> {
    this.selectedLetter = letter;
    this.letterDetailOpen = true;
    if (!letter.isRead) {
      try {
        await this.repository?.markLetterRead(letter.letterId);
        const updatedLetters = this.letters.map((item: DailyLetter) => {
          if (item.letterId !== letter.letterId) return item;
          return {
            letterId: item.letterId,
            localDate: item.localDate,
            timezone: item.timezone,
            title: item.title,
            body: item.body,
            mood: item.mood,
            isRead: true,
            imageUrl: item.imageUrl,
            publishAt: item.publishAt
          } as DailyLetter;
        });
        this.letters = updatedLetters;
        this.selectedLetter = updatedLetters.find((item: DailyLetter) =>
          item.letterId === letter.letterId
        ) ?? letter;
        this.unreadLetters = Math.max(0, this.unreadLetters - 1);
      } catch (_) {
        this.statusText = '来信标记已读失败，请稍后重试';
      }
    }
  }

  @Builder
  private letterDetail(): void {
    Stack() {
      Column()
        .width('100%')
        .height('100%')
        .backgroundColor('#99000000')
        .onClick(() => this.letterDetailOpen = false)
      Column() {
        Row() {
          Text(this.selectedLetter.title)
            .fontSize(20)
            .fontWeight(FontWeight.Bold)
            .fontColor('#262331')
            .layoutWeight(1)
            .maxLines(1)
        }
        .width('100%')
        .height(60)
        .padding({ left: 20, right: 20 })

        Scroll() {
          Column({ space: 16 }) {
            Text(this.letterDate(this.selectedLetter))
              .fontSize(13)
              .fontColor('#6F6A78')
              .width('100%')
              .textAlign(TextAlign.Start)
            if (this.selectedLetter.imageUrl.length > 0) {
              Image(this.selectedLetter.imageUrl)
                .width('100%')
                .objectFit(ImageFit.Contain)
                .borderRadius(8)
            }
            Text(this.selectedLetter.body)
              .fontSize(16)
              .lineHeight(26)
              .fontColor('#262331')
              .width('100%')
              .textAlign(TextAlign.Start)
          }
          .width('100%')
          .padding({ left: 20, right: 20, bottom: 24 })
        }
        .layoutWeight(1)
        .width('100%')

        Row() {
          Button('收好这封信')
            .onClick(() => this.letterDetailOpen = false)
        }
        .width('100%')
        .justifyContent(FlexAlign.End)
        .padding({ left: 20, right: 20, bottom: 16 })
      }
      .width('92%')
      .height('82%')
      .backgroundColor('#FFFBFE')
      .borderRadius(16)
      .shadow({ radius: 20, color: '#66000000', offsetX: 0, offsetY: 8 })
    }
    .width('100%')
    .height('100%')
    .zIndex(20)
  }

  private async logout(): Promise<void> {
    const raw = await this.store.get('session');
    if (this.repository && raw) {
      try {
        const session = JSON.parse(raw) as AuthSession;
        await this.repository.logout(session.refreshToken, session.deviceId);
      } catch (_) {}
    }
    this.eventGeneration += 1;
    this.cancelRevealQueue();
    await this.store.remove('session');
    this.loggedIn = false;
    this.updateOpen = false;
    void this.focusUpdateReminder();
    this.onboarding = false;
    this.verificationId = '';
    this.phone = '';
    this.code = '';
    this.statusText = '';
    this.repository = undefined;
    this.messages = [];
    this.chatLoadError = '';
    this.toast('已退出登录');
  }

  private toast(message: string): void {
    promptAction.showToast({ message });
  }

  @Builder
  private loginView(): void {
    Column({ space: 18 }) {
      Text('Echo')
        .fontSize(36)
        .fontWeight(FontWeight.Bold)
        .fontColor('#E56B5D')
      Text('你的 AI 陪伴')
        .fontSize(20)
        .fontColor('#3C3734')
      TextInput({ placeholder: '手机号', text: this.phone })
        .type(InputType.PhoneNumber)
        .onChange((value: string) => this.phone = value)
      if (this.verificationId.length > 0) {
        TextInput({ placeholder: '验证码', text: this.code })
          .type(InputType.Number)
          .onChange((value: string) => this.code = value)
        Button('登录')
          .width('100%')
          .onClick(() => this.verify())
      } else {
        Button('获取验证码')
          .width('100%')
          .onClick(() => this.requestCode())
      }
      if (this.statusText) Text(this.statusText).fontColor('#8A7770')
    }
    .width('100%')
    .padding(28)
    .justifyContent(FlexAlign.Center)
  }

  @Builder
  private onboardingView(): void {
    Column({ space: 18 }) {
      Text('先认识一下你').fontSize(30).fontWeight(FontWeight.Bold).fontColor('#3C3734')
      Text('告诉 Echo 应该怎么称呼你').fontSize(16).fontColor('#766963')
      TextInput({ placeholder: '例如：小叶', text: this.onboardingName })
        .onChange((value: string) => this.onboardingName = value)
      Button('进入 Echo').width('100%').onClick(() => this.completeOnboarding())
      if (this.statusText) Text(this.statusText).fontColor('#B34D42')
    }.width('100%').padding(28).justifyContent(FlexAlign.Center)
  }

  @Builder
  private chatView(): void {
    Stack({ alignContent: Alignment.TopEnd }) {
      Column() {
        this.chatToolbar()
        Column() {
          Image(this.chatExpanded ? $r('app.media.idle_sit') : $r('app.media.echo_idle'))
            .width('100%')
            .layoutWeight(this.chatExpanded ? 3 : 7)
            .objectFit(ImageFit.Contain)
            .backgroundColor('#F8F7FC')
          Column() {
            Row() {
              Text(this.chatExpanded ? '▼  收起聊天' : '▲  展开聊天')
                .fontSize(15)
                .fontColor('#49454F')
            }
            .width('100%')
            .justifyContent(FlexAlign.Center)
            .height(42)
            .onClick(() => {
              this.chatExpanded = !this.chatExpanded;
              this.scrollChatToBottom();
              setTimeout(() => this.scrollChatToBottom(), 360);
            })
            this.expandedChatPanel()
          }
          .layoutWeight(this.chatExpanded ? 7 : 3)
          .width('100%')
          .backgroundColor('#FFFBFE')
          .borderRadius({ topLeft: 24, topRight: 24 })
        }
        .layoutWeight(1)
        .width('100%')
      }
      .width('100%')
      .height('100%')
      if (this.menuOpen) {
        Column()
          .width('100%')
          .height('100%')
          .backgroundColor('#00000000')
          .zIndex(9)
          .onClick(() => this.menuOpen = false)
        Column() {
          this.chatMenu()
        }
        .width('76%')
        .margin({ top: 62, right: 10 })
        .zIndex(10)
      }
      if (this.stickerPickerOpen) {
        this.stickerPicker()
      }
    }
    .width('100%')
    .height('100%')
  }

  @Builder
  private chatToolbar(): void {
    Row() {
      Text('Echo').fontSize(22).fontWeight(FontWeight.Bold).fontColor('#6750A4')
      Text(`v${AppConfig.appVersion}`).fontSize(12).fontColor('#6F6A78').margin({ left: 6 })
      Blank().layoutWeight(1)
      Stack() {
        Button() {
          Image($r('app.media.mail_outline'))
            .width(25)
            .height(25)
        }
          .backgroundColor(Color.Transparent)
          .width(48)
          .height(48)
          .onClick(() => this.navigate('letters'))
        if (this.unreadLetters > 0) {
          Text(this.unreadLetters > 99 ? '99+' : String(this.unreadLetters))
            .fontSize(10)
            .fontColor(Color.White)
            .backgroundColor('#BA1A1A')
            .borderRadius(10)
            .padding({ left: 4, right: 4, top: 2, bottom: 2 })
            .position({ x: 26, y: 2 })
        }
      }
      Button('☰')
        .fontSize(24)
        .fontColor('#49454F')
        .backgroundColor(Color.Transparent)
        .width(48)
        .height(48)
        .onClick(() => this.menuOpen = !this.menuOpen)
    }
    .width('100%')
    .height(64)
    .padding({ left: 18, right: 10 })
    .backgroundColor('#F8F7FC')
  }

  @Builder
  private expandedChatPanel(): void {
    Column() {
      if (this.loading) {
        Text('正在加载…').fontSize(12).fontColor('#6F6A78').padding(6)
      }
      if (this.chatLoadError.length > 0) {
        Row({ space: 8 }) {
          Text(this.chatLoadError).fontSize(12).fontColor('#BA1A1A').layoutWeight(1)
          Button('重试').onClick(() => void this.loadChat())
        }.width('100%').padding({ left: 16, right: 16, top: 4, bottom: 4 })
      }
      List({ space: 0, scroller: this.chatScroller }) {
        ForEach(this.messages, (message: ChatMessage, index: number) => {
          ListItem() {
            Column() {
              if (this.shouldShowChatTime(index)) {
                this.chatTimeSeparator(this.chatTimeLabel(message.createdAt))
              }
              this.messageBubble(message, 144)
            }
            .width('100%')
          }
        }, (message: ChatMessage) => `${message.id}_${message.clientMessageId ?? ''}`)
        if (this.echoTyping) {
          ListItem() {
            Text('•••').fontSize(18).fontColor('#6F6A78').padding(12)
              .backgroundColor('#F0EDF5').borderRadius(18)
          }
        }
      }
      .layoutWeight(1)
      .width('100%')
      .padding({ left: 16, right: 16, top: 4, bottom: 4 })
      .onReachStart(() => this.loadOlder())
      Row({ space: 8 }) {
        Button() {
          Image($r('app.media.emoji_outline'))
            .width(24)
            .height(24)
        }
          .backgroundColor(Color.Transparent)
          .width(38)
          .height(48)
          .onClick(() => {
            this.menuOpen = false;
            this.stickerPickerOpen = true;
            if (this.stickers.length === 0) void this.loadStickersForPicker();
          })
        TextInput({ placeholder: '说点什么…', text: this.input })
          .layoutWeight(1)
          .height(48)
          .fontSize(16)
          .backgroundColor('#F0EDF5')
          .borderRadius(24)
          .onChange((value: string) => this.input = value)
          .onSubmit(() => this.send())
        Button() {
          Image($r('app.media.send_outline'))
            .width(22)
            .height(22)
        }
          .backgroundColor('#6750A4')
          .width(52)
          .height(48)
          .borderRadius(24)
          .onClick(() => this.send())
      }
      .padding({ left: 12, right: 12, top: 8, bottom: 12 })
    }
    .layoutWeight(1)
    .width('100%')
  }

  private shouldShowChatTime(index: number): boolean {
    if (index < 0 || index >= this.messages.length) return false;
    const current = this.messages[index].createdAt;
    if (current.length === 0) return false;
    const currentTime = new Date(current).getTime();
    if (Number.isNaN(currentTime)) return false;
    if (index === 0) return true;
    const previous = this.messages[index - 1].createdAt;
    if (previous.length === 0) return true;
    const previousTime = new Date(previous).getTime();
    if (Number.isNaN(previousTime)) return true;
    if (new Date(currentTime).toDateString() !== new Date(previousTime).toDateString()) return true;
    return Math.abs(currentTime - previousTime) >= 5 * 60 * 1000;
  }

  private chatTimeLabel(value: string): string {
    const time = new Date(value);
    if (Number.isNaN(time.getTime())) return '';
    const pad = (number: number): string => number < 10 ? `0${number}` : `${number}`;
    const clock = `${pad(time.getHours())}:${pad(time.getMinutes())}`;
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const day = new Date(time.getFullYear(), time.getMonth(), time.getDate()).getTime();
    const days = Math.floor((today - day) / (24 * 60 * 60 * 1000));
    if (days === 0) return clock;
    if (days === 1) return `昨天 ${clock}`;
    if (days > 1 && days < 7) {
      const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
      return `${weekdays[time.getDay()]} ${clock}`;
    }
    return `${time.getMonth() + 1}月${time.getDate()}日 ${clock}`;
  }

  @Builder
  private chatTimeSeparator(label: string): void {
    Row() {
      Text(label)
        .fontSize(11)
        .fontColor('#8B8794')
        .backgroundColor('#EDEAF0')
        .borderRadius(10)
        .padding({ left: 9, right: 9, top: 3, bottom: 3 })
    }
    .width('100%')
    .justifyContent(FlexAlign.Center)
    .padding({ top: 10, bottom: 10 })
  }

  @Builder
  private messageBubble(message: ChatMessage, stickerSize: number): void {
    Row() {
      Column() {
        if (message.stickerUrl !== undefined && message.stickerUrl.length > 0) {
          Image(message.stickerUrl)
            .width(stickerSize)
            .height(stickerSize)
            .objectFit(ImageFit.Contain)
            .margin({ top: 4, bottom: 4 })
        }
        if (message.content.length > 0) {
          Text(message.content)
            .fontSize(16)
            .lineHeight(24)
            .fontColor(message.role === 'user' ? Color.White : '#262331')
            .backgroundColor(message.role === 'user' ? '#6750A4' : '#F0EDF5')
            .borderRadius(18)
            .padding({ left: 14, right: 14, top: 10, bottom: 10 })
            .constraintSize({ maxWidth: '78%' })
        }
        if (message.status === 'failed') {
          Text('发送失败，点击重试')
            .fontSize(12)
            .fontColor(message.role === 'user' ? '#FFDAD6' : '#BA1A1A')
            .margin({ top: 2 })
        }
      }
      .constraintSize({ maxWidth: '78%' })
    }
    .width('100%')
    .justifyContent(message.role === 'user' ? FlexAlign.End : FlexAlign.Start)
    .margin({ top: 4, bottom: 4 })
  }

  private async loadStickersForPicker(): Promise<void> {
    if (!this.repository) return;
    try {
      this.stickers = await this.repository.listStickers();
    } catch (error) {
      this.statusText = `表情包加载失败：${this.describeError(error)}`;
    }
  }

  @Builder
  private stickerPicker(): void {
    Column() {
      Column()
        .width('100%')
        .layoutWeight(1)
        .backgroundColor('#66000000')
        .onClick(() => this.stickerPickerOpen = false)
      Column() {
        Row() {
          Text('表情包')
            .fontSize(18)
            .fontWeight(FontWeight.Medium)
            .fontColor('#262331')
            .layoutWeight(1)
          this.iconButton($r('app.media.photo_library_outline'), () => this.navigate('stickers'))
          this.iconButton($r('app.media.refresh_outline'), () => void this.loadStickersForPicker())
        }
        .width('100%')
        .height(56)
        .padding({ left: 16, right: 8 })
        Grid() {
          ForEach(this.stickers, (sticker: StickerItem) => {
            GridItem() {
              if (sticker.imageUrl.length > 0) {
                Image(sticker.imageUrl)
                  .width('100%')
                  .height(68)
                  .objectFit(ImageFit.Contain)
              } else {
                Text('图片不可用')
                  .fontSize(12)
                  .fontColor('#6F6A78')
                  .width('100%')
                  .height(68)
                  .textAlign(TextAlign.Center)
              }
            }
            .width('100%')
            .height(80)
            .padding(6)
            .backgroundColor('#F3F1F6')
            .borderRadius(8)
            .onClick(() => void this.sendSticker(sticker))
          }, (sticker: StickerItem) => sticker.stickerId)
        }
        .columnsTemplate('repeat(4, 1fr)')
        .rowsGap(8)
        .columnsGap(8)
        .layoutWeight(1)
        .width('100%')
        .padding({ left: 12, right: 12, bottom: 20 })
      }
      .height('58%')
      .width('100%')
      .backgroundColor('#FFFBFE')
      .borderRadius({ topLeft: 20, topRight: 20 })
    }
    .width('100%')
    .height('100%')
    .zIndex(20)
  }

  @Builder
  private chatMenu(): void {
    Column({ space: 0 }) {
      this.menuItem('一起学习', 'study')
      this.menuItem('我的 Echo', 'devices')
      this.menuItem('关于她', 'persona')
      this.menuItem('她的状态', 'presence')
      this.menuItem('长期记忆', 'memory')
      this.menuItem('表情包库', 'stickers')
      this.menuItem('通知设置', 'notifications')
      this.menuItem('主动聊天设置', 'proactive')
      this.menuItem('定时任务', 'tasks')
      this.menuItem('检查更新', 'update')
      this.menuItem('清除聊天上下文', 'clear')
      this.menuItem('退出登录', 'logout')
    }
    .width('100%')
    .padding({ top: 8, bottom: 8, left: 8, right: 8 })
    .backgroundColor('#FFFBFE')
    .borderRadius(12)
    .shadow({ radius: 18, color: '#40000000', offsetX: 0, offsetY: 6 })
  }

  @Builder
  private menuItem(label: string, action: string): void {
    Row() {
      Text(label)
        .fontSize(16)
        .fontColor('#262331')
        .maxLines(1)
    }
      .width('100%')
      .height(44)
      .padding({ left: 14, right: 14 })
      .justifyContent(FlexAlign.Start)
      .borderRadius(8)
      .onClick(() => {
        this.menuOpen = false;
        if (action === 'logout') void this.logout();
        else if (action === 'clear') this.confirmClearContext();
        else if (action === 'update') this.updateOpen = true;
        else this.navigate(action === 'study' ? 'study' : action === 'notifications' ? 'notifications' : action === 'proactive' ? 'proactive' : action === 'update' ? 'update' : action);
      })
  }

  private confirmClearContext(): void {
    if (this.clearingContext) return;
    AlertDialog.show({
      title: '清除聊天上下文',
      message: '会清除聊天记录和会话摘要，长期记忆仍会保留。',
      primaryButton: { value: '取消', action: () => {} },
      secondaryButton: { value: '清除', action: () => void this.clearContext() }
    });
  }

  private async clearContext(): Promise<void> {
    if (!this.repository || this.clearingContext) return;
    this.clearingContext = true;
    try {
      await this.repository.clearChat();
      this.cancelRevealQueue();
      this.greetingOverride = 'restart';
      this.messages = [this.restartGreetingMessage()];
      this.nextBeforeId = 0;
      this.hasMoreHistory = false;
      this.toast('聊天上下文已清除，长期记忆仍会保留');
    } catch (error) {
      this.statusText = `清除失败：${this.describeError(error)}`;
      this.toast(this.statusText);
    } finally {
      this.clearingContext = false;
    }
  }

  private parseStickerTags(value: string): string[] {
    const result: string[] = [];
    value.split(/[,，\s]+/).forEach((item: string) => {
      const tag = item.trim();
      if (tag.length > 0 && !result.includes(tag)) result.push(tag);
    });
    return result;
  }

  private async copyMediaUriToCache(
    context: common.UIAbilityContext,
    sourceUri: string,
    fileName: string
  ): Promise<string> {
    const safeName = fileName.replace(/[^a-zA-Z0-9._-]/g, '_');
    const targetPath = `${context.cacheDir}/echo-sticker-${Date.now()}-${safeName}`;
    const source = await fs.open(sourceUri, fs.OpenMode.READ_ONLY);
    let target: fs.File | undefined;
    try {
      target = await fs.open(
        targetPath,
        fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.TRUNC
      );
      const buffer = new ArrayBuffer(1024 * 1024);
      while (true) {
        const bytesRead = await fs.read(source.fd, buffer);
        if (bytesRead <= 0) break;
        await fs.write(target.fd, buffer, { length: bytesRead });
      }
      console.info(`[EchoUpload] copied media URI to ${targetPath}`);
      return targetPath;
    } finally {
      await fs.close(source);
      if (target !== undefined) await fs.close(target);
    }
  }

  private async chooseStickerImage(): Promise<void> {
    try {
      const picker = new photoAccessHelper.PhotoViewPicker();
      const result = await picker.select({
        MIMEType: photoAccessHelper.PhotoViewMIMETypes.IMAGE_TYPE,
        maxSelectNumber: 1
      });
      if (!result.photoUris || result.photoUris.length === 0) return;
      const uri = result.photoUris[0];
      const context = getContext(this) as common.UIAbilityContext;
      const helper = photoAccessHelper.getPhotoAccessHelper(context);
      const predicates = new dataSharePredicates.DataSharePredicates();
      predicates.equalTo(photoAccessHelper.PhotoKeys.URI, uri);
      const assets = await helper.getAssets({
        fetchColumns: [
          photoAccessHelper.PhotoKeys.URI,
          photoAccessHelper.PhotoKeys.DISPLAY_NAME
        ],
        predicates
      });
      const asset = await assets.getFirstObject();
      const sourceUri = asset.uri;
      const name = asset.displayName || decodeURIComponent(uri.substring(uri.lastIndexOf('/') + 1)) || 'sticker.jpg';
      const lower = name.toLowerCase();
      this.stickerUploadUri = uri;
      this.stickerUploadFilePath = await this.copyMediaUriToCache(context, sourceUri, name);
      this.stickerUploadName = name;
      this.stickerUploadType = lower.endsWith('.png') ? 'image/png'
        : lower.endsWith('.gif') ? 'image/gif'
          : lower.endsWith('.webp') ? 'image/webp' : 'image/jpeg';
      if (!['.png', '.jpg', '.jpeg', '.gif', '.webp'].some((suffix: string) => lower.endsWith(suffix))) {
        this.toast('仅支持 PNG、JPG、GIF 或 WebP 图片');
        return;
      }
      this.uploadDescription = '';
      this.uploadTags = '';
      this.stickerUploadOpen = true;
    } catch (error) {
      this.toast(`无法打开相册：${String(error)}`);
    }
  }

  private async saveSticker(): Promise<void> {
    const description = this.uploadDescription.trim();
    const tags = this.parseStickerTags(this.uploadTags);
    if (this.stickerUploadFilePath.length === 0) {
      this.toast('请先选择图片');
      return;
    }
    if (description.length === 0 || description.length > 300) {
      this.toast('请填写 300 字以内的表情包描述');
      return;
    }
    if (tags.length === 0 || this.uploadTags.length > 300) {
      this.toast('请填写 300 字以内的语义标签');
      return;
    }
    this.stickerSaving = true;
    try {
      await this.repository?.uploadSticker(
        this.stickerUploadFilePath,
        this.stickerUploadName,
        this.stickerUploadType,
        description,
        tags
      );
      this.stickerUploadOpen = false;
      await this.loadPageData();
      this.toast('表情包已保存');
    } catch (error) {
      this.statusText = `上传失败：${this.describeError(error)}`;
      this.toast(this.statusText);
    } finally {
      if (this.stickerUploadFilePath.length > 0) {
        try {
          await fs.unlink(this.stickerUploadFilePath);
        } catch (_) {
          console.warn(`[EchoUpload] failed to remove cache file ${this.stickerUploadFilePath}`);
        }
        this.stickerUploadFilePath = '';
      }
      this.stickerSaving = false;
    }
  }

  private stickerCanDelete(sticker: StickerItem): boolean {
    return sticker.ownerType === 'user' || sticker.source === 'uploaded';
  }

  private async deleteSticker(sticker: StickerItem): Promise<void> {
    if (!this.repository || !this.stickerCanDelete(sticker)) return;
    try {
      await this.repository.deleteSticker(sticker.stickerId);
      this.stickers = this.stickers.filter((item: StickerItem) => item.stickerId !== sticker.stickerId);
      this.toast('表情包已删除');
    } catch (error) {
      this.statusText = `删除失败：${this.describeError(error)}`;
    }
  }

  @Builder
  private stickersPage(): void {
    Stack() {
      Column() {
        Row() {
          this.iconButton($r('app.media.arrow_back_outline'), () => this.navigate('chat'))
          Text(`表情包库 (${this.stickers.length})`)
            .fontSize(22)
            .fontWeight(FontWeight.Bold)
            .fontColor('#262331')
            .layoutWeight(1)
            .margin({ left: 4 })
          this.iconButton($r('app.media.refresh_outline'), () => void this.loadPageData())
          this.iconButton($r('app.media.add_photo_outline'), () => void this.chooseStickerImage())
        }
        .width('100%')
        .height(64)
        .padding({ left: 10, right: 6 })
        .backgroundColor('#F8F7FC')
        if (this.loading && this.stickers.length === 0) {
          Column() {
            Text('正在加载表情包').fontSize(16).fontColor('#6F6A78')
          }
          .layoutWeight(1)
          .width('100%')
          .justifyContent(FlexAlign.Center)
        } else if (this.stickers.length === 0) {
          Column({ space: 10 }) {
            Image($r('app.media.emoji_outline')).width(44).height(44)
            Text('还没有表情包').fontSize(18).fontColor('#49454F')
            Text('点击右上角添加一张图片').fontSize(14).fontColor('#6F6A78')
          }
          .layoutWeight(1)
          .width('100%')
          .justifyContent(FlexAlign.Center)
        } else {
          Grid() {
            ForEach(this.stickers, (sticker: StickerItem) => {
              GridItem() {
                Column({ space: 8 }) {
                  if (sticker.imageUrl.length > 0) {
                    Image(sticker.imageUrl)
                      .width('100%')
                      .height(142)
                      .objectFit(ImageFit.Contain)
                      .backgroundColor('#F3F1F6')
                      .borderRadius(6)
                  } else {
                    Text('图片加载失败')
                      .fontSize(12)
                      .fontColor('#6F6A78')
                      .width('100%')
                      .height(142)
                      .textAlign(TextAlign.Center)
                      .backgroundColor('#F3F1F6')
                      .borderRadius(6)
                  }
                  Text(sticker.description || '未命名表情')
                    .fontSize(14)
                    .fontColor('#262331')
                    .maxLines(1)
                    .textOverflow({ overflow: TextOverflow.Ellipsis })
                    .width('100%')
                  Row() {
                    Text(`${sticker.ownerType === 'user' ? '我保存的' : 'Echo'} · ${sticker.source || '未知'}`)
                      .fontSize(11).fontColor('#6F6A78').layoutWeight(1).maxLines(1)
                    if (this.stickerCanDelete(sticker)) {
                      Button() {
                        Image($r('app.media.delete_outline'))
                          .width(20)
                          .height(20)
                      }
                        .width(32)
                        .height(32)
                        .backgroundColor(Color.Transparent)
                        .onClick(() => void this.deleteSticker(sticker))
                    }
                  }.width('100%')
                }
                .width('100%')
                .height(220)
                .padding(10)
                .backgroundColor('#FFFFFF')
                .border({ width: 1, color: '#E3E0E8' })
                .borderRadius(8)
              }
            }, (sticker: StickerItem) => sticker.stickerId)
          }
          .columnsTemplate('1fr 1fr')
          .rowsGap(12)
          .columnsGap(12)
          .layoutWeight(1)
          .width('100%')
          .padding({ left: 16, right: 16, top: 16, bottom: 24 })
        }
      }
      .width('100%')
      .height('100%')
      if (this.stickerUploadOpen) this.stickerUploadDialog()
    }
    .width('100%')
    .height('100%')
  }

  @Builder
  private stickerUploadDialog(): void {
    Stack() {
      Column().width('100%').height('100%').backgroundColor('#66000000').onClick(() => {
        if (!this.stickerSaving) this.stickerUploadOpen = false;
      })
      Column({ space: 14 }) {
        Text('完善表情包信息').fontSize(20).fontWeight(FontWeight.Bold).fontColor('#262331')
        if (this.stickerUploadUri.length > 0) {
          Image(this.stickerUploadUri).width(120).height(120).objectFit(ImageFit.Contain)
            .backgroundColor('#F3F1F6').borderRadius(8)
        }
        TextInput({ placeholder: '描述，例如：开心地挥手', text: this.uploadDescription })
          .maxLength(300).onChange((value: string) => this.uploadDescription = value)
        TextInput({ placeholder: '语义标签，例如：开心，挥手', text: this.uploadTags })
          .maxLength(300).onChange((value: string) => this.uploadTags = value)
        Row({ space: 12 }) {
          Button('取消').layoutWeight(1).enabled(!this.stickerSaving)
            .onClick(() => this.stickerUploadOpen = false)
          Button(this.stickerSaving ? '上传中' : '保存').layoutWeight(1).enabled(!this.stickerSaving)
            .onClick(() => void this.saveSticker())
        }.width('100%')
      }
      .width('88%')
      .padding(20)
      .backgroundColor('#FFFBFE')
      .borderRadius(16)
    }
    .width('100%')
    .height('100%')
    .zIndex(30)
  }

  @Builder
  private personaOption(choice: PersonaChoice, selected: string, action: () => void): void {
    Button(choice.label)
      .fontSize(14)
      .fontColor(choice.value === selected ? '#FFFFFF' : '#49454F')
      .backgroundColor(choice.value === selected ? '#6750A4' : '#F0EDF5')
      .borderRadius(20)
      .height(40)
      .padding({ left: 16, right: 16 })
      .onClick(action)
  }

  @Builder
  private personaChoiceRow(
    choices: PersonaChoice[],
    selected: string,
    action: (value: string) => void
  ): void {
    Row({ space: 8 }) {
      ForEach(choices, (choice: PersonaChoice) => {
        this.personaOption(choice, selected, () => action(choice.value))
      }, (choice: PersonaChoice) => choice.value)
    }
    .width('100%')
  }

  @Builder
  private personaTopicChip(topic: string): void {
    Row({ space: 5 }) {
      Text(topic)
        .fontSize(14)
        .fontColor(this.personaTopicSelected(topic) ? '#FFFFFF' : '#49454F')
        .maxLines(1)
      if (!PERSONA_PRESET_TOPICS.includes(topic)) {
        Text('×')
          .fontSize(18)
          .fontColor(this.personaTopicSelected(topic) ? '#FFFFFF' : '#6F6A78')
          .onClick(() => this.removePersonaTopic(topic))
      }
    }
    .height(38)
    .padding({ left: 12, right: 10 })
    .margin({ right: 8, bottom: 8 })
    .backgroundColor(this.personaTopicSelected(topic) ? '#6750A4' : '#F0EDF5')
    .borderRadius(19)
    .onClick(() => this.togglePersonaTopic(topic))
  }

  @Builder
  private personaSummary(): void {
    Column({ space: 12 }) {
      Text('和 Echo 的关系')
        .fontSize(17)
        .fontWeight(FontWeight.Medium)
        .fontColor('#262331')
        .width('100%')
      Text('相处方式由你选择，熟悉程度随交流积累。选择后立即生效。')
        .fontSize(13).lineHeight(19).fontColor('#6F6A78').width('100%')
      if (this.relationshipState === undefined) {
        if (this.loading) {
          LoadingProgress().width(24).height(24).color('#6750A4')
        } else {
          Row({ space: 8 }) {
            Text('关系进度加载失败').fontSize(14).fontColor('#BA1A1A').layoutWeight(1)
            Button('重试').fontSize(13).backgroundColor(Color.Transparent).fontColor('#6750A4')
              .onClick(() => void this.loadPageData())
          }.width('100%')
        }
      } else {
        Row({ space: 8 }) {
          ForEach(RELATIONSHIP_MODES, (choice: PersonaChoice) => {
            this.personaOption(choice, this.relationshipState?.relationshipMode || 'friend',
              () => void this.updateRelationshipMode(choice.value))
          }, (choice: PersonaChoice) => choice.value)
          if (this.relationshipModeSaving) {
            LoadingProgress().width(20).height(20).color('#6750A4')
          }
        }.width('100%').enabled(!this.relationshipModeSaving && !this.personaSaving)
        Row({ space: 8 }) {
          Column({ space: 4 }) {
            Text('熟悉程度').fontSize(12).fontColor('#6F6A78')
            Text(relationshipStageLabel(this.relationshipState.stage))
              .fontSize(15).fontColor('#262331').maxLines(1)
          }.layoutWeight(1).padding(12).backgroundColor('#FFFFFF').borderRadius(10)
          Column({ space: 4 }) {
            Text('互动').fontSize(12).fontColor('#6F6A78')
            Text(`${this.relationshipState.interactionTurns} 次`)
              .fontSize(15).fontColor('#262331')
          }.layoutWeight(1).padding(12).backgroundColor('#FFFFFF').borderRadius(10)
          Column({ space: 4 }) {
            Text('活跃').fontSize(12).fontColor('#6F6A78')
            Text(`${this.relationshipState.activeDays} 天`)
              .fontSize(15).fontColor('#262331')
          }.layoutWeight(1).padding(12).backgroundColor('#FFFFFF').borderRadius(10)
        }.width('100%')
      }
    }
    .width('100%').padding(16).backgroundColor('#F0EDF5').borderRadius(16)
  }

  @Builder
  private personaConfirmDialog(): void {
    Stack() {
      Column()
        .width('100%')
        .height('100%')
        .backgroundColor('#88000000')
        .onClick(() => this.personaConfirmAction = '')
      Column({ space: 16 }) {
        Text(this.personaConfirmAction === 'persona' ? '恢复默认设置' : '重置关系')
          .fontSize(20)
          .fontWeight(FontWeight.Bold)
          .fontColor('#262331')
        Text(this.personaConfirmAction === 'persona'
          ? '只会重置个性化偏好，不会删除长期记忆或聊天记录。'
          : '聊天、长期记忆、关系、提醒和称呼边界都会清空，关系回到初识；账号、设备和你的称呼保留。这个操作不能撤销。')
          .fontSize(15)
          .lineHeight(22)
          .fontColor('#49454F')
          .width('100%')
        Row({ space: 12 }) {
          Button('取消')
            .layoutWeight(1)
            .backgroundColor('#F0EDF5')
            .fontColor('#49454F')
            .onClick(() => this.personaConfirmAction = '')
          Button(this.personaConfirmAction === 'persona' ? '恢复默认' : '重置关系')
            .layoutWeight(1)
            .backgroundColor('#6750A4')
            .fontColor(Color.White)
            .onClick(() => {
              if (this.personaConfirmAction === 'persona') void this.resetPersonaSettings();
              else void this.resetRelationshipProgress();
            })
        }.width('100%')
      }
      .width('88%')
      .padding(20)
      .backgroundColor('#FFFBFE')
      .borderRadius(16)
    }
    .width('100%')
    .height('100%')
    .zIndex(40)
  }

  private presenceStatusLabel(status: string): string {
    if (status === 'active') return '正在陪你';
    if (status === 'sleeping') return '安静着';
    if (status === 'focused') return '在专注';
    if (status === 'resting') return '低功耗';
    return '闲着';
  }

  private presenceRelative(value: string | undefined): string {
    if (value === undefined || value.length === 0) return '刚才';
    const time = new Date(value).getTime();
    if (Number.isNaN(time)) return '刚才';
    const minutes = Math.max(0, Math.floor((Date.now() - time) / 60000));
    if (minutes < 1) return '刚刚';
    if (minutes < 60) return `${minutes} 分钟前`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours} 小时前`;
    return `${Math.floor(hours / 24)} 天前`;
  }

  @Builder
  private presencePage(): void {
    Column() {
      Row() {
        this.iconButton($r('app.media.arrow_back_outline'), () => this.navigate('chat'))
        Text('她的状态')
          .fontSize(22)
          .fontWeight(FontWeight.Bold)
          .fontColor('#262331')
          .layoutWeight(1)
          .margin({ left: 4 })
        this.iconButton($r('app.media.refresh_outline'), () => void this.loadPageData())
      }
      .width('100%')
      .height(64)
      .padding({ left: 10, right: 10 })
      .backgroundColor('#F8F7FC')

      if (this.loading && this.presence === undefined) {
        Column({ space: 12 }) {
          LoadingProgress().width(32).height(32).color('#6750A4')
          Text('正在看她刚才在想什么').fontSize(14).fontColor('#6F6A78')
        }
        .width('100%')
        .layoutWeight(1)
        .justifyContent(FlexAlign.Center)
      } else if (this.presenceError.length > 0 && this.presence === undefined) {
        Column({ space: 12 }) {
          Text(this.presenceError).fontSize(14).fontColor('#BA1A1A').textAlign(TextAlign.Center)
          Button('重试').onClick(() => void this.loadPageData())
        }
        .width('100%')
        .layoutWeight(1)
        .justifyContent(FlexAlign.Center)
        .padding(24)
      } else {
        Scroll() {
          Column({ space: 16 }) {
            Column({ space: 8 }) {
              Row({ space: 8 }) {
                Text(this.presenceStatusLabel(this.presence?.status ?? 'idle'))
                  .fontSize(24)
                  .fontWeight(FontWeight.Bold)
                  .fontColor('#262331')
                Text(this.presence?.enabled === false ? '已暂停' : '持续在场')
                  .fontSize(12)
                  .fontColor('#6750A4')
                  .backgroundColor('#EDE7F6')
                  .borderRadius(10)
                  .padding({ left: 8, right: 8, top: 3, bottom: 3 })
              }
              .width('100%')
              Text('她独处时产生的内心念头，默认只留在这里，不会自动发到聊天。')
                .fontSize(13)
                .fontColor('#6F6A78')
                .width('100%')
              if ((this.presence?.lastThoughtAt ?? '').length > 0) {
                Text(`最近念头：${this.presenceRelative(this.presence?.lastThoughtAt)}`)
                  .fontSize(12)
                  .fontColor('#6F6A78')
                  .width('100%')
              }
            }
            .width('100%')
            .padding(16)
            .backgroundColor('#FFFBFE')
            .borderRadius(16)

            Column({ space: 8 }) {
              Row() {
                Text('今天的念头').fontSize(14).fontWeight(FontWeight.Medium)
                Blank()
                Text(`${this.presence?.thoughtsUsed ?? 0} / ${this.presence?.dailyThoughtBudget ?? 8}`)
                  .fontSize(13)
                  .fontColor('#6F6A78')
              }
              .width('100%')
              Text('心跳每 15 分钟检查一次；只有值得的时候才会留下一个念头。')
                .fontSize(12)
                .fontColor('#6F6A78')
                .width('100%')
            }
            .width('100%')
            .padding(16)
            .backgroundColor('#FFFBFE')
            .borderRadius(16)

            Row() {
              Text('内心念头').fontSize(17).fontWeight(FontWeight.Bold).fontColor('#262331')
              Blank()
              Text(`${this.presence?.thoughts.length ?? 0} 条`).fontSize(12).fontColor('#6F6A78')
            }
            .width('100%')

            if ((this.presence?.thoughts.length ?? 0) === 0) {
              Column({ space: 8 }) {
                Text('还没有独处念头').fontSize(15).fontWeight(FontWeight.Medium)
                Text('等她安静一会儿，这里会出现她刚才在想的事。')
                  .fontSize(12)
                  .fontColor('#6F6A78')
                  .textAlign(TextAlign.Center)
              }
              .width('100%')
              .padding({ top: 34, bottom: 34, left: 20, right: 20 })
              .backgroundColor('#FFFBFE')
              .borderRadius(16)
            } else {
              ForEach(this.presence?.thoughts ?? [], (thought: PresenceThought) => {
                Column({ space: 8 }) {
                  Text(thought.text)
                    .fontSize(15)
                    .fontColor('#262331')
                    .lineHeight(23)
                    .width('100%')
                  Row({ space: 6 }) {
                    Text(`◷ ${this.presenceRelative(thought.createdAt)}`)
                      .fontSize(11)
                      .fontColor('#8B8794')
                    Blank()
                    if (thought.salience >= 0.6) {
                      Text('记得比较深').fontSize(11).fontColor('#6750A4')
                    }
                  }
                  .width('100%')
                }
                .width('100%')
                .padding(16)
                .backgroundColor('#FFFBFE')
                .borderRadius(16)
              }, (thought: PresenceThought) => thought.thoughtId)
            }
          }
          .width('100%')
          .padding({ left: 16, right: 16, top: 16, bottom: 32 })
        }
        .layoutWeight(1)
        .width('100%')
      }
    }
    .width('100%')
    .height('100%')
    .backgroundColor('#F8F7FC')
  }

  @Builder
  private aboutHerPage(): void {
    Stack() {
      Column() {
        Row() {
          this.iconButton($r('app.media.arrow_back_outline'), () => this.navigate('chat'))
          Text('关于她')
            .fontSize(20)
            .fontWeight(FontWeight.Bold)
            .fontColor('#262331')
            .layoutWeight(1)
            .margin({ left: 4 })
          this.iconButton($r('app.media.refresh_outline'), () => void this.loadPageData())
        }
        .width('100%')
        .height(64)
        .padding({ left: 10, right: 10 })
        .backgroundColor('#F8F7FC')

        Scroll() {
          Column({ space: 20 }) {
            Row({ space: 14 }) {
              Text('鲸')
                .fontSize(30)
                .fontColor('#6750A4')
                .width(52)
                .height(52)
                .textAlign(TextAlign.Center)
                .backgroundColor('#F0EDF5')
                .borderRadius(26)
              Column({ space: 5 }) {
                Text('Echo · AI 陪伴伙伴')
                  .fontSize(22)
                  .fontWeight(FontWeight.Bold)
                  .fontColor('#262331')
                Text('关系由相处慢慢形成，不用在这里调整人格。')
                  .fontSize(13)
                  .fontColor('#6F6A78')
                  .width('100%')
              }
              .layoutWeight(1)
              .alignItems(HorizontalAlign.Start)
            }
            .width('100%')

            if (this.relationshipState === undefined) {
              if (this.loading) {
                LoadingProgress().width(28).height(28).color('#6750A4')
              } else {
                Row({ space: 8 }) {
                  Text('关系加载失败').fontSize(14).fontColor('#BA1A1A').layoutWeight(1)
                  Button('重试').fontSize(13).backgroundColor(Color.Transparent).fontColor('#6750A4')
                    .onClick(() => void this.loadPageData())
                }.width('100%')
              }
            } else {
              Column({ space: 14 }) {
                Text('关系')
                  .fontSize(13)
                  .fontColor('#6F6A78')
                  .width('100%')
                Text(relationshipTypeLabel(this.relationshipState.relationshipType))
                  .fontSize(30)
                  .fontWeight(FontWeight.Bold)
                  .fontColor('#262331')
                  .width('100%')
                Row({ space: 10 }) {
                  Column({ space: 4 }) {
                    Text('互动').fontSize(12).fontColor('#6F6A78')
                    Text(`${this.relationshipState.interactionTurns} 次`)
                      .fontSize(16).fontColor('#262331')
                  }.layoutWeight(1).padding(12).backgroundColor('#FFFFFF').borderRadius(10)
                  Column({ space: 4 }) {
                    Text('活跃').fontSize(12).fontColor('#6F6A78')
                    Text(`${this.relationshipState.activeDays} 天`)
                      .fontSize(16).fontColor('#262331')
                  }.layoutWeight(1).padding(12).backgroundColor('#FFFFFF').borderRadius(10)
                }.width('100%')
              }
              .width('100%')
              .padding(18)
              .backgroundColor('#F0EDF5')
              .borderRadius(16)

              if (this.relationshipState.pendingProposal !== undefined) {
                Column({ space: 10 }) {
                  Text('Echo 在等你回应')
                    .fontSize(16)
                    .fontWeight(FontWeight.Medium)
                    .fontColor('#262331')
                  Text(`她想和你确认：做${this.relationshipState.pendingProposal.directionLabel}吗？`)
                    .fontSize(14)
                    .fontColor('#49454F')
                  Button('查看确认窗口')
                    .width('100%')
                    .height(44)
                    .fontColor(Color.White)
                    .backgroundColor('#6750A4')
                    .onClick(() => {
                      this.pendingRelationshipProposal = this.relationshipState?.pendingProposal;
                      this.proposalDialogVisible = true;
                    })
                }
                .width('100%')
                .padding(16)
                .backgroundColor('#FFF4E8')
                .borderRadius(14)
              }
            }

            Text('称呼、聊天方式等个性化设置不再放在这里；关系会随着真实交流自然变化。')
              .fontSize(13)
              .lineHeight(20)
              .fontColor('#6F6A78')
              .width('100%')

            Button('重置关系')
              .width('100%')
              .height(46)
              .backgroundColor('#F0EDF5')
              .fontColor('#BA1A1A')
              .enabled(!this.personaSaving)
              .onClick(() => this.personaConfirmAction = 'relationship')
            Text('会清空聊天、长期记忆、关系、提醒和称呼边界，只保留账号、设备与你的称呼。')
              .fontSize(13)
              .lineHeight(20)
              .fontColor('#6F6A78')
              .width('100%')

            if (this.personaError.length > 0) {
              Text(this.personaError)
                .fontSize(13)
                .lineHeight(20)
                .fontColor('#BA1A1A')
                .width('100%')
            }
          }
          .width('100%')
          .padding({ left: 20, right: 20, top: 20, bottom: 32 })
        }
        .layoutWeight(1)
        .width('100%')
        .scrollable(ScrollDirection.Vertical)
        .scrollBar(BarState.Auto)
      }
      .width('100%')
      .height('100%')
      if (this.personaConfirmAction.length > 0) {
        this.personaConfirmDialog()
      }
    }
    .width('100%')
    .height('100%')
  }

  @Builder
  private relationshipProposalDialog(): void {
    Stack() {
      Column()
        .width('100%')
        .height('100%')
        .backgroundColor('#88000000')
        .onClick(() => this.proposalDialogVisible = false)
      Column({ space: 14 }) {
        Text('和 Echo 的关系')
          .fontSize(22)
          .fontWeight(FontWeight.Bold)
          .fontColor('#262331')
        Text(this.pendingRelationshipProposal === undefined
          ? 'Echo 想和你确认一件事。'
          : `Echo 想和你确认：从现在开始，做${relationshipDirectionLabel(this.pendingRelationshipProposal.direction)}吗？`)
          .fontSize(16)
          .lineHeight(24)
          .fontColor('#49454F')
          .width('100%')
        Text('确认后，关于她页面会更新你们的关系。')
          .fontSize(13)
          .fontColor('#6F6A78')
          .width('100%')
        Button(this.relationshipModeSaving ? '确认中…' : '愿意')
          .width('100%')
          .height(46)
          .fontColor(Color.White)
          .backgroundColor(this.relationshipModeSaving ? '#A99BC7' : '#6750A4')
          .enabled(!this.relationshipModeSaving)
          .onClick(() => void this.acceptRelationshipProposal())
        Button('再想想')
          .width('100%')
          .height(44)
          .backgroundColor('#F0EDF5')
          .fontColor('#49454F')
          .enabled(!this.relationshipModeSaving)
          .onClick(() => void this.deferRelationshipProposal())
      }
      .width('84%')
      .padding(22)
      .backgroundColor('#FFFBFE')
      .borderRadius(20)
    }
    .width('100%')
    .height('100%')
    .alignContent(Alignment.Center)
    .zIndex(60)
  }

  @Builder
  private personaPage(): void {
    Stack() {
      Column() {
        Row() {
          this.iconButton($r('app.media.arrow_back_outline'), () => this.navigate('chat'))
          Text('个性化设置')
            .fontSize(20)
            .fontWeight(FontWeight.Bold)
            .fontColor('#262331')
            .layoutWeight(1)
            .margin({ left: 4 })
          Button() {
            Text('▤').fontSize(22).fontColor('#49454F')
          }
            .width(48)
            .height(48)
            .backgroundColor(Color.Transparent)
            .onClick(() => this.navigate('memory'))
          this.iconButton($r('app.media.refresh_outline'), () => void this.loadPageData())
        }
        .width('100%')
        .height(64)
        .padding({ left: 10, right: 10 })
        .backgroundColor('#F8F7FC')

        Scroll() {
          Column({ space: 20 }) {
            Row({ space: 14 }) {
              Text('调节')
                .fontSize(32)
                .fontColor('#6750A4')
                .width(46)
                .height(46)
                .textAlign(TextAlign.Center)
              Column({ space: 5 }) {
                Text('个性化设置')
                  .fontSize(24)
                  .fontWeight(FontWeight.Bold)
                  .fontColor('#262331')
                Text('这里的设置会影响文字聊天中的称呼、语气、关系节奏和长期记忆。')
                  .fontSize(14)
                  .lineHeight(21)
                  .fontColor('#6F6A78')
                  .width('100%')
              }
              .layoutWeight(1)
              .alignItems(HorizontalAlign.Start)
            }
            .width('100%')
            .alignItems(VerticalAlign.Top)

            this.personaSummary()

            Column({ space: 10 }) {
              Text('称呼').fontSize(17).fontWeight(FontWeight.Medium).fontColor('#262331')
              Text('先告诉 Echo 怎么称呼你')
                .fontSize(13).fontColor('#6F6A78')
              TextInput({ placeholder: '例如：小叶', text: this.personaProfile.preferredName })
                .maxLength(40)
                .height(48)
                .fontSize(16)
                .backgroundColor('#F0EDF5')
                .borderRadius(10)
                .onChange((value: string) => this.updatePersonaDraft({ preferredName: value }))
            }.width('100%')

            Column({ space: 10 }) {
              Text('聊天方式').fontSize(17).fontWeight(FontWeight.Medium).fontColor('#262331')
              this.personaChoiceRow(
                PERSONA_REPLY_STYLES,
                this.personaProfile.replyStyle,
                (value: string) => this.updatePersonaDraft({ replyStyle: value })
              )
            }.width('100%')

            Column({ space: 10 }) {
              Text('回复长度').fontSize(17).fontWeight(FontWeight.Medium).fontColor('#262331')
              this.personaChoiceRow(
                PERSONA_REPLY_LENGTHS,
                this.personaProfile.replyLength,
                (value: string) => this.updatePersonaDraft({ replyLength: value })
              )
            }.width('100%')

            Column({ space: 10 }) {
              Text('陪伴偏好').fontSize(17).fontWeight(FontWeight.Medium).fontColor('#262331')
              this.personaChoiceRow(
                PERSONA_SUPPORT_MODES,
                this.personaProfile.supportMode,
                (value: string) => this.updatePersonaDraft({ supportMode: value })
              )
            }.width('100%')

            Column({ space: 10 }) {
              Text('主动程度').fontSize(17).fontWeight(FontWeight.Medium).fontColor('#262331')
              this.personaChoiceRow(
                PERSONA_PROACTIVITY,
                this.personaProfile.proactivity,
                (value: string) => this.updatePersonaDraft({ proactivity: value })
              )
            }.width('100%')

            Column({ space: 10 }) {
              Text('关系节奏').fontSize(17).fontWeight(FontWeight.Medium).fontColor('#262331')
              this.personaChoiceRow(
                PERSONA_RELATIONSHIP_PACES,
                this.personaProfile.relationshipPace,
                (value: string) => this.updatePersonaDraft({ relationshipPace: value })
              )
            }.width('100%')

            Column({ space: 10 }) {
              Text('亲近表达').fontSize(17).fontWeight(FontWeight.Medium).fontColor('#262331')
              this.personaChoiceRow(
                PERSONA_AFFECTION_STYLES,
                this.personaProfile.affectionStyle,
                (value: string) => this.updatePersonaDraft({ affectionStyle: value })
              )
            }.width('100%')

            Column({ space: 10 }) {
              Text('避免话题').fontSize(17).fontWeight(FontWeight.Medium).fontColor('#262331')
              Text('最多 5 个，单个不超过 40 个字')
                .fontSize(13).fontColor('#6F6A78')
              Flex({ wrap: FlexWrap.Wrap }) {
                ForEach(PERSONA_PRESET_TOPICS, (topic: string) => {
                  this.personaTopicChip(topic)
                }, (topic: string) => topic)
                ForEach(this.personaProfile.avoidTopics.filter((topic: string) =>
                  !PERSONA_PRESET_TOPICS.includes(topic)), (topic: string) => {
                    this.personaTopicChip(topic)
                  }, (topic: string) => topic)
              }
              .width('100%')
              Row({ space: 8 }) {
                TextInput({ placeholder: '添加其他话题', text: this.personaCustomTopic })
                  .layoutWeight(1)
                  .height(44)
                  .backgroundColor('#F0EDF5')
                  .borderRadius(10)
                  .onChange((value: string) => this.personaCustomTopic = value)
                  .onSubmit(() => this.addPersonaTopic())
                Button('+ 添加')
                  .height(44)
                  .backgroundColor('#F0EDF5')
                  .fontColor('#49454F')
                  .onClick(() => this.addPersonaTopic())
              }.width('100%')
            }.width('100%')

            Column({ space: 10 }) {
              Text('关于你').fontSize(17).fontWeight(FontWeight.Medium).fontColor('#262331')
              Text('最多 300 个字')
                .fontSize(13).fontColor('#6F6A78')
              TextArea({ placeholder: '例如：最近在准备面试，希望聊天时少一点追问。', text: this.personaProfile.aboutUser })
                .maxLength(300)
                .height(112)
                .fontSize(15)
                .backgroundColor('#F0EDF5')
                .borderRadius(10)
                .onChange((value: string) => this.updatePersonaDraft({ aboutUser: value }))
            }.width('100%')

            Row() {
              Column({ space: 4 }) {
                Text('个性化开关').fontSize(17).fontWeight(FontWeight.Medium).fontColor('#262331')
                Text(this.personaProfile.enabled ? '当前已启用' : '关闭后使用默认交流方式')
                  .fontSize(13).fontColor('#6F6A78')
              }.layoutWeight(1).alignItems(HorizontalAlign.Start)
              Toggle({ type: ToggleType.Switch, isOn: this.personaProfile.enabled })
                .onChange((isOn: boolean) => this.updatePersonaDraft({ enabled: isOn }))
            }
            .width('100%')
            .padding({ top: 4, bottom: 4 })

            Button(this.personaSaving ? '保存中…' : '保存设置')
              .width('100%')
              .height(48)
              .fontSize(16)
              .fontColor(Color.White)
              .backgroundColor(this.personaSaving ? '#A99BC7' : '#6750A4')
              .enabled(!this.personaSaving)
              .onClick(() => void this.savePersona())

            Row({ space: 12 }) {
              Button('恢复默认')
                .layoutWeight(1)
                .height(44)
                .backgroundColor('#F0EDF5')
                .fontColor('#49454F')
                .enabled(!this.personaSaving)
                .onClick(() => this.personaConfirmAction = 'persona')
              Button('重置关系')
                .layoutWeight(1)
                .height(44)
                .backgroundColor('#F0EDF5')
                .fontColor('#49454F')
                .enabled(!this.personaSaving && !this.relationshipModeSaving)
                .onClick(() => this.personaConfirmAction = 'relationship')
            }.width('100%')

            if (this.personaError.length > 0) {
              Text(this.personaError)
                .fontSize(13)
                .lineHeight(20)
                .fontColor('#BA1A1A')
                .width('100%')
            }
          }
          .width('100%')
          .padding({ left: 20, right: 20, top: 20, bottom: 32 })
        }
        .layoutWeight(1)
        .width('100%')
        .scrollable(ScrollDirection.Vertical)
        .scrollBar(BarState.Auto)
      }
      .width('100%')
      .height('100%')
      if (this.personaConfirmAction.length > 0) {
        this.personaConfirmDialog()
      }
    }
    .width('100%')
    .height('100%')
  }

  @Builder
  private listPage(title: string, items: string[]): void {
    Column() {
      Row() {
        Button('返回').onClick(() => this.navigate('chat'))
        Text(title).fontSize(22).fontWeight(FontWeight.Bold).layoutWeight(1).margin({ left: 12 })
        Button('刷新').onClick(() => this.loadPageData())
      }
      .width('100%')
      .padding(16)
      List({ space: 8 }) {
        ForEach(items, (item: string) => {
          ListItem() {
            Text(item)
              .fontSize(16)
              .backgroundColor('#FFFFFF')
              .borderRadius(12)
              .padding(16)
              .width('100%')
          }
        })
      }
      .layoutWeight(1)
      .padding(16)
    }
  }

  @Builder
  private proactiveSwitchRow(
    title: string,
    subtitle: string,
    value: boolean,
    enabled: boolean,
    action: (value: boolean) => void
  ): void {
    Row() {
      Column({ space: 4 }) {
        Text(title)
          .fontSize(16)
          .fontColor(enabled ? '#262331' : '#98939F')
          .width('100%')
        Text(subtitle)
          .fontSize(13)
          .lineHeight(19)
          .fontColor(enabled ? '#6F6A78' : '#AAA5AF')
          .width('100%')
      }
      .layoutWeight(1)
      .alignItems(HorizontalAlign.Start)
      Toggle({ type: ToggleType.Switch, isOn: value })
        .enabled(enabled)
        .onChange((next: boolean) => action(next))
    }
    .width('100%')
    .padding({ top: 12, bottom: 12 })
    .opacity(enabled ? 1 : 0.45)
  }

  @Builder
  private proactiveDependentSwitchRow(
    preference: string,
    title: string,
    subtitle: string,
    action: (value: boolean) => void
  ): void {
    Row() {
      Column({ space: 4 }) {
        Text(title)
          .fontSize(16)
          .fontColor(this.proactivePreferences.enabled && !this.proactiveSaving ? '#262331' : '#98939F')
          .width('100%')
        Text(subtitle)
          .fontSize(13)
          .lineHeight(19)
          .fontColor(this.proactivePreferences.enabled && !this.proactiveSaving ? '#6F6A78' : '#AAA5AF')
          .width('100%')
      }
      .layoutWeight(1)
      .alignItems(HorizontalAlign.Start)
      Toggle({
        type: ToggleType.Switch,
        isOn: preference === 'scheduling'
          ? this.proactivePreferences.allowEchoScheduling
          : this.proactivePreferences.allowSpontaneousChat
      })
        .enabled(this.proactivePreferences.enabled && !this.proactiveSaving)
        .onChange((next: boolean) => action(next))
    }
    .width('100%')
    .padding({ top: 12, bottom: 12 })
    .opacity(this.proactivePreferences.enabled && !this.proactiveSaving ? 1 : 0.45)
  }

  @Builder
  private proactiveTimeDialogView(): void {
    Stack() {
      Column()
        .width('100%')
        .height('100%')
        .backgroundColor('#88000000')
        .onClick(() => this.proactiveTimeDialog = false)
      Column({ space: 16 }) {
        Text('安静时段')
          .fontSize(20)
          .fontWeight(FontWeight.Bold)
          .fontColor('#262331')
        Text('安静时段内，主动聊天和提醒会按照你的策略处理。')
          .fontSize(14)
          .lineHeight(21)
          .fontColor('#6F6A78')
          .width('100%')
        Row({ space: 10 }) {
          Column({ space: 6 }) {
            Text('开始').fontSize(13).fontColor('#6F6A78')
            TextInput({ placeholder: '22:30', text: this.quietStartDraft })
              .height(46)
              .fontSize(16)
              .backgroundColor('#F0EDF5')
              .borderRadius(10)
              .onChange((value: string) => this.quietStartDraft = value)
          }
          .layoutWeight(1)
          Column({ space: 6 }) {
            Text('结束').fontSize(13).fontColor('#6F6A78')
            TextInput({ placeholder: '08:00', text: this.quietEndDraft })
              .height(46)
              .fontSize(16)
              .backgroundColor('#F0EDF5')
              .borderRadius(10)
              .onChange((value: string) => this.quietEndDraft = value)
          }
          .layoutWeight(1)
        }
        .width('100%')
        Row({ space: 12 }) {
          Button('取消')
            .layoutWeight(1)
            .height(44)
            .backgroundColor('#F0EDF5')
            .fontColor('#49454F')
            .onClick(() => this.proactiveTimeDialog = false)
          Button(this.proactiveSaving ? '保存中…' : '保存')
            .layoutWeight(1)
            .height(44)
            .backgroundColor(this.proactiveSaving ? '#A99BC7' : '#6750A4')
            .fontColor(Color.White)
            .enabled(!this.proactiveSaving)
            .onClick(() => void this.saveQuietHours())
        }
        .width('100%')
      }
      .width('88%')
      .padding(20)
      .backgroundColor('#FFFBFE')
      .borderRadius(16)
    }
    .width('100%')
    .height('100%')
    .zIndex(40)
  }

  @Builder
  private proactivePage(): void {
    Stack() {
      Column() {
        Row() {
          this.iconButton($r('app.media.arrow_back_outline'), () => this.navigate('chat'))
          Text('主动聊天设置')
            .fontSize(22)
            .fontWeight(FontWeight.Bold)
            .fontColor('#262331')
            .layoutWeight(1)
            .margin({ left: 4 })
          this.iconButton($r('app.media.refresh_outline'), () => void this.loadPageData())
        }
        .width('100%')
        .height(64)
        .padding({ left: 10, right: 10 })
        .backgroundColor('#F8F7FC')

        Scroll() {
          Column({ space: 0 }) {
            this.proactiveSwitchRow(
              '主动聊天',
              '允许 Echo 在合适的时机发起文字消息',
              this.proactivePreferences.enabled,
              !this.proactiveSaving,
              (value: boolean) => void this.saveProactivePreferences({ enabled: value })
            )
            Row().width('100%').height(1).backgroundColor('#E7E0EC')
            this.proactiveDependentSwitchRow(
              'scheduling',
              '允许 Echo 安排后续问候',
              '例如在面试或重要行程之后再来问候一次',
              (value: boolean) => void this.saveProactivePreferences({ allowEchoScheduling: value })
            )
            this.proactiveDependentSwitchRow(
              'spontaneous',
              '允许自然主动聊天',
              '在你一段时间未互动后，Echo 可以尝试自然开场',
              (value: boolean) => void this.saveProactivePreferences({ allowSpontaneousChat: value })
            )

            Row({ space: 12 }) {
              Column({ space: 4 }) {
                Text(this.proactivePreferences.pauseIndefinite
                  ? '已暂停主动联系'
                  : (this.proactivePreferences.pausedUntil !== undefined
                    ? '已暂停主动联系'
                    : '暂停主动联系'))
                  .fontSize(16)
                  .fontColor('#262331')
                Text(this.proactivePreferences.pauseIndefinite
                  ? '直到你主动恢复'
                  : (this.proactivePreferences.pausedUntil !== undefined
                    ? `暂停到 ${this.proactivePreferences.pausedUntil}`
                    : '也可以在聊天里说“这两天别主动找我”'))
                  .fontSize(13)
                  .fontColor('#6F6A78')
              }
              .layoutWeight(1)
              .alignItems(HorizontalAlign.Start)
              Button(this.proactivePreferences.pauseIndefinite ||
                this.proactivePreferences.pausedUntil !== undefined ? '恢复' : '暂停两天')
                .height(40)
                .fontSize(14)
                .backgroundColor('#F0EDF5')
                .fontColor('#49454F')
                .enabled(!this.proactiveSaving)
                .onClick(() => {
                  if (this.proactivePreferences.pauseIndefinite ||
                    this.proactivePreferences.pausedUntil !== undefined) {
                    void this.resumeProactiveContact();
                  } else {
                    void this.pauseProactiveContact();
                  }
                })
            }
            .width('100%')
            .padding({ top: 12, bottom: 8 })

            Text('Echo 会在合适的时间自然联系，不需要反复调整频率。')
              .fontSize(13)
              .lineHeight(20)
              .fontColor('#6F6A78')
              .width('100%')
              .margin({ bottom: 8 })

            Row().width('100%').height(1).backgroundColor('#E7E0EC')
            Text('通知与安静时段')
              .fontSize(15)
              .fontWeight(FontWeight.Medium)
              .fontColor('#262331')
              .width('100%')
              .margin({ top: 16, bottom: 2 })
            this.proactiveSwitchRow(
              '显示通知正文',
              '默认隐藏，仅显示“Echo 发来了一条消息”',
              this.proactivePreferences.notificationPreview,
              !this.proactiveSaving,
              (value: boolean) => void this.saveProactivePreferences({ notificationPreview: value })
            )
            Row() {
              Column({ space: 4 }) {
                Text('安静时段')
                  .fontSize(16)
                  .fontColor('#262331')
                Text(`${this.proactivePreferences.quietStart} - ${this.proactivePreferences.quietEnd}`)
                  .fontSize(13)
                  .fontColor('#6F6A78')
              }
              .layoutWeight(1)
              .alignItems(HorizontalAlign.Start)
              Image($r('app.media.schedule_outline'))
                .width(24)
                .height(24)
            }
            .width('100%')
            .padding({ top: 12, bottom: 12 })
            .onClick(() => {
              if (!this.proactiveSaving) this.openQuietHours()
            })
            this.proactiveSwitchRow(
              '用户明确提醒不顺延',
              '关闭后，安静时段内的明确提醒会在安静时段结束后发送',
              this.proactivePreferences.explicitReminderQuietPolicy === 'honor',
              !this.proactiveSaving,
              (value: boolean) => void this.saveProactivePreferences({
                explicitReminderQuietPolicy: value ? 'honor' : 'defer'
              })
            )

            Row({ space: 12 }) {
              Image($r('app.media.event_note_outline'))
                .width(26)
                .height(26)
              Column({ space: 4 }) {
                Text('定时任务管理')
                  .fontSize(16)
                  .fontColor('#262331')
                  .width('100%')
                Text(this.schedules.length === 0
                  ? '查看 Echo 提醒和后续问候'
                  : `${this.schedules.length} 个进行中或暂停的任务`)
                  .fontSize(13)
                  .fontColor('#6F6A78')
                  .width('100%')
              }
              .layoutWeight(1)
              Image($r('app.media.chevron_right_outline'))
                .width(22)
                .height(22)
            }
            .width('100%')
            .padding({ top: 18, bottom: 12 })
            .onClick(() => this.openScheduledTasks())

            if (this.proactiveError.length > 0) {
              Text(this.proactiveError)
                .fontSize(13)
                .lineHeight(20)
                .fontColor('#BA1A1A')
                .width('100%')
                .margin({ top: 10 })
            }
          }
          .width('100%')
          .padding({ left: 20, right: 20, top: 12, bottom: 32 })
        }
        .layoutWeight(1)
        .width('100%')
        .scrollable(ScrollDirection.Vertical)
        .scrollBar(BarState.Auto)
      }
      .width('100%')
      .height('100%')
      if (this.proactiveTimeDialog) {
        this.proactiveTimeDialogView()
      }
    }
    .width('100%')
    .height('100%')
  }

  @Builder
  private scheduleRow(schedule: ChatSchedule): void {
    Row({ space: 10 }) {
      Column({ space: 5 }) {
        Text(this.scheduleDisplayLabel(schedule))
          .fontSize(16)
          .fontColor('#262331')
          .width('100%')
          .maxLines(2)
          .textOverflow({ overflow: TextOverflow.Ellipsis })
        Text(`${this.scheduleTypeLabel(schedule.scheduleType)} · ${this.scheduleDateLabel(schedule.nextRunAt)} · ${this.scheduleStatusLabel(schedule.status)}`)
          .fontSize(13)
          .fontColor('#6F6A78')
          .width('100%')
          .maxLines(2)
        if (schedule.intent.length > 0 && schedule.userVisibleLabel.trim().length > 0 &&
          schedule.intent.trim() !== schedule.userVisibleLabel.trim()) {
          Text(schedule.intent)
            .fontSize(12)
            .fontColor('#98939F')
            .width('100%')
            .maxLines(1)
            .textOverflow({ overflow: TextOverflow.Ellipsis })
        }
      }
      .layoutWeight(1)
      .alignItems(HorizontalAlign.Start)
      this.iconButton(
        schedule.status === 'active'
          ? $r('app.media.pause_outline')
          : $r('app.media.play_outline'),
        () => void this.toggleSchedule(schedule)
      )
      this.iconButton($r('app.media.delete_outline'), () => this.requestDeleteSchedule(schedule.scheduleId))
    }
    .width('100%')
    .padding({ top: 14, bottom: 14 })
  }

  @Builder
  private scheduleConfirmDialog(): void {
    Stack() {
      Column()
        .width('100%')
        .height('100%')
        .backgroundColor('#88000000')
        .onClick(() => this.scheduleConfirmId = '')
      Column({ space: 16 }) {
        Text('删除这个定时任务？')
          .fontSize(20)
          .fontWeight(FontWeight.Bold)
          .fontColor('#262331')
        Text('删除后 Echo 不会再执行这个任务。')
          .fontSize(15)
          .lineHeight(22)
          .fontColor('#49454F')
          .width('100%')
        Row({ space: 12 }) {
          Button('取消')
            .layoutWeight(1)
            .backgroundColor('#F0EDF5')
            .fontColor('#49454F')
            .onClick(() => this.scheduleConfirmId = '')
          Button(this.proactiveSaving ? '删除中…' : '删除任务')
            .layoutWeight(1)
            .backgroundColor('#6750A4')
            .fontColor(Color.White)
            .enabled(!this.proactiveSaving)
            .onClick(() => void this.confirmDeleteSchedule())
        }
        .width('100%')
      }
      .width('88%')
      .padding(20)
      .backgroundColor('#FFFBFE')
      .borderRadius(16)
    }
    .width('100%')
    .height('100%')
    .zIndex(40)
  }

  @Builder
  private tasksPage(): void {
    Stack() {
      Column() {
        Row() {
          this.iconButton($r('app.media.arrow_back_outline'), () => this.navigate(this.tasksReturnPage))
          Text('定时任务')
            .fontSize(22)
            .fontWeight(FontWeight.Bold)
            .fontColor('#262331')
            .layoutWeight(1)
            .margin({ left: 4 })
          this.iconButton($r('app.media.refresh_outline'), () => void this.loadPageData())
        }
        .width('100%')
        .height(64)
        .padding({ left: 10, right: 10 })
        .backgroundColor('#F8F7FC')

        if (this.loading && this.schedules.length === 0) {
          Column({ space: 10 }) {
            LoadingProgress().width(30).height(30).color('#6750A4')
            Text('正在加载定时任务').fontSize(14).fontColor('#6F6A78')
          }
          .layoutWeight(1)
          .width('100%')
          .justifyContent(FlexAlign.Center)
        } else if (this.schedules.length === 0) {
          Column({ space: 12 }) {
            Image($r('app.media.event_available_outline'))
              .width(48)
              .height(48)
            Text('还没有定时任务')
              .fontSize(18)
              .fontColor('#49454F')
            Text('你可以在聊天里说“晚上八点提醒我喝水”。')
              .fontSize(14)
              .fontColor('#6F6A78')
              .textAlign(TextAlign.Center)
          }
          .layoutWeight(1)
          .width('100%')
          .justifyContent(FlexAlign.Center)
        } else {
          List({ space: 0 }) {
            ForEach(this.schedules, (schedule: ChatSchedule) => {
              ListItem() {
                this.scheduleRow(schedule)
              }
            }, (schedule: ChatSchedule) => schedule.scheduleId)
          }
          .layoutWeight(1)
          .width('100%')
          .padding({ left: 20, right: 20, top: 6, bottom: 20 })
          .scrollBar(BarState.Auto)
        }
        if (this.proactiveError.length > 0) {
          Text(this.proactiveError)
            .fontSize(13)
            .lineHeight(20)
            .fontColor('#BA1A1A')
            .width('100%')
            .padding({ left: 20, right: 20, bottom: 16 })
        }
      }
      .width('100%')
      .height('100%')
      if (this.scheduleConfirmId.length > 0) {
        this.scheduleConfirmDialog()
      }
    }
    .width('100%')
    .height('100%')
  }

  @Builder
  private memoryTag(label: string, emphasized: boolean = false): void {
    Text(label)
      .fontSize(12)
      .fontColor(emphasized ? '#6750A4' : '#49454F')
      .backgroundColor(emphasized ? '#E8DEF8' : '#F0EDF5')
      .borderRadius(14)
      .padding({ left: 9, right: 9, top: 6, bottom: 6 })
  }

  @Builder
  private memoryCard(memory: MemoryRecord): void {
    Column({ space: 10 }) {
      Row({ space: 8 }) {
        Flex({ wrap: FlexWrap.Wrap }) {
          this.memoryTag(this.memoryTypeLabel(memory.memoryType), true)
          this.memoryTag(`重要度 ${memory.importance}`)
          this.memoryTag(`置信 ${this.memoryConfidenceLabel(memory.confidence)}`)
          this.memoryTag(this.memoryUpdatedLabel(memory.updatedAt))
        }
        .layoutWeight(1)
        if (this.memoryTab === 'active') {
          if (this.memoryDeletingId === memory.memoryId) {
            LoadingProgress()
              .width(22)
              .height(22)
              .color('#6750A4')
          } else {
            Button() {
              Image($r('app.media.delete_outline'))
                .width(24)
                .height(24)
            }
              .width(40)
              .height(40)
              .backgroundColor(Color.Transparent)
              .enabled(this.memoryDeletingId.length === 0)
              .onClick(() => this.requestDeleteMemory(memory.memoryId))
          }
        }
      }
      Text(memory.content)
        .fontSize(16)
        .lineHeight(24)
        .fontColor('#262331')
        .width('100%')
        .maxLines(4)
        .textOverflow({ overflow: TextOverflow.Ellipsis })
      Row({ space: 8 }) {
        this.memoryTag(this.memoryStatusLabel(memory.status))
        if (memory.sourceMessageId !== undefined) {
          this.memoryTag(`来源 #${memory.sourceMessageId}`)
        }
      }
      .width('100%')
    }
    .width('100%')
    .padding(16)
    .backgroundColor('#FFFFFF')
    .borderRadius(14)
  }

  @Builder
  private memoryConfirmDialog(): void {
    Stack() {
      Column()
        .width('100%')
        .height('100%')
        .backgroundColor('#88000000')
        .onClick(() => {
          this.memoryConfirmAction = '';
          this.memoryConfirmId = '';
        })
      Column({ space: 16 }) {
        Text(this.memoryConfirmAction === 'clear' ? '清空长期记忆' : '删除这条记忆')
          .fontSize(20)
          .fontWeight(FontWeight.Bold)
          .fontColor('#262331')
        Text(this.memoryConfirmAction === 'clear'
          ? '只会清空有效的长期记忆，不会删除聊天记录。'
          : '删除后，Echo 不会继续使用这条长期记忆。')
          .fontSize(15)
          .lineHeight(22)
          .fontColor('#49454F')
          .width('100%')
        Row({ space: 12 }) {
          Button('取消')
            .layoutWeight(1)
            .backgroundColor('#F0EDF5')
            .fontColor('#49454F')
            .onClick(() => {
              this.memoryConfirmAction = '';
              this.memoryConfirmId = '';
            })
          Button(this.memoryConfirmAction === 'clear' ? '清空' : '删除')
            .layoutWeight(1)
            .backgroundColor('#6750A4')
            .fontColor(Color.White)
            .onClick(() => void this.confirmMemoryAction())
        }
        .width('100%')
      }
      .width('88%')
      .padding(20)
      .backgroundColor('#FFFBFE')
      .borderRadius(16)
    }
    .width('100%')
    .height('100%')
    .zIndex(40)
  }

  @Builder
  private memoryPage(): void {
    Stack() {
      Column() {
        Row() {
          this.iconButton($r('app.media.arrow_back_outline'), () => this.navigate('chat'))
          Text(`长期记忆 (${this.memoryCount})`)
            .fontSize(22)
            .fontWeight(FontWeight.Bold)
            .fontColor('#262331')
            .layoutWeight(1)
            .margin({ left: 4 })
          this.iconButton($r('app.media.refresh_outline'), () => void this.loadPageData())
          Button() {
            Image($r('app.media.delete_sweep_outline'))
              .width(26)
              .height(26)
          }
            .width(48)
            .height(48)
            .backgroundColor(Color.Transparent)
            .enabled(this.memoryTab === 'active' && this.memories.length > 0 && !this.loading)
            .onClick(() => this.requestClearMemories())
        }
        .width('100%')
        .height(64)
        .padding({ left: 10, right: 10 })
        .backgroundColor('#F8F7FC')

        Row({ space: 10 }) {
          Button() {
            Row({ space: 6 }) {
              Image($r('app.media.inbox_outline')).width(20).height(20)
              Text('有效').fontSize(14)
            }
          }
            .layoutWeight(1)
            .height(44)
            .fontColor(this.memoryTab === 'active' ? '#6750A4' : '#49454F')
            .backgroundColor(this.memoryTab === 'active' ? '#E8DEF8' : '#F0EDF5')
            .onClick(() => void this.switchMemoryTab('active'))
          Button() {
            Row({ space: 6 }) {
              Image($r('app.media.delete_outline')).width(20).height(20)
              Text('已删除').fontSize(14)
            }
          }
            .layoutWeight(1)
            .height(44)
            .fontColor(this.memoryTab === 'deleted' ? '#6750A4' : '#49454F')
            .backgroundColor(this.memoryTab === 'deleted' ? '#E8DEF8' : '#F0EDF5')
            .onClick(() => void this.switchMemoryTab('deleted'))
          Text(`${this.memories.length}/${this.memoryCount}`)
            .fontSize(13)
            .fontColor('#6F6A78')
            .width(58)
            .textAlign(TextAlign.End)
        }
        .width('100%')
        .padding({ left: 16, right: 16, top: 14, bottom: 10 })

        if (this.loading) {
          Row()
            .width('100%')
            .height(2)
            .backgroundColor('#6750A4')
        }
        if (this.memoryError.length > 0) {
          Row({ space: 8 }) {
            Text(this.memoryError)
              .fontSize(13)
              .lineHeight(20)
              .fontColor('#BA1A1A')
              .layoutWeight(1)
            Button('重试')
              .fontSize(13)
              .fontColor('#6750A4')
              .backgroundColor(Color.Transparent)
              .onClick(() => void this.loadPageData())
          }
          .width('100%')
          .padding({ left: 16, right: 16, top: 8, bottom: 8 })
        }

        if (this.loading && this.memories.length === 0 && this.memoryError.length === 0) {
          Column({ space: 10 }) {
            LoadingProgress().width(30).height(30).color('#6750A4')
            Text('正在加载长期记忆').fontSize(14).fontColor('#6F6A78')
          }
          .layoutWeight(1)
          .width('100%')
          .justifyContent(FlexAlign.Center)
        } else if (this.memories.length === 0) {
          Column({ space: 10 }) {
            Image(this.memoryTab === 'active'
              ? $r('app.media.inbox_outline')
              : $r('app.media.delete_outline'))
              .width(44)
              .height(44)
            Text(this.memoryTab === 'active' ? '还没有长期记忆' : '没有已删除的记忆')
              .fontSize(18)
              .fontColor('#49454F')
            Text(this.memoryTab === 'active'
              ? '聊天中沉淀的重要信息会出现在这里。'
              : '被删除的记忆会暂时留在这里。')
              .fontSize(14)
              .fontColor('#6F6A78')
              .textAlign(TextAlign.Center)
          }
          .layoutWeight(1)
          .width('100%')
          .justifyContent(FlexAlign.Center)
        } else {
          List({ space: 12 }) {
            ForEach(this.memories, (memory: MemoryRecord) => {
              ListItem() {
                this.memoryCard(memory)
              }
            }, (memory: MemoryRecord) => memory.memoryId)
          }
          .layoutWeight(1)
          .width('100%')
          .padding({ left: 16, right: 16, top: 8, bottom: 20 })
          .scrollBar(BarState.Auto)
        }
      }
      .width('100%')
      .height('100%')
      if (this.memoryConfirmAction.length > 0) {
        this.memoryConfirmDialog()
      }
    }
    .width('100%')
    .height('100%')
  }

  @Builder
  private pageView(): void {
    if (this.page === 'letters') {
      this.lettersPage();
    } else if (this.page === 'onboarding') {
      this.onboardingView();
    } else if (this.page === 'chat') {
      this.chatView();
    } else if (this.page === 'devices') {
      DevicesPage({
        repository: this.repository, onBack: () => this.navigate('chat'),
        onBackHandler: (handler?: () => void) => this.deviceBackHandler = handler
      })
    } else if (this.page === 'memory') {
      this.memoryPage();
    } else if (this.page === 'stickers') {
      this.stickersPage();
    } else if (this.page === 'tasks') {
      this.tasksPage();
    } else if (this.page === 'presence') {
      this.presencePage();
    } else if (this.page === 'persona') {
      this.aboutHerPage()
    } else if (this.page === 'study') {
      this.studyFocusPage();
    } else if (this.page === 'proactive') {
      this.proactivePage();
    } else if (this.page === 'notifications') {
      NotificationsPage({ onBack: () => this.navigate('chat') })
    } else if (this.page === 'more' || this.page === 'update') {
      this.listPage('功能', ['通知设置', '一起学习', '检查更新', '设备蓝牙配网', 'Wi-Fi 热点配网', '声纹录入']);
    }
  }

  @Builder
  private bottomBar(): void {
    Row() {
      this.navButton('聊天', 'chat')
      this.navButton('设备', 'devices')
      this.navButton('来信', 'letters')
      this.navButton('更多', 'more')
    }
    .width('100%')
    .height(64)
    .backgroundColor('#FFFFFF')
    .justifyContent(FlexAlign.SpaceAround)
  }

  @Builder
  private navButton(label: string, target: string): void {
    Button(label)
      .fontColor(this.page === target ? '#E56B5D' : '#6E625D')
      .backgroundColor(Color.Transparent)
      .onClick(() => this.navigate(target))
  }

  build(): void {
    if (this.initializing) {
      Column({ space: 12 }) {
        LoadingProgress().width(32).height(32).color('#6750A4')
        Text('正在恢复聊天记录').fontSize(14).fontColor('#6F6A78')
      }.width('100%').height('100%').justifyContent(FlexAlign.Center).backgroundColor('#F8F7FC')
    } else if (!this.loggedIn) {
      Row() {
        this.loginView()
      }
      .height('100%')
      .backgroundColor('#FFF8F5')
    } else if (this.onboarding) {
      Row() { this.onboardingView() }.height('100%').backgroundColor('#FFF8F5')
    } else {
      Stack() {
        this.pageView()
        if (this.updateOpen) {
          UpdatePanel({
            repository: this.repository,
            onClose: () => this.updateOpen = false,
            onLockChange: (locked: boolean) => this.updateLocked = locked
          })
        }
        if (this.proposalDialogVisible) {
          this.relationshipProposalDialog()
        }
      }
      .height('100%')
      .backgroundColor('#F8F7FC')
    }
  }
}
