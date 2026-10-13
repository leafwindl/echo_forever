import common from '@ohos.app.ability.common';
import fs from '@ohos.file.fs';
import { EchoRepository } from '../data/EchoRepository';
import { EchoDevice } from '../model/ApiModels';
import { DeviceAccessPoint, DeviceNetwork } from '../platform/DeviceNetwork';
import { DeviceCapabilities, EchoBleDevice } from '../platform/DeviceCapabilities';
import { HarmonyBlufi } from '../platform/HarmonyBlufi';

const SPEAKER_PROMPTS: string[] = [
  '今天我想和你聊聊最近发生的一件开心的事情。',
  '我平时喜欢听音乐，也喜欢和家人朋友一起散步。',
  '我希望每天都能发现一些新的、有意思的事情。',
  '周末有空的时候，我想给自己安排一次轻松的旅行。'
];

@Component
export struct DevicesPage {
  repository?: EchoRepository;
  onBack: () => void = () => {};
  onBackHandler: (handler?: () => void) => void = () => {};
  @State private devices: EchoDevice[] = [];
  @State private loading: boolean = false;
  @State private refreshing: boolean = false;
  @State private busy: boolean = false;
  @State private error: string = '';
  @State private notice: string = '';
  @State private screen: string = 'devices';
  @State private actionSheet: boolean = false;
  @State private selected?: EchoDevice = undefined;
  @State private renameOpen: boolean = false;
  @State private nameDraft: string = '';
  @State private credential: string = '';
  @State private networks: DeviceAccessPoint[] = [];
  @State private wifiSsid: string = '';
  @State private wifiPassword: string = '';
  @State private configured: boolean = false;
  @State private bleDevices: EchoBleDevice[] = [];
  @State private bleConnected: string = '';
  @State private bleReady: boolean = false;
  @State private pairingId: string = '';
  @State private pairingCode: string = '';
  @State private pairingFallback: boolean = false;
  @State private people: Record<string, Object>[] = [];
  @State private person?: Record<string, Object> = undefined;
  @State private consent: boolean = false;
  @State private personName: string = '';
  @State private recording: boolean = false;
  @State private seconds: number = 0;
  @State private pending?: Record<string, Object> = undefined;
  @State private calibration?: Record<string, Object> = undefined;
  private capabilities: DeviceCapabilities = new DeviceCapabilities();
  private blufi: HarmonyBlufi = new HarmonyBlufi();
  private network: DeviceNetwork = new DeviceNetwork();
  private recordTimer?: number;
  private pollTimer?: number;
  private polling: boolean = false;
  private disposed: boolean = false;
  private generation: number = 0;

  aboutToAppear(): void {
    this.onBackHandler(() => this.back());
    void this.refresh();
  }
  aboutToDisappear(): void {
    this.onBackHandler(undefined);
    this.disposed = true;
    this.generation++;
    if (this.recordTimer !== undefined) clearInterval(this.recordTimer);
    if (this.pollTimer !== undefined) clearInterval(this.pollTimer);
    this.capabilities.stopScan();
    this.blufi.disconnect();
    void this.capabilities.cancelRecording();
  }

  private context(): common.UIAbilityContext { return getContext(this) as common.UIAbilityContext; }

  private async refresh(): Promise<void> {
    if (!this.repository || this.loading) return;
    this.loading = true;
    this.error = '';
    try { this.devices = await this.repository.listDevices(); }
    catch (error) { this.error = `设备列表暂时无法加载：${String(error)}`; }
    finally { this.loading = false; this.refreshing = false; }
  }

  private back(): void {
    if (this.busy || this.recording) return;
    if (this.renameOpen) { this.renameOpen = false; return; }
    if (this.credential) { this.credential = ''; return; }
    if (this.actionSheet) { this.actionSheet = false; return; }
    if (this.screen === 'speaker' && this.person) { this.person = undefined; return; }
    this.error = '';
    this.notice = '';
    this.generation++;
    this.capabilities.stopScan();
    this.blufi.disconnect();
    this.bleReady = false;
    this.bleConnected = '';
    if (this.pollTimer !== undefined) { clearInterval(this.pollTimer); this.pollTimer = undefined; }
    if (this.screen === 'devices') this.onBack();
    else { this.screen = 'devices'; void this.refresh(); }
  }

