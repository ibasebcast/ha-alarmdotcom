console.error("ALARM WEBRTC CARD LOADED v2023.3.30");

class AlarmWebRTCCard extends HTMLElement {
  constructor() {
    super();
    this._connected = false;
    this._connecting = false;
    this._requesting = false;
    this._currentConfig = null;
    this._requestTimeout = null;
    this._retryTimer = null;
    this._retryCount = 0;
    this._maxRetries = 5;
    this._retryDelayMs = 4000;
    this.pc = null;
    this.ws = null;
    this.remoteId = null;
    this._janusKeepalive = null;
    this._entityId = null;
  }

  _log(...args) {
    console.error(`[AlarmWebRTC ${this._entityId || "unknown"}]`, ...args);
  }

  setConfig(config) {
    if (!config.entity) throw new Error("Entity required");
    this.config = config;
    this._entityId = config.entity;
    this._log("setConfig", config);
  }

  set hass(hass) {
    this._hass = hass;
    const entityId = this.config?.entity;
    if (!entityId) return;

    this._entityId = entityId;

    const stateObj = hass.states[entityId];
    if (!stateObj) {
      this._log("Entity not found");
      return;
    }

    let config = stateObj.attributes?.webrtc_config;
    // Allow card config to override the Janus stream ID (useful for cameras
    // where the API doesn't expose the correct mountpoint ID).
    if (config && this.config?.janusStreamId != null) {
      config = { ...config, janusStreamId: this.config.janusStreamId };
    }
    const isValid = this.isConfigValid(config);

    this._log(
      "hass update",
      "streamType=",
      config?.streamType,
      "valid=",
      isValid,
      "connected=",
      this._connected,
      "connecting=",
      this._connecting,
      "requesting=",
      this._requesting
    );

    if (!isValid) {
      if (!this._requesting && !this._connecting) {
        this._requestTokens("No valid config");
      }
      return;
    }

    const hasNoCurrentConfig = !this._currentConfig;
    const isNewConfig =
      JSON.stringify(config) !== JSON.stringify(this._currentConfig);
    const streamTypeChanged =
      config?.streamType !== this._currentConfig?.streamType;

    // Only restart for structural changes (URL/stream type), not token rotation.
    const isStructuralChange = streamTypeChanged ||
      config?.signallingServerUrl !== this._currentConfig?.signallingServerUrl ||
      config?.janusGatewayUrl !== this._currentConfig?.janusGatewayUrl ||
      config?.janusStreamId !== this._currentConfig?.janusStreamId;

    const shouldStartFresh =
      !this._connected &&
      !this._connecting &&
      (hasNoCurrentConfig || isNewConfig || streamTypeChanged);

    const shouldRestart =
      isStructuralChange &&
      (this._connected || this._connecting);

    if (shouldRestart) {
      this._log("Config changed, restarting stream");
      this._teardownStream(false);
      this.renderVideo();
      this.startStream(config);
      return;
    }

    if (shouldStartFresh) {
      this._log("Valid config present, starting fresh stream");
      this.renderVideo();
      this.startStream(config);
      return;
    }
  }

  isConfigValid(config) {
    if (!config) return false;

    if (config.streamType === "janus" || config.janusGatewayUrl) {
      return !!(config.janusGatewayUrl && config.janusToken);
    }

    return !!(
      config.signallingServerUrl &&
      config.signallingServerToken &&
      config.cameraAuthToken
    );
  }

  renderPlaceholder(msg) {
    if (this._connected) return;
    this.innerHTML = `<ha-card><div style="padding:16px;text-align:center">${msg}</div></ha-card>`;
  }

  renderVideo() {
    this.innerHTML = `
      <ha-card>
        <video autoplay playsinline muted style="width:100%;height:auto;background:#000"></video>
      </ha-card>
    `;
  }

  _showReconnectButton(message = "Stream unavailable") {
    this.innerHTML = `
      <ha-card>
        <div style="padding:16px;text-align:center">
          <div style="margin-bottom:12px;color:#888">${message}</div>
          <button id="reconnect-btn" style="padding:8px 20px;background:var(--primary-color,#03a9f4);color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:14px">Reconnect</button>
        </div>
      </ha-card>`;

    this.querySelector("#reconnect-btn").addEventListener("click", () => {
      this._log("Manual reconnect");
      this._retryCount = 0;
      this._requesting = false;
      this._connecting = false;
      this._connected = false;
      this._currentConfig = null;

      if (this._retryTimer) {
        clearTimeout(this._retryTimer);
        this._retryTimer = null;
      }

      this._requestTokens("Manual reconnect");
    });
  }

