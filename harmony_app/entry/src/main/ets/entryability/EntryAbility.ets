import UIAbility from '@ohos.app.ability.UIAbility';
import window from '@ohos.window';
import Want from '@ohos.app.ability.Want';
import { HarmonyPush } from '../platform/HarmonyPush';

export default class EntryAbility extends UIAbility {
  onCreate(want: Want): void {
    AppStorage.setOrCreate('deepLink', '');
    AppStorage.setOrCreate('foregroundEpoch', 0);
    AppStorage.setOrCreate('pushStatus', 'starting');
    AppStorage.setOrCreate('pushClientId', '');
    AppStorage.setOrCreate('pushEpoch', 0);
    AppStorage.setOrCreate('pushMessageEpoch', 0);
    AppStorage.setOrCreate('pushClickEpoch', 0);
    AppStorage.setOrCreate('backgroundEpoch', 0);
    void HarmonyPush.initialize(this.context);
    HarmonyPush.handleWant(want);
  }

  onWindowStageCreate(windowStage: window.WindowStage): void {
    windowStage.loadContent('pages/Index', (error) => {
      if (error.code) {
        console.error(`Echo window load failed: ${error.code}`);
      }
    });
  }

  onNewWant(want: Want): void {
    HarmonyPush.handleWant(want);
  }

  onWindowStageDestroy(): void {}
  onForeground(): void {
    AppStorage.setOrCreate('foregroundEpoch', (AppStorage.get<number>('foregroundEpoch') ?? 0) + 1);
  }
  onBackground(): void {}
}
