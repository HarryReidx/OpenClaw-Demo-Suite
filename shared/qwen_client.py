from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Callable

from openai import OpenAI

from shared.config import get_settings, require_api_key


ToolExecutor = Callable[[str, dict[str, Any]], dict[str, Any]]


def _client() -> OpenAI:
    require_api_key()
    settings = get_settings()
    return OpenAI(api_key=settings.qwen_api_key, base_url=settings.qwen_base_url)


def chat_completion(
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    temperature: float = 0.7,
    tools: list[dict[str, Any]] | None = None,
) -> Any:
    settings = get_settings()
    kwargs: dict[str, Any] = dict(
        model=model or settings.qwen_text_model,
        messages=messages,
        temperature=temperature,
    )
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    return _client().chat.completions.create(**kwargs)


def stream_chat_completion(
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    temperature: float = 0.7,
) -> Any:
    settings = get_settings()
    return _client().chat.completions.create(
        model=model or settings.qwen_text_model,
        messages=messages,
        temperature=temperature,
        stream=True,
    )


def simple_chat(
    prompt: str,
    *,
    system_prompt: str = "You are a helpful assistant.",
    model: str | None = None,
    temperature: float = 0.7,
) -> str:
    response = chat_completion(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        model=model,
        temperature=temperature,
    )
    return response.choices[0].message.content or ""


def vision_chat(
    prompt: str,
    image_bytes: bytes,
    *,
    image_mime_type: str = "image/jpeg",
    system_prompt: str = "You are a helpful multimodal assistant.",
) -> str:
    settings = get_settings()
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")
    response = _client().chat.completions.create(
        model=settings.qwen_vision_model,
        messages=[
            {"role": "system", "content": [{"type": "text", "text": system_prompt}]},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{image_mime_type};base64,{image_base64}"
                        },
                    },
                ],
            },
        ],
    )
    return response.choices[0].message.content or ""


def chat_with_tools(
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]],
    executor: ToolExecutor,
    model: str | None = None,
    temperature: float = 0.2,
    max_rounds: int = 4,
) -> tuple[str, list[dict[str, Any]]]:
    history = list(messages)
    for _ in range(max_rounds):
        response = chat_completion(
            history,
            model=model,
            temperature=temperature,
            tools=tools,
        )
        message = response.choices[0].message
        history.append(message.model_dump())
        tool_calls = getattr(message, "tool_calls", None) or []
        if not tool_calls:
            return (message.content or "", history)
        for tool_call in tool_calls:
            args = json.loads(tool_call.function.arguments or "{}")
            result = executor(tool_call.function.name, args)
            history.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_call.function.name,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
    return ("工具调用轮次达到上限，请缩小任务范围后重试。", history)
