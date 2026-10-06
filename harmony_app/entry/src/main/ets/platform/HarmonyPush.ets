import common from '@ohos.app.ability.common';
import Want from '@ohos.app.ability.Want';
import PushManager, {
  GTNotificationMessage,
  GTTransmitMessage
} from '@getui/push';

export interface HarmonyPushEvent {
  payload: Record<string, Object>;
  title: string;
  content: string;
  clicked: boolean;
  notificationId: string;
}

function parsePayload(value: string): Record<string, Object> {
  if (!value || value.trim().length === 0) return {};
  try {
    const parsed = JSON.parse(value) as Object;
    return parsed instanceof Object ? parsed as Record<string, Object> : {};
  } catch (_) {
    return {};
  }
}

function nextEpoch(key: string): void {
  AppStorage.setOrCreate(key, (AppStorage.get<number>(key) ?? 0) + 1);
}

export class HarmonyPush {
  private static initialized: boolean = false;
  private static initializing: boolean = false;
  private static cid: string = '';
  private static listener?: (event: HarmonyPushEvent) => void;

  static async initialize(
    context: common.UIAbilityContext,
    listener?: (event: HarmonyPushEvent) => void
  ): Promise<void> {
    HarmonyPush.listener = listener ?? HarmonyPush.listener;
    if (HarmonyPush.initialized || HarmonyPush.initializing) return;
    HarmonyPush.initializing = true;
    AppStorage.setOrCreate('pushStatus', 'initializing');
    AppStorage.setOrCreate('pushClientId', '');
    try {
      PushManager.preInitialize();
      PushManager.setPushCallback({
        onReceiveClientId: (clientId: string) => {
          HarmonyPush.cid = clientId.trim();
          AppStorage.setOrCreate('pushClientId', HarmonyPush.cid);
          AppStorage.setOrCreate('pushStatus', HarmonyPush.cid.length > 0 ? 'ready' : 'unconfigured');
          nextEpoch('pushEpoch');
        },
        onReceiveMessageData: (message: GTTransmitMessage) => {
          HarmonyPush.dispatch({
            payload: parsePayload(message.payload),
            title: '',
            content: '',
            clicked: false,
            notificationId: message.messageId ?? message.payloadId ?? ''
          });
        },
        onNotificationMessageArrived: (message: GTNotificationMessage) => {
          HarmonyPush.dispatch({
            payload: parsePayload(message.payload),
            title: message.title ?? '',
            content: message.content ?? '',
            clicked: false,
            notificationId: message.messageId ?? ''
          });
        },
        onNotificationMessageClicked: (message: GTNotificationMessage) => {
          const payload = parsePayload(message.payload);
          AppStorage.setOrCreate('deepLink', '/chat');
          AppStorage.setOrCreate('pushLastPayload', JSON.stringify(payload));
          nextEpoch('pushClickEpoch');
          HarmonyPush.dispatch({
            payload,
            title: message.title ?? '',
            content: message.content ?? '',
            clicked: true,
            notificationId: message.messageId ?? ''
          });
        }
      });
      PushManager.initialize({
        context,
        onSuccess: (clientId: string) => {
          HarmonyPush.cid = clientId.trim();
          AppStorage.setOrCreate('pushClientId', HarmonyPush.cid);
          AppStorage.setOrCreate('pushStatus', HarmonyPush.cid.length > 0 ? 'ready' : 'unconfigured');
          nextEpoch('pushEpoch');
        },
        onFailed: (error: string) => {
          console.error(`Echo Getui initialize failed: ${error}`);
          AppStorage.setOrCreate('pushStatus', 'failed');
          AppStorage.setOrCreate('pushError', error);
          nextEpoch('pushEpoch');
        }
      });
      PushManager.turnOnPush();
      HarmonyPush.initialized = true;
      const current = PushManager.getClientId();
      if (current && current.trim().length > 0) {
        HarmonyPush.cid = current.trim();
        AppStorage.setOrCreate('pushClientId', HarmonyPush.cid);
        AppStorage.setOrCreate('pushStatus', 'ready');
      }
    } catch (error) {
      console.error(`Echo Getui unavailable: ${String(error)}`);
      AppStorage.setOrCreate('pushStatus', 'failed');
      AppStorage.setOrCreate('pushError', String(error));
    } finally {
      HarmonyPush.initializing = false;
      nextEpoch('pushEpoch');
    }
  }

  static getClientId(): string {
    if (HarmonyPush.cid.length > 0) return HarmonyPush.cid;
    try {
      const value = PushManager.getClientId();
      HarmonyPush.cid = value?.trim() ?? '';
      if (HarmonyPush.cid.length > 0) {
        AppStorage.setOrCreate('pushClientId', HarmonyPush.cid);
        AppStorage.setOrCreate('pushStatus', 'ready');
      }
    } catch (_) {
      return '';
    }
    return HarmonyPush.cid;
  }

  static handleWant(want: Want): void {
    const uri = want.uri ?? '';
    const parameters = want.parameters;
    if (uri.length === 0 && parameters === undefined) return;
    try {
      PushManager.setClickWant(want);
    } catch (error) {
      console.error(`Echo Getui click report failed: ${String(error)}`);
    }
    if (uri.length > 0) {
      AppStorage.setOrCreate('deepLink', uri);
    } else {
      AppStorage.setOrCreate('deepLink', '/chat');
    }
    nextEpoch('pushClickEpoch');
  }

  private static dispatch(event: HarmonyPushEvent): void {
    AppStorage.setOrCreate('pushLastPayload', JSON.stringify(event.payload));
    nextEpoch(event.clicked ? 'pushClickEpoch' : 'pushMessageEpoch');
    if (HarmonyPush.listener) HarmonyPush.listener(event);
  }
}
