"""
系统提示词模块

包含内容安全审查和陪伴型AI的提示词定义。
"""

from .moral_audit_prompts import (
    MoralAuditPrompts,
    PromptBuilder
)

__all__ = [
    "MoralAuditPrompts",
    "PromptBuilder"
]