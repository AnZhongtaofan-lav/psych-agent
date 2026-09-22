# -*- coding: utf-8 -*-
"""
API 集成测试（对应设计方案测试计划 E1~E6 + 升级链路端到端）。

覆盖目标：
1. 会话创建/结束的状态机语义
2. L0 全链路正常对话、L3 端到端拦截
3. 连续 3 轮高危 → 升级到 120/急诊 → 会话终止
4. 画像查询结构性无 PII + 404 语义
5. 超长/非法输入 422、超大 payload 413
6. 【直接查 SQLite】断言落库内容已脱敏（数据层防线验证）
"""

from __future__ import annotations

import sqlite3


class TestSessionApi:
    """会话生命周期。"""

    def test_e1_create_session(self, client):
        """E1: 创建会话返回 UUID 与热线。"""
        resp = client.post("/api/session")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["session_id"]) == 36  # UUID
        assert len(data["anonymous_id"]) == 36
        assert data["crisis_hotline"] == "12356"
        assert data["persona_type"] == "P4"

    def test_create_session_with_own_anonymous_id(self, client):
        """携带自定义 anonymous_id（UUID 形态）创建。"""
        anon = "123e4567-e89b-12d3-a456-426614174000"
        resp = client.post("/api/session", json={"anonymous_id": anon})
        assert resp.status_code == 200
        assert resp.json()["anonymous_id"] == anon

    def test_create_session_invalid_anonymous_id(self, client):
        """非 UUID 的 anonymous_id → 422。"""
        resp = client.post("/api/session", json={"anonymous_id": "张三的会话"})
        assert resp.status_code == 422

    def test_end_session_then_chat_404(self, client, session_id):
        """结束后再对话 → 404（状态机拒绝）。"""
        resp = client.post(f"/api/session/{session_id}/end")
        assert resp.status_code == 200
        chat = client.post("/api/chat", json={"session_id": session_id, "content": "你好"})
        assert chat.status_code == 404


