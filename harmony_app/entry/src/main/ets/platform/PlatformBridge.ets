export interface PushCallbacks {
  onClientId: (clientId: string) => Promise<void>;
  onNotificationClicked: (payload: Record<string, Object>) => Promise<void>;
  onPayload: (payload: Record<string, Object>) => Promise<void>;
}

export interface PlatformBridge {
  initializePush(callbacks: PushCallbacks): Promise<string | undefined>;
  requestNotificationPermission(): Promise<boolean>;
  scheduleLocalReminder(timestampMs: number, title: string, body: string): Promise<void>;
  cancelLocalReminder(): Promise<void>;
  scanEchoDevices(): Promise<Array<Record<string, string>>>;
  startBlufi(address: string): Promise<void>;
  configureBlufi(ssid: string, password: string, claimToken: string): Promise<void>;
  disconnectBlufi(): Promise<void>;
  connectDeviceHotspot(ssid: string): Promise<boolean>;
  openWifiSettings(): Promise<void>;
  startVoiceEnrollment(): Promise<Uint8Array>;
  installHap(url: string, sha256: string, sizeBytes: number): Promise<void>;
}

export class HarmonyPlatformBridge implements PlatformBridge {
  async initializePush(_callbacks: PushCallbacks): Promise<string | undefined> {
    return undefined;
  }

  async requestNotificationPermission(): Promise<boolean> {
    return false;
  }

  async scheduleLocalReminder(_timestampMs: number, _title: string, _body: string): Promise<void> {}
  async cancelLocalReminder(): Promise<void> {}

  async scanEchoDevices(): Promise<Array<Record<string, string>>> {
    throw new Error('BLE adapter is not configured. Add the HarmonyOS BLE implementation before release.');
  }

  async startBlufi(_address: string): Promise<void> {
    throw new Error('BluFi adapter is not configured.');
  }

  async configureBlufi(_ssid: string, _password: string, _claimToken: string): Promise<void> {
    throw new Error('BluFi adapter is not configured.');
  }

  async disconnectBlufi(): Promise<void> {}

  async connectDeviceHotspot(_ssid: string): Promise<boolean> {
    return false;
  }

  async openWifiSettings(): Promise<void> {}

  async startVoiceEnrollment(): Promise<Uint8Array> {
    throw new Error('Microphone adapter is not configured.');
  }

  async installHap(_url: string, _sha256: string, _sizeBytes: number): Promise<void> {
    throw new Error('HAP installer adapter is not configured.');
  }
}
