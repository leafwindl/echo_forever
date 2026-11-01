export interface AuthSession {
  userId: string;
  accessToken: string;
  refreshToken: string;
  tokenType: string;
  accessExpiresAt: string;
  refreshExpiresAt: string;
  deviceId: string;
  isNewUser: boolean;
}

export interface ApiErrorInfo {
  status: number;
  code: string;
  detail: string;
  requestId: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: string;
  readonly requestId: string;

  constructor(info: ApiErrorInfo) {
    super(info.detail || `HTTP ${info.status}`);
    this.name = 'ApiError';
    this.status = info.status;
    this.code = info.code;
    this.detail = info.detail;
    this.requestId = info.requestId;
  }
}

export interface PersonaProfile {
  preferredName: string;
  replyStyle: string;
  replyLength: string;
  supportMode: string;
  proactivity: string;
  avoidTopics: string[];
  aboutUser: string;
  relationshipPace: string;
  affectionStyle: string;
  enabled: boolean;
  onboardingCompleted: boolean;
}

export interface RelationshipProposal {
  proposalId: string;
  direction: string;
  directionLabel: string;
  status: string;
  createdAt?: string;
  expiresAt?: string;
}

export interface RelationshipState {
  relationshipMode: string;
  relationshipType: string;
  relationshipTypeLabel: string;
  stage: string;
  stageLabel: string;
  interactionTurns: number;
  activeDays: number;
  affectionPermission: string;
  pendingProposal?: RelationshipProposal;
  schemaVersion: number;
  createdAt?: string;
  updatedAt?: string;
}

export interface ChatMessage {
  id: number;
  messageType: string;
  role: string;
  content: string;
  createdAt: string;
  clientMessageId?: string;
  status?: string;
  sources?: Array<Record<string, Object>>;
  stickerUrl?: string;
}

export interface EchoDevice {
  deviceId: string;
  displayName: string;
  firmwareVersion: string;
  status: string;
  lastSeenAt?: string;
  wifiSsid?: string;
}

export interface DailyLetter {
  letterId: string;
  localDate: string;
  timezone: string;
  title: string;
  body: string;
  mood: string;
  isRead: boolean;
  imageUrl: string;
  publishAt?: string;
}

export interface MemoryRecord {
  memoryId: string;
  memoryType: string;
  content: string;
  sourceMessageId?: number;
  confidence: number;
  status: string;
  importance: number;
  createdAt?: string;
  updatedAt?: string;
  expiresAt?: string;
}

export interface MemoryListResult {
  memories: MemoryRecord[];
  count: number;
}

export interface StickerItem {
  stickerId: string;
  imageUrl: string;
  ownerType: string;
  description: string;
  tags: string[];
  source: string;
}

export interface ChatSchedule {
  scheduleId: string;
  createdBy: string;
  status: string;
  scheduleType: string;
  intent: string;
  userVisibleLabel: string;
  timezone: string;
  nextRunAt: string;
  recurrenceRule: Record<string, Object>;
  runCount: number;
  maxRuns?: number;
  lastRunAt?: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface ProactiveChatPreferences {
  enabled: boolean;
  allowEchoScheduling: boolean;
  allowSpontaneousChat: boolean;
  timezone: string;
  quietStart: string;
  quietEnd: string;
  explicitReminderQuietPolicy: string;
  notificationPreview: boolean;
  pausedUntil?: string;
  pauseIndefinite: boolean;
}
