# AI 心理服务智能体（Psych Agent）

基于**三层架构**（交互层 / 逻辑层 / 数据层）的 AI 心理服务智能体，提供情绪识别、四级风险分级与高危拦截、全链路 PII 脱敏能力。系统在**未配置任何 LLM 时以纯规则模式完整可用**，配置 LLM 后自动启用细粒度增强——高危拦截始终由规则引擎保证，不依赖任何外部服务。

> **安全合规声明**：本系统为心理支持辅助工具，不能替代专业心理咨询与医疗诊断。危机场景下系统会立即中断普通对话流程，转介人工热线（12356）与医疗资源（120）。

---

## 核心功能

### 1. 情绪识别

- **六分类**：焦虑 / 抑郁 / 愤怒 / 悲伤 / 平静 / 中性，输出强度（0~1）与置信度（0~1）
- **规则 + LLM 双通道**：词典与程度副词规则兜底，LLM 提供细粒度判断，按置信度竞争融合
- **优雅降级**：LLM 超时 / 异常 / 输出畸形时静默回退纯规则，服务不中断

### 2. 风险分级与高危拦截

四级风险模型（**误报优于漏报**）：

| 等级 | 标签 | 典型信号 | 系统动作 |
|---|---|---|---|
| L0 | 正常 | 日常倾诉 | 模板/LLM 共情回复 |
| L1 | 关注 | "最近很累""睡不好" | 引导式关怀话术 |
| L2 | 高风险 | "一切都没有意义" | 建议就医/心理咨询 |
| L3 | 危机 | "想死""不想活" | **立即拦截**，转介热线 |

**防绕过归一化**：谐音（`huo`/`4`）、汉字插空（`想 4 了`）、全角字符、大小写混排等变体在匹配前统一归一化，全部可被 L3 拦截。

**max 融合原则**：最终风险 = `max(规则判定, LLM 判定)`——LLM 只能升危、不能降危，规则引擎是唯一权威兜底。

**分级升级链**（连续 L3 轮数 streak）：

```
streak=1  → 标准危机话术 + 12356 热线（3 版随机模板，防机械感）
streak=2  → 追加"身边是否有人陪伴"确认 + 备用热线
streak≥3  → 建议拨打 120/110 或前往急诊，会话置 terminated_by_risk
```

### 3. 隐私脱敏（双道防线）

```
用户输入 ──→ 【入口中间件】──→ 风险/情绪分析(用原文) ──→ 【仓储层写入强制脱敏】──→ SQLite
                      │                                              │
                      └────────── 回显 user_message 同源脱敏 ──────────┘
```

- **三处防线共用同一 anonymizer 模块**（单一权威实现）：日志、数据库、前端回显
- 风险/情绪分析使用原文执行（保证判级准确），脱敏仅作用于**存储与展示**
- 掩码规范：

| 类型 | 原文 | 掩码 |
|---|---|---|
| 手机号 | 13812345678 | `138****5678` |
| 身份证 | 110101199001011234 | `110***********1234` |
| 银行卡 | 6222020200112233 | `6222**********2233` |
| 邮箱 | zhangwei@qq.com | `z******@qq.com` |
| 姓名 | 我叫张伟 | `我叫张**` |
| 住址 | 北京市海淀区xx路 | `北京市***` |

- 全角数字（１３８...）、分隔符号码（138-0013-8000）等变体先归一化再匹配
- 每次脱敏动作写入 `audit_log`（只记动作类型，绝不含原文）

### 4. 用户画像

四类画像自动推断并动态迁移：`P1 学生` / `P2 职场` / `P3 危机看护`（L2+ 或历史危机强制优先）/ `P4 通用`。画像决定对话策略——如 P3 用户走纯模板陪伴模式（禁用 LLM，保证确定性）。

---

## 技术栈

| 层 | 技术 | 说明 |
|---|---|---|
| 交互层 | FastAPI + Pydantic v2 | 路由、schema 校验、输入护栏（长度/控制字符/payload 体积） |
| 逻辑层 | 纯 Python 规则引擎 + httpx | 风险/情绪规则、归一化、拦截器、画像、对话策略 |
| LLM（可插拔） | OpenAI 兼容接口 | 未配置则全链路纯规则，配置后自动增强 |
| 数据层 | SQLite（WAL 模式） | 读写并发友好、崩溃自恢复；外键显式开启 |
| 前端 | 原生 HTML/CSS/JS 单文件 | 零构建依赖；textContent 防 XSS；无本地存储 |
| 测试 | pytest + pytest-html | 120 个用例，含 API 集成与落库脱敏断言 |

---

## 快速启动

### 环境要求

- Python **3.11+**

### 1. 安装依赖

```bash
pip install -e ".[dev]"
```

### 2. 配置（可选）

```bash
# 复制环境变量样例；不配置 LLM 则以纯规则模式运行（功能完整）
cp .env.example .env
```

关键环境变量（均有安全默认值，见 `.env.example`）：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `LLM_BASE_URL` / `LLM_API_KEY` | 空 | 不配置 = 纯规则模式 |
| `CRISIS_HOTLINE_PRIMARY` | `12356` | 主热线（可按地区覆盖） |
| `CRISIS_HOTLINE_SECONDARY` | `010-82951332` | 备用热线 |
| `EMERGENCY_NUMBER` | `120` | 紧急医疗电话 |
| `DB_PATH` | `./data/psych.db` | SQLite 路径 |
| `MAX_INPUT_LENGTH` | `2000` | 单条输入上限 |

> **安全红线**：真实密钥只允许存在于环境变量 / `.env`，严禁提交代码库。

