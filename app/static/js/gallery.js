/* ============================================================
  相册模块 —— 照片 / 录像 列表、预览、删除
  数据源：GET /api/media/list/{type} 与 GET /api/media/{type}/{filename}
  ============================================================ */
window.Gallery = (() => {
  let galleryList = null;
  let modal, modalContent, modalClose;
  let currentGtype = "photo";     // photo | video
  let galleryTabs = [];
  let currentObjectUrl = null;    // 用于 revokeObjectURL

  function revokeCurrentUrl() {
    if (currentObjectUrl) {
      URL.revokeObjectURL(currentObjectUrl);
      currentObjectUrl = null;
    }
  }

  /* ---------- 加载列表 ---------- */
  async function load(gtype) {
    currentGtype = gtype;
    galleryList.innerHTML = '<div class="gallery-empty">加载中...</div>';

    try {
      const resp = await fetch(`/api/media/list/${gtype}`);
      if (!resp.ok) {
        galleryList.innerHTML = `<div class="gallery-empty">加载失败 (HTTP ${resp.status})</div>`;
        return;
      }
      const items = await resp.json();
      render(items, gtype);
    } catch (e) {
      galleryList.innerHTML = '<div class="gallery-empty">加载失败：' + e.message + '</div>';
    }
  }

  function render(items, gtype) {
    if (!items || items.length === 0) {
      const emptyTip = gtype === "photo"
        ? "暂无照片，去摄像头页拍一张吧 📸"
        : "暂无录像，去摄像头页录一段吧 🎬";
      galleryList.innerHTML = `<div class="gallery-empty">${emptyTip}</div>`;
      return;
    }

    galleryList.innerHTML = "";
    items.forEach(item => {
      const div = document.createElement("div");
      div.className = "gallery-item";

      const url = `/api/media/${gtype}/${item.filename}`;

      if (gtype === "photo") {
        const img = document.createElement("img");
        img.src = url;
        img.alt = item.filename;
        img.loading = "lazy";
        div.appendChild(img);
      } else {
        const video = document.createElement("video");
        video.src = url;
        video.muted = true;
        video.preload = "metadata";
        div.appendChild(video);

        const tag = document.createElement("span");
        tag.className = "type-tag";
        tag.textContent = "录像";
        div.appendChild(tag);
      }

      // 删除按钮
      const del = document.createElement("button");
      del.className = "del-btn";
      del.textContent = "×";
      del.title = "删除";
      del.addEventListener("click", (e) => {
        e.stopPropagation();
        confirmDelete(gtype, item.filename);
      });
      div.appendChild(del);

      // 点击 → 全屏预览
      div.addEventListener("click", () => openPreview(url, gtype, item.mime));

      galleryList.appendChild(div);
    });
  }

  /* ---------- 全屏预览 ---------- */
  function openPreview(url, gtype, mime) {
    revokeCurrentUrl();
    modalContent.innerHTML = "";

    let el;
    if (gtype === "photo") {
      el = document.createElement("img");
      el.src = url;
    } else {
      el = document.createElement("video");
      el.src = url;
      el.controls = true;
      el.autoplay = true;
    }
    modalContent.appendChild(el);
    modal.classList.add("active");
  }

  function closePreview() {
    modal.classList.remove("active");
    modalContent.innerHTML = "";
    revokeCurrentUrl();
  }

  /* ---------- 删除 ---------- */
  async function confirmDelete(gtype, filename) {
    if (!confirm(`确认删除该${gtype === "photo" ? "照片" : "录像"}？此操作不可恢复。`)) return;
    try {
      const resp = await fetch(`/api/media/${gtype}/${filename}`, { method: "DELETE" });
      if (!resp.ok) throw new Error((await resp.json()).detail || "删除失败");
      await load(gtype);   // 刷新
    } catch (e) {
      alert("删除失败：" + e.message);
    }
  }

  /* ---------- 对外 API ---------- */
  function init() {
    galleryList = document.getElementById("gallery-list");
    modal = document.getElementById("preview-modal");
    modalContent = document.getElementById("preview-content");
    modalClose = document.getElementById("preview-close");

    modalClose.addEventListener("click", closePreview);
    modal.addEventListener("click", (e) => {
      if (e.target === modal) closePreview();
    });

    galleryTabs = document.querySelectorAll(".gallery-tab");
    galleryTabs.forEach(tab => {
      tab.addEventListener("click", () => {
        galleryTabs.forEach(t => t.classList.remove("active"));
        tab.classList.add("active");
        load(tab.dataset.gtype);
      });
    });
  }

  return { init, load };
})();
