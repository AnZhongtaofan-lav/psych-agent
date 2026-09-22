# -*- coding: utf-8 -*-
"""
全局配置加载模块。

设计要点：
1. 所有可变配置集中于此，业务代码禁止散落读取环境变量（便于测试与审计）
2. LLM 相关配置为"可插拔增强"：未配置 API Key 时系统必须以纯规则模式完整可用
3. 危机热线号码支持环境变量覆盖，便于多地区部署
4. 安全红线：真实密钥只允许存在于环境变量/.env，禁止硬编码进代码
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# ------------------------------------------------------------
# 尝试加载 .env 文件（不引入第三方依赖，用极简解析器实现）
# 这样部署者只需复制 .env.example 为 .env 即可，无需额外安装 dotenv
# ------------------------------------------------------------
def _load_dotenv(path: Path) -> dict[str, str]:
    """极简 .env 解析器：仅支持 KEY=VALUE 格式，# 开头为注释。

    注意：解析结果只写入 os.environ 中尚未设置的键，
    即"环境变量优先于 .env 文件"，符合 12-Factor 规范。
    """
    loaded: dict[str, str] = {}
    if not path.is_file():
        return loaded
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        # 跳过空行与注释行
        if not line or line.startswith("#"):
            continue
        # 只处理包含等号且等号前是合法变量名的行
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        # 去除可选的引号包裹
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        # 环境变量优先：已存在则不覆盖
        if key and key not in os.environ:
            os.environ[key] = value
        loaded[key] = value
    return loaded


# 项目根目录：app/common/config.py 向上两级
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 加载项目根目录下的 .env（存在才生效）
_load_dotenv(PROJECT_ROOT / ".env")


def _get_env_bool(key: str, default: bool) -> bool:
    """读取布尔型环境变量（"1"/"true"/"yes" 视为真，不区分大小写）。"""
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    """全局只读配置对象（frozen 防止运行期被意外篡改）。"""

    # ---------- 数据层配置 ----------
    # SQLite 数据库文件路径；测试时会通过环境变量 DB_PATH 覆盖为临时文件
    db_path: str = field(
        default_factory=lambda: os.getenv("DB_PATH", str(PROJECT_ROOT / "data" / "psych.db"))
    )

    # ---------- LLM 配置（可插拔增强，缺失即降级纯规则） ----------
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", "").strip())
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", "").strip())
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "gpt-4o-mini").strip())
    # LLM 读取超时秒数：超时后静默降级为规则结果，不向用户暴露内部错误
    llm_timeout_seconds: float = field(default_factory=lambda: float(os.getenv("LLM_TIMEOUT_SECONDS", "15")))

    # ---------- 危机干预热线（安全关键配置，必须始终有默认值） ----------
    # 全国统一心理援助热线
    crisis_hotline_primary: str = field(default_factory=lambda: os.getenv("CRISIS_HOTLINE_PRIMARY", "12356"))
    # 备用热线
    crisis_hotline_secondary: str = field(
        default_factory=lambda: os.getenv("CRISIS_HOTLINE_SECONDARY", "010-82951332")
    )
    # 紧急医疗电话（连续 L3 升级时提示）
    emergency_number: str = field(default_factory=lambda: os.getenv("EMERGENCY_NUMBER", "120"))

    # ---------- 媒体存储（摄像头照片/录像） ----------
    # 媒体根目录（相对项目根，存放 photos/ 与 videos/ 两个子目录）
    media_dir: str = field(
        default_factory=lambda: os.getenv(
            "MEDIA_DIR", str(PROJECT_ROOT / "data" / "media")
        )
    )
    # 单张照片上限（字节）：默认 5 MB
    max_photo_bytes: int = field(
        default_factory=lambda: int(os.getenv("MAX_PHOTO_BYTES", "5242880"))
    )
    # 单个视频上限（字节）：默认 50 MB
    max_video_bytes: int = field(
        default_factory=lambda: int(os.getenv("MAX_VIDEO_BYTES", "52428800"))
    )

    # ---------- 交互层护栏 ----------
    # 单条用户输入最大长度：超出直接 422，防止超长文本攻击与成本失控
    max_input_length: int = field(default_factory=lambda: int(os.getenv("MAX_INPUT_LENGTH", "2000")))

    # ---------- 日志 ----------
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper())

    @property
    def llm_enabled(self) -> bool:
        """LLM 是否可用：必须同时配置 base_url 与 api_key。

        安全语义：此开关只影响"细粒度情绪增强"，绝不能影响高危拦截——
        高危拦截由规则引擎保证，无论 LLM 是否可用都必须生效。
        """
        return bool(self.llm_base_url and self.llm_api_key)


# 模块级单例：全局共享的配置对象
settings = Settings()
