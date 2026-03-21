class AlarmWebRTCCard extends HTMLElement {

  // -------------------------------------------------------------------------
  // Token helpers
  // -------------------------------------------------------------------------

  isTokenValid(token) {
    if (!token) return false;
    try {
      const payload = JSON.parse(atob(token.split('.')[1]));
      const now = Math.floor(Date.now() / 1000);
      return payload.exp > (now + 30); // 30-second buffer
    } catch (e) {
      console.error('[AlarmWebRTC] Invalid token format', e);
      return false;
    }
  }

  // -------------------------------------------------------------------------
  // HA state updates
  // -------------------------------------------------------------------------

  set hass(hass) {
    this._hass = hass;

    const entityId = this.config.entity;
    const stateObj = hass.states[entityId];

    if (!stateObj) {
      this.innerHTML = `
        <ha-card>
          <div style="padding:16px;color:red">Entity not found: ${entityId}</div>
        </ha-card>`;
      return;
    }

    const attrs  = stateObj.attributes;
    const config = attrs.webrtc_config;
    const isValid = config && this.isTokenValid(config.signallingServerToken);

    // --- Need fresh tokens ---
    if (!isValid && !this._requesting) {
      const reason = !config ? 'Missing config' : 'Expired token';
      console.log(`[AlarmWebRTC] Requesting tokens (${reason})...`);
      this._requesting = true;

      // Safety timeout: if HA never responds, unblock after 15 s
      clearTimeout(this._requestTimeout);
      this._requestTimeout = setTimeout(() => {
        console.warn('[AlarmWebRTC] Token request timed out — resetting.');
        this._requesting = false;
      }, 15000);

      this._hass.callService('camera', 'turn_on', { entity_id: entityId })
        .catch(err => {
          console.error('[AlarmWebRTC] turn_on failed:', err);
          this._requesting = false;
        });

      this.renderPlaceholder('Refreshing session...');
      return;
    }

    // --- Have valid tokens, not yet streaming ---
    if (isValid && !this._connected && !this._connecting) {
      clearTimeout(this._requestTimeout);
      this._requesting = false;

      // Restart stream only if config actually changed
      if (JSON.stringify(config) !== JSON.stringify(this._currentConfig)) {
        this._retried = false;
        this.renderVideo();
        this.startStream(config);
      }
    }
  }

  // -------------------------------------------------------------------------
  // Config
  // -------------------------------------------------------------------------

  setConfig(config) {
    if (!config.entity) throw new Error('You need to define an entity');
    this.config = config;
  }

  // -------------------------------------------------------------------------
  // Rendering
  // -------------------------------------------------------------------------

  renderPlaceholder(msg) {
    if (this._connected) return;
    this.innerHTML = `
      <ha-card>
        <div style="padding:16px;text-align:center">${msg}</div>
      </ha-card>`;
  }

  renderVideo() {
    if (this.querySelector('video')) return;
    this.innerHTML = `
      <ha-card>
        <div style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;background:#000">
          <video id="video" autoplay playsinline muted
            style="position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none">
          </video>
        </div>
      </ha-card>`;
  }

  // -------------------------------------------------------------------------
  // WebRTC stream
  // -------------------------------------------------------------------------

  async startStream(config) {
    this._connecting = true;
    this._currentConfig = config;
    console.log('[AlarmWebRTC] Starting stream', config);

    const pc = new RTCPeerConnection({ iceServers: config.iceServers || [] });
    this.pc = pc;

    const videoEl = this.querySelector('#video');

    // Robust play with retry loop
    const attemptPlay = async () => {
      if (videoEl && (videoEl.paused || videoEl.ended)) {
        try {
          videoEl.muted = true;
          await videoEl.play();
          console.log('[AlarmWebRTC] Play success');
        } catch (e) {
          console.warn('[AlarmWebRTC] Play failed:', e);
        }
      }
    };

    const startPlayLoop = () => {
      let attempts = 0;
      const interval = setInterval(() => {
        if (!this._connected) { clearInterval(interval); return; }
        if (!videoEl.paused && videoEl.currentTime > 0 && videoEl.videoWidth > 0) {
          clearInterval(interval); return;
        }
        attempts++;
        attemptPlay();
        if (attempts > 10) clearInterval(interval);
      }, 1000);
    };

    pc.ontrack = (event) => {
      console.log('[AlarmWebRTC] Track received');
      videoEl.srcObject = event.streams[0];
      startPlayLoop();
      this._connected  = true;
      this._connecting = false;
    };

    pc.onicecandidate = (event) => {
      if (event.candidate && this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ to: this.remoteId, ice: event.candidate }));
      }
    };

    // Visibility handler — stored so we can remove it later
    this._visibilityHandler = () => {
      if (document.visibilityState === 'visible' && this._connected) attemptPlay();
    };
    document.addEventListener('visibilitychange', this._visibilityHandler);

    // WebSocket signalling
    const wsUrl = `${config.signallingServerUrl}/${config.signallingServerToken}`;
    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      console.log('[AlarmWebRTC] WS connected');
      this.ws.send('HELLO 2.0.1');
    };

    this.ws.onmessage = async (event) => {
      const msg = event.data;

      if (msg.startsWith('HELLO')) {
        this.ws.send(`START_SESSION ${config.cameraAuthToken}`);
        return;
      }
      if (msg.startsWith('SESSION_STARTED')) return;

      let data;
      try { data = JSON.parse(msg); } catch { return; }

      if (data.sdp?.type === 'offer') {
        this.remoteId = data.from;
        await pc.setRemoteDescription(data.sdp);
        const answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);
        this.ws.send(JSON.stringify({
          to: this.remoteId,
          from: data.to,
          sdp: pc.localDescription,
        }));
      }

      if (data.ice) await pc.addIceCandidate(data.ice);
    };

    this.ws.onclose = () => {
      if (this._connected) {
        console.log('[AlarmWebRTC] WS closed after connection');
      } else if (!this._retried) {
        // One automatic retry with fresh tokens
        console.log('[AlarmWebRTC] WS closed before connection — retrying with fresh tokens');
        this._retried     = true;
        this._connecting  = false;
        this._currentConfig = null;
        this._requesting  = false; // allow turn_on to be called again
        clearTimeout(this._requestTimeout);
        this._hass.callService('camera', 'turn_on', { entity_id: this.config.entity })
          .catch(err => console.error('[AlarmWebRTC] Retry turn_on failed:', err));
      }
      this._connected  = false;
      this._connecting = false;
    };

    this.ws.onerror = (err) => {
      console.error('[AlarmWebRTC] WS error:', err);
      // onclose will fire after onerror, so let that handle reset
    };
  }

  // -------------------------------------------------------------------------
  // Cleanup
  // -------------------------------------------------------------------------

  disconnectedCallback() {
    clearTimeout(this._requestTimeout);
    if (this._visibilityHandler) {
      document.removeEventListener('visibilitychange', this._visibilityHandler);
      this._visibilityHandler = null;
    }
    if (this.pc)  { this.pc.close();  this.pc  = null; }
    if (this.ws)  { this.ws.close();  this.ws  = null; }
    this._connected  = false;
    this._connecting = false;
    this._requesting = false;
  }
}

customElements.define('alarm-webrtc-card', AlarmWebRTCCard);
