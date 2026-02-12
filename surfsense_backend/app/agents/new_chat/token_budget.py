"""Token budget manager for Supervisor context window management."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.utils.context_metrics import estimate_tokens_from_text
from app.utils.document_converters import get_model_context_window

# Number of recent messages to always keep (4 messages = ~2 exchanges)
# Preserves immediate conversation context for coherent responses
TAIL_MESSAGE_COUNT = 4


@dataclass
class TokenBudget:
    """Manages token budget for Supervisor LLM calls."""
    
    model_name: str
    reserved_output: int = 4096
    reserved_system: int = 2000
    _max_context: int = field(init=False, default=0)
    
    def __post_init__(self):
        self._max_context = get_model_context_window(self.model_name)
    
    @property
    def max_context(self) -> int:
        return self._max_context
    
    @property
    def available_for_messages(self) -> int:
        return max(0, self._max_context - self.reserved_output - self.reserved_system)
    
    def estimate_message_tokens(self, message: Any) -> int:
        content = getattr(message, "content", "")
        if isinstance(content, list):
            content = " ".join(str(part) for part in content)
        return estimate_tokens_from_text(str(content or ""), model=self.model_name)
    
    def estimate_messages_tokens(self, messages: list[Any]) -> int:
        return sum(self.estimate_message_tokens(m) for m in messages)
    
    def fit_messages(self, messages: list[Any]) -> list[Any]:
        """Trim oldest non-essential messages to fit within token budget.
        
        Strategy:
        - Always keep: first SystemMessage, last HumanMessage, last 2 exchanges
        - Drop oldest middle messages first
        - Replace dropped block with a "[earlier context omitted]" marker
        """
        if not messages:
            return messages
        
        budget = self.available_for_messages
        total = self.estimate_messages_tokens(messages)
        
        if total <= budget:
            return messages
        
        # Partition into head (system), tail (recent), and compressible middle
        head: list[Any] = []
        tail: list[Any] = []
        middle: list[Any] = []
        
        # Head: leading SystemMessages
        idx = 0
        while idx < len(messages) and isinstance(messages[idx], SystemMessage):
            head.append(messages[idx])
            idx += 1
        
        # Tail: last TAIL_MESSAGE_COUNT messages (ensures recent context)
        tail_start = max(idx, len(messages) - TAIL_MESSAGE_COUNT)
        tail = messages[tail_start:]
        middle = messages[idx:tail_start]
        
        # Calculate fixed costs
        head_tokens = self.estimate_messages_tokens(head)
        tail_tokens = self.estimate_messages_tokens(tail)
        remaining = budget - head_tokens - tail_tokens
        
        if remaining <= 0:
            # Even head + tail exceeds budget; keep only tail
            return tail
        
        # Fill middle from most recent backward
        kept_middle: list[Any] = []
        used = 0
        for msg in reversed(middle):
            msg_tokens = self.estimate_message_tokens(msg)
            if used + msg_tokens <= remaining:
                kept_middle.insert(0, msg)
                used += msg_tokens
            else:
                break
        
        dropped_count = len(middle) - len(kept_middle)
        
        result = list(head)
        if dropped_count > 0:
            marker = SystemMessage(
                content=f"[{dropped_count} earlier messages omitted to fit context window]"
            )
            result.append(marker)
        result.extend(kept_middle)
        result.extend(tail)
        
        return result
    
    def get_usage_summary(self, messages: list[Any]) -> dict[str, int]:
        """Return a summary of token usage."""
        total = self.estimate_messages_tokens(messages)
        return {
            "used_tokens": total,
            "available_tokens": self.available_for_messages,
            "max_context": self._max_context,
            "headroom": max(0, self.available_for_messages - total),
        }
