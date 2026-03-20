class AlarmWebRTCCard extends HTMLElement {
  isTokenValid(token) {
      if (!token) return false;
      try {
          const payload = JSON.parse(atob(token.split('.')[1]));
          const now = Math.floor(Date.now() / 1000);
          // Buffer of 30 seconds
          return payload.exp > (now + 30);
      } catch (e) {
          console.error("Invalid token format", e);
          return false;
      }
  }

  set hass(hass) {
    this._hass = hass;
    
    const entityId = this.config.entity;
    const stateObj = hass.states[entityId];

    if (!stateObj) {
      this.innerHTML = `
        <ha-card>
          <div style="padding: 16px; color: red">
            Entity not found: ${entityId}
          </div>
        </ha-card>`;
      return;
    }

    // Check if we need to request tokens
    const attrs = stateObj.attributes;
    const config = attrs.webrtc_config;

    // Check if config exists AND is valid (not expired)
    const isValid = config && this.isTokenValid(config.signallingServerToken);

    // If config is missing or expired, ask HA to turn it on (fetch tokens)
    if ((!config || !isValid) && stateObj.state !== 'on' && !this._requesting) {
      this._requesting = true;
      const reason = !config ? "Missing config" : "Expired token";
      console.log(`[AlarmWebRTC] Requesting tokens (${reason})...`);
      this._hass.callService("camera", "turn_on", { entity_id: entityId });
      this.renderPlaceholder("Refreshing session...");
      return;
    }

    // If we have config and haven't started streaming, start now
    if (isValid && !this._connected && !this._connecting) {
      // Check if config changed
      if (JSON.stringify(config) !== JSON.stringify(this._currentConfig)) {
          this._retried = false;
      }

      this._requesting = false;
      this.renderVideo(); // Must render BEFORE starting stream so video element exists!
      this.startStream(config);
    }
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error("You need to define an entity");
    }
    this.config = config;
  }

  renderPlaceholder(msg) {
    if (this._connected) return;
    this.innerHTML = `
      <ha-card>
        <div style="padding: 16px; text-align: center;">
          ${msg}
        </div>
      </ha-card>`;
  }

  renderVideo() {
    if (this.querySelector("video")) return;
    
    this.innerHTML = `
      <ha-card>
        <div style="position: relative; padding-bottom: 56.25%; height: 0; overflow: hidden; background: black;">
            <video id="video" autoplay playsinline muted style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none;"></video>
        </div>
      </ha-card>
    `;
    
    // No reconnect button needed
  }

  updateStatus(msg) {
      // Debug logging only, no UI overlay
      // console.log("[AlarmWebRTC Status]", msg);
  }

  async startStream(config) {
    this._connecting = true;
    this._currentConfig = config;
    console.log("[AlarmWebRTC v1.2] Starting stream with config", config);
    this.updateStatus("Signaling...");

    const pc = new RTCPeerConnection({
        iceServers: config.iceServers || []
    });
    this.pc = pc;

    const videoEl = this.querySelector("#video");
    
    // Robust play logic
    const attemptPlay = async () => {
        if (videoEl.paused || videoEl.ended) {
            try {
                videoEl.muted = true; 
                await videoEl.play();
                console.log("[AlarmWebRTC] Play success");
            } catch (e) {
                console.warn("[AlarmWebRTC] Play failed:", e);
            }
        }
    };

    // Retry loop for the first few seconds
    const startPlayLoop = () => {
        let attempts = 0;
        const interval = setInterval(() => {
            if (!this._connected) {
                clearInterval(interval);
                return;
            }
            if (!videoEl.paused && videoEl.currentTime > 0) {
                // It's playing!
                this.updateStatus(`Live (${videoEl.videoWidth}x${videoEl.videoHeight})`);
                if (videoEl.videoWidth === 0) {
                    // Decoder hasn't kicked in, keep retrying status update
                    return; 
                }
                clearInterval(interval);
                return;
            }
            
            attempts++;
            this.updateStatus(`Starting ${attempts}... (${videoEl.videoWidth}x${videoEl.videoHeight})`);
            attemptPlay();
            
            // Stop after 10 seconds
            if (attempts > 10) clearInterval(interval);
        }, 1000);
    };

    pc.ontrack = (event) => {
      console.log("[AlarmWebRTC] Track received");
      this.updateStatus("Live (Buffering...)");
      videoEl.srcObject = event.streams[0];
      startPlayLoop();
      this._connected = true;
      this._connecting = false;
    };
    
    // Re-check visibility
    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible" && this._connected) {
            attemptPlay();
        }
    });

    pc.onicecandidate = (event) => {
      if (event.candidate && this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({
          to: this.remoteId,
          ice: event.candidate
        }));
      }
    };

    // WebSocket Signaling
    const wsUrl = `${config.signallingServerUrl}/${config.signallingServerToken}`;
    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      console.log("[AlarmWebRTC] WS Connected");
      this.ws.send("HELLO 2.0.1");
    };

    this.ws.onmessage = async (event) => {
      const msg = event.data;

      if (msg.startsWith("HELLO")) {
        this.ws.send(`START_SESSION ${config.cameraAuthToken}`);
        return;
      }

      if (msg.startsWith("SESSION_STARTED")) {
        this.updateStatus("Waiting for video...");
        return;
      }

      let data;
      try { data = JSON.parse(msg); } catch { return; }

      if (data.sdp?.type === "offer") {
        this.remoteId = data.from;
        const myId = data.to;

        await pc.setRemoteDescription(data.sdp);
        const answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);

        this.ws.send(JSON.stringify({
          to: this.remoteId,
          from: myId,
          sdp: pc.localDescription
        }));
      }

      if (data.ice) {
        await pc.addIceCandidate(data.ice);
      }
    };
    
    this.ws.onclose = () => {
        if (this._connected) {
            this.updateStatus("Disconnected");
        } else if (!this._retried) {
            // Auto-retry once if we never connected (stale token?)
            console.log("Connection failed, requesting fresh tokens...");
            this.updateStatus("Refreshing...");
            this._retried = true;
            this._connecting = false; // Reset so new config triggers startStream
            this._hass.callService("camera", "turn_on", { entity_id: this.config.entity });
            this._currentConfig = null; // Force reset
            return;
        }
        
        this._connected = false;
        this._connecting = false;
    }
  }
  
  disconnectedCallback() {
      if (this.pc) this.pc.close();
      if (this.ws) this.ws.close();
  }
}

customElements.define('alarm-webrtc-card', AlarmWebRTCCard);