  _scheduleRetry(reason) {
    if (this._retryTimer) return;

    if (this._retryCount >= this._maxRetries) {
      this._log("Max retries reached", reason);
      this._showReconnectButton(`Stream unavailable (${reason})`);
      return;
    }

    this._retryCount += 1;
    this._log(
      `Scheduling retry ${this._retryCount}/${this._maxRetries} in ${this._retryDelayMs}ms`,
      reason
    );

    this.renderPlaceholder(`Reconnecting... (${this._retryCount}/${this._maxRetries})`);

    this._retryTimer = setTimeout(() => {
      this._retryTimer = null;
      this._requestTokens(reason);
    }, this._retryDelayMs);
  }

  _requestTokens(reason) {
    if (this._requesting) return;

    this._log("Requesting tokens", reason);
    this._requesting = true;

    clearTimeout(this._requestTimeout);
    this._requestTimeout = setTimeout(() => {
      this._log("Token request timed out");
      this._requesting = false;
      this._scheduleRetry("Token timeout");
    }, 15000);

    this._hass
      .callService("camera", "turn_on", {
        entity_id: this.config.entity,
      })
      .catch((err) => {
        this._log("turn_on failed", err);
        this._requesting = false;
        this._scheduleRetry("turn_on failed");
      });

    this.renderPlaceholder("Refreshing session...");
  }

  _teardownStream(resetConfig = true) {
    if (this._janusKeepalive) {
      clearInterval(this._janusKeepalive);
      this._janusKeepalive = null;
    }

    if (this.pc) {
      try {
        this.pc.close();
      } catch (e) {}
      this.pc = null;
    }

    if (this.ws) {
      try {
        this.ws.close();
      } catch (e) {}
      this.ws = null;
    }

    this._connected = false;
    this._connecting = false;
    this.remoteId = null;

    if (resetConfig) {
      this._currentConfig = null;
    }
  }

  _markConnected() {
    this._connected = true;
    this._connecting = false;
    this._requesting = false;
    this._retryCount = 0;

    clearTimeout(this._requestTimeout);

    if (this._retryTimer) {
      clearTimeout(this._retryTimer);
      this._retryTimer = null;
    }
  }

  async startStream(config) {
    if (this._connecting) return;

    this._connecting = true;
    this._currentConfig = config;

    this._log("Starting stream", config);

    try {
      if (config.streamType === "janus" || config.janusGatewayUrl) {
        this._log(">>> USING JANUS <<<");
        await this._startJanus(config);
      } else {
        this._log(">>> USING LEGACY <<<");
        await this._startLegacy(config);
      }
    } catch (err) {
      this._log("startStream failed", err);
      this._teardownStream(false);
      this._requesting = false;
      this._scheduleRetry("startStream failed");
    }
  }

  async _startLegacy(config) {
    const pc = new RTCPeerConnection({
      iceServers: config.iceServers || [],
    });
    this.pc = pc;

    const video = this.querySelector("video");

    const attemptPlay = async () => {
      if (video && (video.paused || video.ended)) {
        try {
          video.muted = true;
          await video.play();
          this._log("Legacy play success");
        } catch (e) {
          this._log("Legacy play failed", e);
        }
      }
    };

    pc.ontrack = (e) => {
      if (!video.srcObject) {
        video.srcObject = e.streams[0];
        this._markConnected();
      }
      this._log("Legacy track received");
      attemptPlay();
    };

    pc.oniceconnectionstatechange = () => {
      const s = pc.iceConnectionState;
      this._log("Legacy ICE state", s);
      if (s === "disconnected" || s === "failed" || s === "closed") {
        this._teardownStream(false);
        this._scheduleRetry(`Legacy ICE ${s}`);
      }
    };

    const ws = new WebSocket(
      `${config.signallingServerUrl}/${config.signallingServerToken}`
    );
    this.ws = ws;

    ws.onopen = () => {
      this._log("Legacy WS connected");
      ws.send("HELLO 2.0.1");
    };

    ws.onerror = (err) => {
      this._log("Legacy WS error", err);
    };

    ws.onmessage = async (msg) => {
      if (msg.data.startsWith("HELLO")) {
        ws.send(`START_SESSION ${config.cameraAuthToken}`);
        return;
      }

      if (msg.data.startsWith("SESSION_STARTED")) {
        return;
      }

      let data;
      try {
        data = JSON.parse(msg.data);
      } catch {
        return;
      }

      if (data.sdp?.type === "offer") {
        await pc.setRemoteDescription(data.sdp);
        const answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);

        // Wait for ICE gathering to complete before sending answer,
        // so the SDP includes TURN relay candidates.
        await new Promise((resolve) => {
          if (pc.iceGatheringState === "complete") {
            resolve();
          } else {
            const onStateChange = () => {
              if (pc.iceGatheringState === "complete") {
                pc.removeEventListener("icegatheringstatechange", onStateChange);
                resolve();
              }
            };
            pc.addEventListener("icegatheringstatechange", onStateChange);
            // Safety timeout: don't wait more than 5s
            setTimeout(resolve, 5000);
          }
        });

        ws.send(
          JSON.stringify({
            to: data.from,
            sdp: pc.localDescription,
          })
        );
      }

      if (data.ice) {
        try {
          await pc.addIceCandidate(data.ice);
        } catch (e) {
          this._log("Failed to add ICE candidate", e);
        }
      }
    };

