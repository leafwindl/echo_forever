'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { createRequire } = require('node:module');
const { test } = require('node:test');

// Run with DevEco's Node. TYPESCRIPT_PATH can point to another installed compiler.
const devEco = process.env.DEVECO_STUDIO_HOME || 'D:/Devstudio/DevEco Studio';
const ts = process.env.TYPESCRIPT_PATH
  ? require(process.env.TYPESCRIPT_PATH)
  : createRequire(path.join(devEco, 'tools/hvigor/hvigor-ohos-plugin/package.json'))('typescript');
const project = path.resolve(__dirname, '..');
const ets = path.join(project, 'entry/src/main/ets');

function compile(source, imports = {}) {
  const output = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 }
  }).outputText;
  const module = { exports: {} };
  const resolve = (name) => {
    assert.ok(Object.hasOwn(imports, name), `Unexpected import: ${name}`);
    return imports[name];
  };
  new Function('require', 'module', 'exports', output)(resolve, module, module.exports);
  return module.exports;
}

const models = compile(fs.readFileSync(path.join(ets, 'model/ApiModels.ets'), 'utf8'));
const config = compile(fs.readFileSync(path.join(ets, 'common/AppConfig.ets'), 'utf8'));

function clientHarness(handler) {
  const calls = [];
  let destroyed = 0;
  let cleared = 0;
  const saved = [];
  const session = {
    accessToken: 'expired-access',
    refreshToken: 'refresh',
    tokenType: 'Bearer',
    deviceId: 'device'
  };
  const http = {
    RequestMethod: { GET: 'GET', POST: 'POST', PUT: 'PUT', PATCH: 'PATCH', DELETE: 'DELETE' },
    createHttp: () => ({
      request: async (url, options) => {
        calls.push({ url, options });
        return handler(url, options);
      },
      destroy: () => destroyed++
    })
  };
  const { ApiClient } = compile(
    fs.readFileSync(path.join(ets, 'common/ApiClient.ets'), 'utf8'),
    {
      '@ohos.net.http': { default: http },
      '@ohos.util': { default: {} },
      '@ohos.request': { default: {} },
      '@ohos.app.ability.common': { default: {} },
      './AppConfig': config,
      '../model/ApiModels': models
    }
  );
  const client = new ApiClient(
    async () => session,
    async (next) => saved.push({ ...next }),
    async () => cleared++
  );
  return { client, session, calls, saved, destroyed: () => destroyed, cleared: () => cleared };
}

function response(code, body) {
  return { responseCode: code, result: JSON.stringify(body) };
}

function refreshResponse() {
  return response(200, { access_token: 'fresh-access', refresh_token: 'rotated-refresh' });
}

test('expired token refreshes and automatically retries the original history request', async () => {
  const harness = clientHarness(async (url, options) => {
    if (url.endsWith('/login/refresh')) return refreshResponse();
    return options.header.Authorization.toLowerCase() === 'bearer fresh-access'
      ? response(200, { items: [{ message_id: 42 }] })
      : response(401, {});
  });
  const result = await harness.client.get('/chat/messages', { limit: '10' });
  assert.equal(result.items[0].message_id, 42);
  assert.equal(harness.calls.length, 3);
  assert.equal(harness.calls[0].url, harness.calls[2].url);
  assert.equal(harness.saved[0].refreshToken, 'rotated-refresh');
  assert.equal(harness.destroyed(), 3);
  assert.equal(harness.cleared(), 0);
});

test('POST retry preserves payload and client message ID', async () => {
  const harness = clientHarness(async (url, options) => {
    if (url.endsWith('/login/refresh')) return refreshResponse();
    return response(options.header.Authorization.toLowerCase() === 'bearer fresh-access' ? 202 : 401, {});
  });
  const body = { client_message_id: 'same-id', message_type: 'text', text: 'hello' };
  await harness.client.post('/chat/messages', body);
  assert.equal(harness.calls[0].options.extraData, harness.calls[2].options.extraData);
  assert.equal(harness.calls[2].options.method, 'POST');
});

test('concurrent unauthorized requests share one refresh rotation', async () => {
  let refreshes = 0;
  const harness = clientHarness(async (url, options) => {
    if (url.endsWith('/login/refresh')) {
      refreshes++;
      await new Promise((resolve) => setImmediate(resolve));
      return refreshResponse();
    }
    return response(options.header.Authorization.toLowerCase() === 'bearer fresh-access' ? 200 : 401, {});
  });
  await Promise.all([harness.client.get('/persona/me'), harness.client.get('/chat/messages')]);
  assert.equal(refreshes, 1);
  assert.equal(harness.cleared(), 0);
});

test('failed refresh does not loop or report a successful login', async () => {
  const harness = clientHarness(async () => response(401, {}));
  await assert.rejects(harness.client.get('/chat/messages'), { code: 'AUTH_ACCESS_INVALID' });
  assert.equal(harness.calls.length, 2);
  assert.equal(harness.cleared(), 1);
});

