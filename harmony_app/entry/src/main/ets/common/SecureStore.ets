import preferences from '@ohos.data.preferences';
import common from '@ohos.app.ability.common';

export class SecureStore {
  private static readonly storeName: string = 'echo_session';
  private preferences?: preferences.Preferences;

  async initialize(context: common.UIAbilityContext): Promise<void> {
    this.preferences = await preferences.getPreferences(context, SecureStore.storeName);
  }

  async get(key: string): Promise<string> {
    return (await this.preferences?.get(key, '') as string) ?? '';
  }

  async set(key: string, value: string): Promise<void> {
    await this.preferences?.put(key, value);
    await this.preferences?.flush();
  }

  async remove(key: string): Promise<void> {
    await this.preferences?.delete(key);
    await this.preferences?.flush();
  }
}
