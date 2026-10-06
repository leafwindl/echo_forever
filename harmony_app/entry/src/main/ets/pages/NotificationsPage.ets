import common from '@ohos.app.ability.common';
import preferences from '@ohos.data.preferences';
import { HarmonyNotifications } from '../platform/HarmonyNotifications';

@Component
export struct NotificationsPage {
  onBack: () => void = () => {};
  @State private status: string = 'unknown';
  @State private busy: boolean = false;
  @State private error: string = '';
  @StorageProp('pushStatus') private pushStatus: string = 'starting';
  @StorageProp('pushClientId') private pushClientId: string = '';
  @StorageProp('pushError') private pushError: string = '';
  @StorageProp('pushEpoch') @Watch('refresh') private pushEpoch: number = 0;
  @StorageProp('foregroundEpoch') @Watch('refresh') private foregroundEpoch: number = 0;
  private notifications: HarmonyNotifications = new HarmonyNotifications();
  private timer?: number;
  private polling: boolean = false;
  private disposed: boolean = false;

  aboutToAppear(): void {
    void this.refresh();
    this.timer = setInterval(() => void this.refresh(), 1000);
  }

  aboutToDisappear(): void {
    this.disposed = true;
    if (this.timer !== undefined) clearInterval(this.timer);
  }

  private async refresh(): Promise<void> {
    if (this.disposed || this.polling) return;
    this.polling = true;
    try {
      const context = getContext(this) as common.UIAbilityContext;
      const store = await preferences.getPreferences(context, 'echo-notifications');
      const requested = await store.get('requested', false);
      const enabled = await this.notifications.enabled();
      if (!this.disposed) {
        this.status = enabled ? 'authorized'
          : requested || this.status === 'authorized' ? 'denied' : 'unknown';
        this.error = '';
      }
    } catch (error) {
      this.error = `无法读取通知状态：${String(error)}`;
    } finally {
      this.polling = false;
    }
  }

  private async configure(): Promise<void> {
    if (this.busy) return;
    this.busy = true;
    this.error = '';
    const context = getContext(this) as common.UIAbilityContext;
    try {
      if (this.status === 'authorized' || this.status === 'denied') {
        await this.notifications.openSettings(context);
      } else {
        const store = await preferences.getPreferences(context, 'echo-notifications');
        await store.put('requested', true);
        await store.flush();
        await this.notifications.request(context);
      }
    } catch (error) {
      this.error = `通知设置未完成：${String(error)}`;
    } finally {
      await this.refresh();
      this.busy = false;
    }
  }

  build() {
    Column() {
      Row() {
        Button() { Image($r('app.media.arrow_back_outline')).width(24).height(24) }
          .width(48).height(48).backgroundColor(Color.Transparent).onClick(this.onBack)
        Text('通知设置').fontSize(22).fontWeight(FontWeight.Bold).fontColor('#262331').layoutWeight(1)
      }.width('100%').height(64).padding({ left: 10, right: 10 })
      Scroll() {
        Column({ space: 20 }) {
          Text('通知只用于提醒 Echo 来信等与你的账号相关的事件。锁屏通知不会包含聊天正文、Persona、记忆或转写内容。你可以随时在系统设置中关闭通知。')
            .fontSize(15).lineHeight(23).fontColor('#49454F').width('100%')
          Row({ space: 12 }) {
            Column({ space: 4 }) {
              Text('Echo 通知').fontSize(16).fontColor('#262331').width('100%')
              Text(this.status === 'authorized' ? '已允许' : this.status === 'denied'
                ? '已拒绝，可前往系统设置修改' : '尚未设置')
                .fontSize(14).fontColor('#6F6A78').width('100%')
            }.layoutWeight(1)
            Button() {
              Row({ space: 6 }) {
                Image(this.status === 'unknown'
                  ? $r('app.media.notifications_outline') : $r('app.media.settings_outline')).width(20).height(20)
                  .fillColor(Color.White)
                Text(this.status === 'unknown' ? '允许通知' : '系统设置').fontSize(14)
              }
            }.height(42).backgroundColor('#6750A4').fontColor(Color.White)
              .enabled(!this.busy).onClick(() => void this.configure())
          }.width('100%')
          Text(this.pushStatus === 'registered'
            ? '远程推送已注册'
            : this.pushStatus === 'ready'
            ? '已获取推送标识，等待登录注册'
            : this.pushStatus === 'unconfigured'
            ? '未配置鸿蒙个推 AppID，暂时无法后台推送'
            : this.pushStatus === 'registration_failed'
            ? '推送注册失败，请检查网络和服务端会话'
            : this.pushStatus === 'failed'
            ? '个推初始化失败，请检查鸿蒙 AppID 和 HAR 配置'
            : '正在初始化远程推送')
            .fontSize(13).fontColor('#6F6A78').width('100%')
          if (this.error) { Text(this.error).fontColor('#BA1A1A').fontSize(14).width('100%') }
        }.padding(20).width('100%').alignItems(HorizontalAlign.Start)
      }.layoutWeight(1).width('100%').align(Alignment.TopStart)
    }.width('100%').height('100%').backgroundColor('#F8F7FC')
  }
}