  private async deviceOperation(action: string): Promise<void> {
    this.actionSheet = false;
    this.error = '';
    this.notice = '';
    if (!this.repository || !this.selected || this.busy) return;
    const device = this.selected;
    if (action === 'rename') { this.nameDraft = device.displayName; this.renameOpen = true; return; }
    if (action === 'provision' || action === 'ble') {
      this.screen = action;
      this.configured = false;
      this.wifiPassword = '';
      if (action === 'ble') void this.scanBle();
      return;
    }
    if (action === 'speaker') {
      this.person = undefined;
      this.people = [];
      this.screen = 'speaker';
      await this.loadPeople();
      this.pollTimer = setInterval(() => void this.pollPeople(), 3000);
      return;
    }
    if (action === 'unbind') {
      AlertDialog.show({
        title: '解绑设备？', message: '解绑后设备需要重新配对才能使用。',
        primaryButton: { value: '取消', action: () => {} },
        secondaryButton: { value: '解绑', action: () => void this.unbind(device) }
      });
      return;
    }
    this.busy = true;
    try {
      if (action === 'probe') {
        await this.repository.connectDevice(device.deviceId);
        this.notice = '设备检测成功，已收到硬件回执';
        await this.refresh();
      }
      if (action === 'rotate') {
        const result = await this.repository.rotateDeviceCredential(device.deviceId);
        this.credential = String(result.credential ?? '');
        if (!this.credential) throw new Error('服务器未返回新设备凭证');
      }
    } catch (error) { this.error = String(error); }
    finally { this.busy = false; }
  }

  private async saveName(): Promise<void> {
    const name = this.nameDraft.trim();
    if (!this.repository || !this.selected || !name || this.busy) return;
    this.busy = true;
    try {
      const updated = await this.repository.renameDevice(this.selected.deviceId, name);
      this.devices = this.devices.map((device: EchoDevice) => device.deviceId === updated.deviceId ? updated : device);
      this.selected = updated;
      this.renameOpen = false;
    } catch (error) { this.error = String(error); }
    finally { this.busy = false; }
  }

  private async unbind(device: EchoDevice): Promise<void> {
    if (!this.repository || this.busy) return;
    this.busy = true;
    try {
      await this.repository.unbindDevice(device.deviceId);
      this.devices = this.devices.filter((item: EchoDevice) => item.deviceId !== device.deviceId);
      this.selected = undefined;
      this.notice = '设备已解绑';
    } catch (error) { this.error = String(error); }
    finally { this.busy = false; }
  }

  private async scanWifi(): Promise<void> {
    if (this.busy) return;
    this.busy = true;
    this.error = '';
    try {
      this.networks = await this.network.scan();
      if (!this.wifiSsid && this.networks.length) this.wifiSsid = this.networks[0].ssid;
      if (!this.networks.length) this.notice = '设备未扫描到 Wi-Fi，可以手动填写网络名称';
    } catch (error) { this.error = `无法读取设备热点，请确认手机已连接 Xiaozhi-*：${String(error)}`; }
    finally { this.busy = false; }
  }

  private async configureWifi(): Promise<void> {
    if (!this.wifiSsid.trim() || this.busy) return;
    this.busy = true;
    this.error = '';
    try {
      await this.network.configure(this.wifiSsid.trim(), this.wifiPassword);
      this.wifiPassword = '';
      this.configured = true;
      this.notice = '配网完成，设备会退出热点并连接 Echo 服务器';
    } catch (error) { this.error = String(error); }
    finally { this.busy = false; }
  }

  private async openWifi(browser: boolean): Promise<void> {
    try {
      if (browser) await this.capabilities.openBrowser(this.context());
      else await this.capabilities.openWifi(this.context());
    } catch (error) { this.error = `无法打开${browser ? '浏览器' : 'Wi-Fi 设置'}：${String(error)}`; }
  }

