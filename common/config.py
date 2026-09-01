"""远端数据库连接配置: 从环境变量 / 项目根目录 .env 读取。"""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


def load_dotenv(path: Path | None = None) -> None:
    """极简 .env 加载器, 不依赖第三方库。已存在的环境变量优先。"""
    path = path or ENV_FILE
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def get_database_config(overrides: dict | None = None) -> dict:
    """合并 .env / 环境变量 与请求覆盖项, 返回连接配置字典。"""
    load_dotenv()

    config = {
        "db_type": os.environ.get("DB_TYPE", "postgresql").strip().lower(),
        "host": os.environ.get("DB_HOST", "192.168.3.100").strip(),
        "port": int(os.environ.get("DB_PORT", "3306")),
        "user": os.environ.get("DB_USER", "root").strip(),
        "password": os.environ.get("DB_PASSWORD", ""),
        "database": os.environ.get("DB_NAME", "postgres").strip(),
        "schema": (os.environ.get("DB_SCHEMA", "").strip() or None),
    }

    for key, value in (overrides or {}).items():
        if key not in config:
            continue
        if value in (None, ""):
            continue
        config[key] = int(value) if key == "port" else str(value).strip()

    if config["db_type"] not in ("postgresql", "mysql"):
        raise ValueError(
            f"不支持的数据库类型: {config['db_type']}, 仅支持 postgresql / mysql"
        )
    return config


def _merge_overrides(config: dict, overrides: dict | None) -> dict:
    """把请求覆盖项合并进配置字典(只接受已有 key)。"""
    for key, value in (overrides or {}).items():
        if key not in config:
            continue
        if value in (None, ""):
            continue
        config[key] = int(value) if key == "port" else str(value).strip()
    return config


def _merge_mapped_overrides(config: dict, overrides: dict | None, key_map: dict) -> dict:
    """按 key_map(请求字段 -> 配置字段) 合并覆盖项。"""
    for request_key, config_key in key_map.items():
        value = (overrides or {}).get(request_key)
        if value in (None, ""):
            continue
        config[config_key] = int(value) if config_key == "port" else str(value).strip()
    return config


DORIS_OVERRIDE_MAP = {
    "doris_host": "host",
    "doris_port": "port",
    "doris_user": "user",
    "doris_password": "password",
    "doris_database": "database",
}

DATAX_OVERRIDE_MAP = {
    "datax_home": "home",
    "datax_python": "python",
}


def get_doris_config(overrides: dict | None = None) -> dict:
    """Doris FE 连接配置(走 MySQL 协议, 默认端口 9030)。"""
    load_dotenv()
    config = {
        "host": os.environ.get("DORIS_HOST", os.environ.get("DB_HOST", "192.168.3.100")).strip(),
        "port": int(os.environ.get("DORIS_PORT", "9030")),
        "user": os.environ.get("DORIS_USER", "root").strip(),
        "password": os.environ.get("DORIS_PASSWORD", ""),
        "database": os.environ.get("DORIS_DATABASE", "").strip(),
    }
    return _merge_mapped_overrides(config, overrides, DORIS_OVERRIDE_MAP)


def get_datax_config(overrides: dict | None = None) -> dict:
    """DataX 安装路径配置。"""
    load_dotenv()
    config = {
        "home": os.environ.get("DATAX_HOME", "").strip(),
        "python": os.environ.get("DATAX_PYTHON", "python3").strip(),
    }
    return _merge_mapped_overrides(config, overrides, DATAX_OVERRIDE_MAP)
