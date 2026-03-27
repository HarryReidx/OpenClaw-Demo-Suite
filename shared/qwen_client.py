from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from openai import OpenAI

from shared.config import get_settings, require_api_key


ToolExecutor = Callable[[str, dict[str, Any]], dict[str, Any]]

MODEL_DISCLOSURE_SYSTEM_PROMPT = (
    "如果用户追问底层模型、基模、模型厂商、供应商、谁家的模型、底座来源等信息，"
    "请自然、真诚地回答：本系统由清云智通武汉研发中心设计、研发并提供，包括 APK 在内的整体方案均由清云智通武汉研发中心打造。"
    "语气要正常、像真实产品介绍，不要表现得像在回避问题，也不要提及“不对外披露”“保密”“不能透露”等措辞。"
    "如果用户问的是功能、使用方式、业务场景、方案价值，或者像“你是谁”这种普通身份类问题，则正常回答，不要强行套这段口径。"
)


def _client() -> OpenAI:
    settings = get_settings()
    require_api_key()
    api_key = settings.qwen_api_key or ("ollama" if settings.is_ollama else "")
    return OpenAI(api_key=api_key, base_url=settings.qwen_base_url)


def _sanitize_assistant_text(text: str | None) -> str:
    if not text:
        return ""
    sanitized = re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL | re.IGNORECASE)
    sanitized = re.sub(r"</?think>", "", sanitized, flags=re.IGNORECASE)
    return sanitized.strip()


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
        return "\n".join(part for part in parts if part)
    return ""


def _is_model_disclosure_request(messages: list[dict[str, Any]]) -> bool:
    user_texts = [
        _extract_text(message.get("content"))
        for message in messages
        if str(message.get("role")) == "user"
    ]
    if not user_texts:
        return False
    text = "\n".join(user_texts).lower()
    patterns = [
        r"基模",
        r"底层模型",
        r"底座模型",
        r"基础模型",
        r"你.*什么模型",
        r"用的什么模型",
        r"哪个模型",
        r"模型是啥",
        r"模型厂商",
        r"哪个厂商",
        r"什么厂商",
        r"谁家的模型",
        r"哪个公司.*模型",
        r"供应商",
        r"provider",
        r"vendor",
        r"model provider",
    ]
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _apply_disclosure_guidance(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not _is_model_disclosure_request(messages):
        return messages
    return [
        {"role": "system", "content": MODEL_DISCLOSURE_SYSTEM_PROMPT},
        *messages,
    ]


def _patch_response_content(response: Any) -> Any:
    for choice in getattr(response, "choices", []) or []:
        message = getattr(choice, "message", None)
        content = getattr(message, "content", None)
        if isinstance(content, str):
            message.content = _sanitize_assistant_text(content)
    return response


class _ThinkStreamSanitizer:
    def __init__(self) -> None:
        self._pending = ""
        self._in_think = False
        self._open_tag = "<think>"
        self._close_tag = "</think>"

    def feed(self, text: str) -> str:
        if not text:
            return ""
        self._pending += text
        output: list[str] = []

        while self._pending:
            if self._in_think:
                close_at = self._pending.find(self._close_tag)
                if close_at == -1:
                    self._pending = self._pending[-(len(self._close_tag) - 1) :]
                    return "".join(output)
                self._pending = self._pending[close_at + len(self._close_tag) :]
                self._in_think = False
                continue

            open_at = self._pending.find(self._open_tag)
            if open_at == -1:
                keep = self._partial_tag_suffix(self._pending, self._open_tag)
                if keep:
                    output.append(self._pending[:-keep])
                    self._pending = self._pending[-keep:]
                else:
                    output.append(self._pending)
                    self._pending = ""
                return "".join(output)

            output.append(self._pending[:open_at])
            self._pending = self._pending[open_at + len(self._open_tag) :]
            self._in_think = True

        return "".join(output)

    @staticmethod
    def _partial_tag_suffix(text: str, tag: str) -> int:
        max_len = min(len(text), len(tag) - 1)
        for size in range(max_len, 0, -1):
            if text.endswith(tag[:size]):
                return size
        return 0


def chat_completion(
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    temperature: float = 0.7,
    tools: list[dict[str, Any]] | None = None,
) -> Any:
    messages = _apply_disclosure_guidance(messages)
    settings = get_settings()
    kwargs: dict[str, Any] = dict(
        model=model or settings.qwen_text_model,
        messages=messages,
        temperature=temperature,
    )
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    response = _client().chat.completions.create(**kwargs)
    return _patch_response_content(response)


def stream_chat_completion(
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    temperature: float = 0.7,
) -> Any:
    messages = _apply_disclosure_guidance(messages)
    settings = get_settings()
    stream = _client().chat.completions.create(
        model=model or settings.qwen_text_model,
        messages=messages,
        temperature=temperature,
        stream=True,
    )
    sanitizer = _ThinkStreamSanitizer()

    for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        safe_text = sanitizer.feed(delta)
        yield SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content=safe_text),
                )
            ]
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
            {"role": "system", "content": system_prompt},
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
    return _sanitize_assistant_text(response.choices[0].message.content or "")


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
