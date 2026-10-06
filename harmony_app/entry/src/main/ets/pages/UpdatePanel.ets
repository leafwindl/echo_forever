import common from '@ohos.app.ability.common';
import { EchoRepository } from '../data/EchoRepository';
import { HarmonyRelease, InstalledApp, parseHarmonyRelease } from '../model/AppRelease';
import { HarmonyUpdater } from '../platform/HarmonyUpdater';

@Component
export struct UpdatePanel {
  repository?: EchoRepository;
  onClose: () => void = () => {};
  onLockChange: (locked: boolean) => void = () => {};
  @State @Watch('updateLock') private phase: string = 'checking';
  @State private error: string = '';
  @State private release?: HarmonyRelease = undefined;
  @State private progress: number = 0;
  private installed?: InstalledApp;
  private path: string = '';
  private updater: HarmonyUpdater = new HarmonyUpdater();
  private disposed: boolean = false;

  aboutToAppear(): void { void this.check(); }
  aboutToDisappear(): void { this.disposed = true; this.updater.cancel(); this.onLockChange(false); }

  private updateLock(): void {
    this.onLockChange(this.release?.mandatory === true || this.phase === 'downloading' ||
      this.phase === 'verifying' || this.phase === 'installing');
  }

  private async check(): Promise<void> {
    if (!this.repository) return;
    this.phase = 'checking';
    this.error = '';
    try {
      this.installed = await this.updater.installed();
      const value = await this.repository.latestRelease(this.installed.versionCode);
      if (this.disposed) return;
      this.release = parseHarmonyRelease(value, this.installed);
      this.phase = this.release ? 'available' : 'current';
    } catch (error) {
      if (!this.disposed) { this.phase = 'failed'; this.error = String(error); }
    }
  }

  private async update(): Promise<void> {
    if (!this.repository || !this.release || !this.installed) { await this.check(); return; }
    const context = getContext(this) as common.UIAbilityContext;
    try {
      if (!this.path) {
        this.phase = 'downloading';
        this.progress = 0;
        const url = await this.repository.releaseDownload(this.release.releaseId, this.installed.versionCode);
        if (this.disposed) return;
        this.path = await this.updater.download(context, url, this.release, (value: number) => this.progress = value);
        if (this.disposed) return;
        this.phase = 'verifying';
        try { await this.updater.verify(this.path, this.release); }
        catch (error) { this.path = ''; throw new Error(String(error)); }
      }
      if (this.disposed) return;
      this.phase = 'installing';
      await this.updater.openInstaller(context, this.path);
      // Opening the installer does not mean installation succeeded.
      this.phase = 'ready';
    } catch (error) {
      if (!this.disposed) { this.phase = 'failed'; this.error = String(error); }
    }
  }

  build() {
    Stack() {
      Column().width('100%').height('100%').backgroundColor('#88000000')
      Column({ space: 16 }) {
        Text(this.phase === 'checking' ? '正在检查更新…' : this.phase === 'current'
          ? '当前已经是最新版本' : !this.release ? '检查更新失败'
            : this.release.mandatory ? '需要更新 Echo' : 'Echo 有新版本')
          .fontSize(21).fontWeight(FontWeight.Bold).fontColor('#262331').width('100%')
        if (this.installed) {
          Text(`当前版本 ${this.installed.versionName}`).fontSize(14).fontColor('#6F6A78').width('100%')
        }
        if (this.release) {
          Text(`版本 ${this.release.versionName} · ${(this.release.sizeBytes / 1048576).toFixed(1)} MB`)
            .fontSize(14).fontColor('#49454F').width('100%')
          Scroll() {
            Column({ space: 6 }) {
              ForEach(this.release.releaseNotes, (note: string) => {
                Text(`• ${note}`).fontSize(14).lineHeight(21).fontColor('#49454F').width('100%')
              })
            }.width('100%')
          }.constraintSize({ maxHeight: 200 }).width('100%')
        }
        if (this.phase === 'checking' || this.phase === 'verifying') {
          LoadingProgress().width(32).height(32).color('#6750A4')
          if (this.phase === 'verifying') { Text('正在校验安装包…').fontSize(14) }
        }
        if (this.phase === 'downloading') {
          Progress({ value: this.progress * 100, total: 100 }).width('100%').color('#6750A4')
          Text(`正在下载 ${(this.progress * 100).toFixed(0)}%`).fontSize(14)
        }
        if (this.phase === 'ready') { Text('请在系统安装程序中确认更新；取消后可再次打开。').fontSize(14) }
        if (this.error) { Text(this.error).fontSize(14).fontColor('#BA1A1A').lineHeight(21).width('100%') }
        Row({ space: 10 }) {
          if (!this.release?.mandatory || this.phase === 'current') {
            Button(this.phase === 'current' ? '知道了' : '稍后')
              .fontColor('#6750A4').backgroundColor(Color.Transparent)
              .enabled(this.phase !== 'downloading' && this.phase !== 'verifying')
              .onClick(this.onClose)
          }
          if (this.phase === 'available' || this.phase === 'failed' || this.phase === 'ready') {
            Button(this.phase === 'failed' ? '重试' : this.phase === 'ready' ? '打开安装程序' : '立即更新')
              .backgroundColor('#6750A4').fontColor(Color.White).onClick(() => void this.update())
          }
        }.width('100%').justifyContent(FlexAlign.End)
      }.width('88%').constraintSize({ maxWidth: 420 }).padding(24).backgroundColor('#FFFBFE').borderRadius(20)
    }.width('100%').height('100%').zIndex(60)
  }
}