  private async scanBle(): Promise<void> {
    if (this.busy || this.bleConnected) return;
    this.busy = true;
    this.error = '';
    this.notice = '';
    try {
      this.bleDevices = await this.capabilities.scan(this.context());
      if (!this.bleDevices.length) this.notice = '未找到 Echo BLE 设备，请确认设备已进入配网模式';
    } catch (error) { this.error = `蓝牙扫描失败，请检查权限和蓝牙开关：${String(error)}`; }
    finally { this.busy = false; }
  }

  private async connectBle(device: EchoBleDevice): Promise<void> {
    if (this.busy || this.bleConnected) return;
    this.busy = true;
    this.error = '';
    this.notice = `正在连接 ${device.name}，建立 BluFi 加密通道`;
    this.pairingFallback = false;
    try {
      await this.blufi.connect(device.address);
      this.bleConnected = device.address;
      this.bleReady = true;
      this.notice = '蓝牙配网已就绪，请填写家庭 Wi-Fi';
    } catch (error) { this.error = String(error); this.bleReady = false; this.notice = ''; }
    finally { this.busy = false; }
  }

  private async configureBle(): Promise<void> {
    if (!this.repository || !this.bleReady || !this.wifiSsid.trim() || this.busy) return;
    this.busy = true;
    this.error = '';
    this.pairingFallback = false;
    const generation = this.generation;
    try {
      const before = await this.repository.listDevices();
      const session = await this.repository.createProvisioningSession();
      const token = String(session.claim_token ?? '');
      if (!token) throw new Error('设备绑定会话为空');
      await this.blufi.configure(this.wifiSsid.trim(), this.wifiPassword, token,
        (text: string) => this.notice = text);
      this.wifiPassword = '';
      this.notice = 'Echo 已连接 Wi-Fi，正在写入我的 Echo';
      for (let attempt = 0; attempt < 24; attempt++) {
        await new Promise<void>((resolve) => setTimeout(resolve, 2000));
        if (this.disposed || generation !== this.generation) return;
        const devices = await this.repository.listDevices();
        const found = devices.some((device: EchoDevice) =>
          !before.some((known: EchoDevice) => known.deviceId === device.deviceId) ||
          (this.selected?.deviceId === device.deviceId && device.status === 'online'));
        if (found) {
          this.devices = devices;
          this.notice = '设备已绑定到当前账号';
          this.screen = 'devices';
          this.blufi.disconnect();
          this.bleReady = false;
          this.bleConnected = '';
          return;
        }
      }
      this.pairingFallback = true;
      this.notice = 'Wi-Fi 已配置，暂时还没在设备列表看到它';
    } catch (error) {
      this.error = String(error);
      this.bleReady = false;
      this.blufi.disconnect();
      this.bleConnected = '';
      this.pairingFallback = true;
    } finally { this.busy = false; }
  }

  private async claimPairing(): Promise<void> {
    if (!this.repository || this.busy) return;
    if (!this.pairingId.trim() || !/^\d{6}$/.test(this.pairingCode.trim())) {
      this.error = '请输入设备配对 ID 和设备屏幕上的 6 位配对码';
      return;
    }
    this.busy = true;
    this.error = '';
    try {
      await this.repository.claimPairing(this.pairingId.trim(), this.pairingCode.trim());
      this.pairingCode = '';
      this.pairingId = '';
      this.devices = await this.repository.listDevices();
      this.screen = 'devices';
      this.notice = '设备已绑定到当前账号';
      this.blufi.disconnect();
      this.bleConnected = '';
      this.bleReady = false;
    } catch (error) { this.error = String(error); }
    finally { this.busy = false; }
  }

  private async loadPeople(): Promise<void> {
    if (!this.repository || !this.selected) return;
    this.busy = true;
    try { this.people = await this.repository.listSpeakerPeople(this.selected.deviceId); }
    catch (error) { this.error = String(error); }
    finally { this.busy = false; }
  }

  private async pollPeople(): Promise<void> {
    if (!this.repository || !this.selected || this.busy || this.recording || this.polling || this.screen !== 'speaker') return;
    this.polling = true;
    const generation = this.generation;
    try {
      const pending = await this.repository.speakerState(this.selected.deviceId, 'speaker-enrollment-request');
      const calibration = await this.repository.speakerState(this.selected.deviceId, 'speaker-calibration');
      const people = await this.repository.listSpeakerPeople(this.selected.deviceId);
      if (this.disposed || generation !== this.generation || this.busy || this.recording) return;
      this.pending = pending.request as Record<string, Object> | undefined;
      this.calibration = calibration.session as Record<string, Object> | undefined;
      this.people = people;
      if (this.person) this.person = people.find((item: Record<string, Object>) => item.person_id === this.person?.person_id);
    } catch (_) { this.pending = undefined; }
    finally { this.polling = false; }
  }

