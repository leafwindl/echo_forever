export class AppConfig {
  static readonly baseUrl: string = 'https://api.echoaiforever.cn';
  static readonly appVersion: string = '1.1.7';
  static readonly versionCode: number = 23;
  static readonly appPlatform: string = 'harmonyos';
  static readonly pushRegistrationPlatform: string = 'harmonyos';
  static readonly channel: string = 'internal';
  // Filled when the HarmonyOS app is created in the Getui console.
  static readonly getuiAppId: string = 'u5JfZJNhsF65eKmzD17ok8';
}

export function encodePath(value: string): string {
  return encodeURIComponent(value);
}

export function normalizeMainlandPhone(value: string): string {
  let normalized = value.replace(/[\s-]/g, '');
  if (normalized.startsWith('0086')) {
    normalized = `+86${normalized.substring(4)}`;
  } else if (/^1\d{10}$/.test(normalized)) {
    normalized = `+86${normalized}`;
  }
  if (!/^\+861[3-9]\d{9}$/.test(normalized)) {
    throw new Error('请输入正确的中国大陆手机号');
  }
  return normalized;
}
