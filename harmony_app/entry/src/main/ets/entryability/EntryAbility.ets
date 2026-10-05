import UIAbility from '@ohos.app.ability.UIAbility';
import window from '@ohos.window';
import Want from '@ohos.app.ability.Want';

export default class EntryAbility extends UIAbility {
  onCreate(_want: Want): void {
    AppStorage.setOrCreate('deepLink', '');
  }

  onWindowStageCreate(windowStage: window.WindowStage): void {
    windowStage.loadContent('pages/Index', (error) => {
      if (error.code) {
        console.error(`Echo window load failed: ${error.code}`);
      }
    });
  }

  onNewWant(want: Want): void {
    AppStorage.setOrCreate('deepLink', want.uri ?? '');
  }

  onWindowStageDestroy(): void {}
  onForeground(): void {}
  onBackground(): void {}
}
