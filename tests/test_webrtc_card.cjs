// Exercise the real card lifecycle without a camera or browser credentials.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");

function loadCard() {
  const timers = new Map();
  let serial = 0;
  let Card;
  const document = {};
  const context = {
    HTMLElement: class {}, document, console,
    setTimeout: (fn) => { timers.set(++serial, fn); return serial; },
    clearTimeout: (id) => timers.delete(id),
    clearInterval: () => {},
    customElements: { get: () => undefined, define: (_name, cls) => { Card = cls; } },
  };
  vm.runInNewContext(fs.readFileSync("custom_components/alarmdotcom/www/alarm-webrtc-card.js", "utf8"), context);
  return { card: new Card(), timers, document, context };
}

test("rotation preserves the current stream and resumes the same video", () => {
  const { card, timers } = loadCard();
  let played = 0;
  const video = { srcObject: {}, paused: true, play: () => { played++; return Promise.resolve(); } };
  card.querySelector = () => video;
  card.pc = { close: () => assert.fail("rotation must not close the peer") };
  card.disconnectedCallback();
  assert.equal(timers.size, 1);
  card.connectedCallback();
  assert.equal(timers.size, 0);
  assert.equal(played, 1);
});

test("actual card removal closes transports and invalidates outstanding credentials", () => {
  const { card, timers } = loadCard();
  let closed = 0;
  card.pc = { close: () => { closed++; } };
  card.ws = { close: () => { closed++; } };
  card._secureConfig = { private: "token" };
  card.disconnectedCallback();
  [...timers.values()][0]();
  assert.equal(closed, 2);
  assert.equal(card._secureConfig, null);
  assert.equal(card._requestSerial, 1);
});

test("fullscreen uses standard API and falls back to the iPhone player", async () => {
  const { card, document } = loadCard();
  let entered = 0;
  card.querySelector = (name) => name === "ha-card" ? { requestFullscreen: async () => { entered++; } } : {};
  await card._toggleFullscreen();
  assert.equal(entered, 1);
  let exited = 0;
  document.fullscreenElement = {};
  document.exitFullscreen = async () => { exited++; };
  await card._toggleFullscreen();
  assert.equal(exited, 1);
  document.fullscreenElement = null;
  card.querySelector = (name) => name === "video" ? { webkitEnterFullscreen: () => { entered++; } } : {};
  await card._toggleFullscreen();
  assert.equal(entered, 2);
});

test("Janus websocket opening resolves after an open event", async () => {
  const { card, context } = loadCard();
  let socket;
  context.WebSocket = class { constructor() { socket = this; } close() {} };
  const connection = card._connectJanusWebSocket("wss://example.test");
  socket.onopen();
  assert.equal(await connection, socket);
});

test("late Janus connection cannot replace the current stream", async () => {
  const { card, context } = loadCard();
  context.RTCPeerConnection = class {};
  card.querySelector = () => ({});
  let resolveSocket;
  card._openJanusWebSocket = () => new Promise((resolve) => { resolveSocket = resolve; });
  const opening = card._startJanus({});
  card._streamGeneration++;
  let closed = false;
  resolveSocket({ close: () => { closed = true; } });
  await opening;
  assert.equal(closed, true);
  assert.equal(card.ws, null);
});
