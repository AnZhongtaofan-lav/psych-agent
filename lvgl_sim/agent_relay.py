# -*- coding: utf-8 -*-
"""
agent_relay.py -- GEC6818 板子智能体的笔记本中转脚本
================================================================
作用:
  板子(触摸输入问题) --串口COMx--> 本脚本 --WiFi/互联网--> 硅基流动大模型
  回答再经串口发回板子, 显示在 LVGL CHAT 页。

准备 (只做一次):
  1. 安装依赖:
       pip install pyserial
  2. 申请免费 API Key (硅基流动, 手机号注册即送额度):
       https://siliconflow.cn  -> 控制台 -> API密钥 -> 新建密钥
  3. 把 Key 填到下面 API_KEY 里 (或设环境变量 SILICONFLOW_KEY)。
     也可以用 DeepSeek: 改 API_URL 和模型名即可。

使用:
  1. 先用 SecureCRT 在板子里启动 /tmp/gec6818_app
  2. 启动后可以直接关掉 SecureCRT (程序会继续在板子上跑)
  3. 在笔记本上运行:
       python agent_relay.py COM8
     (端口号以设备管理器里 USB-SERIAL 对应的 COM 号为准)
  4. 在板子屏幕上点输入框, 用屏幕键盘输入英文问题, 点 SEND,
     回答会在几秒内出现在屏幕上。
  5. Ctrl+C 退出本脚本。需要看板子日志时重新打开 SecureCRT 即可。

注意: 本脚本运行期间 SecureCRT 不要同时打开同一个 COM 口
      (一个串口同一时刻只能被一个程序占用)。
"""
import sys
import os
import json
import time
import urllib.request
import urllib.error

# ==================== 配置区 (按需修改) ====================
API_KEY = os.environ.get("SILICONFLOW_KEY" , "sk-bnmoeztvmhbevqlgaxrlyvktqwnwqjfdkrddumognryjssvw")

# 硅基流动 OpenAI 兼容接口
API_URL = "https://api.siliconflow.cn/v1/chat/completions"
MODEL = "Qwen/Qwen2.5-7B-Instruct"   # 免费模型; 也可换 Qwen/Qwen2.5-14B-Instruct

SERIAL_BAUD = 115200
# ===========================================================

# 系统提示词: 板子字体只含英文字库, 要求用简短英文回答
SYSTEM_PROMPT = (
    "You are a warm psychological support assistant named Psych AI. "
    "Reply in simple English only (the terminal has no Chinese font). "
    "Keep each reply under 60 words, kind and encouraging. "
    "Do not use markdown symbols like ** or #."
)

history = [{"role": "system", "content": SYSTEM_PROMPT}]


def call_model(question: str) -> str:
    """调硅基流动对话接口, 返回回答文本"""
    history.append({"role": "user", "content": question})
    payload = {
        "model": MODEL,
        "messages": history,
        "temperature": 0.7,
        "max_tokens": 300,
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + API_KEY,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            obj = json.loads(resp.read().decode("utf-8"))
        answer = obj["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        answer = "API error %d: %s" % (e.code, e.read().decode("utf-8", "ignore")[:120])
    except Exception as e:
        answer = "Network error: %s" % e
    history.append({"role": "assistant", "content": answer})
    # 协议要求一条回答必须是单个物理行, 去掉所有换行
    answer = answer.replace("\r", " ").replace("\n", " ")
    while "  " in answer:
        answer = answer.replace("  ", " ")
    return answer.strip()


def main():
    if len(sys.argv) < 2:
        print("Usage: python agent_relay.py COM8")
        sys.exit(1)
    port = sys.argv[1]

    if not API_KEY or API_KEY.startswith("在这里"):
        print("[ERROR] 请先在脚本顶部填好 API_KEY (或 set SILICONFLOW_KEY=xxx)")
        sys.exit(1)

    try:
        import serial
    except ImportError:
        print("[ERROR] 缺少 pyserial, 请先运行: pip install pyserial")
        sys.exit(1)

    ser = serial.Serial(port, SERIAL_BAUD, timeout=1)
    print("=" * 56)
    print(" Psych AI relay connected on %s @ %d" % (port, SERIAL_BAUD))
    print(" Model: %s" % MODEL)
    print(" Type on the board's touch screen. Ctrl+C to quit.")
    print("=" * 56)

    buf = b""
    while True:
        try:
            chunk = ser.read(256)
        except KeyboardInterrupt:
            break
        if not chunk:
            continue
        # 把板子所有日志原样打到电脑屏幕, 方便观察
        try:
            text = chunk.decode("utf-8", "replace")
            sys.stdout.write(text)
            sys.stdout.flush()
        except Exception:
            pass

        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.strip(b"\r")
            if line.startswith(b"@@Q"):
                question = line[3:].decode("utf-8", "replace").strip()
                if not question:
                    continue
                t0 = time.time()
                print("\n[Q] %s" % question)
                answer = call_model(question)
                print("[A] %s  (%.1fs)\n" % (answer, time.time() - t0))
                ser.write(b"@@A" + answer.encode("utf-8") + b"\n")

    ser.close()
    print("\nrelay stopped.")


if __name__ == "__main__":
    main()
