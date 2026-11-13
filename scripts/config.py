from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

ROOT_DIR = Path(__file__).resolve().parent.parent
API_DIR = ROOT_DIR / "api"
DEFAULT_NDWI_THRESHOLD = 0.0
APP_TITLE = "PondWatch AI"
APP_SUBTITLE = "AI-assisted satellite monitoring of ponds, reservoirs, and other water bodies."


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values = dotenv_values(path)
    if not values:
        return {}
    cleaned: dict[str, str] = {}
    for key, value in values.items():
        if key and value is not None:
            cleaned[key] = str(value).strip()
    return cleaned


def load_api_file(file_name: str) -> dict[str, str]:
    return _read_env_file(API_DIR / file_name)


def is_placeholder(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    return not text or text.upper() == "AAAA" or text.upper().startswith("PASTE_")


def _load_from_env(namespace: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for key in [
        f"{namespace}_API_KEY",
        f"{namespace}_BASE_URL",
        f"{namespace}_MODEL",
        "CDSE_CLIENT_ID",
        "CDSE_CLIENT_SECRET",
        "CDSE_TOKEN_URL",
        "SENTINEL_HUB_BASE_URL",
        "WIC_COLLECTION_ID",
    ]:
        value = os.getenv(key)
        if value is not None and str(value).strip():
            result[key] = str(value).strip()
    return result


def get_featherless_config() -> dict[str, str]:
    config = load_api_file("featherless.txt")
    if not config:
        config = load_api_file("featherless.example.txt")
    config.update(_load_from_env("FEATHERLESS"))
    config.update(_load_from_env("CDSE"))
    return {k: v for k, v in config.items() if v is not None}


def get_copernicus_config() -> dict[str, str]:
    config = load_api_file("copernicus.txt")
    if not config:
        config = load_api_file("copernicus.example.txt")
    config.update(_load_from_env("CDSE"))
    config.update(_load_from_env("SENTINEL"))
    return {k: v for k, v in config.items() if v is not None}


def has_real_featherless() -> bool:
    config = get_featherless_config()
    value = config.get("FEATHERLESS_API_KEY")
    return bool(value) and not is_placeholder(value)


def has_real_copernicus() -> bool:
    config = get_copernicus_config()
    client_id = config.get("CDSE_CLIENT_ID")
    client_secret = config.get("CDSE_CLIENT_SECRET")
    token_url = config.get("CDSE_TOKEN_URL")
    return bool(client_id and client_secret and token_url) and not any(
        is_placeholder(x) for x in [client_id, client_secret, token_url]
    )


def mask_secret(value: str | None) -> str:
    if not value:
        return "není nastaveno"
    text = str(value).strip()
    if len(text) <= 8:
        return "********"
    return f"{text[:2]}********{text[-2:]}"


def get_api_status() -> dict[str, Any]:
    featherless = get_featherless_config()
    copernicus = get_copernicus_config()
    return {
        "featherless": {
            "configured": bool(featherless.get("FEATHERLESS_API_KEY")),
            "ready": has_real_featherless(),
            "model": featherless.get("FEATHERLESS_MODEL", "Qwen/Qwen3-32B"),
            "api_key": mask_secret(featherless.get("FEATHERLESS_API_KEY")),
        },
        "copernicus": {
            "configured": bool(copernicus.get("CDSE_CLIENT_ID") and copernicus.get("CDSE_CLIENT_SECRET")),
            "ready": has_real_copernicus(),
            "token_url": copernicus.get("CDSE_TOKEN_URL"),
            "client_id": mask_secret(copernicus.get("CDSE_CLIENT_ID")),
        },
    }