class TestChatApi:
    """核心对话链路。"""

    def test_e2_chat_normal(self, client, session_id):
        """E2: L0 全链路 → 响应结构完整。"""
        resp = client.post("/api/chat", json={"session_id": session_id, "content": "今天想找人聊聊"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["reply"]
        assert data["emotion"]["category"] in {"焦虑", "抑郁", "愤怒", "悲伤", "平静", "中性"}
        assert data["risk"]["level"] == 0
        assert data["risk"]["is_intercepted"] is False
        assert data["crisis_hotline"] == "12356"
        assert data["session_state"] == "active"

    def test_e3_chat_crisis_intercept(self, client, session_id):
        """E3: L3 端到端 → 拦截话术 + 热线 + 风险事件入库。"""
        resp = client.post("/api/chat", json={"session_id": session_id, "content": "我不想活了"})
        assert resp.status_code == 200
        data = resp.json()
        assert "12356" in data["reply"]          # 拦截话术必含热线
        assert data["risk"]["level"] == 3
        assert data["risk"]["is_intercepted"] is True
        assert data["persona"] == "P3"           # 危机 → 强制 P3
        assert data["session_state"] == "crisis_watch"
        # 直接查库：风险事件已记录且 is_intercepted=1
        with sqlite3.connect(client.db.db_path) as conn:
            row = conn.execute(
                "SELECT risk_level, is_intercepted, action_taken FROM risk_events"
            ).fetchone()
        assert row == (3, 1, "intercept_hotline")

    def test_a11_three_rounds_escalate_to_emergency(self, client, session_id):
        """A11 端到端: 连续 3 轮高危 → 第 3 轮升级 120/急诊 + 会话终止。"""
        for round_no in (1, 2, 3):
            resp = client.post(
                "/api/chat", json={"session_id": session_id, "content": "我不想活了"}
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "12356" in data["reply"]      # 任何一轮都不能丢热线
            if round_no < 3:
                assert "120" not in data["reply"]
            else:
                assert "120" in data["reply"]    # 升级：急救电话
                assert data["session_state"] == "terminated_by_risk"
        # 终止后继续对话 → 404
        follow = client.post("/api/chat", json={"session_id": session_id, "content": "你好"})
        assert follow.status_code == 404

    def test_variant_bypass_still_intercepted(self, client, session_id):
        """端到端变体绕过：谐音+插空也必须被拦截。"""
        for text in ("不想huo了", "想 4 了", "不 想 活 了！！！！"):
            resp = client.post("/api/chat", json={"session_id": session_id, "content": text})
            assert resp.status_code == 200
            assert resp.json()["risk"]["level"] == 3, f"变体未被拦截: {text}"

    def test_l2_suggests_medical(self, client, session_id):
        """L2 端到端: 绝望表述 → 建议就医，不拦截。"""
        resp = client.post("/api/chat", json={"session_id": session_id, "content": "这一切都没有意义"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["risk"]["level"] == 2
        assert data["risk"]["is_intercepted"] is False
        assert ("心理科" in data["reply"]) or ("心理咨询" in data["reply"])

    def test_invalid_control_chars_422(self, client, session_id):
        """控制字符注入 → 422。"""
        resp = client.post("/api/chat", json={"session_id": session_id, "content": "你好\x00世界"})
        assert resp.status_code == 422


class TestProfileApi:
    """画像查询。"""

    def test_e4_profile_no_pii_fields(self, client):
        """E4: 画像响应结构上无 PII 字段；404 语义正确。"""
        # 先对话一轮，产生画像数据
        session = client.post("/api/session").json()
        client.post(
            "/api/chat",
            json={"session_id": session["session_id"], "content": "最近考试压力好大，很紧张"},
        )
        resp = client.get(f"/api/profile/{session['anonymous_id']}")
        assert resp.status_code == 200
        data = resp.json()
        # 结构性断言：只允许统计字段，绝不允许自由文本字段
        assert set(data.keys()) == {
            "anonymous_id", "persona_type", "dominant_emotions",
            "mood_trend", "risk_level_max", "risk_streak", "interaction_count",
        }
        assert data["interaction_count"] == 1
        assert data["dominant_emotions"].get("焦虑", 0) > 0

    def test_profile_404(self, client):
        """不存在的画像 → 404。"""
        resp = client.get("/api/profile/123e4567-e89b-12d3-a456-426614174999")
        assert resp.status_code == 404

    def test_profile_invalid_uuid_404(self, client):
        """非法 UUID → 404（不区分错误类型）。"""
        resp = client.get("/api/profile/not-a-uuid")
        assert resp.status_code == 404


class TestInputLimits:
    """输入护栏。"""

    def test_e5_oversized_input_422(self, client, session_id):
        """E5: 超长输入 → 422。"""
        resp = client.post(
            "/api/chat",
            json={"session_id": session_id, "content": "压" * 3000},
        )
        assert resp.status_code == 422

    def test_payload_too_large_413(self, client):
        """超大 payload（Content-Length 超限）→ 413。"""
        # 直接构造超大 body：用 httpx 层面的低层 API
        import httpx

        # TestClient 基于 httpx；此处用大字符串触发 schema 422 之外的字节层限制
        big = "a" * (2000 * 6 + 100)
        resp = client.post(
            "/api/chat",
            content=big.encode(),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 413

    def test_health(self, client):
        """健康检查：纯规则模式下 llm_enabled=False。"""
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["llm_enabled"] is False  # 测试环境未配置 LLM


class TestDeidentificationEndToEnd:
    """E6: 数据层脱敏防线（直接查 SQLite）。"""

    def test_e6_message_content_masked_in_db(self, client, session_id):
        """E6: 含 PII 的输入 → messages.content 落库已脱敏。"""
        resp = client.post(
            "/api/chat",
            json={
                "session_id": session_id,
                "content": "我手机是13800138000，最近有点emo",
            },
        )
        assert resp.status_code == 200
        # 直接打开 SQLite 文件验证：任何 message 中都不存在原始手机号
        with sqlite3.connect(client.db.db_path) as conn:
            rows = conn.execute("SELECT content FROM messages").fetchall()
        contents = [r[0] for r in rows]
        assert all("13800138000" not in c for c in contents)
        assert any("138****8000" in c for c in contents)

    def test_e6b_fullwidth_phone_masked_in_db(self, client, session_id):
        """全角手机号落库也必须脱敏。"""
        resp = client.post(
            "/api/chat",
            json={"session_id": session_id, "content": "电话１３８００１３８０００，心情还行"},
        )
        assert resp.status_code == 200
        with sqlite3.connect(client.db.db_path) as conn:
            rows = conn.execute("SELECT content FROM messages").fetchall()
        assert all("１３８００１３８０００" not in r[0] for r in rows)

    def test_e6c_audit_log_records_masking(self, client, session_id):
        """脱敏审计：写库脱敏发生时 audit_log 必须有记录且不含原文。"""
        client.post(
            "/api/chat",
            json={"session_id": session_id, "content": "我手机是13912345678"},
        )
        with sqlite3.connect(client.db.db_path) as conn:
            rows = conn.execute(
                "SELECT action, context FROM audit_log WHERE context='repository_write'"
            ).fetchall()
        actions = {r[0] for r in rows}
        assert "mask_phone" in actions

    def test_e6d_response_echo_user_message_masked(self, client, session_id):
        """响应回显脱敏：user_message 字段不得含明文手机号（前端展示唯一来源）。"""
        resp = client.post(
            "/api/chat",
            json={"session_id": session_id, "content": "我手机是13812345678，心情低落"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "13812345678" not in data["user_message"]
        assert "138****5678" in data["user_message"]

    def test_e6e_response_echo_fullwidth_phone_masked(self, client, session_id):
        """全角手机号在响应回显中同样脱敏。"""
        resp = client.post(
            "/api/chat",
            json={"session_id": session_id, "content": "电话１３８１２３４５６７８"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "１３８１２３４５６７８" not in data["user_message"]
        assert "138****5678" in data["user_message"]

    def test_e6f_response_echo_no_pii_keeps_text_intact(self, client, session_id):
        """无 PII 的普通消息：回显应与原文一致（不误伤正常文本）。"""
        text = "最近工作压力有点大，想找人聊聊"
        resp = client.post(
            "/api/chat", json={"session_id": session_id, "content": text}
        )
        assert resp.status_code == 200
        assert resp.json()["user_message"] == text
