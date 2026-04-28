import os
from typing import Any, Optional
from pathlib import Path

from langchain_openai import ChatOpenAI

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model


# Load .env from repository root (prefer python-dotenv, otherwise manual parser)
def _find_repo_root(start: Optional[Path] = None) -> Optional[Path]:
    p = Path(start or Path(__file__).resolve())
    for parent in [p] + list(p.parents):
        if (parent / '.env').exists() or (parent / 'pyproject.toml').exists() or (parent / 'setup.py').exists():
            return parent
    return None


def _load_dotenv_from_repo():
    repo_root = _find_repo_root()
    if not repo_root:
        return
    dotenv_path = repo_root / '.env'
    if not dotenv_path.exists():
        return

    try:
        # prefer python-dotenv when available
        from dotenv import load_dotenv

        load_dotenv(dotenv_path=str(dotenv_path), override=False)
        return
    except Exception:
        # fall back to a tiny manual parser
        try:
            with dotenv_path.open('r', encoding='utf-8') as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith('#'):
                        continue
                    if line.startswith('export '):
                        line = line[len('export '):]
                    if '=' not in line:
                        continue
                    key, val = line.split('=', 1)
                    key = key.strip()
                    val = val.strip()
                    if (val.startswith("\"") and val.endswith("\"")) or (val.startswith("'") and val.endswith("'")):
                        val = val[1:-1]
                    # do not override existing environment variables
                    if key not in os.environ:
                        os.environ[key] = val
        except Exception:
            return


_load_dotenv_from_repo()


def _sanitize_messages(obj: Any) -> Any:
    """Walk message-like structures and map role 'tool' -> 'function'.

    Accepts lists/dicts (the shapes used by various langchain adapters).
    Returns a sanitized copy (non-mutating for safety).
    """
    if isinstance(obj, dict):
        # shallow copy to avoid mutating original
        new = {}
        for k, v in obj.items():
            if k == "role" and isinstance(v, str) and v == "tool":
                new[k] = "function"
            else:
                new[k] = _sanitize_messages(v)
        return new
    elif isinstance(obj, list):
        return [_sanitize_messages(x) for x in obj]
    else:
        return obj


class NormalizedChatOpenAI(ChatOpenAI):
    """ChatOpenAI with normalized content output and message sanitization.

    We sanitize any message structures passed into invoke/with_structured_output
    so providers that use an intermediate role 'tool' don't cause pydantic
    validation failures (which expect roles: user, assistant, system, function).
    """

    def invoke(self, input, config=None, **kwargs):
        # sanitize commonly-used locations for messages
        sanitized_input = _sanitize_messages(input)
        if "messages" in kwargs:
            kwargs = dict(kwargs)
            kwargs["messages"] = _sanitize_messages(kwargs["messages"])
        return normalize_content(super().invoke(sanitized_input, config, **kwargs))

    def with_structured_output(self, *args, **kwargs):
        if "method" not in kwargs:
            kwargs["method"] = "function_calling"
        return super().with_structured_output(*args, **kwargs)

# Kwargs forwarded from user config to ChatOpenAI
_PASSTHROUGH_KWARGS = (
    "timeout", "max_retries", "reasoning_effort",
    "api_key", "callbacks", "http_client", "http_async_client",
)

# Provider base URLs and API key env vars
_PROVIDER_CONFIG = {
    "xai": ("https://api.x.ai/v1", "XAI_API_KEY"),
    "deepseek": ("https://api.deepseek.com", "DEEPSEEK_API_KEY"),
    "qwen": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY"),
    "glm": ("https://api.z.ai/api/paas/v4/", "ZHIPU_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "ollama": ("http://localhost:11434/v1", None),
}


class OpenAIClient(BaseLLMClient):
    """Client for OpenAI, Ollama, OpenRouter, and xAI providers.

    For native OpenAI models, uses the Responses API (/v1/responses) which
    supports reasoning_effort with function tools across all model families
    (GPT-4.1, GPT-5). Third-party compatible providers (xAI, OpenRouter,
    Ollama) use standard Chat Completions.
    """

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        provider: str = "openai",
        **kwargs,
    ):
        super().__init__(model, base_url, **kwargs)
        self.provider = provider.lower()

    def get_llm(self) -> Any:
        """Return configured ChatOpenAI instance."""
        self.warn_if_unknown_model()
        self.provider='qwen'
        self.model='qwen-plus'
        llm_kwargs = {"model": self.model}

        # Provider-specific base URL and auth
        if self.provider in _PROVIDER_CONFIG:
            base_url, api_key_env = _PROVIDER_CONFIG[self.provider]
            llm_kwargs["base_url"] = base_url

            # Try provider-specific env var first, then fall back to OPENAI_API_KEY.
            api_key = None
            if api_key_env:
                api_key = os.environ.get(api_key_env) or os.environ.get("OPENAI_API_KEY")
                if api_key:
                    llm_kwargs["api_key"] = api_key
                    # Some underlying libraries (and the openai client) expect
                    # OPENAI_API_KEY to be set; populate it at runtime if missing
                    # so users who set e.g. DASHSCOPE_API_KEY in .env don't get the
                    # confusing OpenAIError.
                    if "OPENAI_API_KEY" not in os.environ:
                        os.environ["OPENAI_API_KEY"] = api_key
            else:
                # Ollama uses a special api_key placeholder in langchain-openai
                if self.provider == "ollama":
                    llm_kwargs["api_key"] = "ollama"
        elif self.base_url:
            llm_kwargs["base_url"] = self.base_url

        # Forward user-provided kwargs
        for key in _PASSTHROUGH_KWARGS:
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        # If provider is OpenAI-compatible, ensure an API key exists
        if self.provider in ("openai", "qwen", "xai", "glm", "openrouter"):
            if "api_key" not in llm_kwargs:
                # Prefer explicit env var for provider; we already tried above for known providers.
                api_key = os.environ.get("OPENAI_API_KEY")
                if api_key:
                    llm_kwargs["api_key"] = api_key
                else:
                    raise RuntimeError(
                        "API key 未设置；请设置对应提供者的环境变量（如 DASHSCOPE_API_KEY）或 `OPENAI_API_KEY`，或在 client 配置中传入 `api_key`。"
                    )

        return NormalizedChatOpenAI(**llm_kwargs)

    def validate_model(self) -> bool:
        """Validate model for the provider."""
        return validate_model(self.provider, self.model)
