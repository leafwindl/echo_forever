import ble from '@ohos.bluetooth.ble';
import crypto from '@ohos.security.cryptoFramework';
import util from '@ohos.util';
import { blufiCrc, bytesHex, concatBytes, frameBlufi, hexBytes } from './BlufiProtocol';

const BLUFI_SERVICE = '0000ffff-0000-1000-8000-00805f9b34fb';
const BLUFI_WRITE = '0000ff01-0000-1000-8000-00805f9b34fb';
const BLUFI_NOTIFY = '0000ff02-0000-1000-8000-00805f9b34fb';
const DH_P = 'cf5cf5c38419a724957ff5dd323b9c45c3cdd261eb740f69aa94b8bb1a5c9640' +
  '9153bd76b24222d03274e4725a5406092e9e82e9135c643cae98132b0d95f7d6' +
  '5347c68afc1e677da90e51bbab5f5cf429c291b4ba39c6b2dc5e8c7231e46aa7' +
  '728e87664532cdf547be20c9a3fa8342be6e34371a27c06f7dc0edddd2f86373';

export class HarmonyBlufi {
  private client?: ble.GattClientDevice;
  private writeCharacteristic?: ble.BLECharacteristic;
  private key?: crypto.SymKey;
  private sendSequence: number = 0;
  private readSequence: number = 0;
  private fragmentType: number = -1;
  private fragments: Uint8Array[] = [];
  private receiveChain: Promise<void> = Promise.resolve();
  private received: Map<number, Uint8Array> = new Map<number, Uint8Array>();
  private wake?: () => void;
  private failure: string = '';
  private ready: boolean = false;
  private generation: number = 0;
  private cancelConnection?: () => void;

  private checkGeneration(generation: number): void {
    if (generation !== this.generation) throw new Error('蓝牙连接已取消');
  }

  private async wait(type: number, timeout: number): Promise<Uint8Array> {
    const generation = this.generation;
    const deadline = Date.now() + timeout;
    while (Date.now() < deadline) {
      this.checkGeneration(generation);
      if (this.failure) throw new Error(this.failure);
      const value = this.received.get(type);
      if (value) { this.received.delete(type); return value; }
      await new Promise<void>((resolve) => {
        const timer = setTimeout(resolve, Math.min(250, Math.max(1, deadline - Date.now())));
        this.wake = () => { clearTimeout(timer); resolve(); };
      });
      this.wake = undefined;
    }
    throw new Error('BluFi 设备响应超时，请重新连接后重试');
  }

  async connect(address: string): Promise<void> {
    this.disconnect();
    this.failure = '';
    this.sendSequence = 0;
    this.readSequence = 0;
    this.received.clear();
    this.fragments = [];
    this.receiveChain = Promise.resolve();
    const generation = this.generation;
    const client = ble.createGattClientDevice(address);
    this.client = client;
    try {
      await new Promise<void>((resolve, reject) => {
        let connected = false;
        const timer = setTimeout(() => {
          this.cancelConnection = undefined;
          reject(new Error('蓝牙连接超时'));
        }, 15000);
        this.cancelConnection = () => { clearTimeout(timer); reject(new Error('蓝牙连接已取消')); };
        client.on('BLEConnectionStateChange', (state: ble.BLEConnectionChangeState) => {
          if (generation !== this.generation) return;
          if (state.state === 2) {
            connected = true; clearTimeout(timer); this.cancelConnection = undefined; resolve();
          }
          else if (state.state === 0) {
            this.failure = 'Echo 蓝牙已断开，请重新连接';
            this.ready = false;
            this.wake?.();
            if (!connected) {
              clearTimeout(timer); this.cancelConnection = undefined; reject(new Error(this.failure));
            }
          }
        });
        try { client.connect(); }
        catch (error) {
          clearTimeout(timer); this.cancelConnection = undefined; reject(new Error(String(error)));
        }
      });
      this.checkGeneration(generation);
      const services = await client.getServices();
      this.checkGeneration(generation);
      const service = services.find((item: ble.GattService) => item.serviceUuid.toLowerCase() === BLUFI_SERVICE);
      if (!service) throw new Error('设备未提供 BluFi 服务');
      this.writeCharacteristic = service.characteristics.find((item: ble.BLECharacteristic) => item.characteristicUuid.toLowerCase() === BLUFI_WRITE);
      const notify = service.characteristics.find((item: ble.BLECharacteristic) => item.characteristicUuid.toLowerCase() === BLUFI_NOTIFY);
      if (!this.writeCharacteristic || !notify) throw new Error('BluFi 服务特征不完整');
      client.on('BLECharacteristicChange', (characteristic: ble.BLECharacteristic) => {
        if (generation !== this.generation || characteristic.characteristicUuid.toLowerCase() !== BLUFI_NOTIFY) return;
        const packet = new Uint8Array(characteristic.characteristicValue.slice(0));
        this.receiveChain = this.receiveChain.then(() => {
          this.checkGeneration(generation);
          return this.receive(packet);
        }).catch((error: Error) => {
          if (generation === this.generation) { this.failure = String(error); this.wake?.(); }
        });
      });
      await client.setCharacteristicChangeNotification(notify, true);
      this.checkGeneration(generation);
      await this.negotiate();
      if (generation !== this.generation) throw new Error('蓝牙连接已取消');
      this.ready = true;
    } catch (error) {
      if (generation === this.generation) this.disconnect();
      throw new Error(`BluFi 连接失败：${String(error)}`);
    }
  }

