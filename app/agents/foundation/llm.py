from typing import Dict, Any, Tuple, Optional

from pydantic_ai.agent import AgentRunResult
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.models.openrouter import (
    OpenRouterModel,
    OpenRouterModelSettings,
    OpenRouterProviderConfig,
)


def get_llm_model(model_name: str, temperature: float = 0.3, timeout: int = 30) -> FallbackModel:
    """
    Get the LLM model with a FallbackModel chain for provider resilience.

    Parameters
    ----------
    model_name: str
        The name of the model.
    temperature: float
        The temperature of the model. Default is 0.3.
    timeout: int
        The timeout in seconds. Default is 30.

    Returns
    -------
    FallbackModel
        A chain of models: primary -> OpenRouter fallback -> smaller stable models.
    """

    # Base fallback models used as safety net across all branches
    base_fallback_models = (
        OpenAIChatModel(
            "gpt-5-mini-2025-08-07",
            settings=OpenAIChatModelSettings(
                openai_reasoning_effort="minimal",
                openai_reasoning_summary="detailed",
                timeout=timeout,
                temperature=temperature,
                seed=0,
            ),
        ),
        OpenAIChatModel(
            "gpt-4.1-mini-2025-04-14",
            settings=OpenAIChatModelSettings(
                timeout=timeout,
                temperature=temperature,
                seed=0,
            ),
        ),
        OpenAIChatModel(
            "gpt-4.1-2025-04-14",
            settings=OpenAIChatModelSettings(
                timeout=timeout,
                temperature=temperature,
                seed=0,
            ),
        ),
    )

    if model_name == "gpt-5.4":
        model = FallbackModel(
            OpenAIChatModel(
                "gpt-5.4-2026-03-05",
                settings=OpenAIChatModelSettings(
                    timeout=timeout,
                    temperature=temperature,
                    seed=0,
                ),
            ),
            OpenRouterModel(
                "openai/gpt-5.4",
                settings=OpenRouterModelSettings(
                    timeout=timeout,
                    temperature=temperature,
                    seed=0,
                ),
            ),
            *base_fallback_models,
        )

    elif model_name == "gpt-5.4-mini":
        model = FallbackModel(
            OpenAIChatModel(
                "gpt-5.4-mini-2026-03-17",
                settings=OpenAIChatModelSettings(
                    timeout=timeout,
                    temperature=temperature,
                    seed=0,
                ),
            ),
            OpenRouterModel(
                "openai/gpt-5.4-mini",
                settings=OpenRouterModelSettings(
                    timeout=timeout,
                    temperature=temperature,
                    seed=0,
                ),
            ),
            *base_fallback_models,
        )

    elif model_name == "gpt-5.2":
        model = FallbackModel(
            OpenAIChatModel(
                "gpt-5.2-2025-12-11",
                settings=OpenAIChatModelSettings(
                    openai_reasoning_effort="none",
                    openai_reasoning_summary="detailed",
                    timeout=timeout,
                    temperature=temperature,
                    seed=0,
                ),
            ),
            *base_fallback_models,
        )

    elif model_name == "gpt-5.1":
        model = FallbackModel(
            OpenAIChatModel(
                "gpt-5.1-2025-11-13",
                settings=OpenAIChatModelSettings(
                    openai_reasoning_effort="none",
                    openai_reasoning_summary="detailed",
                    timeout=timeout,
                    temperature=temperature,
                    seed=0,
                ),
            ),
            *base_fallback_models,
        )

    elif model_name == "gpt-5-mini-openrouter":
        model = FallbackModel(
            OpenRouterModel(
                "openai/gpt-5-mini",
                settings=OpenRouterModelSettings(
                    openrouter_reasoning={"effort": "minimal"},
                    timeout=timeout,
                    temperature=temperature,
                    seed=0,
                ),
            ),
            OpenRouterModel(
                "google/gemini-3.1-flash-lite",
                settings=OpenRouterModelSettings(
                    openrouter_reasoning={"effort": None},
                    timeout=timeout,
                    temperature=temperature,
                    seed=0,
                ),
            ),
            OpenAIChatModel(
                "gpt-4.1-mini-2025-04-14",
                settings=OpenAIChatModelSettings(
                    timeout=timeout,
                    temperature=temperature,
                    seed=0,
                ),
            ),
        )

    elif model_name == "gpt-5.4-nano-openrouter":
        model = FallbackModel(
            OpenRouterModel(
                "openai/gpt-5.4-nano",
                settings=OpenRouterModelSettings(
                    openrouter_reasoning={"effort": "minimal"},
                    timeout=timeout,
                    temperature=temperature,
                    seed=0,
                ),
            ),
            OpenRouterModel(
                "google/gemini-3.1-flash-lite",
                settings=OpenRouterModelSettings(
                    openrouter_reasoning={"effort": None},
                    timeout=timeout,
                    temperature=temperature,
                    seed=0,
                ),
            ),
            OpenRouterModel(
                "openai/gpt-5-mini",
                settings=OpenRouterModelSettings(
                    openrouter_reasoning={"effort": "minimal"},
                    timeout=timeout,
                    temperature=temperature,
                    seed=0,
                ),
            ),
            OpenAIChatModel(
                "gpt-5.4-nano",
                settings=OpenAIChatModelSettings(
                    timeout=timeout,
                    temperature=temperature,
                    seed=0,
                ),
            ),
            OpenAIChatModel(
                "gpt-5-mini",
                settings=OpenAIChatModelSettings(
                    timeout=timeout,
                    temperature=temperature,
                    seed=0,
                ),
            ),
        )

    elif model_name == "gpt-5-mini":
        model = FallbackModel(
            OpenAIChatModel(
                "gpt-5-mini-2025-08-07",
                settings=OpenAIChatModelSettings(
                    openai_reasoning_effort="minimal",
                    openai_reasoning_summary="detailed",
                    timeout=timeout,
                    temperature=temperature,
                    seed=0,
                ),
            ),
            OpenRouterModel(
                "openai/gpt-5-mini",
                settings=OpenRouterModelSettings(
                    openrouter_reasoning={"effort": "minimal"},
                    timeout=timeout,
                    temperature=temperature,
                    seed=0,
                ),
            ),
            OpenRouterModel(
                "openai/gpt-4.1-mini",
                settings=OpenRouterModelSettings(
                    timeout=timeout,
                    temperature=temperature,
                    seed=0,
                ),
            ),
        )

    elif model_name == "gpt-5.4-nano":
        model = FallbackModel(
            OpenAIChatModel(
                "gpt-5.4-nano",
                settings=OpenAIChatModelSettings(
                    timeout=timeout,
                    temperature=temperature,
                    seed=0,
                ),
            ),
            *base_fallback_models,
        )

    elif model_name == "gpt-oss-120b":
        model = FallbackModel(
            OpenRouterModel(
                "openai/gpt-oss-120b",
                settings=OpenRouterModelSettings(
                    openrouter_reasoning={"effort": "low"},
                    timeout=timeout,
                    temperature=temperature,
                    seed=0,
                    openrouter_provider=OpenRouterProviderConfig(order=["groq"]),
                ),
            ),
            *base_fallback_models,
        )

    elif model_name == "gpt-oss-20b":
        model = FallbackModel(
            OpenRouterModel(
                "openai/gpt-oss-20b",
                settings=OpenRouterModelSettings(
                    openrouter_reasoning={"effort": "low"},
                    timeout=timeout,
                    temperature=temperature,
                    seed=0,
                    openrouter_provider=OpenRouterProviderConfig(order=["groq"]),
                ),
            ),
            *base_fallback_models,
        )

    elif model_name == "gpt-oss-safeguard-20b":
        model = FallbackModel(
            OpenRouterModel(
                "openai/gpt-oss-safeguard-20b",
                settings=OpenRouterModelSettings(
                    timeout=timeout,
                    temperature=temperature,
                    seed=0,
                ),
            ),
            *base_fallback_models,
        )

    elif model_name == "gpt-4.1-mini":
        model = FallbackModel(
            OpenAIChatModel(
                "gpt-4.1-mini-2025-04-14",
                settings=OpenAIChatModelSettings(
                    timeout=timeout,
                    temperature=temperature,
                    seed=0,
                ),
            ),
            *base_fallback_models,
        )

    elif model_name == "claude-haiku-4.5":
        model = FallbackModel(
            OpenRouterModel(
                "anthropic/claude-haiku-4.5",
                settings=OpenRouterModelSettings(
                    openrouter_reasoning={"effort": None},
                    timeout=timeout,
                    temperature=temperature,
                    seed=0,
                ),
            ),
            *base_fallback_models,
        )

    elif model_name == "claude-sonnet-4.6":
        model = FallbackModel(
            OpenRouterModel(
                "anthropic/claude-sonnet-4.6",
                settings=OpenRouterModelSettings(
                    openrouter_reasoning={"effort": None},
                    timeout=timeout,
                    temperature=temperature,
                    seed=0,
                ),
            ),
            *base_fallback_models,
        )

    elif model_name == "claude-opus-4.6":
        model = FallbackModel(
            OpenRouterModel(
                "anthropic/claude-opus-4.6",
                settings=OpenRouterModelSettings(
                    openrouter_reasoning={"effort": None},
                    timeout=timeout,
                    temperature=temperature,
                    seed=0,
                ),
            ),
            *base_fallback_models,
        )

    elif model_name == "gemini-3.1-pro-preview":
        model = FallbackModel(
            OpenRouterModel(
                "google/gemini-3.1-pro-preview",
                settings=OpenRouterModelSettings(
                    timeout=timeout,
                    temperature=temperature,
                    seed=0,
                ),
            ),
            *base_fallback_models,
        )

    elif model_name == "gemini-3.1-flash-lite-preview":
        model = FallbackModel(
            OpenRouterModel(
                "google/gemini-3.1-flash-lite",
                settings=OpenRouterModelSettings(
                    openrouter_reasoning={"effort": None},
                    timeout=timeout,
                    temperature=temperature,
                    seed=0,
                ),
            ),
            OpenRouterModel(
                "openai/gpt-5.4-nano",
                settings=OpenRouterModelSettings(
                    openrouter_reasoning={"effort": "minimal"},
                    timeout=timeout,
                    temperature=temperature,
                    seed=0,
                ),
            ),
            OpenRouterModel(
                "openai/gpt-5.4-mini",
                settings=OpenRouterModelSettings(
                    timeout=timeout,
                    temperature=temperature,
                    seed=0,
                ),
            ),
            *base_fallback_models,
        )

    elif model_name == "gemini-3-flash-preview":
        model = FallbackModel(
            OpenRouterModel(
                "google/gemini-3-flash-preview",
                settings=OpenRouterModelSettings(
                    openrouter_reasoning={"effort": None},
                    timeout=timeout,
                    temperature=temperature,
                    seed=0,
                ),
            ),
            *base_fallback_models,
        )

    else:
        # Unknown model: fall back to gpt-4.1-mini chain
        model = FallbackModel(
            OpenAIChatModel(
                "gpt-4.1-mini-2025-04-14",
                settings=OpenAIChatModelSettings(
                    timeout=timeout,
                    temperature=temperature,
                    seed=0,
                ),
            ),
            *base_fallback_models,
        )

    return model