  private async createPerson(): Promise<void> {
    if (!this.repository || !this.selected || !this.consent || !this.personName.trim() || this.busy) return;
    this.busy = true;
    this.error = '';
    try {
      this.person = await this.repository.createSpeakerPerson(this.selected.deviceId, this.personName);
      this.people = [...this.people, this.person];
      this.personName = '';
      this.consent = false;
    } catch (error) { this.error = String(error); }
    finally { this.busy = false; }
  }

  private async startRecording(): Promise<void> {
    if (this.busy || this.recording || !this.person) return;
    this.busy = true;
    this.error = '';
    this.notice = '';
    try {
      await this.capabilities.startRecording(this.context());
      this.recording = true;
      this.seconds = 0;
      this.recordTimer = setInterval(() => {
        this.seconds++;
        if (this.seconds >= 10) void this.stopRecording();
      }, 1000);
    } catch (error) { this.error = String(error); }
    finally { this.busy = false; }
  }

  private async stopRecording(): Promise<void> {
    if (!this.recording || this.busy || !this.repository || !this.selected || !this.person) return;
    if (this.recordTimer !== undefined) clearInterval(this.recordTimer);
    this.recordTimer = undefined;
    this.recording = false;
    this.busy = true;
    let path = '';
    try {
      path = await this.capabilities.stopRecording(this.context());
      this.person = await this.repository.uploadSpeakerSample(this.selected.deviceId, String(this.person.person_id), path);
      this.notice = this.person.status === 'active' ? '录入与独立验证已完成' : '本段已保存，请录制下一句';
      this.people = this.people.map((item: Record<string, Object>) => item.person_id === this.person?.person_id ? this.person! : item);
    } catch (error) { this.error = String(error); }
    finally {
      try {
        if (path && fs.accessSync(path)) await fs.unlink(path);
      } catch (_) {
        this.error = this.error || '录音缓存清理失败，请退出后重试';
      } finally { this.busy = false; }
    }
  }

  private confirmPersonAction(action: string, person: Record<string, Object>): void {
    const name = String(person.display_name);
    AlertDialog.show({
      title: action === 'delete' ? `删除 ${name} 的声纹？` : `为${name}校准 Echo 声音`,
      message: action === 'delete' ? '删除后 Echo 不再使用该人员的声纹。'
        : '请确认由本人对 Echo 朗读 App 显示的四句话，并已同意保存声纹特征。前三段采样，第四段独立验证；录音不会保存。',
      primaryButton: { value: '取消', action: () => {} },
      secondaryButton: { value: action === 'delete' ? '删除' : '本人同意，开始',
        action: () => void this.personAction(action, person) }
    });
  }

  private async personAction(action: string, person?: Record<string, Object>): Promise<void> {
    if (!this.repository || !this.selected || this.busy || this.recording) return;
    this.busy = true;
    this.error = '';
    try {
      const id = this.selected.deviceId;
      if (action === 'delete' && person) {
        await this.repository.deleteSpeakerPerson(id, String(person.person_id));
        this.people = this.people.filter((item: Record<string, Object>) => item.person_id !== person.person_id);
        if (this.person?.person_id === person.person_id) this.person = undefined;
      } else if (action === 'calibrate' && person) {
        this.calibration = await this.repository.calibrateSpeaker(id, String(person.person_id));
      } else if (action === 'cancel') {
        await this.repository.cancelSpeakerCalibration(id);
        this.calibration = undefined;
      } else if (action === 'removeCalibration' && person) {
        await this.repository.cancelSpeakerCalibration(id, String(person.person_id));
        this.people = await this.repository.listSpeakerPeople(id);
      } else if (this.pending) {
        await this.repository.approveSpeakerRequest(id, String(this.pending.session_id), action === 'approve');
        this.pending = undefined;
        this.notice = action === 'approve' ? '已批准，请对 Echo 说“开始录入”' : '已取消硬件录入';
      }
    } catch (error) { this.error = String(error); }
    finally { this.busy = false; }
  }

