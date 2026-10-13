'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { createRequire } = require('node:module');
const { test } = require('node:test');
const devEco = process.env.DEVECO_STUDIO_HOME || 'D:/Devstudio/DevEco Studio';
const ts = createRequire(path.join(devEco, 'tools/hvigor/hvigor-ohos-plugin/package.json'))('typescript');
const ets = path.resolve(__dirname, '../entry/src/main/ets');

function load(name, imports = {}) {
  const source = fs.readFileSync(path.join(ets, name), 'utf8');
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 }
  }).outputText;
  const module = { exports: {} };
  new Function('require', 'module', 'exports', compiled)((key) => {
    assert.ok(Object.hasOwn(imports, key), `Unexpected import: ${key}`);
    return imports[key];
  }, module, module.exports);
  return module.exports;
}

const releases = load('model/AppRelease.ets');
const installed = { bundleName: 'cn.echoaiforever.echo_app.dev', versionName: '1.1.7-dev', versionCode: 10107 };
const release = {
  release_id: 'release', platform: 'harmonyos', channel: 'internal', package_name: installed.bundleName,
  version_name: '1.1.8-dev', version_code: 10108, size_bytes: 3, sha256: 'a'.repeat(64),
  release_notes: [' Fixed ', ''], mandatory: false
};
const parse = (patch = {}) => releases.parseHarmonyRelease({ update_available: true, release: { ...release, ...patch } }, installed);

test('Harmony update parses matching HAP release and actual installed version', () => {
  assert.equal(parse().versionCode, 10108);
  assert.deepEqual(parse().releaseNotes, ['Fixed']);
  assert.equal(releases.parseHarmonyRelease({ update_available: false }, installed), undefined);
});

for (const [name, patch] of [
  ['Android release', { platform: 'android' }],
  ['wrong bundle name', { package_name: 'cn.echoaiforever.echo_app' }],
  ['downgrade', { version_code: 10106 }],
  ['same version', { version_code: 10107 }],
  ['fractional version', { version_code: 10108.5 }],
  ['missing hash', { sha256: '' }],
  ['invalid size', { size_bytes: 0 }],
  ['missing release ID', { release_id: '' }]
]) {
  test(`update rejects ${name}`, () => assert.throws(() => parse(patch)));
}

test('malformed response is not reported as latest version', () => {
  assert.throws(() => releases.parseHarmonyRelease({}, installed));
  assert.throws(() => releases.parseHarmonyRelease({ update_available: true }, installed));
});

test('download URL accepts signed HTTPS links, rejects plaintext or invalid authority', () => {
  assert.equal(releases.validateDownloadUrl('https://api.echoaiforever.cn/releases/r/artifact?signature=x'),
    'https://api.echoaiforever.cn/releases/r/artifact?signature=x');
  for (const url of ['http://api.echoaiforever.cn/x', 'file:///a.hap', 'https://', 'https://user@host/a.hap']) {
    assert.throws(() => releases.validateDownloadUrl(url));
  }
});

const config = load('common/AppConfig.ets');
const models = load('model/ApiModels.ets');
function repository(api) {
  const { EchoRepository } = load('data/EchoRepository.ets', {
    '../common/ApiClient': {}, '../common/AppConfig': config, '../model/ApiModels': models,
    '../model/AppRelease': releases
  });
  return new EchoRepository(api);
}

test('hardware probe requires acknowledged=true as Android does', async () => {
  await assert.rejects(repository({ post: async () => ({ acknowledged: false }) }).connectDevice('device'),
    /未收到硬件检测回执/);
  await assert.rejects(repository({ post: async () => ({}) }).connectDevice('device'),
    /未收到硬件检测回执/);
  await repository({ post: async () => ({ acknowledged: true }) }).connectDevice('device');
});

test('device rename, rotation and unbind use Android paths and payload', async () => {
  const calls = [];
  const repo = repository({
    patch: async (...args) => { calls.push(['patch', ...args]); return { device_id: 'd /1', display_name: 'new' }; },
    post: async (...args) => { calls.push(['post', ...args]); return { credential: 'secret' }; },
    delete: async (...args) => calls.push(['delete', ...args])
  });
  const device = await repo.renameDevice('d /1', 'new');
  assert.equal(device.displayName, 'new');
  await repo.rotateDeviceCredential('d /1');
  await repo.unbindDevice('d /1');
  assert.deepEqual(calls, [
    ['patch', '/devices/d%20%2F1', { display_name: 'new' }],
    ['post', '/devices/d%20%2F1/credentials/rotate'],
    ['delete', '/devices/d%20%2F1']
  ]);
});

