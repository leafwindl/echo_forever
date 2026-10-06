import common from '@ohos.app.ability.common';
import abilityAccessCtrl from '@ohos.abilityAccessCtrl';
import { Permissions } from '@ohos.abilityAccessCtrl';
import ble from '@ohos.bluetooth.ble';
import audio from '@ohos.multimedia.audio';
import fs from '@ohos.file.fs';

export interface EchoBleDevice {
  address: string;
  name: string;
  rssi: number;
}

export class DeviceCapabilities {
  private capturer?: audio.AudioCapturer;
  private chunks: ArrayBuffer[] = [];
  private bytes: number = 0;
  private scanCallback?: (results: ble.ScanResult[]) => void;
  private scanDone?: () => void;

  private async permission(context: common.UIAbilityContext, microphone: boolean): Promise<void> {
    const permissions: Array<Permissions> = [microphone ? 'ohos.permission.MICROPHONE' : 'ohos.permission.ACCESS_BLUETOOTH'];
    const result = await abilityAccessCtrl.createAtManager().requestPermissionsFromUser(context, permissions);
    if (result.authResults.some((value: number) => value !== 0)) {
      throw new Error(microphone ? '请允许 Echo 使用麦克风' : '请允许 Echo 使用蓝牙');
    }
  }

  async scan(context: common.UIAbilityContext): Promise<EchoBleDevice[]> {
    await this.permission(context, false);
    this.stopScan();
    const found: Map<string, EchoBleDevice> = new Map<string, EchoBleDevice>();
    this.scanCallback = (results: ble.ScanResult[]) => {
      results.forEach((result: ble.ScanResult) => {
        if (/xiaozhi|echo|blufi/i.test(result.deviceName)) {
          found.set(result.deviceId, {
            address: result.deviceId, name: result.deviceName, rssi: result.rssi
          });
        }
      });
    };
    try {
      ble.on('BLEDeviceFind', this.scanCallback);
      ble.startBLEScan([], { interval: 0 });
      await new Promise<void>((resolve) => {
        const timer = setTimeout(resolve, 6000);
        this.scanDone = () => { clearTimeout(timer); resolve(); };
      });
      const devices: EchoBleDevice[] = [];
      found.forEach((device: EchoBleDevice) => devices.push(device));
      return devices.sort((a: EchoBleDevice, b: EchoBleDevice) => b.rssi - a.rssi);
    } finally {
      this.stopScan();
    }
  }

  stopScan(): void {
    this.scanDone?.();
    this.scanDone = undefined;
    if (this.scanCallback) {
      try { ble.stopBLEScan(); ble.off('BLEDeviceFind', this.scanCallback); } catch (_) {}
      this.scanCallback = undefined;
    }
  }

  async openWifi(context: common.UIAbilityContext): Promise<void> {
    await context.startAbility({ action: 'ohos.settings.wifi' });
  }

  async openBrowser(context: common.UIAbilityContext): Promise<void> {
    await context.startAbility({ action: 'ohos.want.action.viewData', uri: 'http://192.168.4.1' });
  }

  async startRecording(context: common.UIAbilityContext): Promise<void> {
    await this.permission(context, true);
    await this.cancelRecording();
    this.chunks = [];
    this.bytes = 0;
    const capturer = await audio.createAudioCapturer({
      streamInfo: { samplingRate: 16000, channels: 1,
        sampleFormat: audio.AudioSampleFormat.SAMPLE_FORMAT_S16LE,
        encodingType: audio.AudioEncodingType.ENCODING_TYPE_RAW },
      capturerInfo: { source: audio.SourceType.SOURCE_TYPE_MIC, capturerFlags: 0 }
    });
    this.capturer = capturer;
    capturer.on('readData', (buffer: ArrayBuffer) => {
      const remaining = 384000 - this.bytes;
      if (remaining > 0) {
        const chunk = buffer.slice(0, Math.min(buffer.byteLength, remaining));
        this.chunks.push(chunk);
        this.bytes += chunk.byteLength;
      }
    });
    try { await capturer.start(); }
    catch (error) { await this.cancelRecording(); throw new Error(String(error)); }
  }

  async stopRecording(context: common.UIAbilityContext): Promise<string> {
    if (!this.capturer) throw new Error('录音未开始');
    const capturer = this.capturer;
    this.capturer = undefined;
    try { await capturer.stop(); }
    finally { capturer.off('readData'); await capturer.release(); }
    if (this.bytes < 96000) { this.chunks = []; this.bytes = 0; throw new Error('请至少录制 3 秒'); }
    const data = new Uint8Array(this.bytes);
    let offset = 0;
    this.chunks.forEach((chunk: ArrayBuffer) => {
      data.set(new Uint8Array(chunk), offset);
      offset += chunk.byteLength;
    });
    this.chunks = [];
    this.bytes = 0;
    const path = `${context.cacheDir}/echo-voice-sample.pcm`;
    const file = await fs.open(path, fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.TRUNC);
    try { await fs.write(file.fd, data.buffer); }
    finally { await fs.close(file); }
    return path;
  }

  async cancelRecording(): Promise<void> {
    const capturer = this.capturer;
    this.capturer = undefined;
    if (capturer) {
      try { await capturer.stop(); }
      finally { capturer.off('readData'); await capturer.release(); }
    }
    this.chunks = [];
    this.bytes = 0;
  }
}
