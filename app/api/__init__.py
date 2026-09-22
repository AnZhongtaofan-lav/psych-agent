# -*- coding: utf-8 -*-
"""api 包初始化：交互层（第一层）。

组成：
- schemas/    pydantic 请求/响应模型（响应结构上不携带 PII）
- middleware/ 输入护栏（长度/控制字符）与访问日志（无正文记录）
- routes/     chat / session / profile 路由（全链路编排点）

依赖方向：交互层 → 逻辑层（core）→ 数据层（storage），禁止反向。
"""