test('speaker enrollment retains consent and Android audio multipart field', async () => {
  const calls = [];
  const repo = repository({
    post: async (...args) => { calls.push(args); return { person_id: 'p' }; },
    uploadMultipartResponse: async (...args) => { calls.push(args); return { status: 'active' }; }
  });
  await repo.createSpeakerPerson('d', ' name ');
  await repo.uploadSpeakerSample('d', 'p', '/cache/sample.pcm');
  assert.deepEqual(calls[0], ['/devices/d/speakers', { display_name: 'name', consent: true }]);
  assert.deepEqual(calls[1], ['/devices/d/speakers/p/samples', '/cache/sample.pcm', 'sample.pcm', 'audio/L16', {}, 'audio']);
});

test('update download request is public and targets HarmonyOS current installed version', async () => {
  const calls = [];
  const repo = repository({
    get: async (...args) => { calls.push(args); return { update_available: false }; },
    post: async (...args) => { calls.push(args); return { download_url: 'https://api.echoaiforever.cn/a.hap' }; }
  });
  await repo.latestRelease(installed.versionCode);
  await repo.releaseDownload('r /1', installed.versionCode);
  assert.deepEqual(calls[0], ['/releases/latest',
    { platform: 'harmonyos', channel: 'internal', version_code: '10107' }, false]);
  assert.deepEqual(calls[1], ['/releases/r%20%2F1/download',
    { platform: 'harmonyos', channel: 'internal', version_code: 10107 }, false]);
});

function deviceNetwork(handler) {
  const calls = [];
  let destroyed = 0;
  const http = {
    RequestMethod: { GET: 'GET', POST: 'POST' },
    createHttp: () => ({
      request: async (url, options) => {
        calls.push({ url, options });
        return { responseCode: 200, result: JSON.stringify(await handler(url, options)) };
      }, destroy: () => destroyed++
    })
  };
  const { DeviceNetwork } = load('platform/DeviceNetwork.ets', { '@ohos.net.http': { default: http } });
  return { client: new DeviceNetwork(), calls, destroyed: () => destroyed };
}

test('SoftAP sends Wi-Fi only to device and exits only after successful submit', async () => {
  const harness = deviceNetwork(async () => ({ success: true }));
  await harness.client.configure('Home', 'wifi-password');
  assert.equal(harness.calls[0].url, 'http://192.168.4.1/submit');
  assert.deepEqual(JSON.parse(harness.calls[0].options.extraData), { ssid: 'Home', password: 'wifi-password' });
  assert.equal(harness.calls[1].url, 'http://192.168.4.1/exit');
  assert.equal(harness.destroyed(), 2);
});

test('SoftAP failure must not exit or report success', async () => {
  const harness = deviceNetwork(async () => ({ success: false, error: 'Wrong password' }));
  await assert.rejects(harness.client.configure('Home', 'bad'), /Wrong password/);
  assert.equal(harness.calls.length, 1);
  assert.equal(harness.destroyed(), 1);
});

test('SoftAP scan parses aps/rssi/authmode as Android does', async () => {
  const harness = deviceNetwork(async () => ({ aps: [{ ssid: 'Home', rssi: -55, authmode: 3 }, { ssid: '' }] }));
  assert.deepEqual(await harness.client.scan(), [{ ssid: 'Home', rssi: -55, authMode: 3 }]);
});