  @Builder
  private header() {
    Row() {
      Button() { Image($r('app.media.arrow_back_outline')).width(24).height(24) }
        .width(48).height(48).backgroundColor(Color.Transparent).enabled(!this.busy && !this.recording)
        .onClick(() => this.back())
      Text(this.screen === 'devices' ? '我的 Echo' : this.screen === 'speaker'
        ? '人员声纹' : this.screen === 'ble' ? '设备蓝牙配网' : 'Echo Wi-Fi 配网')
        .fontSize(22).fontWeight(FontWeight.Bold).fontColor('#262331').layoutWeight(1)
      Button() { Image($r('app.media.refresh_outline')).width(24).height(24) }
        .width(48).height(48).backgroundColor(Color.Transparent).enabled(!this.busy && !this.loading && !this.recording)
        .onClick(() => {
          if (this.screen === 'devices') void this.refresh();
          else if (this.screen === 'speaker') void this.loadPeople();
          else if (this.screen === 'ble') void this.scanBle();
          else void this.scanWifi();
        })
    }.width('100%').height(64).padding({ left: 10, right: 10 })
  }

  @Builder
  private devicesContent() {
    if (this.loading && !this.devices.length) {
      Column({ space: 12 }) {
        LoadingProgress().width(30).height(30).color('#6750A4')
        Text('正在加载设备').fontSize(14).fontColor('#6F6A78')
      }.layoutWeight(1).width('100%').justifyContent(FlexAlign.Center)
    } else if (!this.devices.length && !this.error) {
      Column({ space: 16 }) {
        Text('还没有绑定 Echo 设备').fontSize(16).fontColor('#49454F')
        Button('添加新设备').fontColor('#6750A4').backgroundColor('#E8DEF8')
          .onClick(() => { this.screen = 'ble'; void this.scanBle(); })
      }.width('100%').layoutWeight(1).justifyContent(FlexAlign.Center)
    } else {
      Button('添加新设备').fontSize(14).fontColor('#6750A4').backgroundColor(Color.Transparent)
        .enabled(!this.busy).width('100%').onClick(() => {
          this.screen = 'ble';
          void this.scanBle();
        })
      Refresh({ refreshing: $$this.refreshing }) {
        List({ space: 10 }) {
          ForEach(this.devices, (device: EchoDevice) => {
            ListItem() {
              Row({ space: 14 }) {
                Image($r('app.media.speaker_outline')).width(36).height(36)
                Column({ space: 6 }) {
                  Text(device.displayName).fontSize(17).fontColor('#262331').width('100%')
                  Text(`${device.status === 'online' ? '在线' : device.status === 'offline' ? '离线' : '未知'} · 固件 ${device.firmwareVersion || '未知'}`)
                    .fontSize(14).fontColor(device.status === 'online' ? '#2E7D32' : '#6F6A78').width('100%')
                }.layoutWeight(1)
                Button() { Image($r('app.media.more_vert_outline')).width(24).height(24) }
                  .width(44).height(44).backgroundColor(Color.Transparent).enabled(!this.busy)
                  .accessibilityText('设备设置').onClick(() => { this.selected = device; this.actionSheet = true; })
              }.width('100%').padding(16)
            }
          }, (device: EchoDevice) => device.deviceId)
        }.width('100%').height('100%').padding({ left: 16, right: 16, bottom: 96 })
      }.layoutWeight(1).width('100%').onRefreshing(() => void this.refresh())
    }
  }

