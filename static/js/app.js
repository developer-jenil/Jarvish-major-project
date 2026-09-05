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
  let recognition = null;
  let contactsCache = [];

  // --- 1. Clock Initializer ---
  function updateClock() {
    const now = new Date();
    hudClock.textContent = now.toTimeString().split(" ")[0];
  }
  setInterval(updateClock, 1000);
  updateClock();

  // --- 2. Web Speech API Setup ---
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = "en-IN"; // English + Indian accent / Hinglish friendly

    recognition.onstart = () => {
      isListening = true;
      setReactorState("listening", "LISTENING...", "JARVIS is listening to your speech. Speak clearly.");
    };

    recognition.onresult = (event) => {
      const speechResult = event.results[0][0].transcript;
      commandInput.value = speechResult;
      executeCommand(speechResult);
    };

    recognition.onerror = (event) => {
      console.warn("Speech recognition error:", event.error);
      setReactorState("idle", "SYSTEM READY", "Voice detection ended. Ready for commands.");
      isListening = false;
    };

    recognition.onend = () => {
      isListening = false;
      if (!reactorContainer.classList.contains("processing") && !reactorContainer.classList.contains("speaking")) {
        setReactorState("idle", "SYSTEM READY", "Ready for voice or keyboard commands.");
      }
    };
  }

  function toggleSpeechInput() {
    if (!recognition) {
      alert("Speech recognition is not natively supported in this browser. Please use the text command bar or Chrome/Edge.");
      return;
    }

    if (isListening) {
      recognition.stop();
      isListening = false;
      setReactorState("idle", "SYSTEM READY", "Ready for commands.");
    } else {
      try {
        recognition.start();
      } catch (err) {
        console.warn("Recognition start error:", err);
      }
    }
  }

  micBtn.addEventListener("click", toggleSpeechInput);
  subMicBtn.addEventListener("click", toggleSpeechInput);

  // --- 3. Reactor Visualizer State Transitions ---
  function setReactorState(state, statusTag, desc) {
    reactorContainer.className = "reactor-container " + state;
    statusStateTag.textContent = statusTag;
    statusDesc.textContent = desc;

    if (state === "listening") {
      coreIcon.textContent = "👂";
      coreStatusText.textContent = "HEARING";
    } else if (state === "processing") {
      coreIcon.textContent = "⚡";
      coreStatusText.textContent = "THINKING";
    } else if (state === "speaking") {
      coreIcon.textContent = "🔊";
      coreStatusText.textContent = "SPEAKING";
    } else {
      coreIcon.textContent = "🎙️";
      coreStatusText.textContent = "IDLE";
    }
  }

  // --- 4. Command Execution ---
  async function executeCommand(cmdText) {
    const text = (cmdText || commandInput.value || "").trim();
    if (!text) return;

    commandInput.value = "";
    appendFeedMessage("user", text);
    setReactorState("processing", "PROCESSING COMMAND", `Executing subroutine: "${text}"...`);

    try {
      const response = await fetch("/api/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: text,
          speak: false // We handle audio playback through the browser player
        })
      });

      const data = await response.json();
      if (data.success) {
        appendFeedMessage("assistant", data.reply, data.audio_url);
        playSpokenReply(data.audio_url);
      } else {
        appendFeedMessage("assistant", "An error occurred: " + (data.error || "Unknown error"));
        setReactorState("idle", "SYSTEM READY", "Ready for commands.");
      }
    } catch (err) {
      console.error("Execution error:", err);
      appendFeedMessage("assistant", "Network failure connecting to JARVIS neural backend.");
      setReactorState("idle", "SYSTEM READY", "Error encountered. Ready for commands.");
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
      setReactorState("idle", "SYSTEM READY", "Ready for commands.");
      return;
    }

    setReactorState("speaking", "JARVIS SPEAKING", "Transmitting neural audio reply...");
    audioStatusText.textContent = "Synthesizing voice via Piper TTS...";

    ttsAudioPlayer.src = audioUrl;
    ttsAudioPlayer.play().then(() => {
      audioStatusText.textContent = "Speaking...";
    }).catch(err => {
      console.warn("Audio playback prevented or failed:", err);
      setReactorState("idle", "SYSTEM READY", "Ready for commands.");
    });

    ttsAudioPlayer.onended = () => {
      audioStatusText.textContent = "Voice Ready (Piper TTS)";
      setReactorState("idle", "SYSTEM READY", "Ready for commands.");
    };

    ttsAudioPlayer.onerror = () => {
      audioStatusText.textContent = "Audio playback error";
      setReactorState("idle", "SYSTEM READY", "Ready for commands.");
    };
  }

  // Audio Mute Toggle
  audioMuteBtn.addEventListener("click", () => {
    isAudioMuted = !isAudioMuted;
    if (isAudioMuted) {
      audioMuteIcon.textContent = "🔇";
      audioMuteBtn.style.color = "var(--text-dim)";
      audioStatusText.textContent = "Audio Muted";
      ttsAudioPlayer.pause();
      if (reactorContainer.classList.contains("speaking")) {
        setReactorState("idle", "SYSTEM READY", "Ready for commands.");
      }
    } else {
      audioMuteIcon.textContent = "🔊";
      audioMuteBtn.style.color = "var(--text-main)";
      audioStatusText.textContent = "Voice Ready (Piper TTS)";
    }
  });

  // --- 6. Conversation Feed ---
  function appendFeedMessage(role, content, audioUrl = null) {
    const msgDiv = document.createElement("div");
    msgDiv.className = `feed-message ${role}`;

    const now = new Date();
    const timeStr = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    const authorName = role === "user" ? "OPERATOR" : "J.A.R.V.I.S.";

    let actionHtml = "";
    if (audioUrl && role === "assistant") {
      actionHtml = `
        <div class="msg-actions">
          <button class="audio-replay-btn" title="Replay voice audio" data-audio="${audioUrl}">🔊 Replay</button>
        </div>
      `;
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
        appendFeedMessage("assistant", res.message);
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
});