### 3. 启动服务

```bash
# 方式一：uvicorn
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 方式二：pip install -e . 后使用脚本
psych-server
```

### 4. 访问

| 入口 | 地址 |
|---|---|
| 对话前端（输入框 + 发送按钮，实时展示情绪/风险标签） | http://127.0.0.1:8000/ |
| API 文档（Swagger UI） | http://127.0.0.1:8000/docs |
| 健康检查 | http://127.0.0.1:8000/api/health |

---

## API 一览

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/session` | 创建匿名会话（服务端生成 UUID，不收集任何身份信息） |
| POST | `/api/chat` | 核心对话：返回回复、脱敏回显 `user_message`、情绪标签、风险等级、画像 |
| POST | `/api/session/{id}/end` | 结束会话 |
| GET | `/api/profile/{anonymous_id}` | 查询画像聚合（结构性无 PII 字段） |
| GET | `/api/health` | 探活 + LLM 配置状态 |

`/api/chat` 响应示例：

```json
{
  "reply": "我在听。你说的事情里，哪一部分最让你在意？",
  "user_message": "我手机是138****5678，心情低落",
  "emotion": { "category": "悲伤", "intensity": 0.7, "confidence": 0.9, "source": "rule" },
  "risk": { "level": 0, "label": "正常", "is_intercepted": false, "matched_lexicons": [] },
  "persona": "P4",
  "crisis_hotline": "12356",
  "session_state": "active"
}
```

---

## 测试

### 运行全量测试（120 个用例）

```bash
python -m pytest tests/ -v
```

| 测试文件 | 用例数 | 覆盖内容 |
|---|---|---|
| test_anonymizer.py | 20 | PII 脱敏（各类型 + 全角/分隔符变体） |
| test_risk_engine.py | 15 | 四级分级、max 融合、LLM 不可降级 |
| test_llm_client.py | 15 | 超时/异常/畸形输出降级、JSON 提取 |
| test_api.py | 22 | 会话状态机、L3 拦截、升级链、脱敏落库与回显 |
| test_emotion_engine.py | 11 | 六分类、置信度融合、降级 |
| test_profile_builder.py | 11 | 画像推断、EMA 聚合、streak 语义 |
| test_database.py | 9 | drop_all/reset/safe_remove 清理机制 |
| test_interceptors.py | 9 | 三级升级、LLM 输出安检 |
| test_dialogue_strategy.py | 8 | 策略调度、P3 陪伴模式 |

### 测试报告（HTML）

最新一轮全量测试的自包含 HTML 报告（可直接浏览器打开）：

**[reports/test-report.html](reports/test-report.html)**

> 报告由 pytest-html 生成，内联全部样式与结果数据，单文件可离线查看、直接归档或随邮件分享。若仓库内未包含，可用下方命令重新生成。

重新生成报告：

```bash
pip install pytest-html
python -m pytest tests/ --html=reports/test-report.html --self-contained-html -q
```

---

## 目录结构

```
psych/
├── app/
│   ├── main.py                 # 应用装配点（依赖注入 + 路由 + 中间件）
│   ├── api/                    # 交互层：路由 / schema / 中间件 / 依赖注入
│   │   ├── routes/             #   chat / session / profile
│   │   ├── schemas/            #   Pydantic 请求/响应模型（边界校验）
│   │   └── middleware/         #   输入护栏 + 无 PII 访问日志
│   ├── core/                   # 逻辑层：核心业务（零框架依赖，可独立测试）
│   │   ├── normalizer.py       #   防绕过归一化（谐音/插空/全角）
│   │   ├── risk/               #   风险规则引擎 + 危机拦截器
│   │   ├── emotion/            #   情绪词典规则引擎
│   │   ├── profile/            #   画像推断与聚合
│   │   ├── dialogue/           #   对话策略 + 回复生成
│   │   └── llm/                #   LLM 客户端（可插拔 + 降级）
│   ├── storage/                # 数据层：SQLite + 仓储 + 审计
│   │   ├── anonymizer.py       #   PII 脱敏器（单一权威实现）
│   │   ├── database.py         #   连接管理 + 建表 + drop_all/reset
│   │   ├── repositories.py     #   仓储（写入强制脱敏）
│   │   └── audit.py            #   脱敏动作审计
│   ├── resources/              # 风险/情绪词典 JSON
│   ├── static/index.html       # 前端单页（零依赖）
│   └── common/                 # 配置 / 常量 / 日志 / 异常
├── tests/                      # 120 个测试用例
├── reports/test-report.html    # 测试报告（HTML）
├── data/                       # SQLite 数据文件
└── .env.example                # 环境变量样例
```

---

## 安全设计红线

1. **高危拦截不依赖 LLM**——规则引擎兜底，LLM 故障不影响危机识别
2. **PII 默认脱敏**——日志 / 数据库 / 前端回显三处共用同一 anonymizer；疑似即脱敏（宁可误脱敏，不可漏脱敏）
3. **误报优于漏报**——拦截话术对非危机用户只是"多一句关怀"
4. **最小化暴露**——404 不区分"不存在"与"已终止"；异常响应不回显内部细节；访问日志不记请求体
5. **LLM 输出安检**——LLM 生成内容须再过一遍 L3 规则，命中即丢弃回退模板

---

## 免责声明

本系统用于心理支持场景的技术探索与辅助服务，输出内容不构成医学诊断或治疗建议。如有心理健康困扰，请联系专业机构：

- 全国心理援助热线：**12356**（24 小时）
- 紧急医疗：**120**