  @Builder
  private wifiContent() {
    Scroll() {
      Column({ space: 16 }) {
        Text(this.configured ? '配网完成' : '把 Echo 连接到家庭 Wi-Fi').fontSize(22).fontColor('#262331').width('100%')
        if (!this.configured) {
          Text('手机需要先连接设备热点 Xiaozhi-*。Wi-Fi 密码只发送给设备，不会上传到 Echo 服务器。')
            .fontSize(14).lineHeight(22).fontColor('#49454F').width('100%')
          Button('打开 Wi-Fi 设置').width('100%').enabled(!this.busy).onClick(() => void this.openWifi(false))
          Button('已连接热点，重新扫描').width('100%').enabled(!this.busy).onClick(() => void this.scanWifi())
          Button('使用浏览器配网').width('100%').backgroundColor('#E8DEF8').fontColor('#6750A4')
            .enabled(!this.busy).onClick(() => void this.openWifi(true))
          if (this.networks.length) {
            Select(this.networks.map((point: DeviceAccessPoint): SelectOption => ({ value: `${point.ssid}  ${point.rssi} dBm` })))
              .value(this.wifiSsid).width('100%').enabled(!this.busy)
              .onSelect((index: number) => this.wifiSsid = this.networks[index].ssid)
          }
          TextInput({ text: this.wifiSsid, placeholder: '家庭 Wi-Fi 名称' }).enabled(!this.busy)
            .onChange((value: string) => this.wifiSsid = value)
          TextInput({ text: this.wifiPassword, placeholder: 'Wi-Fi 密码' }).type(InputType.Password).enabled(!this.busy)
            .onChange((value: string) => this.wifiPassword = value)
          Button('连接 Wi-Fi').width('100%').enabled(!this.busy && this.wifiSsid.trim().length > 0)
            .backgroundColor('#6750A4').fontColor(Color.White).onClick(() => void this.configureWifi())
        } else {
          Text('设备会自动退出热点并连接 Echo 服务器。').fontSize(14).fontColor('#49454F').width('100%')
          Button('完成').onClick(() => this.back())
        }
      }.padding(20).width('100%')
    }.layoutWeight(1).width('100%').align(Alignment.TopStart)
  }

  @Builder
  private bleContent() {
    Scroll() {
    Column({ space: 14 }) {
      Text('扫描并连接 Echo BLE 设备').fontSize(16).fontColor('#49454F').width('100%')
      if (this.busy) { LoadingProgress().width(32).height(32).color('#6750A4') }
      Column({ space: 10 }) {
        ForEach(this.bleDevices, (device: EchoBleDevice) => {
          Row({ space: 8 }) {
            Column({ space: 6 }) {
              Text(device.name).fontSize(16).width('100%')
              Text(`${device.address} · ${device.rssi} dBm`).fontSize(13).fontColor('#6F6A78').width('100%')
            }.layoutWeight(1)
            Button('连接').enabled(!this.busy && !this.bleConnected).onClick(() => void this.connectBle(device))
          }
          .padding(12).width('100%')
        }, (device: EchoBleDevice) => device.address)
      }.width('100%')
      if (this.bleReady) {
        TextInput({ text: this.wifiSsid, placeholder: '家庭 Wi-Fi 名称' }).enabled(!this.busy)
          .onChange((value: string) => this.wifiSsid = value)
        TextInput({ text: this.wifiPassword, placeholder: 'Wi-Fi 密码' }).type(InputType.Password).enabled(!this.busy)
          .onChange((value: string) => this.wifiPassword = value)
        Button('配网并绑定 Echo').width('100%').enabled(!this.busy && this.wifiSsid.trim().length > 0)
          .backgroundColor('#6750A4').fontColor(Color.White).onClick(() => void this.configureBle())
        Button('断开连接').enabled(!this.busy).onClick(() => {
          this.blufi.disconnect(); this.bleReady = false; this.bleConnected = '';
        })
      }
      if (this.pairingFallback) {
        TextInput({ text: this.pairingId, placeholder: '设备配对 ID' }).enabled(!this.busy)
          .onChange((value: string) => this.pairingId = value)
        TextInput({ text: this.pairingCode, placeholder: '设备屏幕上的 6 位配对码' }).maxLength(6).type(InputType.Number)
          .enabled(!this.busy).onChange((value: string) => this.pairingCode = value)
        Button('绑定设备').enabled(!this.busy).onClick(() => void this.claimPairing())
      }
      Button('使用设备热点配网').width('100%').fontColor('#6750A4').backgroundColor('#E8DEF8')
        .enabled(!this.busy).onClick(() => {
          this.blufi.disconnect(); this.bleReady = false; this.bleConnected = '';
          this.error = ''; this.notice = '';
          this.screen = 'provision'; this.configured = false;
        })
    }.width('100%').padding(20)
    }.layoutWeight(1).width('100%').align(Alignment.TopStart)
  }