    ws.onclose = () => {
      const wasConnected = this._connected;
      this._log("Legacy WS closed");
      this._connected = false;
      this._connecting = false;
      this._requesting = false;
      this._teardownStream(false);
      this._scheduleRetry(
        wasConnected ? "Legacy stream ended" : "Legacy WS closed before connection"
      );
    };
  }

  _startJanusKeepalive(ws, sessionId, send) {
    // Janus kills sessions after 60s without a keepalive. Ping every 25s.
    const interval = setInterval(() => {
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        clearInterval(interval);
        return;
      }
      send({ janus: "keepalive", session_id: sessionId });
    }, 25000);
    return interval;
  }


  _buildJanusUrlCandidates(config) {
    return config.janusGatewayUrl ? [config.janusGatewayUrl] : [];
  }

  _connectJanusWebSocket(url) {
    return new Promise((resolve, reject) => {
      let settled = false;
      let ws;

      try {
        ws = new WebSocket(url, ["janus-protocol"]);
      } catch (err) {
        reject(err);
        return;
      }

      const cleanup = () => {
        ws.onopen = null;
        ws.onerror = null;
        ws.onclose = null;
      };

      const fail = (err) => {
        if (settled) return;
        settled = true;
        cleanup();
        try {
          ws.close();
        } catch (e) {}
        reject(err);
      };

      ws.onopen = () => {
        if (settled) return;
        settled = true;
        cleanup();
        resolve(ws);
      };

      ws.onerror = (err) => {
        fail(err || new Error("WebSocket error"));
      };

      ws.onclose = () => {
        fail(new Error(`WebSocket closed before open for ${url}`));
      };

      setTimeout(() => {
        fail(new Error(`WebSocket open timeout for ${url}`));
      }, 5000);
    });
  }

  async _openJanusWebSocket(config) {
    const candidates = this._buildJanusUrlCandidates(config);
    let lastError = null;

    for (const url of candidates) {
      this._log("Trying Janus WS URL", url);
      try {
        const ws = await this._connectJanusWebSocket(url);
        this._log("Janus WS opened", url);
        return ws;
      } catch (err) {
        lastError = err;
        this._log("Janus WS candidate failed", url, err);
      }
    }

    throw lastError || new Error("No Janus WebSocket URL could be opened");
  }

  async _startJanus(config) {
    const pc = new RTCPeerConnection({
      iceServers: config.iceServers || [],
    });
    this.pc = pc;

    const video = this.querySelector("video");

    const attemptPlay = async () => {
      if (video && (video.paused || video.ended)) {
        try {
          video.muted = true;
          await video.play();
          this._log("Janus play success");
        } catch (e) {
          this._log("Janus play failed", e);
        }
      }
    };

    pc.ontrack = (e) => {
      if (!video.srcObject) {
        video.srcObject = e.streams[0];
        this._markConnected();
      }
      this._log("Janus track received");
      attemptPlay();
    };

    pc.oniceconnectionstatechange = () => {
      const s = pc.iceConnectionState;
      this._log("Janus ICE state", s);
      if (s === "disconnected" || s === "failed" || s === "closed") {
        this._teardownStream(false);
        this._scheduleRetry(`Janus ICE ${s}`);
      }
    };

    const ws = await this._openJanusWebSocket(config);
    this.ws = ws;

    let sessionId = null;
    let handleId = null;
    let streamId = config.janusStreamId ?? null;
    // For proxy streams, we need to create the mountpoint first before watching.
    // proxyUrl is the media_uri Janus uses to pull the stream from the camera.
    // Always create the mountpoint for proxy streams — the Janus stream ID is dynamic per session.
    const needsCreate = !!(config.proxyUrl);
    let mountpointCreated = false;

    const send = (msg) => {
      if (!ws || ws.readyState !== WebSocket.OPEN) return;
      const payload = {
        ...msg,
        token: config.janusToken,
        transaction: Math.random().toString(36).slice(2),
      };
      this._log("Janus send", payload);
      ws.send(JSON.stringify(payload));
    };

    this._log("Janus WS connected");

    send({ janus: "create" });

    ws.onerror = (err) => {
      this._log("Janus WS error", err);
    };

    ws.onmessage = async (event) => {
      let msg;
      try {
        msg = JSON.parse(event.data);
      } catch (err) {
        this._log("Janus parse failed", event.data, err);
        return;
      }

      this._log("Janus message", msg);

      if (msg.janus === "success" && !sessionId) {
        sessionId = msg.data?.id;
        this._log("Janus session created", sessionId);
        this._janusKeepalive = this._startJanusKeepalive(ws, sessionId, send);

        send({
          janus: "attach",
          session_id: sessionId,
          plugin: "janus.plugin.streaming",
        });
        return;
      }

      if (msg.janus === "success" && sessionId && !handleId) {
        handleId = msg.data?.id;
        this._log("Janus handle attached", handleId);

        if (needsCreate) {
          // Step 1: create the mountpoint so Janus pulls the stream from the camera.
          // The response will contain the assigned stream ID which we then use to watch.
          this._log("Janus creating proxy mountpoint", config.proxyUrl);
          send({
            janus: "message",
            session_id: sessionId,
            handle_id: handleId,
            body: {
              request: "create",
              type: "rtp",
              media_uri: config.proxyUrl,
              name: `${config.janusToken?.split(",")[0] ?? "stream"}_Live`,
              is_private: true,
              streaming_type: "Live",
              video: true,
              videoport: 0,
              videopt: 126,
              videortpmap: "H264/90000",
              timeout_seconds: 180,
              max_timeout_seconds: 900,
            },
          });
        } else {
          send({
            janus: "message",
            session_id: sessionId,
            handle_id: handleId,
            body: {
              request: "watch",
              id: streamId,
              token: config.janusToken,
              audio: true,
              video: true,
            },
          });
        }
        return;
      }

      // Handle the "create" mountpoint response — extract the assigned stream ID
      // then immediately send the "watch" request with it.
      if (msg.janus === "success" && sessionId && handleId && needsCreate && !mountpointCreated) {
        const createdId = msg.plugindata?.data?.stream?.id ?? msg.data?.id ?? msg.plugindata?.data?.id;
        if (createdId) {
          mountpointCreated = true;
          streamId = createdId;
          this._log("Janus mountpoint created, streamId", streamId);
          send({
            janus: "message",
            session_id: sessionId,
            handle_id: handleId,
            body: {
              request: "watch",
              id: streamId,
              token: config.janusToken,
              audio: true,
              video: true,
            },
          });
          return;
        }
      }

      if (msg.janus === "ack") {
        return;
      }

      if (msg.janus === "event") {
        const pluginData = msg.plugindata?.data;
        if (pluginData?.error) {
          this._log("Janus plugin error", pluginData.error_code, pluginData.error);
          this._teardownStream(false);
          this._scheduleRetry(`Plugin error ${pluginData.error_code}`);
          return;
        }
        // Non-error events (e.g. status updates) — fall through to JSEP check below
      }

      if (msg.jsep) {
        this._log("Janus JSEP received");
        await pc.setRemoteDescription(msg.jsep);

        const answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);

        send({
          janus: "message",
          session_id: sessionId,
          handle_id: handleId,
          body: { request: "start" },
          jsep: pc.localDescription,
        });
        return;
      }

      if (msg.candidate) {
        try {
          await pc.addIceCandidate(msg.candidate);
        } catch (err) {
          this._log("Failed to add Janus candidate", err);
        }
        return;
      }

      if (msg.janus === "webrtcup") {
        this._log("Janus WebRTC up");
        return;
      }

      if (msg.janus === "media") {
        this._log("Janus media event", msg);
        return;
      }

      if (msg.janus === "hangup") {
        this._log("Janus hangup", msg);
        this._teardownStream(false);
        this._scheduleRetry("Janus hangup");
        return;
      }

      if (msg.janus === "detached") {
        this._log("Janus detached", msg);
        this._teardownStream(false);
        this._scheduleRetry("Janus detached");
        return;
      }

      if (msg.janus === "error") {
        this._log("Janus error", msg);
        this._teardownStream(false);
        this._scheduleRetry("Janus error");
        return;
      }
    };

    pc.onicecandidate = (e) => {
      if (e.candidate && sessionId && handleId) {
        send({
          janus: "trickle",
          session_id: sessionId,
          handle_id: handleId,
          candidate: e.candidate,
        });
      }
    };

    ws.onclose = () => {
      const wasConnected = this._connected;
      this._log("Janus WS closed");
      this._connected = false;
      this._connecting = false;
      this._requesting = false;
      this._teardownStream(false);
      this._scheduleRetry(
        wasConnected ? "Janus stream ended" : "Janus WS closed before connection"
      );
    };
  }

  disconnectedCallback() {
    clearTimeout(this._requestTimeout);

    if (this._retryTimer) {
      clearTimeout(this._retryTimer);
      this._retryTimer = null;
    }

    this._teardownStream();
    this._requesting = false;
    this._connecting = false;
  }
}

customElements.define("alarm-webrtc-card", AlarmWebRTCCard);