test('BLE unrestricted scan uses null filters and releases its listener on cancellation', async () => {
  let callback;
  let released = false;
  let stopped = false;
  const ble = {
    on: (event, listener) => { assert.equal(event, 'BLEDeviceFind'); callback = listener; },
    startBLEScan: (filters, options) => {
      assert.equal(filters, null);
      assert.equal(options.interval, 0);
      callback([
        { deviceId: 'a', deviceName: 'Xiaozhi-Blufi', rssi: -60 },
        { deviceId: 'b', deviceName: 'Echo', rssi: -40 },
        { deviceId: 'c', deviceName: 'Unrelated', rssi: -20 }
      ]);
      setImmediate(() => client.stopScan());
    },
    stopBLEScan: () => { stopped = true; },
    off: (event, listener) => {
      assert.equal(event, 'BLEDeviceFind');
      assert.equal(listener, callback);
      released = true;
    }
  };
  const { DeviceCapabilities } = load('platform/DeviceCapabilities.ets', {
    '@ohos.app.ability.common': { default: {} },
    '@ohos.abilityAccessCtrl': { default: {
      createAtManager: () => ({ requestPermissionsFromUser: async () => ({ authResults: [0] }) })
    } },
    '@ohos.bluetooth.ble': { default: ble },
    '@ohos.multimedia.audio': { default: {} },
    '@ohos.file.fs': { default: {} }
  });
  const client = new DeviceCapabilities();
  assert.deepEqual(await client.scan({}), [
    { address: 'b', name: 'Echo', rssi: -40 },
    { address: 'a', name: 'Xiaozhi-Blufi', rssi: -60 }
  ]);
  assert.equal(stopped, true);
  assert.equal(released, true);
});

const protocol = load('platform/BlufiProtocol.ets');
test('BluFi CRC matches the complemented CCITT Android checksum', () => {
  // Standard CCITT-FALSE check vector 0x29b1, complemented by BlufiCRC.
  assert.equal(protocol.blufiCrc(new Uint8Array(Buffer.from('123456789'))), 0xd64e);
});
test('BluFi frame preserves encrypted payload but checksums plaintext and asks for mode ACK', () => {
  const plain = new Uint8Array([1]);
  const frame = protocol.frameBlufi(8, 4, plain, new Uint8Array([0x82]), true, false, true);
  const crc = protocol.blufiCrc(new Uint8Array([4, 1, 1]));
  assert.deepEqual(Array.from(frame), [8, 11, 4, 1, 0x82, crc & 255, crc >> 8]);
});

test('BluFi DH uses native private length and derives the Android-compatible AES key', async () => {
  let local;
  let peer;
  let secret;
  const posts = [];
  const cryptoMock = {
    AsyKeySpecType: { COMMON_PARAMS_SPEC: 0, PUBLIC_KEY_SPEC: 1 },
    AsyKeySpecItem: { DH_PK_BN: 2 },
    createAsyKeyGeneratorBySpec: (spec) => ({
      generateKeyPair: async () => {
        assert.equal(spec.l, 0, 'Do not force a 1024-bit private exponent in the native DH backend');
        assert.equal(spec.g, 2n);
        const prime = Buffer.from(spec.p.toString(16), 'hex');
        assert.equal(prime.length, 128);
        local = crypto.createDiffieHellman(prime, 2);
        peer = crypto.createDiffieHellman(prime, 2);
        local.generateKeys();
        peer.generateKeys();
        return { priKey: local, pubKey: {
          getAsyKeySpec: () => BigInt(`0x${local.getPublicKey('hex')}`)
        } };
      },
      generatePubKey: async () => Buffer.from(spec.pk.toString(16).padStart(256, '0'), 'hex')
    }),
    createKeyAgreement: () => ({ generateSecret: async (privateKey, publicKey) => {
      secret = privateKey.computeSecret(publicKey);
      return { data: new Uint8Array(secret) };
    } }),
    createMd: () => {
      const hash = crypto.createHash('md5');
      return { update: async ({ data }) => hash.update(data),
        digest: async () => ({ data: new Uint8Array(hash.digest()) }) };
    },
    createSymKeyGenerator: () => ({ convertKey: async ({ data }) => data })
  };
  const { HarmonyBlufi } = load('platform/HarmonyBlufi.ets', {
    '@ohos.bluetooth.ble': { default: {} }, '@ohos.security.cryptoFramework': { default: cryptoMock },
    '@ohos.util': { default: {} }, './BlufiProtocol': protocol
  });
  const client = new HarmonyBlufi();
  client.post = async (...args) => posts.push(args);
  client.wait = async (type) => {
    assert.equal(type, 1);
    return new Uint8Array(peer.getPublicKey());
  };
  await client.negotiate();
  const expectedSecret = peer.computeSecret(local.getPublicKey());
  assert.deepEqual(secret, expectedSecret);
  let offset = 0;
  while (offset < expectedSecret.length && expectedSecret[offset] === 0) offset++;
  assert.deepEqual(Buffer.from(client.key), crypto.createHash('md5').update(expectedSecret.subarray(offset)).digest());
  assert.deepEqual(Array.from(posts[0][1]), [0, 1, 7]);
  assert.equal(posts[1][1].length, 264);
  assert.deepEqual(posts[2], [4, new Uint8Array([3]), false, true]);
});