  @Builder
  private speakerContent() {
    Scroll() {
      Column({ space: 16 }) {
        if (this.pending?.state === 'approval') {
          Text(`Echo 请求录入：${String(this.pending?.display_name ?? '')}`).fontSize(16).width('100%')
          Row({ space: 12 }) {
            Button('拒绝').enabled(!this.busy).onClick(() => void this.personAction('reject'))
            Button('批准本次录入').enabled(!this.busy).onClick(() => void this.personAction('approve'))
          }
        }
        if (this.calibration) {
          Text(`硬件校准：${String(this.calibration.state ?? '')}`).fontSize(16).width('100%')
          Text(String(this.calibration.prompt ?? this.calibration.current_prompt ?? '')).fontSize(16).lineHeight(24).width('100%')
          Button('取消本次校准').enabled(!this.busy).onClick(() => void this.personAction('cancel'))
        }
        if (!this.person) {
          ForEach(this.people, (person: Record<string, Object>) => {
            Row({ space: 10 }) {
              Column({ space: 5 }) {
                Text(String(person.display_name)).fontSize(16).width('100%')
                Text(person.status === 'active' ? '已录入' : '待完成录入').fontSize(13).fontColor('#6F6A78').width('100%')
              }.layoutWeight(1).onClick(() => { this.person = person; this.error = ''; this.notice = ''; })
              Button() { Image($r('app.media.delete_outline')).width(24).height(24) }
                .width(44).height(44).backgroundColor(Color.Transparent).enabled(!this.busy)
                .onClick(() => this.confirmPersonAction('delete', person))
            }.width('100%')
            if (person.status === 'active') {
              Row({ space: 8 }) {
                Button(person.hardware_calibrated === true ? '重新校准 Echo' : '校准 Echo')
                  .enabled(!this.busy).onClick(() => this.confirmPersonAction('calibrate', person))
                if (person.hardware_calibrated === true) {
                  Button('删除硬件校准').enabled(!this.busy).onClick(() => void this.personAction('removeCalibration', person))
                }
              }.width('100%')
            }
          }, (person: Record<string, Object>) => String(person.person_id))
          TextInput({ text: this.personName, placeholder: '新成员称呼' }).maxLength(40).enabled(!this.busy)
            .onChange((value: string) => this.personName = value)
          Row({ space: 8 }) {
            Checkbox().select(this.consent).enabled(!this.busy).onChange((value: boolean) => this.consent = value)
            Text('本人同意保存声纹特征，用于称呼识别').fontSize(14).layoutWeight(1)
          }.width('100%')
          Button('创建成员').enabled(this.consent && this.personName.trim().length > 0 && !this.busy)
            .onClick(() => void this.createPerson())
        } else {
          Text(String(this.person.display_name)).fontSize(20).width('100%')
          Text(this.person.status === 'active' ? '录入与独立验证已完成' : `第 ${Math.min(Number(this.person.sample_count ?? 0) + 1, 4)} 段 / 共 4 段`)
            .fontSize(15).fontColor('#49454F').width('100%')
          if (this.person.status !== 'active') {
            Text(SPEAKER_PROMPTS[Math.min(Number(this.person.sample_count ?? 0), 3)])
              .fontSize(18).lineHeight(28).fontColor('#262331').width('100%')
            Text(this.recording ? `正在录音 ${this.seconds} 秒` : '每段至少 3 秒，最多 10 秒').fontSize(14)
            Button(this.recording ? '停止并保存' : '开始录音').enabled(!this.busy)
              .backgroundColor('#6750A4').fontColor(Color.White)
              .onClick(() => { if (this.recording) void this.stopRecording(); else void this.startRecording(); })
          }
          Button('返回人员列表').enabled(!this.busy && !this.recording).onClick(() => this.person = undefined)
        }
      }.padding(20).width('100%').alignItems(HorizontalAlign.Start)
    }.layoutWeight(1).width('100%').align(Alignment.TopStart)
  }

