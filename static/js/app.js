/**
 * J.A.R.V.I.S. // Client-side Neural Controller
 * Manages Speech Recognition, API interactions, Audio synthesis, and UI reactivity.
 */

document.addEventListener("DOMContentLoaded", () => {
  // --- DOM Elements ---
  const reactorContainer = document.getElementById("reactorContainer");
  const micBtn = document.getElementById("micBtn");
  const subMicBtn = document.getElementById("subMicBtn");
  const coreStatusText = document.getElementById("coreStatusText");
  const coreIcon = document.getElementById("coreIcon");
  const statusStateTag = document.getElementById("statusStateTag");
  const statusDesc = document.getElementById("statusDesc");

  const commandForm = document.getElementById("commandForm");
  const commandInput = document.getElementById("commandInput");
  const suggestionChips = document.getElementById("suggestionChips");

  const feedStream = document.getElementById("feedStream");
  const clearFeedBtn = document.getElementById("clearFeedBtn");
  const ttsAudioPlayer = document.getElementById("ttsAudioPlayer");
  const audioMuteBtn = document.getElementById("audioMuteBtn");
  const audioMuteIcon = document.getElementById("audioMuteIcon");
  const audioStatusText = document.getElementById("audioStatusText");

  // Voice Engine & HUD Controls
  const voiceEngineSelect = document.getElementById("voiceEngineSelect");
  const ttsBadgeVal = document.getElementById("ttsBadgeVal");
  const silenceCountdownBadge = document.getElementById("silenceCountdownBadge");
  const silenceCountdownText = document.getElementById("silenceCountdownText");
  const micPermissionBanner = document.getElementById("micPermissionBanner");

  const handsFreeToggleBtn = document.getElementById("handsFreeToggleBtn");
  const handsFreeStatusText = document.getElementById("handsFreeStatusText");
  const autoMicBadgeVal = document.getElementById("autoMicBadgeVal");

  const wakewordToggleBtn = document.getElementById("wakewordToggleBtn");
  const wakewordStatusText = document.getElementById("wakewordStatusText");
  const brainStatus = document.getElementById("brainStatus");
  const hudClock = document.getElementById("hudClock");

  // Tabs
  const tabBtns = document.querySelectorAll(".tab-btn");
  const tabPanes = document.querySelectorAll(".tab-pane");

  // Apps Launchpad
  const appTiles = document.querySelectorAll(".app-tile");
  const customAppInput = document.getElementById("customAppInput");
  const customAppLaunchBtn = document.getElementById("customAppLaunchBtn");

  // WhatsApp
  const waRecipient = document.getElementById("waRecipient");
  const waQuickContact = document.getElementById("waQuickContact");
  const waMessage = document.getElementById("waMessage");
  const waAiDraftBtn = document.getElementById("waAiDraftBtn");
  const waSendBtn = document.getElementById("waSendBtn");

  // Email
  const emailTo = document.getElementById("emailTo");
  const emailQuickContact = document.getElementById("emailQuickContact");
  const emailSubject = document.getElementById("emailSubject");
  const emailTopic = document.getElementById("emailTopic");
  const emailAiDraftBtn = document.getElementById("emailAiDraftBtn");
  const emailSendBtn = document.getElementById("emailSendBtn");

  // Search
  const searchInput = document.getElementById("searchInput");
  const searchExecBtn = document.getElementById("searchExecBtn");
  const searchResultsBox = document.getElementById("searchResultsBox");

  // Contacts
  const contactsTableBody = document.getElementById("contactsTableBody");
  const saveContactBtn = document.getElementById("saveContactBtn");
  const newContactName = document.getElementById("newContactName");
  const newContactWA = document.getElementById("newContactWA");
  const newContactEmail = document.getElementById("newContactEmail");
  const newContactRelation = document.getElementById("newContactRelation");

  // --- State Variables ---
  let isAudioMuted = false;
  let isListening = false;
  let isSpeaking = false;
  let isExecuting = false;
  let handsFreeEnabled = localStorage.getItem("jarvis_hands_free") !== "false"; // default TRUE
  let recognition = null;
  let contactsCache = [];

  // Silence Timer State (3-second continuous listening pause)
  let silenceTimer = null;
  let countdownInterval = null;
  let countdownRemaining = 3;
  let accumulatedTranscript = "";

  // --- Voice Selection & Preference Management ---
  function updateVoiceBadge(val) {
    if (!ttsBadgeVal) return;
    if (val.includes("Madhur")) {
      ttsBadgeVal.textContent = "NATURAL HINGLISH 👨";
    } else if (val.includes("Swara")) {
      ttsBadgeVal.textContent = "NATURAL HINGLISH 👩";
    } else if (val.includes("Neerja")) {
      ttsBadgeVal.textContent = "INDIAN ENGLISH 👩";
    } else if (val.includes("piper")) {
      ttsBadgeVal.textContent = "PIPER OFFLINE 🤖";
    } else {
      ttsBadgeVal.textContent = "STUDIO NEURAL";
    }
  }

  function getActiveVoiceConfig() {
    const val = (voiceEngineSelect && voiceEngineSelect.value) || "edge:hi-IN-MadhurNeural";
    const parts = val.split(":");
    return {
      engine: parts[0] || "edge",
      voice: parts[1] || "hi-IN-MadhurNeural"
    };
  }

  const savedVoicePref = localStorage.getItem("jarvis_voice_pref") || "edge:hi-IN-MadhurNeural";
  if (voiceEngineSelect) {
    voiceEngineSelect.value = savedVoicePref;
    updateVoiceBadge(savedVoicePref);

    voiceEngineSelect.addEventListener("change", () => {
      const val = voiceEngineSelect.value;
      localStorage.setItem("jarvis_voice_pref", val);
      updateVoiceBadge(val);
      const { engine } = getActiveVoiceConfig();
      if (audioStatusText) {
        audioStatusText.textContent = engine === "edge" ? "Voice Ready (Neural AI)" : "Voice Ready (Piper Offline)";
      }
    });
  }

  // --- 1. Clock Initializer ---
  function updateClock() {
    const now = new Date();
    hudClock.textContent = now.toTimeString().split(" ")[0];
  }
  setInterval(updateClock, 1000);
  updateClock();

  // --- Hands-Free / Auto-Listen Mode Controller ---
  function updateHandsFreeUI(enabled) {
    if (handsFreeToggleBtn && handsFreeStatusText) {
      if (enabled) {
        handsFreeToggleBtn.classList.add("active");
        handsFreeStatusText.textContent = "ON";
      } else {
        handsFreeToggleBtn.classList.remove("active");
        handsFreeStatusText.textContent = "OFF";
      }
    }
    if (autoMicBadgeVal) {
      autoMicBadgeVal.textContent = enabled ? "AUTO-LISTEN" : "MANUAL";
    }
  }

  function startListening() {
    if (!recognition) return;
    if (isSpeaking || isExecuting || isListening) return;

    try {
      accumulatedTranscript = "";
      if (silenceCountdownBadge) silenceCountdownBadge.style.display = "none";
      recognition.start();
      isListening = true;
      if (handsFreeEnabled) {
        setReactorState("listening", "HANDS-FREE ACTIVE", "Listening automatically. Speak anytime; commands submit after 3s pause.");
      } else {
        setReactorState("listening", "LISTENING...", "JARVIS is listening. Speak clearly; pauses under 3s are kept.");
      }
    } catch (err) {
      if (err.name !== "InvalidStateError") {
        console.warn("Recognition start error:", err);
      }
    }
  }

  function stopListening() {
    if (silenceTimer) {
      clearTimeout(silenceTimer);
      silenceTimer = null;
    }
    if (countdownInterval) {
      clearInterval(countdownInterval);
      countdownInterval = null;
    }
    if (silenceCountdownBadge) {
      silenceCountdownBadge.style.display = "none";
    }
    if (recognition) {
      try {
        recognition.stop();
      } catch (_) {}
    }
    isListening = false;
  }

  // --- 2. Web Speech API Setup with Continuous 3s Pause Detection ---
  function resetSilenceCountdown() {
    if (silenceTimer) {
      clearTimeout(silenceTimer);
      silenceTimer = null;
    }
    if (countdownInterval) {
      clearInterval(countdownInterval);
      countdownInterval = null;
    }

    countdownRemaining = 3;
    if (silenceCountdownBadge && silenceCountdownText) {
      silenceCountdownBadge.style.display = "flex";
      silenceCountdownText.textContent = `Silence detected: transmitting in ${countdownRemaining}s...`;
    }

    countdownInterval = setInterval(() => {
      countdownRemaining--;
      if (countdownRemaining > 0) {
        if (silenceCountdownText) {
          silenceCountdownText.textContent = `Silence detected: transmitting in ${countdownRemaining}s...`;
        }
      } else {
        clearInterval(countdownInterval);
        countdownInterval = null;
      }
    }, 1000);

    silenceTimer = setTimeout(() => {
      if (countdownInterval) {
        clearInterval(countdownInterval);
        countdownInterval = null;
      }
      if (silenceCountdownBadge) {
        silenceCountdownBadge.style.display = "none";
      }
      stopListeningAndTransmit();
    }, 3000);
  }

  function stopListeningAndTransmit() {
    if (silenceTimer) {
      clearTimeout(silenceTimer);
      silenceTimer = null;
    }
    if (countdownInterval) {
      clearInterval(countdownInterval);
      countdownInterval = null;
    }
    if (silenceCountdownBadge) {
      silenceCountdownBadge.style.display = "none";
    }

    const textToSend = (accumulatedTranscript || commandInput.value || "").trim();
    accumulatedTranscript = "";

    // Stop recognition while executing so it doesn't pick up ambient background noise
    stopListening();

    if (textToSend) {
      commandInput.value = textToSend;
      executeCommand(textToSend);
    } else {
      if (handsFreeEnabled) {
        setTimeout(startListening, 300);
      } else {
        setReactorState("idle", "SYSTEM READY", "Ready for voice or keyboard commands.");
      }
    }
  }

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = "en-IN"; // English + Indian accent / Hinglish friendly

    recognition.onstart = () => {
      isListening = true;
      accumulatedTranscript = "";
      if (silenceCountdownBadge) silenceCountdownBadge.style.display = "none";
      if (handsFreeEnabled) {
        setReactorState("listening", "HANDS-FREE ACTIVE", "Listening automatically. Speak anytime; commands submit after 3s pause.");
      } else {
        setReactorState("listening", "LISTENING...", "JARVIS is listening. Speak clearly; pauses under 3s are kept.");
      }
    };

    recognition.onresult = (event) => {
      if (isSpeaking || isExecuting) return; // Prevent echoing JARVIS's voice output

      let interim = "";
      let final = "";

      for (let i = 0; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          final += event.results[i][0].transcript + " ";
        } else {
          interim += event.results[i][0].transcript;
        }
      }

      const combined = (final + interim).trim();
      if (combined) {
        if (micPermissionBanner) micPermissionBanner.style.display = "none";
        accumulatedTranscript = combined;
        commandInput.value = combined;
        setReactorState("listening", "HEARING SPEECH...", `"${combined}"`);
        // Reset and trigger the 3-second silence countdown
        resetSilenceCountdown();
      }
    };

    recognition.onerror = (event) => {
      console.warn("Speech recognition error:", event.error);
      if (event.error === "not-allowed" || event.error === "service-not-allowed") {
        if (micPermissionBanner) micPermissionBanner.style.display = "flex";
        handsFreeEnabled = false;
        updateHandsFreeUI(false);
        setReactorState("idle", "MIC PERMISSION REQUIRED", "Click anywhere or allow mic access in your browser.");
      } else if (event.error === "no-speech") {
        // Normal pause; onend will automatically loop back
      } else {
        if (silenceCountdownBadge) silenceCountdownBadge.style.display = "none";
        if (handsFreeEnabled && !isSpeaking && !isExecuting) {
          setTimeout(() => {
            if (handsFreeEnabled && !isSpeaking && !isExecuting && !isListening) {
              startListening();
            }
          }, 500);
        }
      }
    };

    recognition.onend = () => {
      isListening = false;
      if (silenceCountdownBadge) silenceCountdownBadge.style.display = "none";

      const textToSend = (accumulatedTranscript || commandInput.value || "").trim();
      if (textToSend && silenceTimer) {
        stopListeningAndTransmit();
        return;
      }

      if (handsFreeEnabled && !isSpeaking && !isExecuting) {
        setTimeout(() => {
          if (handsFreeEnabled && !isSpeaking && !isExecuting && !isListening) {
            startListening();
          }
        }, 250);
      } else if (!isSpeaking && !isExecuting) {
        setReactorState("idle", "SYSTEM READY", "Ready for voice or keyboard commands.");
      }
    };
  }

  function toggleSpeechInput() {
    if (!recognition) {
      alert("Speech recognition is not natively supported in this browser. Please use Google Chrome or Microsoft Edge.");
      return;
    }

    if (isListening) {
      // If user clicks mic while listening, transmit what was spoken immediately without waiting 3s!
      const currentText = (accumulatedTranscript || commandInput.value || "").trim();
      if (currentText) {
        stopListeningAndTransmit();
      } else if (!handsFreeEnabled) {
        stopListening();
        setReactorState("idle", "SYSTEM READY", "Ready for commands.");
      }
    } else {
      startListening();
    }
  }

  micBtn.addEventListener("click", toggleSpeechInput);
  subMicBtn.addEventListener("click", toggleSpeechInput);

  // Hands-Free Toggle Button Listener
  if (handsFreeToggleBtn) {
    updateHandsFreeUI(handsFreeEnabled);

    handsFreeToggleBtn.addEventListener("click", () => {
      handsFreeEnabled = !handsFreeEnabled;
      localStorage.setItem("jarvis_hands_free", handsFreeEnabled ? "true" : "false");
      updateHandsFreeUI(handsFreeEnabled);

      if (handsFreeEnabled) {
        appendFeedMessage("assistant", "Hands-Free Auto-Listening activated. Speak anytime without clicking the mic!");
        startListening();
      } else {
        appendFeedMessage("assistant", "Hands-Free Auto-Listening disabled. Click the mic button to speak manually.");
        stopListening();
        setReactorState("idle", "SYSTEM READY", "Manual mode active. Click mic or type to speak.");
      }
    });
  }

  // --- 3. Reactor Visualizer State Transitions ---
  function setReactorState(state, statusTag, desc) {
    reactorContainer.className = "reactor-container " + state;
    statusStateTag.textContent = statusTag;
    statusDesc.textContent = desc;

    if (state === "listening") {
      if (statusTag.includes("HEARING")) {
        coreIcon.textContent = "👂";
        coreStatusText.textContent = "HEARING";
      } else {
        coreIcon.textContent = "🎙️";
        coreStatusText.textContent = handsFreeEnabled ? "AUTO-ON" : "LISTENING";
      }
    } else if (state === "processing") {
      coreIcon.textContent = "⚡";
      coreStatusText.textContent = "THINKING";
    } else if (state === "speaking") {
      coreIcon.textContent = "🔊";
      coreStatusText.textContent = "SPEAKING";
    } else {
      coreIcon.textContent = "🎙️";
      coreStatusText.textContent = handsFreeEnabled ? "AUTO-ON" : "IDLE";
    }
  }

  // --- 4. Command Execution ---
  async function executeCommand(cmdText) {
    const text = (cmdText || commandInput.value || "").trim();
    if (!text) return;

    isExecuting = true;
    stopListening(); // Make sure mic is stopped while waiting for backend

    const { engine, voice } = getActiveVoiceConfig();

    commandInput.value = "";
    appendFeedMessage("user", text);
    setReactorState("processing", "PROCESSING COMMAND", `Executing subroutine: "${text}"...`);

    try {
      const response = await fetch("/api/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: text,
          engine: engine,
          voice: voice,
          speak: false // Audio played through web browser player
        })
      });

      const data = await response.json();
      isExecuting = false;

      if (data.success) {
        appendFeedMessage("assistant", data.reply, data.audio_url, data.open_url);
        if (data.open_url) {
          try {
            window.open(data.open_url, "_blank");
          } catch (e) {
            console.warn("window.open blocked:", e);
          }
        }
        playSpokenReply(data.audio_url);
      } else {
        appendFeedMessage("assistant", "An error occurred: " + (data.error || "Unknown error"));
        if (handsFreeEnabled) {
          setTimeout(startListening, 500);
        } else {
          setReactorState("idle", "SYSTEM READY", "Ready for commands.");
        }
      }
    } catch (err) {
      console.error("Execution error:", err);
      isExecuting = false;
      appendFeedMessage("assistant", "Network failure connecting to JARVIS neural backend.");
      if (handsFreeEnabled) {
        setTimeout(startListening, 1000);
      } else {
        setReactorState("idle", "SYSTEM READY", "Error encountered. Ready for commands.");
      }
    }
  }

  commandForm.addEventListener("submit", (e) => {
    e.preventDefault();
    executeCommand();
  });

  // Suggestion Chips
  suggestionChips.addEventListener("click", (e) => {
    if (e.target.classList.contains("chip")) {
      const cmd = e.target.getAttribute("data-cmd");
      if (cmd) {
        commandInput.value = cmd;
        executeCommand(cmd);
      }
    }
  });

  // --- 5. Spoken Audio Playback ---
  function playSpokenReply(audioUrl) {
    if (isAudioMuted || !audioUrl) {
      isSpeaking = false;
      if (handsFreeEnabled) {
        setTimeout(startListening, 400);
      } else {
        setReactorState("idle", "SYSTEM READY", "Ready for commands.");
      }
      return;
    }

    isSpeaking = true;
    stopListening(); // Crucial: mic stays off while JARVIS is speaking out loud!

    const { engine, voice } = getActiveVoiceConfig();
    const voiceDisplayName = engine === "edge" ? "Neural AI Voice" : "Piper Offline Voice";

    setReactorState("speaking", "JARVIS SPEAKING", `Transmitting neural speech (${voiceDisplayName})...`);
    if (audioStatusText) {
      audioStatusText.textContent = `Streaming speech (${voiceDisplayName})...`;
    }

    ttsAudioPlayer.src = audioUrl;
    ttsAudioPlayer.play().then(() => {
      if (audioStatusText) audioStatusText.textContent = `Speaking (${voiceDisplayName})...`;
    }).catch(err => {
      console.warn("Audio playback prevented or failed:", err);
      isSpeaking = false;
      if (handsFreeEnabled) {
        setTimeout(startListening, 400);
      } else {
        setReactorState("idle", "SYSTEM READY", "Ready for commands.");
      }
    });

    ttsAudioPlayer.onended = () => {
      isSpeaking = false;
      if (audioStatusText) audioStatusText.textContent = `Voice Ready (${voiceDisplayName})`;
      if (handsFreeEnabled) {
        setTimeout(startListening, 300); // Hands-Free resumes automatically!
      } else {
        setReactorState("idle", "SYSTEM READY", "Ready for commands.");
      }
    };

    ttsAudioPlayer.onerror = () => {
      isSpeaking = false;
      if (audioStatusText) audioStatusText.textContent = "Audio playback error";
      if (handsFreeEnabled) {
        setTimeout(startListening, 400);
      } else {
        setReactorState("idle", "SYSTEM READY", "Ready for commands.");
      }
    };
  }

  // Audio Mute Toggle
  audioMuteBtn.addEventListener("click", () => {
    isAudioMuted = !isAudioMuted;
    const { engine } = getActiveVoiceConfig();
    const voiceDisplayName = engine === "edge" ? "Neural AI" : "Piper Offline";

    if (isAudioMuted) {
      audioMuteIcon.textContent = "🔇";
      audioMuteBtn.style.color = "var(--text-dim)";
      if (audioStatusText) audioStatusText.textContent = "Audio Muted";
      ttsAudioPlayer.pause();
      isSpeaking = false;
      if (reactorContainer.classList.contains("speaking")) {
        if (handsFreeEnabled) {
          setTimeout(startListening, 300);
        } else {
          setReactorState("idle", "SYSTEM READY", "Ready for commands.");
        }
      }
    } else {
      audioMuteIcon.textContent = "🔊";
      audioMuteBtn.style.color = "var(--text-main)";
      if (audioStatusText) audioStatusText.textContent = `Voice Ready (${voiceDisplayName})`;
    }
  });

  // --- 6. Conversation Feed ---
  function appendFeedMessage(role, content, audioUrl = null, openUrl = null) {
    const msgDiv = document.createElement("div");
    msgDiv.className = `feed-message ${role}`;

    const now = new Date();
    const timeStr = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    const authorName = role === "user" ? "OPERATOR" : "J.A.R.V.I.S.";

    let actionHtml = "";
    if (role === "assistant") {
      let replayBtn = "";
      if (audioUrl) {
        replayBtn = `<button class="audio-replay-btn" title="Replay voice audio" data-audio="${audioUrl}">🔊 Replay</button>`;
      }
      let linkBtn = "";
      if (openUrl) {
        let label = "🌐 Open in Chrome";
        if (openUrl.includes("mail.google.com")) {
          label = "✉️ Open Gmail Draft";
        } else if (openUrl.includes("google.com/search")) {
          label = "🔍 View Search in Chrome";
        }
        linkBtn = `<a href="${openUrl}" target="_blank" rel="noopener noreferrer" class="hud-link-btn" title="Open in Chrome: ${openUrl}">${label}</a>`;
      }
      if (replayBtn || linkBtn) {
        actionHtml = `<div class="msg-actions">${linkBtn}${replayBtn}</div>`;
      }
    }

    msgDiv.innerHTML = `
      <div class="msg-meta">
        <span class="msg-author">${authorName}</span>
        <span class="msg-time">${timeStr}</span>
      </div>
      <div class="msg-content">${escapeHtml(content)}</div>
      ${actionHtml}
    `;

    feedStream.appendChild(msgDiv);
    feedStream.scrollTop = feedStream.scrollHeight;
  }

  feedStream.addEventListener("click", (e) => {
    if (e.target.classList.contains("audio-replay-btn")) {
      const url = e.target.getAttribute("data-audio");
      if (url) playSpokenReply(url);
    }
  });

  clearFeedBtn.addEventListener("click", () => {
    feedStream.innerHTML = "";
    appendFeedMessage("assistant", "Neural log cleared. System ready for commands.");
  });

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  // --- 7. Tab Switching ---
  tabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      tabBtns.forEach(b => b.classList.remove("active"));
      tabPanes.forEach(p => p.classList.remove("active"));

      btn.classList.add("active");
      const targetPane = document.getElementById(btn.getAttribute("data-tab"));
      if (targetPane) targetPane.classList.add("active");
    });
  });

  // --- 8. App Launchpad ---
  appTiles.forEach(tile => {
    tile.addEventListener("click", async () => {
      const appName = tile.getAttribute("data-app");
      tile.style.transform = "scale(0.95)";
      setTimeout(() => tile.style.transform = "", 150);

      appendFeedMessage("user", `Open ${appName}`);
      setReactorState("processing", "LAUNCHING APP", `Starting ${appName}...`);

      try {
        const resp = await fetch("/api/skills/open-app", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ app: appName })
        });
        const res = await resp.json();
        appendFeedMessage("assistant", res.message, null, res.open_url);
        if (res.open_url) {
          try {
            window.open(res.open_url, "_blank");
          } catch (e) {
            console.warn("window.open blocked:", e);
          }
        }
        playSpokenReply(`/api/tts?text=${encodeURIComponent(res.message)}`);
      } catch (e) {
        appendFeedMessage("assistant", `Failed to launch ${appName}`);
        setReactorState("idle", "SYSTEM READY", "Ready for commands.");
      }
    });
  });

  customAppLaunchBtn.addEventListener("click", async () => {
    const val = customAppInput.value.trim();
    if (!val) return;
    customAppInput.value = "";
    executeCommand(`open ${val}`);
  });

  // --- 9. WhatsApp Skill Deck ---
  waQuickContact.addEventListener("change", () => {
    if (waQuickContact.value) {
      waRecipient.value = waQuickContact.value;
    }
  });

  waAiDraftBtn.addEventListener("click", async () => {
    const rec = waRecipient.value.trim() || "friend";
    setReactorState("processing", "AI DRAFTING", "Drafting WhatsApp message with LLaMA...");
    try {
      const prompt = `Draft a very short (1 sentence), friendly WhatsApp message in Hinglish or English to ${rec} saying I'll get back soon. Return only the message text.`;
      const resp = await fetch("/api/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: prompt, speak: false })
      });
      const data = await resp.json();
      if (data.reply) {
        waMessage.value = data.reply.replace(/^["']|["']$/g, "");
      }
      setReactorState("idle", "SYSTEM READY", "Message drafted.");
    } catch (e) {
      setReactorState("idle", "SYSTEM READY", "Error generating draft.");
    }
  });

  waSendBtn.addEventListener("click", async () => {
    const rec = waRecipient.value.trim();
    const msg = waMessage.value.trim();
    if (!rec) {
      alert("Please specify a recipient name or phone number.");
      return;
    }

    setReactorState("processing", "OPENING WHATSAPP", `Opening WhatsApp for ${rec}...`);
    try {
      const resp = await fetch("/api/skills/whatsapp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ recipient: rec, message: msg, dry_run: false })
      });
      const res = await resp.json();
      appendFeedMessage("assistant", res.message);
      playSpokenReply(`/api/tts?text=${encodeURIComponent(res.message)}`);
    } catch (e) {
      appendFeedMessage("assistant", "Could not trigger WhatsApp Web.");
      setReactorState("idle", "SYSTEM READY", "Ready for commands.");
    }
  });

  // --- 10. Email Skill Deck ---
  emailQuickContact.addEventListener("change", () => {
    const selected = emailQuickContact.selectedOptions[0];
    if (selected && selected.getAttribute("data-email")) {
      emailTo.value = selected.getAttribute("data-email");
    } else if (emailQuickContact.value) {
      emailTo.value = emailQuickContact.value;
    }
  });

  emailAiDraftBtn.addEventListener("click", async () => {
    const to = emailTo.value.trim() || "recipient";
    const topic = emailTopic.value.trim() || "project update";
    setReactorState("processing", "AI DRAFTING", "Drafting email with LLaMA...");

    try {
      const prompt = `Draft a polite professional email to ${to} regarding ${topic}. Format: SUBJECT: <subject> then BODY: <body>`;
      const resp = await fetch("/api/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: prompt, speak: false })
      });
      const data = await resp.json();
      if (data.reply) {
        const lines = data.reply.split("\n");
        let subject = "";
        let body = [];
        for (const line of lines) {
          if (line.toUpperCase().startsWith("SUBJECT:")) {
            subject = line.substring(8).trim();
          } else if (line.toUpperCase().startsWith("BODY:")) {
            body.push(line.substring(5).trim());
          } else {
            body.push(line);
          }
        }
        if (subject) emailSubject.value = subject;
        emailTopic.value = body.join("\n").trim();
      }
      setReactorState("idle", "SYSTEM READY", "Email drafted.");
    } catch (e) {
      setReactorState("idle", "SYSTEM READY", "Error generating email draft.");
    }
  });

  emailSendBtn.addEventListener("click", async () => {
    const to = emailTo.value.trim();
    const topic = emailTopic.value.trim() || emailSubject.value.trim();
    if (!to) {
      alert("Please provide a recipient email address.");
      return;
    }

    setReactorState("processing", "DISPATCHING EMAIL", `Sending email to ${to}...`);
    try {
      const resp = await fetch("/api/skills/email", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ to: to, topic: topic, dry_run: false })
      });
      const res = await resp.json();
      appendFeedMessage("assistant", res.message);
      playSpokenReply(`/api/tts?text=${encodeURIComponent(res.message)}`);
    } catch (e) {
      appendFeedMessage("assistant", "Failed to dispatch email.");
      setReactorState("idle", "SYSTEM READY", "Ready for commands.");
    }
  });

  // --- 11. Search Terminal Deck ---
  searchExecBtn.addEventListener("click", runSearch);
  searchInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") runSearch();
  });

  async function runSearch() {
    const query = searchInput.value.trim();
    if (!query) return;

    searchResultsBox.innerHTML = '<div class="empty-state">Searching DuckDuckGo...</div>';
    setReactorState("processing", "WEB SEARCH", `Querying DuckDuckGo for "${query}"...`);

    try {
      const resp = await fetch("/api/skills/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query, max_results: 4 })
      });
      const data = await resp.json();

      if (data.results && data.results.length > 0) {
        searchResultsBox.innerHTML = "";
        data.results.forEach(r => {
          const card = document.createElement("div");
          card.className = "search-result-card";
          card.innerHTML = `
            <a href="${r.url || '#'}" target="_blank" rel="noopener noreferrer" class="search-result-title">${escapeHtml(r.title || 'Untitled')}</a>
            <p class="search-result-snippet">${escapeHtml(r.body || '')}</p>
          `;
          searchResultsBox.appendChild(card);
        });
        appendFeedMessage("assistant", `Searched web for "${query}". Found ${data.results.length} results.`);
      } else {
        searchResultsBox.innerHTML = '<div class="empty-state">No matching results found.</div>';
      }
      setReactorState("idle", "SYSTEM READY", "Ready for commands.");
    } catch (e) {
      searchResultsBox.innerHTML = '<div class="empty-state">Search query failed. Check connection.</div>';
      setReactorState("idle", "SYSTEM READY", "Ready for commands.");
    }
  }

  // --- 12. Contacts Management ---
  async function loadContacts() {
    try {
      const resp = await fetch("/api/contacts");
      const data = await resp.json();
      contactsCache = data.contacts || [];

      // Render table
      if (contactsCache.length === 0) {
        contactsTableBody.innerHTML = '<tr><td colspan="4">No contacts stored yet.</td></tr>';
      } else {
        contactsTableBody.innerHTML = "";
        contactsCache.forEach(c => {
          const tr = document.createElement("tr");
          tr.innerHTML = `
            <td><strong>${escapeHtml(c.name)}</strong></td>
            <td>${escapeHtml(c.whatsapp_id || '—')}</td>
            <td>${escapeHtml(c.email || '—')}</td>
            <td>${escapeHtml(c.relation || '—')}</td>
          `;
          contactsTableBody.appendChild(tr);
        });
      }

      // Populate Quick Selectors in WhatsApp and Email
      waQuickContact.innerHTML = '<option value="">-- Quick Contact --</option>';
      emailQuickContact.innerHTML = '<option value="">-- Quick Contact --</option>';

      contactsCache.forEach(c => {
        const waOpt = document.createElement("option");
        waOpt.value = c.whatsapp_id || c.name;
        waOpt.textContent = `${c.name} (${c.relation || 'Contact'})`;
        waQuickContact.appendChild(waOpt);

        if (c.email) {
          const emOpt = document.createElement("option");
          emOpt.value = c.email;
          emOpt.setAttribute("data-email", c.email);
          emOpt.textContent = `${c.name} (${c.email})`;
          emailQuickContact.appendChild(emOpt);
        }
      });
    } catch (e) {
      console.warn("Failed to load contacts:", e);
    }
  }

  saveContactBtn.addEventListener("click", async () => {
    const name = newContactName.value.trim();
    if (!name) {
      alert("Name is required.");
      return;
    }

    try {
      const resp = await fetch("/api/contacts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name,
          whatsapp_id: newContactWA.value.trim(),
          email: newContactEmail.value.trim(),
          relation: newContactRelation.value.trim(),
        })
      });
      const data = await resp.json();
      if (data.success) {
        newContactName.value = "";
        newContactWA.value = "";
        newContactEmail.value = "";
        newContactRelation.value = "";
        loadContacts();
        appendFeedMessage("assistant", `Contact '${name}' updated in neural database.`);
      }
    } catch (e) {
      alert("Error saving contact.");
    }
  });

  // --- 13. System Status & Wake-word Toggle ---
  async function checkSystemStatus() {
    try {
      const resp = await fetch("/api/status");
      const data = await resp.json();

      if (data.brain_connected) {
        brainStatus.textContent = "ONLINE (LLAMA-3.1)";
        brainStatus.style.color = "var(--cyan-bright)";
      } else {
        brainStatus.textContent = "OFFLINE";
        brainStatus.style.color = "var(--text-dim)";
      }

      updateWakewordButton(data.wakeword_active);
    } catch (e) {
      console.warn("Status check failed:", e);
    }
  }

  function updateWakewordButton(isActive) {
    if (isActive) {
      wakewordToggleBtn.classList.add("active");
      wakewordStatusText.textContent = "LISTENING";
    } else {
      wakewordToggleBtn.classList.remove("active");
      wakewordStatusText.textContent = "OFF";
    }
  }

  wakewordToggleBtn.addEventListener("click", async () => {
    try {
      const resp = await fetch("/api/wakeword/toggle", { method: "POST" });
      const data = await resp.json();
      updateWakewordButton(data.wakeword_active);
      appendFeedMessage("assistant", data.wakeword_active ? "Wake-word listener activated ('Hey Jarvis')." : "Wake-word listener deactivated.");
    } catch (e) {
      alert("Could not toggle wake-word.");
    }
  });

  // Initial loads
  checkSystemStatus();
  loadContacts();

  // Hands-Free Auto-Start on page launch
  if (handsFreeEnabled) {
    setTimeout(startListening, 500);
  }

  // Fallback: unlock on first gesture if browser security blocks cold-start speech recognition
  const unlockHandsFreeOnGesture = () => {
    if (micPermissionBanner) micPermissionBanner.style.display = "none";
    if (handsFreeEnabled && !isListening && !isSpeaking && !isExecuting) {
      startListening();
    }
  };
  window.addEventListener("pointerdown", unlockHandsFreeOnGesture, { once: true });
  window.addEventListener("keydown", unlockHandsFreeOnGesture, { once: true });

  if (micPermissionBanner) {
    micPermissionBanner.addEventListener("click", unlockHandsFreeOnGesture);
  }
});
