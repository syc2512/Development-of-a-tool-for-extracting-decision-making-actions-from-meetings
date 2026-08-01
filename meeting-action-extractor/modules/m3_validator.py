# -*- coding: utf-8 -*-
"""
M3 - 合规校验与标记模块
职责：校验信息完整性，过滤非正式结论，标记待确认项
业务规则：
  1. 不得虚构责任人和截止时间
  2. 不得将讨论意见当作正式决定
  3. 信息缺失时必须标记需人工确认
  4. 未经本人确认不得替他人作出承诺
"""

import re
from typing import List
from dataclasses import dataclass

from modules.m2_extractor import ExtractionResult


@dataclass
class ValidationResult:
    """校验结果"""
    passed: bool          # 是否通过校验
    issues: List[str]     # 发现的问题列表
    action: str           # 处理动作: pass / mark_review / downgrade


def _validate_owner(result: ExtractionResult) -> ValidationResult:
    """校验责任人字段"""
    issues = []

    if not result.owner:
        if result.content_type in ("正式决策", "行动项"):
            issues.append("责任人缺失")
            return ValidationResult(False, issues, "mark_review")
        return ValidationResult(True, issues, "pass")

    # 检查是否可能为虚构（过于模糊的指代）
    vague_indicators = ["大家", "所有人", "相关人", "某", "一些"]
    for v in vague_indicators:
        if v in result.owner:
            issues.append(f"责任人模糊: '{result.owner}'")
            return ValidationResult(False, issues, "mark_review")

    return ValidationResult(True, issues, "pass")


def _validate_deadline(result: ExtractionResult) -> ValidationResult:
    """校验截止时间字段"""
    issues = []

    if not result.deadline:
        if result.content_type == "行动项":
            issues.append("行动项缺少截止时间")
            return ValidationResult(False, issues, "mark_review")
        return ValidationResult(True, issues, "pass")

    # 格式校验
    date_pattern = r'^\d{4}-\d{2}-\d{2}$'
    if not re.match(date_pattern, result.deadline):
        issues.append(f"截止时间格式异常: '{result.deadline}'")
        return ValidationResult(False, issues, "mark_review")

    return ValidationResult(True, issues, "pass")


def _validate_content_type(result: ExtractionResult) -> ValidationResult:
    """校验内容类型是否合规"""
    issues = []

    valid_types = {"正式决策", "行动项", "普通讨论"}
    if result.content_type not in valid_types:
        issues.append(f"无效内容类型: '{result.content_type}'，降级为普通讨论")
        return ValidationResult(False, issues, "downgrade")

    # 检查是否存在将讨论误判为决策的情况
    discussion_indicators = ["我觉得", "我建议", "可以考虑", "要不要", "可能", "应该"]
    if result.content_type == "正式决策":
        for indicator in discussion_indicators:
            if indicator in result.description:
                issues.append(f"疑似将讨论误判为决策 (含'{indicator}')")
                return ValidationResult(False, issues, "downgrade")

    return ValidationResult(True, issues, "pass")


def _validate_description(result: ExtractionResult) -> ValidationResult:
    """校验描述字段"""
    issues = []

    if not result.description or not result.description.strip():
        issues.append("描述为空")
        return ValidationResult(False, issues, "mark_review")

    if len(result.description) > 500:
        issues.append("描述过长(>500字)")
        return ValidationResult(False, issues, "mark_review")

    return ValidationResult(True, issues, "pass")


def validate(results: List[ExtractionResult]) -> List[ExtractionResult]:
    """
    M3 主入口：合规校验
    输入：M2输出的提取结果列表
    输出：校验后的结果列表（可能被标记、降级或补充问题说明）
    """
    validated = []

    for result in results:
        all_issues = []

        # 逐项校验
        checks = [
            _validate_content_type(result),
            _validate_description(result),
            _validate_owner(result),
            _validate_deadline(result),
        ]

        for check in checks:
            all_issues.extend(check.issues)
            if check.action == "downgrade":
                if check == checks[0]:  # content_type校验
                    result.content_type = "普通讨论"
                    all_issues.append("已降级为普通讨论")
            elif check.action == "mark_review":
                result.needs_review = True

        # 置信度低于阈值时也标记
        if result.confidence < 0.6:
            result.needs_review = True
            all_issues.append(f"置信度偏低({result.confidence:.0%})")

        # 正式决策和行动项缺少关键字段时强制标记
        if result.content_type in ("正式决策", "行动项"):
            if not result.owner:
                result.needs_review = True
            if result.content_type == "行动项" and not result.deadline:
                result.needs_review = True

        # 普通讨论不需要人工确认（除非有其他问题）
        if result.content_type == "普通讨论" and not all_issues:
            result.needs_review = False

        validated.append(result)

    return validated