def get_llm_run_metadata(result: Any) -> Optional[Dict[str, Any]]:
    """
    Get the metadata from the LLM run result.

    Parameters
    ----------
    result : Any
        The result from the agent run (AgentRunResult[Any]).

    Returns
    -------
    Optional[Dict[str, Any]]
        Metadata including model_name, provider, token counts, and prompt.
        Returns None if parsing fails.
    """
    try:
        model_name, provider = get_model_name_and_provider(result)
        token_usage = get_token_usage(result)
        prompt = get_prompt(result)

        return {
            "model_name": model_name,
            "provider": provider,
            "input_tokens": token_usage.get("input_tokens"),
            "reasoning_tokens": token_usage.get("reasoning_tokens"),
            "output_tokens": token_usage.get("output_tokens"),
            "prompt": prompt,
        }
    except Exception:
        return None


def get_prompt(result: Any) -> str:
    """
    Get the prompt from the agent run result.

    Parameters
    ----------
    result : Any
        The result from the agent run (AgentRunResult[Any]).

    Returns
    -------
    str
        The prompt from the agent run result.
    """
    return "".join([p.content for p in result.all_messages()[0].parts])


def get_token_usage(result: Any) -> Dict[str, int]:
    """
    Get the token usage from the agent run result.

    Parameters
    ----------
    result : Any
        The result from the agent run (AgentRunResult[Any]).

    Returns
    -------
    Dict[str, int]
        Dictionary with "input_tokens", "reasoning_tokens", and "output_tokens".
    """
    usage = result.usage()

    return {
        "input_tokens": usage.input_tokens,
        "reasoning_tokens": usage.details.get("reasoning_tokens"),
        "output_tokens": usage.output_tokens,
    }


def get_model_name_and_provider(result: Any) -> Tuple[str, str]:
    """
    Get the model name and provider from the agent run result.

    Parameters
    ----------
    result : Any
        The result from the agent run (AgentRunResult[Any]).

    Returns
    -------
    Tuple[str, str]
        Tuple of (model_name, provider). Provider is one of:
        "openai", "openrouter", "anthropic", "google", or "other".
    """
    provider = result.response.provider_name
    model_name = result.response.model_name

    return model_name, provider