test('a second 401 after rotation stops after one retry', async () => {
  const harness = clientHarness(async (url) =>
    url.endsWith('/login/refresh') ? refreshResponse() : response(401, {}));
  await assert.rejects(harness.client.get('/chat/messages'), { code: 'AUTH_ACCESS_INVALID' });
  assert.equal(harness.calls.length, 3);
  assert.equal(harness.cleared(), 1);
});

const indexSource = fs.readFileSync(path.join(ets, 'pages/Index.ets'), 'utf8');
function method(start, end) {
  const from = indexSource.indexOf(start);
  const to = indexSource.indexOf(end, from + start.length);
  assert.ok(from >= 0 && to > from, `Missing startup method: ${start}`);
  return indexSource.slice(from, to);
}

// Execute the actual non-UI page methods, without mocking their control flow.
const { StartupHarness } = compile(`
  export class StartupHarness {
    constructor(repository) {
      this.repository = repository;
      this.loggedIn = true;
      this.onboarding = false;
      this.messages = [];
      this.greetingOverride = '';
      this.chatLoadError = '';
      this.nextBeforeId = 0;
      this.hasMoreHistory = false;
      this.scrolled = 0;
      this.streams = 0;
    }
    describeError(error) { return String(error); }
    scrollChatToBottom() { this.scrolled++; }
    startEvents() { this.streams++; return new Promise(() => {}); }
    greetingMessage() { return { id: 0, content: 'greeting' }; }
    restartGreetingMessage() { return { id: 0, content: 'restart' }; }
    ${method('  private async restoreSession()', '  private configureRepository(')}
    ${method('  private async loadChat()', '  private async send()')}
  }
  function messageFromJson(item) { return { id: item.message_id, content: item.content }; }
`);

function repository(overrides = {}) {
  return {
    getPersonaProfile: async () => ({
      preferredName: 'Leaf',
      onboardingCompleted: true
    }),
    getChatHistory: async () => ({
      items: [{ message_id: 42, content: 'history' }],
      next_before_id: 42,
      has_more: false
    }),
    ...overrides
  };
}

test('cold start renders history without waiting for the long-lived SSE stream', { timeout: 1000 }, async () => {
  const page = new StartupHarness(repository());
  await page.restoreSession();
  assert.equal(page.messages[0].id, 42);
  assert.equal(page.messages[0].content, 'history');
  assert.equal(page.streams, 1);
  assert.equal(page.scrolled, 1);
  assert.equal(page.loading, false);
});

test('persona failure still loads chat history on startup', async () => {
  const page = new StartupHarness(repository({
    getPersonaProfile: async () => { throw new Error('profile unavailable'); }
  }));
  await page.restoreSession();
  assert.equal(page.messages[0].id, 42);
  assert.equal(page.streams, 1);
});

test('history failure preserves existing messages and exposes retry error', async () => {
  const page = new StartupHarness(repository({
    getChatHistory: async () => { throw new Error('offline'); }
  }));
  page.messages = [{ id: 10, content: 'existing' }];
  page.nextBeforeId = 10;
  page.hasMoreHistory = true;
  await page.loadChat();
  assert.equal(page.messages[0].id, 10);
  assert.equal(page.nextBeforeId, 10);
  assert.equal(page.hasMoreHistory, true);
  assert.match(page.chatLoadError, /offline/);
  assert.equal(page.loading, false);
});

test('only a successful empty history response displays the greeting', async () => {
  const page = new StartupHarness(repository({
    getChatHistory: async () => ({ items: [], has_more: false })
  }));
  await page.loadChat();
  assert.equal(page.messages[0].id, 0);
  assert.equal(page.chatLoadError, '');
});

test('new users still enter onboarding before loading chat', async () => {
  let historyRequests = 0;
  const page = new StartupHarness(repository({
    getPersonaProfile: async () => ({ preferredName: '', onboardingCompleted: false }),
    getChatHistory: async () => { historyRequests++; return { items: [] }; }
  }));
  await page.restoreSession();
  assert.equal(page.onboarding, true);
  assert.equal(historyRequests, 0);
  assert.equal(page.streams, 0);
});

test('Harmony app and ability icons use the cropped 1024px PNG', () => {
  const icon = fs.readFileSync(path.join(project, 'entry/src/main/resources/base/media/echo_launcher_icon.png'));
  const android = fs.readFileSync(path.join(project, '../app/android/echo_launcher_icon_source.png'));
  assert.notDeepEqual(icon, android);
  assert.equal(icon.subarray(0, 8).toString('hex'), '89504e470d0a1a0a');
  assert.equal(icon.readUInt32BE(16), 1024);
  assert.equal(icon.readUInt32BE(20), 1024);
  const app = JSON.parse(fs.readFileSync(path.join(project, 'AppScope/app.json5'), 'utf8'));
  const module = JSON.parse(fs.readFileSync(path.join(project, 'entry/src/main/module.json5'), 'utf8'));
  assert.equal(app.app.icon, '$media:echo_launcher_icon');
  assert.equal(module.module.abilities[0].icon, app.app.icon);
  assert.equal(module.module.abilities[0].startWindowIcon, app.app.icon);
});
