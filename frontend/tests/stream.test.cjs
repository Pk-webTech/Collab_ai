const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

function apiWithStream(events) {
  const bytes = new TextEncoder().encode(events);
  const exports = {};
  const source = ts.transpileModule(fs.readFileSync('lib/api.ts', 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  vm.runInNewContext(source, {
    exports, process: { env: {} }, TextDecoder,
    require: () => ({ supabase: { auth: { getSession: async () => ({ data: { session: { access_token: 'test' } } }) } } }),
    fetch: async () => new Response(new ReadableStream({
      start(controller) {
        // Split every byte, including UTF-8 characters and JSON boundaries.
        for (const byte of bytes) controller.enqueue(new Uint8Array([byte]));
        controller.close();
      },
    })),
  });
  return exports;
}

test('renders split UTF-8 deltas and waits for persisted completion', async () => {
  const api = apiWithStream('{"type":"delta","text":"Hello 🌍"}\n{"type":"done"}\n');
  let text = '';
  await api.sendMessageStream('id', 'hi', chunk => { text += chunk; });
  assert.equal(text, 'Hello 🌍');
});

test('server stream errors reach the user', async () => {
  const api = apiWithStream('{"type":"error","message":"Save failed"}\n');
  await assert.rejects(api.sendMessageStream('id', 'hi', () => {}), /Save failed/);
});

test('truncated streams cannot silently succeed', async () => {
  const api = apiWithStream('{"type":"delta","text":"partial"}\n');
  await assert.rejects(api.sendMessageStream('id', 'hi', () => {}), /interrupted/);
});
