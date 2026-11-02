import { ApiClient } from '../common/ApiClient';
import { AppConfig, encodePath } from '../common/AppConfig';
import { validateDownloadUrl } from '../model/AppRelease';
import {
  AuthSession,
  ChatMessage,
  ChatSchedule,
  DailyLetter,
  EchoDevice,
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

interface LetterValue {
  letterId: string;
  localDate: string;
  timezone: string;
  title: string;
  body: string;
  mood: string;
  isRead: boolean;
  imageUrl: string;
  publishAt: string;
}

interface StickerValue {
  stickerId: string;
  imageUrl: string;
  description: string;
  tags: string[];
  source: string;
}

interface ScheduleValue {
  scheduleId: string;
  title: string;
  status: string;
  scheduleType: string;
  nextRunAt: string;
}

export class EchoRepository {
  private readonly api: ApiClient;

  constructor(api: ApiClient) {
    this.api = api;
  }

  async requestPhoneCode(phone: string, deviceId: string): Promise<Record<string, Object>> {
    const request: Record<string, Object> = {};
    request.phone = phone;
    request.device_id = deviceId;
    request.purpose = 'login';
    return this.api.post<Record<string, Object>>('/login/phone', request, false);
  }

  async verifyCode(phone: string, code: string, requestId: string, deviceId: string): Promise<AuthSession> {
    const body: Record<string, Object> = {};
    body.phone = phone;
    body.code = code;
    body.request_id = requestId;
    body.device_id = deviceId;
    const response = await this.api.post<Record<string, Object>>('/login/verify', body, false);
    return {
      userId: String(response.user_id ?? ''),
      accessToken: String(response.access_token ?? ''),
      refreshToken: String(response.refresh_token ?? ''),
      tokenType: String(response.token_type ?? 'bearer'),
      accessExpiresAt: String(response.expires_in ?? ''),
      refreshExpiresAt: String(response.refresh_expires_in ?? ''),
      deviceId,
      isNewUser: response.is_new_user === true
    };
  }

  async getChatHistory(beforeId?: number, afterId?: number): Promise<Record<string, Object>> {
    const query: Record<string, string> = {};
    query.limit = '10';
    if (beforeId !== undefined) query.before_id = String(beforeId);
    if (afterId !== undefined) query.after_id = String(afterId);
    return this.api.get<Record<string, Object>>('/chat/messages', query);
  }

  async getChatHistoryPage(beforeId?: number, afterId?: number): Promise<Record<string, Object>> {
    const query: Record<string, string> = {};
    query.limit = '10';
    if (beforeId !== undefined) query.before_id = String(beforeId);
    if (afterId !== undefined) query.after_id = String(afterId);
    return this.api.get<Record<string, Object>>('/chat/messages', query);
  }

  async sendMessage(content: string, clientMessageId: string): Promise<Record<string, Object>> {
    const request: Record<string, Object> = {};
    request.client_message_id = clientMessageId;
    request.message_type = 'text';
    request.text = content;
    return this.api.post<Record<string, Object>>('/chat/messages', request);
  }

  async sendSticker(stickerId: string, clientMessageId: string): Promise<Record<string, Object>> {
    const request: Record<string, Object> = {};
    request.client_message_id = clientMessageId;
    request.message_type = 'sticker';
    request.sticker_id = stickerId;
    return this.api.post<Record<string, Object>>('/chat/messages', request);
  }

  async clearChat(): Promise<void> {
    await this.api.post<Record<string, Object>>('/chat/clear');
  }

  async subscribeChat(afterMessageId: number, onEvent: (eventName: string, data: Record<string, Object>) => void): Promise<void> {
    await this.api.openSse('/chat/events', afterMessageId, onEvent);
  }

  async listDevices(): Promise<EchoDevice[]> {
    const result = await this.api.get<Record<string, Object>>('/devices');
    return this.asArray(result.items).map((item) => this.toDevice(item));
  }

  async renameDevice(deviceId: string, displayName: string): Promise<EchoDevice> {
    const request: Record<string, Object> = {};
    request.display_name = displayName;
    const result = await this.api.patch<Record<string, Object>>(`/devices/${encodePath(deviceId)}`, request);
    return this.toDevice(result);
  }

  async unbindDevice(deviceId: string): Promise<void> {
    await this.api.delete<Record<string, Object>>(`/devices/${encodePath(deviceId)}`);
  }

  async connectDevice(deviceId: string): Promise<void> {
    const response = await this.api.post<Record<string, Object>>(`/devices/${encodePath(deviceId)}/probe`);
    if (response.acknowledged !== true) throw new Error('未收到硬件检测回执');
  }

  async rotateDeviceCredential(deviceId: string): Promise<Record<string, Object>> {
    return this.api.post<Record<string, Object>>(`/devices/${encodePath(deviceId)}/credentials/rotate`);
  }

  async claimPairing(pairingId: string, code: string): Promise<Record<string, Object>> {
    const request: Record<string, Object> = {};
    request.pairing_id = pairingId;
    request.code = code;
    return this.api.post<Record<string, Object>>('/devices/pairings/claim', request);
  }

  async createProvisioningSession(): Promise<Record<string, Object>> {
    return this.api.post<Record<string, Object>>('/devices/provisioning/sessions');
  }

  async listMemories(status: string = 'active'): Promise<MemoryListResult> {
    const memoryQuery: Record<string, string> = {};
    memoryQuery.status = status;
    memoryQuery.limit = '100';
    const result = await this.api.get<Record<string, Object>>('/memory/list', memoryQuery);
    return {
      memories: this.asArray(result.memories).map((item): MemoryRecord => ({
        memoryId: this.asString(item.memory_id),
        memoryType: this.asString(item.memory_type),
        content: this.asString(item.content),
        sourceMessageId: item.source_message_id === undefined || item.source_message_id === null
          ? undefined
          : this.asNumber(item.source_message_id),
        confidence: this.asNumber(item.confidence),
        status: this.asString(item.status),
        importance: this.asNumber(item.importance),
        createdAt: this.asString(item.created_at),
        updatedAt: this.asString(item.updated_at),
        expiresAt: this.asString(item.expires_at)
      })),
      count: this.asNumber(result.count)
    };
  }

  async deleteMemory(memoryId: string): Promise<void> {
    await this.api.delete<Record<string, Object>>(`/memory/${encodePath(memoryId)}`);
  }

  async clearMemories(): Promise<void> {
    await this.api.post<Record<string, Object>>('/memory/clear');
  }

  async listLetters(): Promise<DailyLetter[]> {
    const letterQuery: Record<string, string> = {};
    letterQuery.limit = '50';
    const result = await this.api.get<Record<string, Object>>('/letters', letterQuery);
    return this.asArray(result.items).map((item): DailyLetter => ({
      letterId: this.asString(item.letter_id),
      localDate: this.asString(item.local_date),
      timezone: this.asString(item.timezone),
      title: this.asString(item.subject),
      body: this.asString(item.content),
      mood: this.asString(item.mood),
      isRead: this.asString(item.read_at).length > 0,
      imageUrl: this.asString(item.image_url),
      publishAt: this.asString(item.published_at)
    }));
  }

  async markLetterRead(letterId: string): Promise<void> {
    await this.api.post<Record<string, Object>>(`/letters/${encodePath(letterId)}/read`);
  }

  async listStickers(query: string = ''): Promise<StickerItem[]> {
    const stickerQuery: Record<string, string> = {};
    stickerQuery.query = query;
    stickerQuery.limit = '100';
    const result = await this.api.get<Record<string, Object>>('/stickers', stickerQuery);
    return this.asArray(result.items).map((item): StickerItem => ({
      stickerId: this.asString(item.sticker_id),
      imageUrl: this.asString(item.url),
      ownerType: this.asString(item.owner_type),
      description: this.asString(item.description),
      tags: this.asArray(item.semantic_tags).map((tag) => this.asString(tag)),
      source: this.asString(item.source)
    }));
  }

  async uploadSticker(
    fileUri: string,
    fileName: string,
    contentType: string,
    description: string,
    tags: string[]
  ): Promise<StickerItem> {
    const fields: Record<string, string> = {};
    fields.description = description;
    fields.tags = tags.join(',');
    const uploaded = await this.api.uploadMultipartResponse(
      '/stickers/upload',
      fileUri,
      fileName,
      contentType,
      fields
    );
    const stickerId = this.asString(uploaded.sticker_id);
    if (stickerId.length === 0) {
      throw new Error('涓婁紶鎴愬姛锛屾湇鍔″櫒鏈繑鍥炶〃鎯呭寘 ID');
    }
    return this.confirmSticker(stickerId);

    if (false) {
      throw new Error('上传成功，但未找到新表情包');
    }
    return this.confirmSticker(stickerId);
  }

  async confirmSticker(stickerId: string): Promise<StickerItem> {
    const result = await this.api.post<Record<string, Object>>(
      `/stickers/${encodePath(stickerId)}/confirm-save`
    );
    return this.toSticker(result);
  }

  async deleteSticker(stickerId: string): Promise<void> {
    await this.api.delete<Record<string, Object>>(`/stickers/${encodePath(stickerId)}`);
  }

  async getPersona(): Promise<Record<string, Object>> {
    return this.api.get<Record<string, Object>>('/persona/me');
  }

  async getPresence(): Promise<PresenceSnapshot> {
    const query: Record<string, string> = {};
    query.thought_limit = '20';
    const result = await this.api.get<Record<string, Object>>('/presence/me', query);
    return {
      status: this.asString(result.status),
      enabled: this.asBoolean(result.enabled),
      lastUserMessageAt: this.asString(result.last_user_message_at),
      lastTickAt: this.asString(result.last_tick_at),
      lastThoughtAt: this.asString(result.last_thought_at),
      thoughtsUsed: this.asNumber(result.thoughts_used),
      dailyThoughtBudget: this.asNumber(result.daily_thought_budget),
      lastDecision: this.asString(result.last_decision),
      lastDecisionReason: this.asString(result.last_decision_reason),
      thoughts: this.asArray(result.thoughts).map((item): PresenceThought => ({
        thoughtId: this.asString(item.thought_id),
        text: this.asString(item.text),
        salience: this.asNumber(item.salience),
        shareable: this.asBoolean(item.shareable),
        actionIntent: this.asString(item.action_intent),
        createdAt: this.asString(item.created_at)
      }))
    };
  }

  async getPersonaProfile(): Promise<PersonaProfile> {
    const value = await this.getPersona();
    return this.toPersona(value);
  }

  async updatePersona(data: Record<string, Object>): Promise<Record<string, Object>> {
    return this.api.put<Record<string, Object>>('/persona/me', data);
  }

  async resetPersona(): Promise<PersonaProfile> {
    const value = await this.api.post<Record<string, Object>>('/persona/me/reset');
    return this.toPersona(value);
  }

  async getRelationship(): Promise<RelationshipState> {
    const value = await this.api.get<Record<string, Object>>('/relationship/me');
    return this.toRelationship(value);
  }

  async updateRelationshipMode(mode: string): Promise<RelationshipState> {
    const body: Record<string, Object> = {};
    body.relationship_mode = mode;
    const value = await this.api.put<Record<string, Object>>('/relationship/me', body);
    return this.toRelationship(value);
  }

  async resetRelationship(): Promise<RelationshipState> {
    const value = await this.api.post<Record<string, Object>>('/relationship/me/reset');
    return this.toRelationship(value);
  }

  async resetCompanionship(): Promise<void> {
    await this.api.post<Record<string, Object>>('/account/reset');
  }

  async acceptRelationshipProposal(proposalId: string): Promise<RelationshipState> {
    const value = await this.api.post<Record<string, Object>>(
      `/relationship/proposals/${encodePath(proposalId)}/accept`
    );
    return this.toRelationship(value);
  }

  async deferRelationshipProposal(proposalId: string): Promise<void> {
    await this.api.post<Record<string, Object>>(
      `/relationship/proposals/${encodePath(proposalId)}/defer`
    );
  }

  async declineRelationshipProposal(proposalId: string): Promise<void> {
    await this.api.post<Record<string, Object>>(
      `/relationship/proposals/${encodePath(proposalId)}/decline`
    );
  }

  async logout(refreshToken: string, deviceId: string): Promise<void> {
    const body: Record<string, Object> = {};
    body.refresh_token = refreshToken;
    body.device_id = deviceId;
    await this.api.post<Record<string, Object>>('/login/logout', body);
  }

  async getProactivePreferences(): Promise<ProactiveChatPreferences> {
    const value = await this.api.get<Record<string, Object>>('/proactive/preferences');
    return this.toProactivePreferences(value);
  }

  async updateProactivePreferences(data: Record<string, Object>): Promise<ProactiveChatPreferences> {
    const value = await this.api.put<Record<string, Object>>('/proactive/preferences', data);
    return this.toProactivePreferences(value);
  }

  async pauseProactive(days: number): Promise<ProactiveChatPreferences> {
    const body: Record<string, Object> = {};
    body.days = days;
    body.indefinite = false;
    const value = await this.api.post<Record<string, Object>>('/proactive/pause', body);
    return this.toProactivePreferences(value);
  }

  async resumeProactive(): Promise<ProactiveChatPreferences> {
    const value = await this.api.post<Record<string, Object>>('/proactive/resume');
    return this.toProactivePreferences(value);
  }

  async listSchedules(): Promise<ChatSchedule[]> {
    const result = await this.api.get<Record<string, Object>>('/proactive/schedules');
    return this.asArray(result.items).map((item): ChatSchedule => ({
      scheduleId: this.asString(item.schedule_id),
      createdBy: this.asString(item.created_by),
      status: this.asString(item.status),
      scheduleType: this.asString(item.schedule_type),
      intent: this.asString(item.intent),
      userVisibleLabel: this.asString(item.user_visible_label),
      timezone: this.asString(item.timezone) || 'Asia/Shanghai',
      nextRunAt: this.asString(item.next_run_at),
      recurrenceRule: item.recurrence_rule instanceof Object
        ? item.recurrence_rule as Record<string, Object>
        : {},
      runCount: this.asNumber(item.run_count),
      maxRuns: item.max_runs === undefined || item.max_runs === null
        ? undefined
        : this.asNumber(item.max_runs),
      lastRunAt: this.asString(item.last_run_at),
      createdAt: this.asString(item.created_at),
      updatedAt: this.asString(item.updated_at)
    }));
  }

  async updateSchedule(scheduleId: string, status: string): Promise<void> {
    const schedule: Record<string, Object> = {};
    schedule.status = status;
    await this.api.put<Record<string, Object>>(`/proactive/schedules/${encodePath(scheduleId)}`, schedule);
  }

  async deleteSchedule(scheduleId: string): Promise<void> {
    await this.api.delete<Record<string, Object>>(`/proactive/schedules/${encodePath(scheduleId)}`);
  }

  async registerPushToken(deviceId: string, token: string): Promise<void> {
    const request: Record<string, Object> = {};
    request.device_id = deviceId;
    request.platform = AppConfig.pushRegistrationPlatform;
    request.provider = 'getui';
    request.token = token;
    request.app_version = AppConfig.appVersion;
    request.environment = 'production';
    request.locale = 'zh-CN';
    await this.api.put<Record<string, Object>>('/push/tokens/me', request);
  }

  async createFocusSession(session: Record<string, Object>): Promise<Record<string, Object>> {
    return this.api.post<Record<string, Object>>('/study-focus/sessions', session);
  }

  async updateFocusSession(sessionId: string, session: Record<string, Object>): Promise<Record<string, Object>> {
    return this.api.patch<Record<string, Object>>(`/study-focus/sessions/${encodePath(sessionId)}`, session);
  }

  async latestRelease(versionCode: number): Promise<Record<string, Object>> {
    const releaseQuery: Record<string, string> = {};
    releaseQuery.platform = AppConfig.appPlatform;
    releaseQuery.channel = AppConfig.channel;
    releaseQuery.version_code = String(versionCode);
    return this.api.get<Record<string, Object>>('/releases/latest', releaseQuery, false);
  }

  async releaseDownload(releaseId: string, versionCode: number): Promise<string> {
    const body: Record<string, Object> = {};
    body.platform = AppConfig.appPlatform;
    body.channel = AppConfig.channel;
    body.version_code = versionCode;
    const result = await this.api.post<Record<string, Object>>(
      `/releases/${encodePath(releaseId)}/download`, body, false
    );
    return validateDownloadUrl(result.download_url);
  }

  async listSpeakerPeople(deviceId: string): Promise<Record<string, Object>[]> {
    const result = await this.api.get<Record<string, Object>>(`/devices/${encodePath(deviceId)}/speakers`);
    return this.asArray(result.items);
  }

  async createSpeakerPerson(deviceId: string, name: string): Promise<Record<string, Object>> {
    const body: Record<string, Object> = {};
    body.display_name = name.trim();
    body.consent = true;
    return this.api.post<Record<string, Object>>(`/devices/${encodePath(deviceId)}/speakers`, body);
  }

  async deleteSpeakerPerson(deviceId: string, personId: string): Promise<void> {
    await this.api.delete<Record<string, Object>>(
      `/devices/${encodePath(deviceId)}/speakers/${encodePath(personId)}`
    );
  }

  async uploadSpeakerSample(deviceId: string, personId: string, path: string): Promise<Record<string, Object>> {
    return this.api.uploadMultipartResponse(
      `/devices/${encodePath(deviceId)}/speakers/${encodePath(personId)}/samples`,
      path, 'sample.pcm', 'audio/L16', {}, 'audio'
    );
  }

  async speakerState(deviceId: string, path: string): Promise<Record<string, Object>> {
    return this.api.get<Record<string, Object>>(`/devices/${encodePath(deviceId)}/${path}`);
  }

  async approveSpeakerRequest(deviceId: string, sessionId: string, approved: boolean): Promise<void> {
    const body: Record<string, Object> = {};
    body.session_id = sessionId;
    body.approved = approved;
    await this.api.post<Record<string, Object>>(
      `/devices/${encodePath(deviceId)}/speaker-enrollment-request`, body
    );
  }

  async calibrateSpeaker(deviceId: string, personId: string): Promise<Record<string, Object>> {
    const body: Record<string, Object> = {};
    body.consent = true;
    return this.api.post<Record<string, Object>>(
      `/devices/${encodePath(deviceId)}/speakers/${encodePath(personId)}/calibration`, body
    );
  }

  async cancelSpeakerCalibration(deviceId: string, personId?: string): Promise<void> {
    const path = personId
      ? `speakers/${encodePath(personId)}/calibration` : 'speaker-calibration';
    await this.api.delete<Record<string, Object>>(`/devices/${encodePath(deviceId)}/${path}`);
  }

  private toDevice(item: Record<string, Object>): EchoDevice {
    return {
      deviceId: this.asString(item.device_id),
      displayName: this.asString(item.display_name) || '我的 Echo',
      firmwareVersion: this.asString(item.firmware_version),
      status: this.asString(item.status),
      lastSeenAt: this.asString(item.last_seen_at),
      wifiSsid: this.asString(item.wifi_ssid)
    };
  }

  private toSticker(item: Record<string, Object>): StickerItem {
    return {
      stickerId: this.asString(item.sticker_id),
      imageUrl: this.asString(item.url),
      ownerType: this.asString(item.owner_type),
      description: this.asString(item.description),
      tags: this.asArray(item.semantic_tags).map((tag) => this.asString(tag)),
      source: this.asString(item.source)
    };
  }

  private toPersona(value: Record<string, Object>): PersonaProfile {
    return {
      preferredName: this.asString(value.preferred_name),
      replyStyle: this.asString(value.reply_style) || 'natural',
      replyLength: this.asString(value.reply_length) || 'balanced',
      supportMode: this.asString(value.support_mode) || 'balanced',
      proactivity: this.asString(value.proactivity) || 'balanced',
      avoidTopics: this.asStringArray(value.avoid_topics),
      aboutUser: this.asString(value.about_user),
      relationshipPace: this.asString(value.relationship_pace) || 'natural',
      affectionStyle: this.asString(value.affection_style) || 'contextual',
      enabled: value.enabled === undefined ? true : this.asBoolean(value.enabled),
      onboardingCompleted: this.asBoolean(value.onboarding_completed)
    };
  }

  private toRelationship(value: Record<string, Object>): RelationshipState {
    let pending: RelationshipProposal | undefined = undefined;
    if (value.pending_proposal !== undefined && value.pending_proposal !== null) {
      const raw = value.pending_proposal as Record<string, Object>;
      pending = {
        proposalId: this.asString(raw.proposal_id),
        direction: this.asString(raw.direction),
        directionLabel: this.asString(raw.direction_label),
        status: this.asString(raw.status),
        createdAt: this.asString(raw.created_at),
        expiresAt: this.asString(raw.expires_at)
      };
    }
    return {
      relationshipMode: this.asString(value.relationship_mode) || 'friend',
      relationshipType: this.asString(value.relationship_type) || 'acquaintance',
      relationshipTypeLabel: this.asString(value.relationship_type_label) || '初识',
      stage: this.asString(value.stage),
      stageLabel: this.asString(value.stage_label),
      interactionTurns: this.asNumber(value.interaction_turns),
      activeDays: this.asNumber(value.active_days),
      affectionPermission: this.asString(value.affection_permission),
      pendingProposal: pending,
      schemaVersion: this.asNumber(value.schema_version),
      createdAt: this.asString(value.created_at),
      updatedAt: this.asString(value.updated_at)
    };
  }

  private toProactivePreferences(value: Record<string, Object>): ProactiveChatPreferences {
    return {
      enabled: this.asBoolean(value.enabled),
      allowEchoScheduling: value.allow_echo_scheduling === undefined
        ? true
        : this.asBoolean(value.allow_echo_scheduling),
      allowSpontaneousChat: this.asBoolean(value.allow_spontaneous_chat),
      timezone: this.asString(value.timezone) || 'Asia/Shanghai',
      quietStart: this.shortTime(this.asString(value.quiet_start), '22:30'),
      quietEnd: this.shortTime(this.asString(value.quiet_end), '08:00'),
      explicitReminderQuietPolicy: this.asString(value.explicit_reminder_quiet_policy) || 'defer',
      notificationPreview: this.asBoolean(value.notification_preview),
      pausedUntil: this.asString(value.paused_until),
      pauseIndefinite: this.asBoolean(value.pause_indefinite)
    };
  }

  private shortTime(value: string, fallback: string): string {
    return value.length >= 5 ? value.substring(0, 5) : fallback;
  }

  private asArray(value: Object | undefined): Record<string, Object>[] {
    const result: Record<string, Object>[] = [];
    if (Array.isArray(value)) {
      value.forEach((item: Object) => {
        if (item instanceof Object) {
          result.push(item as Record<string, Object>);
        }
      });
    }
    return result;
  }

  private asStringArray(value: Object | undefined): string[] {
    const result: string[] = [];
    if (Array.isArray(value)) {
      value.forEach((item: Object) => {
        if (item !== undefined && item !== null) result.push(String(item));
      });
    }
    return result;
  }

  private asString(value: Object | undefined): string {
    return value === undefined || value === null ? '' : String(value);
  }

  private asNumber(value: Object | undefined): number {
    return typeof value === 'number' ? value : Number(this.asString(value)) || 0;
  }

  private asBoolean(value: Object | undefined): boolean {
    return value === true || this.asString(value).toLowerCase() === 'true';
  }
}

export function messageFromJson(item: Record<string, Object>): ChatMessage {
  const attachments = item.attachments;
  let stickerUrl: string | undefined = item.sticker_url === undefined ? undefined : String(item.sticker_url);
  const contentParts = item.content_parts;
  if (stickerUrl === undefined && Array.isArray(contentParts)) {
    for (let index = 0; index < contentParts.length; index++) {
      const part: Object = contentParts[index] as Object;
      if (part instanceof Object) {
        const value = part as Record<string, Object>;
        if (String(value.type ?? '') === 'sticker') {
          stickerUrl = String(value.url ?? '');
          break;
        }
      }
    }
  }
  if (stickerUrl === undefined && Array.isArray(attachments)) {
    for (let index = 0; index < attachments.length; index++) {
      const attachment: Object = attachments[index] as Object;
      if (attachment instanceof Object) {
        const value = attachment as Record<string, Object>;
        if (String(value.type ?? value.attachment_type ?? '') === 'sticker') {
          stickerUrl = String(value.url ?? '');
          break;
        }
      }
    }
  }
  return {
    id: Number(item.message_id ?? item.id) || 0,
    messageType: String(item.message_type ?? ''),
    role: String(item.role ?? ''),
    content: String(item.content ?? item.text ?? ''),
    createdAt: String(item.created_at ?? ''),
    clientMessageId: item.client_message_id === undefined ? undefined : String(item.client_message_id),
    status: item.status === undefined ? undefined : String(item.status),
    sources: Array.isArray(item.sources) ? item.sources as Array<Record<string, Object>> : [],
    stickerUrl
  };
}
