/* ============================================================
  对话模块 —— 从原 index.html 搬移，逻辑完全不变。
  暴露到 window.Chat，供 main.js 调用 init() 初始化。
  ============================================================ */
window.Chat = (() => {
  let sessionId = null;
  let sending = false;

  const RISK_META = {
    0: { cls: "risk-l0", name: "L0 正常" },
    1: { cls: "risk-l1", name: "L1 关注" },
    2: { cls: "risk-l2", name: "L2 高风险" },
    3: { cls: "risk-l3", name: "L3 危机" },
  };

  function addUserBubble(text) {
    const div = document.createElement("div");
    div.className = "msg user";
    div.textContent = text;
    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;
    return div;
  }

  function addBotBubble(data) {
    const wrap = document.createElement("div");
    wrap.className = "msg bot";

    const text = document.createElement("div");
    text.textContent = data.reply;
    wrap.appendChild(text);

    const riskMeta = RISK_META[data.risk.level] || RISK_META[0];
    const meta = document.createElement("div");
    meta.className = "meta";

    const emotionTag = document.createElement("span");
    emotionTag.className = "tag emotion";
    const emo = data.emotion || {};
    emotionTag.textContent =
      "情绪：" + (emo.category || "未知") + "（强度 " + (emo.intensity ?? "-") + "）";
    meta.appendChild(emotionTag);

    const riskTag = document.createElement("span");
    riskTag.className = "tag " + riskMeta.cls;
    riskTag.textContent = "风险：" + riskMeta.name;
    meta.appendChild(riskTag);

    wrap.appendChild(meta);

    if (data.risk.level === 3 && data.crisis_hotline) {
      const banner = document.createElement("div");
      banner.className = "crisis-banner";
      banner.innerHTML =
        "⚠ 你似乎正处于危机之中。<strong>请立即拨打全国心理援助热线 " +
        data.crisis_hotline + "</strong>（24 小时免费），或前往最近医院急诊。";
      wrap.appendChild(banner);
    }

    chatBox.appendChild(wrap);
    chatBox.scrollTop = chatBox.scrollHeight;
  }

  function addSystemNote(text) {
    const div = document.createElement("div");
    div.className = "msg bot";
    div.style.background = "#fdf3d7";
    div.textContent = text;
    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;
  }

  async function ensureSession() {
    if (sessionId) return true;
    const resp = await fetch("/api/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    if (!resp.ok) return false;
    const data = await resp.json();
    sessionId = data.session_id;
    if (data.crisis_hotline) {
      document.getElementById("hotline-header").textContent = data.crisis_hotline;
    }
    chatStatus.textContent = "会话已建立（匿名，无任何身份信息收集）。";
    return true;
  }

  async function sendMessage() {
    const content = chatInput.value.trim();
    if (!content || sending) return;

    sending = true;
    sendBtn.disabled = true;
    const userBubble = addUserBubble(content);
    chatInput.value = "";

    try {
      if (!(await ensureSession())) {
        addSystemNote("会话创建失败，请确认服务已启动后重试。");
        return;
      }

      const resp = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, content: content }),
      });

      if (resp.status === 404) {
        addSystemNote("当前会话已结束。刷新页面可开始新的会话。");
        sessionId = null;
        return;
      }
      if (resp.status === 422) {
        addSystemNote("输入未通过校验（可能包含非法字符或超过长度限制）。");
        return;
      }
      if (!resp.ok) {
        addSystemNote("服务暂时不可用，请稍后重试。");
        return;
      }

      const data = await resp.json();

      if (typeof data.user_message === "string") {
        userBubble.textContent = data.user_message;
      }

      addBotBubble(data);
      chatStatus.textContent =
        "会话状态：" + data.session_state + " · 用户画像：" + data.persona;
    } catch (err) {
      addSystemNote("网络异常，请检查服务是否已启动（uvicorn app.main:app）。");
    } finally {
      sending = false;
      sendBtn.disabled = false;
      chatInput.focus();
    }
  }

  let chatBox, chatInput, sendBtn, chatStatus;

  function init() {
    chatBox = document.getElementById("chat-box");
    chatInput = document.getElementById("chat-input");
    sendBtn = document.getElementById("chat-send");
    chatStatus = document.getElementById("chat-status");

    sendBtn.addEventListener("click", sendMessage);
    chatInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") sendMessage();
    });
  }

  return { init };
})();