  private async aes(bytes: Uint8Array, sequence: number, encrypt: boolean): Promise<Uint8Array> {
    if (!this.key) throw new Error('BluFi 加密通道尚未就绪');
    const cipher = crypto.createCipher('AES128|CFB128|NoPadding');
    const iv = new Uint8Array(16);
    iv[0] = sequence;
    const params: crypto.IvParamsSpec = { algName: 'IvParamsSpec', iv: { data: iv } };
    await cipher.init(encrypt ? crypto.CryptoMode.ENCRYPT_MODE : crypto.CryptoMode.DECRYPT_MODE, this.key, params);
    return (await cipher.doFinal({ data: bytes })).data;
  }

  private async post(type: number, data: Uint8Array, encrypt: boolean = false, checksum: boolean = false,
    requireAck: boolean = false): Promise<number> {
    if (!this.client || !this.writeCharacteristic || this.failure) throw new Error(this.failure || '蓝牙未连接');
    const generation = this.generation;
    const client = this.client;
    const characteristic = this.writeCharacteristic;
    let offset = 0;
    let lastSequence = 0;
    do {
      this.checkGeneration(generation);
      const capacity = checksum ? 12 : 14;
      const take = Math.min(capacity, data.length - offset);
      const fragmented = offset + take < data.length;
      const chunk = data.slice(offset, offset + take);
      const remaining = data.length - offset;
      const plain = fragmented ? concatBytes([new Uint8Array([remaining & 255, remaining >> 8]), chunk]) : chunk;
      const sequence = this.sendSequence++ & 255;
      lastSequence = sequence;
      const encrypted = encrypt ? plain.length ? await this.aes(plain, sequence, true) : plain : undefined;
      this.checkGeneration(generation);
      const frame = frameBlufi(type, sequence, plain, encrypted, checksum, fragmented, requireAck);
      characteristic.characteristicValue = frame.buffer as ArrayBuffer;
      await client.writeCharacteristicValue(characteristic, ble.GattWriteType.WRITE);
      this.checkGeneration(generation);
      offset += take;
      await new Promise<void>((resolve) => setTimeout(resolve, 10));
    } while (offset < data.length);
    return lastSequence;
  }

  private async receive(packet: Uint8Array): Promise<void> {
    const generation = this.generation;
    if (packet.length < 4) throw new Error('BluFi 响应帧不完整');
    const type = packet[0];
    const flags = packet[1];
    const sequence = packet[2];
    const length = packet[3];
    const checksum = (flags & 2) !== 0;
    if (sequence !== (this.readSequence++ & 255) || packet.length !== 4 + length + (checksum ? 2 : 0)) {
      throw new Error('BluFi 响应顺序或长度错误');
    }
    let plain = packet.slice(4, 4 + length);
    if ((flags & 1) && plain.length) plain = await this.aes(plain, sequence, false);
    this.checkGeneration(generation);
    if (checksum) {
      const expected = blufiCrc(concatBytes([new Uint8Array([sequence, length]), plain]));
      if (expected !== (packet[4 + length] | packet[5 + length] << 8)) throw new Error('BluFi 响应校验失败');
    }
    if (this.fragments.length && this.fragmentType !== type) throw new Error('BluFi 分片类型不一致');
    if (flags & 16) {
      if (plain.length < 2) throw new Error('BluFi 分片不完整');
      this.fragmentType = type;
      this.fragments.push(plain.slice(2));
      if (this.fragments.reduce((sum: number, part: Uint8Array) => sum + part.length, 0) > 4096) {
        throw new Error('BluFi 响应过长');
      }
      return;
    }
    const data = concatBytes([...this.fragments, plain]);
    this.fragments = [];
    this.fragmentType = -1;
    if (type === ((0x12 << 2) | 1)) throw new Error(`设备返回 BluFi 错误，错误码 ${data[0] ?? -1}`);
    this.received.set(type, data);
    this.wake?.();
  }

