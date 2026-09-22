# -*- coding: utf-8 -*-
"""
app 包初始化。

三层架构说明：
- 交互层（app.api）：FastAPI 路由、schema、输入护栏、日志脱敏中间件
- 逻辑层（app.core）：情绪识别、风险分级、高危拦截、用户画像、对话策略、LLM 客户端
- 数据层（app.storage）：SQLite 存储、PII 脱敏器、脱敏审计

依赖方向（单向，禁止反向依赖）：
    交互层 → 逻辑层 → 数据层
"""