test('BluFi requests the device version before selecting v1 or v2 security', async () => {
  const { HarmonyBlufi } = load('platform/HarmonyBlufi.ets', {
    '@ohos.bluetooth.ble': { default: {} }, '@ohos.security.cryptoFramework': { default: {} },
    '@ohos.util': { default: {} }, './BlufiProtocol': protocol
  });
  for (const [version, expected] of [[0x0103, 1], [0x0104, 2], [0x0105, 2]]) {
    const client = new HarmonyBlufi();
    client.post = async (type, data) => {
      assert.equal(type, 0x1c);
      assert.equal(data.length, 0);
    };
    client.wait = async (type) => {
      assert.equal(type, 0x41);
      return new Uint8Array([version >> 8, version & 255]);
    };
    await client.requestDeviceVersion();
    assert.equal(client.deviceVersion, version);
    assert.equal(client.securityVersion, expected);
  }
  const client = new HarmonyBlufi();
  client.post = async () => {};
  client.wait = async () => new Uint8Array([1]);
  await assert.rejects(client.requestDeviceVersion(), /version response is invalid/);
  const source = fs.readFileSync(path.join(ets, 'platform/HarmonyBlufi.ets'), 'utf8');
  assert.ok(source.indexOf('await this.requestDeviceVersion();') < source.indexOf('await this.negotiate();'));
});

