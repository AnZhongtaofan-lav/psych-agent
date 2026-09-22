/* ============================================================
  摄像头模块
  - getUserMedia 预览
  - canvas.toBlob 拍照上传
  - MediaRecorder 录像上传（MIME 自动检测）
  - 切换标签页时 stopCamera() 释放设备
  ============================================================ */
window.Camera = (() => {
  let videoEl = null;           // <video> 预览元素
  let placeholderEl = null;     // 初始占位提示
  let previewEl = null;         // 预览容器
  let stream = null;            // MediaStream
  let mediaRecorder = null;     // MediaRecorder
  let recordChunks = [];        // 录像 chunks
  let btnPhoto, btnStartRec, btnStopRec, btnGalleryGo;
  let recIndicator, cameraMsg;
  let canvas = null;            // 拍照用隐藏 canvas

  /* ---------- MIME 检测 ---------- */
  function pickVideoMime() {
    // MediaRecorder 浏览器支持不同：Chrome video/webm，Safari video/mp4
    const candidates = ["video/webm", "video/mp4"];
    for (const mt of candidates) {
      if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(mt)) {
        return mt;
      }
    }
    return "video/webm";  // 兜底
  }

  /* ---------- 启动摄像头 ---------- */
  async function startCamera() {
    if (stream) return;  // 已在运行

    cameraMsg.textContent = "正在请求摄像头权限...";
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });

      // 创建 <video> 元素替换占位符
      placeholderEl.style.display = "none";
      videoEl = document.createElement("video");
      videoEl.autoplay = true;
      videoEl.muted = true;   // 不需要麦克风
      videoEl.playsInline = true;
      videoEl.srcObject = stream;
      previewEl.appendChild(videoEl);

      btnPhoto.disabled = false;
      btnStartRec.disabled = false;
      cameraMsg.textContent = "摄像头已就绪 · 点击拍照或开始录像";
    } catch (err) {
      cameraMsg.textContent = "摄像头启动失败：" + (err.name || err.message || "未知错误")
        + "（请检查浏览器权限或设备是否被占用）";
      cameraMsg.style.color = "#e74c3c";
    }
  }

  /* ---------- 停止摄像头（离开标签页时调用） ---------- */
  function stopCamera() {
    // 先停止录像（如果在录）
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
    }
    mediaRecorder = null;
    recordChunks = [];

    if (stream) {
      stream.getTracks().forEach(t => t.stop());
      stream = null;
    }
    if (videoEl) {
      videoEl.srcObject = null;
      videoEl.remove();
      videoEl = null;
    }
    placeholderEl.style.display = "block";
    btnPhoto.disabled = true;
    btnStartRec.disabled = true;
    btnStopRec.classList.remove("recording");
    btnStartRec.classList.remove("recording");
    recIndicator.classList.remove("active");
    cameraMsg.textContent = "";
  }

  /* ---------- 拍照 ---------- */
  async function capturePhoto() {
    if (!videoEl || !stream) return;
    btnPhoto.disabled = true;
    cameraMsg.textContent = "正在拍照并上传...";

    // 创建隐藏 canvas 截取当前帧
    if (!canvas) canvas = document.createElement("canvas");
    canvas.width = videoEl.videoWidth;
    canvas.height = videoEl.videoHeight;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(videoEl, 0, 0, canvas.width, canvas.height);

    return new Promise((resolve, reject) => {
      canvas.toBlob(async (blob) => {
        if (!blob) {
          cameraMsg.textContent = "拍照失败：无法生成图像数据";
          btnPhoto.disabled = false;
          return reject(new Error("toBlob 失败"));
        }
        try {
          await uploadBlob(blob, "photo", "photo.jpg");
          cameraMsg.textContent = "照片已保存 ✓";
        } catch (e) {
          cameraMsg.textContent = "照片上传失败：" + e.message;
        } finally {
          btnPhoto.disabled = false;
          resolve();
        }
      }, "image/jpeg", 0.9);  // JPEG 90% 质量
    });
  }

  /* ---------- 录像 ---------- */
  function startRecording() {
    if (!stream) return;
    const mime = pickVideoMime();

    recordChunks = [];
    mediaRecorder = new MediaRecorder(stream, { mimeType: mime });

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) recordChunks.push(e.data);
    };

    mediaRecorder.onstop = async () => {
      const blob = new Blob(recordChunks, { type: mime });
      recordChunks = [];
      try {
        const ext = mime.includes("webm") ? "webm" : "mp4";
        await uploadBlob(blob, "video", `video.${ext}`);
        cameraMsg.textContent = "录像已保存 ✓ (" + (blob.size / 1024 / 1024).toFixed(1) + " MB)";
      } catch (e) {
        cameraMsg.textContent = "录像上传失败：" + e.message;
      }
      mediaRecorder = null;
    };

    mediaRecorder.start();
    btnStartRec.classList.add("recording");
    btnStopRec.classList.add("recording");
    recIndicator.classList.add("active");
    btnPhoto.disabled = true;
    cameraMsg.textContent = "录像中... 点击停止结束录制";
  }

  function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
    }
    btnStartRec.classList.remove("recording");
    btnStopRec.classList.remove("recording");
    recIndicator.classList.remove("active");
    btnPhoto.disabled = false;
  }

  /* ---------- 通用上传 ---------- */
  async function uploadBlob(blob, mediaType, filename) {
    const fd = new FormData();
    fd.append("media_type", mediaType);
    fd.append("file", blob, filename);

    const resp = await fetch("/api/media/upload", { method: "POST", body: fd });
    if (!resp.ok) {
      let detail = resp.statusText;
      try { detail = (await resp.json()).detail || detail; } catch (_) {}
      throw new Error(detail + " (HTTP " + resp.status + ")");
    }
    return await resp.json();
  }

  /* ---------- 导航到相册页 ---------- */
  function goGallery() {
    document.querySelector('.tab[data-tab="gallery"]').click();
  }

  /* ---------- 对外 API ---------- */
  function init() {
    previewEl = document.getElementById("camera-preview");
    placeholderEl = previewEl.querySelector(".camera-placeholder");
    btnPhoto = document.getElementById("btn-photo");
    btnStartRec = document.getElementById("btn-start-rec");
    btnStopRec = document.getElementById("btn-stop-rec");
    btnGalleryGo = document.getElementById("btn-gallery-go");
    recIndicator = document.getElementById("rec-indicator");
    cameraMsg = document.getElementById("camera-msg");

    btnPhoto.addEventListener("click", capturePhoto);
    btnStartRec.addEventListener("click", startRecording);
    btnStopRec.addEventListener("click", stopRecording);
    btnGalleryGo.addEventListener("click", goGallery);
  }

  return { init, startCamera, stopCamera };
})();