  @Builder
  private actionRow(label: string, action: string) {
    Row({ space: 12 }) {
      Image(action === 'probe' ? $r('app.media.network_check_outline') : action === 'ble'
        ? $r('app.media.bluetooth_outline') : action === 'provision' ? $r('app.media.wifi_outline')
          : action === 'rename' ? $r('app.media.edit_outline') : action === 'rotate' ? $r('app.media.key_outline')
            : action === 'speaker' ? $r('app.media.voice_outline') : $r('app.media.link_off_outline')).width(24).height(24)
      Column({ space: 3 }) {
        Text(label).fontSize(16).fontColor('#262331').width('100%')
        if (action === 'ble' || action === 'provision') {
          Text(action === 'ble' ? '扫描并连接 Echo BLE 设备' : '连接设备热点并设置家庭 Wi-Fi')
            .fontSize(13).fontColor('#6F6A78').width('100%')
        }
      }.layoutWeight(1)
    }.width('100%').height(action === 'ble' || action === 'provision' ? 68 : 52)
      .padding({ left: 20, right: 20 })
      .onClick(() => void this.deviceOperation(action))
  }

  build() {
    Stack({ alignContent: Alignment.Bottom }) {
      Column() {
        this.header()
        if (this.error) {
          Row({ space: 10 }) {
            Text(this.error).fontSize(14).fontColor('#BA1A1A').layoutWeight(1)
            if (this.screen === 'devices') {
              Button('重试').enabled(!this.loading).onClick(() => void this.refresh())
            }
          }.width('100%').padding({ left: 20, right: 20, top: 8, bottom: 8 })
        }
        if (this.notice) {
          Text(this.notice).fontSize(14).fontColor('#49454F').width('100%').padding({ left: 20, right: 20, top: 8, bottom: 8 })
        }
        if (this.busy && this.screen !== 'ble') {
          Progress({ value: 0 }).width('90%').color('#6750A4')
        }
        if (this.screen === 'devices') { this.devicesContent() }
        else if (this.screen === 'provision') { this.wifiContent() }
        else if (this.screen === 'speaker') { this.speakerContent() }
        else { this.bleContent() }
      }.width('100%').height('100%')
      if (this.actionSheet) {
        Column().width('100%').height('100%').backgroundColor('#88000000').onClick(() => this.actionSheet = false)
        Column() {
          Row().width(32).height(4).borderRadius(2).backgroundColor('#79747E').margin({ bottom: 8 })
          this.actionRow('设备检测', 'probe')
          this.actionRow('蓝牙配网', 'ble')
          this.actionRow('重新配网', 'provision')
          this.actionRow('重命名', 'rename')
          this.actionRow('轮换设备凭证', 'rotate')
          this.actionRow('人员声纹', 'speaker')
          this.actionRow('解绑设备', 'unbind')
        }.width('100%').padding({ top: 12, bottom: 24 }).backgroundColor('#FFFBFE')
          .borderRadius({ topLeft: 20, topRight: 20 })
      }
      if (this.renameOpen || this.credential) {
        Stack() {
          Column().width('100%').height('100%').backgroundColor('#88000000')
          Column({ space: 18 }) {
            Text(this.renameOpen ? '重命名设备' : '新设备凭证').fontSize(20).fontWeight(FontWeight.Bold).width('100%')
            if (this.renameOpen) {
              TextInput({ text: this.nameDraft }).maxLength(40).enabled(!this.busy)
                .onChange((value: string) => this.nameDraft = value)
            } else {
              Text(this.credential).copyOption(CopyOptions.LocalDevice).fontSize(14).width('100%')
            }
            Row({ space: 12 }) {
              if (this.renameOpen) {
                Button('取消').enabled(!this.busy).onClick(() => this.renameOpen = false)
                Button('保存').enabled(!this.busy && this.nameDraft.trim().length > 0).onClick(() => void this.saveName())
              } else { Button('完成').onClick(() => this.credential = '') }
            }.width('100%').justifyContent(FlexAlign.End)
          }.width('88%').padding(24).backgroundColor('#FFFBFE').borderRadius(20)
        }.width('100%').height('100%')
      }
    }.width('100%').height('100%').backgroundColor('#F8F7FC')
  }
}