test('BluFi v2 matches Android 3072-bit DH, SHA-256 and continuous directional AES-CTR', async () => {
  let local;
  let peer;
  let primeLength;
  const posts = [];
  const ciphers = [];
  const cryptoMock = {
    AsyKeySpecType: { COMMON_PARAMS_SPEC: 0, PUBLIC_KEY_SPEC: 1 },
    AsyKeySpecItem: { DH_PK_BN: 2 },
    CryptoMode: { ENCRYPT_MODE: 0, DECRYPT_MODE: 1 },
    createAsyKeyGeneratorBySpec: (spec) => ({
      generateKeyPair: async () => {
        assert.equal(spec.l, 0);
        const prime = Buffer.from(spec.p.toString(16), 'hex');
        primeLength = prime.length;
        assert.equal(primeLength, 384);
        const android = fs.readFileSync(path.resolve(__dirname,
          '../../app/android/app/src/main/java/blufi/espressif/BlufiClientImpl.java'), 'utf8');
        const declaration = android.match(/DH_P_3072\s*=\s*([\s\S]*?);/)[1];
        const androidPrime = [...declaration.matchAll(/"([A-F0-9]+)"/g)].map((part) => part[1]).join('');
        assert.equal(prime.toString('hex').toUpperCase(), androidPrime);
        local = crypto.createDiffieHellman(prime, 2);
        peer = crypto.createDiffieHellman(prime, 2);
        local.generateKeys();
        peer.generateKeys();
        return { priKey: local, pubKey: {
          getAsyKeySpec: () => BigInt(`0x${local.getPublicKey('hex')}`)
        } };
      },
      generatePubKey: async () => Buffer.from(spec.pk.toString(16).padStart(primeLength * 2, '0'), 'hex')
    }),
    createKeyAgreement: () => ({
      generateSecret: async (privateKey, publicKey) => ({ data: new Uint8Array(privateKey.computeSecret(publicKey)) })
    }),
    createMd: (algorithm) => {
      assert.equal(algorithm, 'SHA256');
      const hash = crypto.createHash('sha256');
      return { update: async ({ data }) => hash.update(data),
        digest: async () => ({ data: new Uint8Array(hash.digest()) }) };
    },
    createSymKeyGenerator: (algorithm) => {
      assert.equal(algorithm, 'AES256');
      return { convertKey: async ({ data }) => data };
    },
    createCipher: (algorithm) => {
      assert.equal(algorithm, 'AES256|CTR|NoPadding');
      let stream;
      return {
        init: async (mode, key, params) => {
          ciphers.push({ mode, iv: Buffer.from(params.iv.data) });
          stream = mode === 0 ? crypto.createCipheriv('aes-256-ctr', key, params.iv.data) :
            crypto.createDecipheriv('aes-256-ctr', key, params.iv.data);
        },
        update: async ({ data }) => ({ data: new Uint8Array(stream.update(data)) })
      };
    }
  };
  const { HarmonyBlufi } = load('platform/HarmonyBlufi.ets', {
    '@ohos.bluetooth.ble': { default: {} }, '@ohos.security.cryptoFramework': { default: cryptoMock },
    '@ohos.util': { default: { TextEncoder: class {
      encodeInto(value) { return new Uint8Array(Buffer.from(value, 'utf8')); }
    } } }, './BlufiProtocol': protocol
  });
  const client = new HarmonyBlufi();
  client.securityVersion = 2;
  client.post = async (...args) => posts.push(args);
  client.wait = async () => new Uint8Array(peer.getPublicKey());
  await client.negotiate();
  const shared = peer.computeSecret(local.getPublicKey());
  let offset = 0;
  while (offset < shared.length && shared[offset] === 0) offset++;
  const secret = shared.subarray(offset);
  const key = crypto.createHash('sha256').update(secret).digest();
  const iv = (domain) => crypto.createHash('sha256').update(domain).update(secret).digest().subarray(0, 16);
  assert.deepEqual(Buffer.from(client.key), key);
  assert.deepEqual(ciphers, [{ mode: 0, iv: iv('blufi_dec') }, { mode: 1, iv: iv('blufi_enc') }]);
  assert.deepEqual(Array.from(posts[0][1]), [0, 3, 7]);
  assert.equal(posts[1][1].length, 776);
  assert.deepEqual(posts[2], [4, new Uint8Array([3]), false, true]);
  const deviceDecrypt = crypto.createDecipheriv('aes-256-ctr', key, iv('blufi_dec'));
  const deviceEncrypt = crypto.createCipheriv('aes-256-ctr', key, iv('blufi_enc'));
  for (const [sequence, message] of ['binding', 'wifi-network', 'wifi-password'].entries()) {
    const plain = Buffer.from(message);
    const encrypted = await client.aes(plain, sequence, true);
    assert.deepEqual(deviceDecrypt.update(encrypted), plain);
    assert.deepEqual(Buffer.from(await client.aes(deviceEncrypt.update(plain), sequence, false)), plain);
  }
  client.disconnect();
  assert.equal(client.encryptCipher, undefined);
  assert.equal(client.decryptCipher, undefined);
});

test('device list exposes add-device action with and without existing devices', () => {
  const source = fs.readFileSync(path.join(ets, 'pages/DevicesPage.ets'), 'utf8');
  assert.equal([...source.matchAll(/Button\('添加新设备'\)/g)].length, 2);
  for (const match of source.matchAll(/Button\('添加新设备'\)([\s\S]*?)void this\.scanBle\(\);/g)) {
    assert.match(match[1], /this\.screen = 'ble'/);
  }
});

function updaterHarness(bytes = Buffer.from('abc')) {
  let removed = false;
  let offset = 0;
  const fsMock = {
    OpenMode: { READ_ONLY: 0 }, accessSync: () => !removed,
    stat: async () => ({ size: bytes.length }), unlink: async () => { removed = true; },
    open: async () => ({ fd: 1 }), close: async () => {},
    read: async (_, buffer) => {
      const count = Math.min(buffer.byteLength, bytes.length - offset);
      new Uint8Array(buffer).set(bytes.subarray(offset, offset + count));
      offset += count;
      return count;
    }
  };
  const cryptoMock = {
    createMd: () => {
      const hash = crypto.createHash('sha256');
      return { update: async ({ data }) => hash.update(data), digest: async () => ({ data: hash.digest() }) };
    }
  };
  const { HarmonyUpdater } = load('platform/HarmonyUpdater.ets', {
    '@ohos.app.ability.common': { default: {} },
    '@ohos.bundle.bundleManager': { default: { getBundleInfoForSelf: async () => ({
      name: installed.bundleName, versionName: installed.versionName, versionCode: installed.versionCode
    }) } },
    '@ohos.request': { default: {} }, '@ohos.file.fs': { default: fsMock },
    '@ohos.file.fileuri': { default: { getUriFromPath: (value) => `file://${value}` } },
    '@ohos.security.cryptoFramework': { default: cryptoMock }, '../model/AppRelease': releases
  });
  return { updater: new HarmonyUpdater(), removed: () => removed };
}

