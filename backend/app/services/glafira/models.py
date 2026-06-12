"""Конфигурация LLM-моделей для AI-сервисов"""

# Белый список разрешённых LLM-моделей (slugs сверены по live OpenRouter)
ALLOWED_LLM_MODELS = [
    {"value": "qwen/qwen3.7-max", "label": "Qwen3.7-Max"},
    {"value": "moonshotai/kimi-k2.6", "label": "Kimi K2.6"},
    {"value": "deepseek/deepseek-v4-flash", "label": "DeepSeek V4 Flash"},
    {"value": "anthropic/claude-sonnet-4.6", "label": "Claude Sonnet 4.6"},
]

# Set валидных slug для быстрой проверки
ALLOWED_MODEL_VALUES = {model["value"] for model in ALLOWED_LLM_MODELS}

# Дефолтная модель
DEFAULT_MODEL = "anthropic/claude-sonnet-4.6"