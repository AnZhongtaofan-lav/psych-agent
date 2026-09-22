/* ============================================================
  应用入口 —— 标签路由 + 模块初始化 + 生命周期
  ============================================================ */
(function main() {
  const tabs = document.querySelectorAll(".tab");
  const panels = {
    chat: document.getElementById("panel-chat"),
    camera: document.getElementById("panel-camera"),
    gallery: document.getElementById("panel-gallery"),
  };
  let currentTab = "chat";

  function switchTab(target) {
    if (target === currentTab) return;

    // 离开当前 tab 时清理资源
    if (currentTab === "camera") {
      window.Camera.stopCamera();  // 释放摄像头设备
    }
    currentTab = target;

    // UI 切换
    tabs.forEach(t => t.classList.toggle("active", t.dataset.tab === target));
    Object.entries(panels).forEach(([name, el]) => {
      el.classList.toggle("active", name === target);
    });

    // 进入新 tab 时初始化
    if (target === "camera") {
      window.Camera.startCamera();
    } else if (target === "gallery") {
      window.Gallery.load("photo");  // 默认显示照片
    }
  }

  // 标签点击绑定
  tabs.forEach(tab => {
    tab.addEventListener("click", () => switchTab(tab.dataset.tab));
  });

  // 切到后台页面时主动释放摄像头（浏览器 tab 被隐藏时）
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden" && currentTab === "camera") {
      window.Camera.stopCamera();
    }
  });

  // 初始化各模块
  window.Chat.init();
  window.Camera.init();
  window.Gallery.init();
})();