test('HAP verification streams file bytes and accepts matching SHA-256/size', async () => {
  const harness = updaterHarness();
  await harness.updater.verify('/cache/a.hap', { sizeBytes: 3, sha256: crypto.createHash('sha256').update('abc').digest('hex') });
  assert.equal(harness.removed(), false);
  assert.deepEqual(await harness.updater.installed(), installed);
});
test('HAP hash or size mismatch removes unsafe artifact', async () => {
  const hash = updaterHarness();
  await assert.rejects(hash.updater.verify('/cache/a.hap', { sizeBytes: 3, sha256: 'a'.repeat(64) }), /SHA-256/);
  assert.equal(hash.removed(), true);
  const size = updaterHarness();
  await assert.rejects(size.updater.verify('/cache/a.hap', { sizeBytes: 4 }), /不完整/);
  assert.equal(size.removed(), true);
});
test('installer rejection is exposed and not falsely reported as installed', async () => {
  const harness = updaterHarness();
  await assert.rejects(harness.updater.openInstaller({ startAbility: async () => { throw new Error('No installer'); } }, '/cache/a.hap'),
    /不允许.*HAP/);
});

test('clear-context action opens Android-equivalent confirmation; request happens only inside affirmative action', () => {
  const index = fs.readFileSync(path.join(ets, 'pages/Index.ets'), 'utf8');
  assert.match(index, /action === 'clear'\) this\.confirmClearContext\(\)/);
  const confirmation = index.slice(index.indexOf('private confirmClearContext()'), index.indexOf('private async clearContext()'));
  assert.match(confirmation, /会清除聊天记录和会话摘要，长期记忆仍会保留。/);
  assert.match(confirmation, /value: '取消', action: \(\) => \{\}/);
  assert.match(confirmation, /value: '清除', action: \(\) => void this\.clearContext\(\)/);
  assert.doesNotMatch(confirmation, /repository/);
});

test('notification permissions do not use privileged NOTIFICATION_CONTROLLER', () => {
  const manifest = fs.readFileSync(path.resolve(ets, '../module.json5'), 'utf8');
  assert.doesNotMatch(manifest, /NOTIFICATION_CONTROLLER/);
  assert.match(manifest, /PUBLISH_AGENT_REMINDER/);
});

function notificationHarness(options = {}) {
  const values = new Map();
  const calls = [];
  const live = new Set();
  let sequence = 0;
  let enabled = options.enabled !== false;
  const store = {
    get: async (key, fallback) => values.has(key) ? values.get(key) : fallback,
    put: async (key, value) => values.set(key, value),
    delete: async (key) => values.delete(key),
    flush: async () => {}
  };
  const manager = {
    isNotificationEnabled: async () => enabled,
    requestEnableNotification: async () => {
      calls.push('request');
      if (options.rejectPermission) throw new Error('permission denied');
      enabled = true;
    },
    openNotificationSettings: async () => calls.push('settings')
  };
  const reminders = {
    ReminderType: { REMINDER_TYPE_TIMER: 0 },
    publishReminder: async (request) => {
      calls.push(['publish', request]);
      const id = ++sequence;
      live.add(id);
      return id;
    },
    cancelReminder: async (id) => {
      calls.push(['cancel', id]);
      if (options.rejectCancel) throw new Error('cancel failed');
      live.delete(id);
    }
  };
  const { HarmonyNotifications } = load('platform/HarmonyNotifications.ets', {
    '@ohos.app.ability.common': { default: {} },
    '@ohos.notificationManager': { default: manager },
    '@ohos.reminderAgentManager': { default: reminders },
    '@ohos.data.preferences': { default: { getPreferences: async () => store } }
  });
  return { client: new HarmonyNotifications(), values, calls, live };
}
const notificationContext = { applicationInfo: { name: installed.bundleName } };