  private async negotiate(): Promise<void> {
    // Android initiates the default BluFi v1 handshake before querying version.
    // Use platform crypto for DH and AES; never downgrade to plaintext Wi-Fi.
    const generation = this.generation;
    const params: crypto.DHCommonParamsSpec = {
      algName: 'DH', specType: crypto.AsyKeySpecType.COMMON_PARAMS_SPEC,
      p: BigInt(`0x${DH_P}`), g: BigInt(2), l: 1024
    };
    const keys = await crypto.createAsyKeyGeneratorBySpec(params).generateKeyPair();
    this.checkGeneration(generation);
    const publicValue = keys.pubKey.getAsyKeySpec(crypto.AsyKeySpecItem.DH_PK_BN) as bigint;
    const p = hexBytes(DH_P);
    const g = new Uint8Array([2]);
    const publicBytes = hexBytes(publicValue.toString(16).padStart(256, '0'));
    const total = p.length + g.length + publicBytes.length + 6;
    await this.post(1, new Uint8Array([0, total >> 8, total & 255]));
    const all = concatBytes([new Uint8Array([1, p.length >> 8, p.length & 255]), p,
      new Uint8Array([0, 1]), g, new Uint8Array([publicBytes.length >> 8, publicBytes.length & 255]), publicBytes]);
    await this.post(1, all);
    const peerBytes = await this.wait(1, 20000);
    this.checkGeneration(generation);
    if (!peerBytes.length || peerBytes.length > p.length) throw new Error('设备 DH 公钥无效');
    const peerValue = BigInt(`0x${bytesHex(peerBytes)}`);
    if (peerValue <= BigInt(1) || peerValue >= params.p - BigInt(1)) throw new Error('设备 DH 公钥超出有效范围');
    const peerSpec: crypto.DHPubKeySpec = {
      algName: 'DH', specType: crypto.AsyKeySpecType.PUBLIC_KEY_SPEC, params, pk: peerValue
    };
    const peer = await crypto.createAsyKeyGeneratorBySpec(peerSpec).generatePubKey();
    this.checkGeneration(generation);
    const shared = (await crypto.createKeyAgreement('DH').generateSecret(keys.priKey, peer)).data;
    let offset = 0;
    while (offset < shared.length && shared[offset] === 0) offset++;
    const md = crypto.createMd('MD5');
    await md.update({ data: shared.slice(offset) });
    const key = await crypto.createSymKeyGenerator('AES128').convertKey(await md.digest());
    shared.fill(0);
    this.checkGeneration(generation);
    this.key = key;
    await this.post(4, new Uint8Array([3]), false, true);
  }

  async configure(ssid: string, password: string, claimToken: string, status: (text: string) => void): Promise<void> {
    if (!this.ready || !claimToken || !ssid.trim()) throw new Error('蓝牙加密通道或绑定会话未就绪');
    const generation = this.generation;
    const encode = (text: string): Uint8Array => new util.TextEncoder().encodeInto(text);
    const payload: Record<string, Object> = {};
    payload.type = 'echo_bind';
    payload.version = 1;
    payload.claim_token = claimToken;
    status('正在通过蓝牙发送设备绑定信息');
    await this.post((0x13 << 2) | 1, encode(JSON.stringify(payload)), true, true);
    this.received.delete(0);
    const modeSequence = await this.post(8, new Uint8Array([1]), true, true, true);
    const ack = await this.wait(0, 5000);
    if (ack.length !== 1 || ack[0] !== modeSequence) throw new Error('设备模式设置回执无效');
    await this.post(9, encode(ssid.trim()), true, true);
    await this.post(13, encode(password), true, true);
    this.received.delete(61);
    await this.post(12, new Uint8Array());
    const started = Date.now();
    status('凭据已发送，设备正在连接 Wi-Fi');
    while (Date.now() - started < 60000) {
      this.checkGeneration(generation);
      await this.post(20, new Uint8Array(), true, true);
      const response = await this.wait(61, 5000);
      if (response.length < 3) throw new Error('设备 Wi-Fi 状态无效');
      if (response[1] === 0) { status('设备已连接家庭 Wi-Fi'); return; }
      if ((response[1] === 1 || response[1] === 3) && Date.now() - started > 15000) {
        throw new Error('设备连接 Wi-Fi 失败，请检查 SSID 和密码');
      }
      await new Promise<void>((resolve) => setTimeout(resolve, 2000));
    }
    throw new Error('设备未确认 Wi-Fi 连接，请检查设备联网状态后重试');
  }

  disconnect(): void {
    this.generation++;
    this.cancelConnection?.();
    this.cancelConnection = undefined;
    this.ready = false;
    this.failure = '蓝牙连接已取消';
    this.wake?.();
    this.wake = undefined;
    const client = this.client;
    this.client = undefined;
    this.key = undefined;
    this.writeCharacteristic = undefined;
    if (client) {
      try {
        client.off('BLECharacteristicChange');
        client.off('BLEConnectionStateChange');
        client.disconnect();
      } catch (_) {}
      try { client.close(); } catch (_) {}
    }
  }
}
