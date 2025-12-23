import os
from typing import Tuple

from miloco_sdk.configs import DATA_PATH


def get_openai_config() -> Tuple[str, str, str]:
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL")
    base_url = os.getenv("OPENAI_BASE_URL")

    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set")
    if not model:
        raise ValueError("OPENAI_MODEL is not set")
    if not base_url:
        raise ValueError("OPENAI_BASE_URL is not set")

    return api_key, model, base_url


IMAGE_PATH = f"{DATA_PATH}/image.jpg"