test('notification actions read real system permission and open native settings', async () => {
  const harness = notificationHarness({ enabled: false });
  assert.equal(await harness.client.enabled(), false);
  assert.equal(await harness.client.request(notificationContext), true);
  await harness.client.openSettings(notificationContext);
  assert.deepEqual(harness.calls, ['request', 'settings']);
});

test('notification permission rejection is not reported as authorized', async () => {
  const harness = notificationHarness({ enabled: false, rejectPermission: true });
  await assert.rejects(harness.client.request(notificationContext), /permission denied/);
  assert.equal(await harness.client.enabled(), false);
});

test('focus reminders serialize concurrent replacements and cancellation without leaving duplicates', async () => {
  const harness = notificationHarness();
  const end = Date.now() + 60000;
  await Promise.all([
    harness.client.schedule(notificationContext, end),
    harness.client.schedule(notificationContext, end + 60000),
    harness.client.cancel(notificationContext)
  ]);
  assert.deepEqual(harness.calls.map((call) => call[0]), ['publish', 'cancel', 'publish', 'cancel']);
  assert.equal(harness.live.size, 0);
  assert.equal(harness.values.has('focus-reminder'), false);
  assert.equal(harness.calls[0][1].wantAgent.pkgName, installed.bundleName);
});

test('disabled permission or elapsed timer never publishes a focus reminder', async () => {
  const denied = notificationHarness({ enabled: false });
  await denied.client.schedule(notificationContext, Date.now() + 60000);
  assert.deepEqual(denied.calls, []);
  const elapsed = notificationHarness();
  await elapsed.client.schedule(notificationContext, Date.now() - 1);
  assert.deepEqual(elapsed.calls, []);
});

test('failed reminder cancellation preserves its ID and does not create another reminder', async () => {
  const harness = notificationHarness({ rejectCancel: true });
  await harness.client.schedule(notificationContext, Date.now() + 60000);
  const id = harness.values.get('focus-reminder');
  await assert.rejects(harness.client.schedule(notificationContext, Date.now() + 120000), /cancel failed/);
  assert.equal(harness.values.get('focus-reminder'), id);
  assert.equal(harness.live.size, 1);
});

test('leaving a pending BluFi connection cancels immediately and releases the GATT client', async () => {
  let disconnected = 0;
  let closed = 0;
  const gatt = {
    on: () => {}, off: () => {}, connect: () => {},
    disconnect: () => disconnected++, close: () => closed++
  };
  const { HarmonyBlufi } = load('platform/HarmonyBlufi.ets', {
    '@ohos.bluetooth.ble': { default: { createGattClientDevice: () => gatt } },
    '@ohos.security.cryptoFramework': { default: {} },
    '@ohos.util': { default: {} },
    './BlufiProtocol': protocol
  });
  const client = new HarmonyBlufi();
  const pending = client.connect('device');
  client.disconnect();
  await assert.rejects(pending, /蓝牙连接已取消/);
  assert.equal(disconnected, 1);
  assert.equal(closed, 1);
});

test('native secondary screens top-align scroll content and route hardware back events locally', () => {
  const notifications = fs.readFileSync(path.join(ets, 'pages/NotificationsPage.ets'), 'utf8');
  const devices = fs.readFileSync(path.join(ets, 'pages/DevicesPage.ets'), 'utf8');
  const index = fs.readFileSync(path.join(ets, 'pages/Index.ets'), 'utf8');
  assert.match(notifications, /align\(Alignment.TopStart\)/);
  assert.equal((devices.match(/align\(Alignment.TopStart\)/g) || []).length, 3);
  assert.match(devices, /if \(this\.busy \|\| this\.recording\) return/);
  assert.match(devices, /if \(this\.actionSheet\) \{ this\.actionSheet = false; return; \}/);
  assert.match(index, /this\.page === 'devices' && this\.deviceBackHandler/);
});
