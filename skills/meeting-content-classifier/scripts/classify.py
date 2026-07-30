#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
会议内容分类器（M2 子环节 Skill 原型）

功能：对「单条」会议字幕句子做内容分类，判定其属于：
    - 决策(decision)
    - 行动项(action_item)
    - 普通讨论(discussion)

设计原则（遵守五条业务铁律）：
    1. 不把讨论意见当作正式决定（讨论特征词优先于弱决策信号）
    2. 不虚构责任人和截止时间（本环节只做分类，不做实体补全）
    3. 信息不全须人工确认（无特征词 / 缺原始位置 → needs_human_confirmation=True）
    4. 不替他人承诺（本环节不产出责任人，仅判定类型）
    5. 任务须可追溯（缺 position 一律需人工确认，并在 reason 中标注）

用法：
    # CLI 交互模式（直接传一句话）
    python classify.py "我们决定下周三发布 v2.0"

    # JSON 模式（从 stdin 读一条标准输入 JSON）
    echo '{"text":"张三负责跟进","position":"00:15:20","speaker":"李四"}' | python classify.py --json

    # 从测试样本文件批量跑
    python classify.py --file ../tests/sample_inputs.json
"""

import argparse
import json
import sys
from typing import Any


# ----------------------------- 特征词表 -----------------------------
# 决策类：表示已形成正式结论 / 共识 / 授权
DECISION_KEYWORDS = [
    "决定", "确定", "拍板", "通过", "批准", "决议", "一致认为",
    "最终决定", "最终确定", "统一意见", "达成共识", "会议决定",
    "原则上通过", "审议通过", "同意立项", "确认采用",
]

# 行动项类：表示存在「待执行」的任务与责任指派
ACTION_ITEM_KEYWORDS = [
    "负责", "跟进", "落实", "督办", "安排", "推进", "交付", "完成",
    "待办", "todo", "TODO", "牵头", "执行", "指派", "认领", "归口",
]

# 讨论类：表示尚在商讨 / 征询 / 表达个人看法，未形成结论
DISCUSSION_KEYWORDS = [
    "我觉得", "我认为", "可能", "是否", "建议", "大家怎么看",
    "讨论一下", "再想想", "待商榷", "倾向于", "可以考虑",
    "怎么样", "你们觉得", "有没有可能", "或许", "好像",
]


# ----------------------------- 分类核心 -----------------------------
def classify_one(text: str, position: str | None = None,
                 speaker: str | None = None) -> dict[str, Any]:
    """
    对单条字幕句子做三分类。

    Args:
        text: 字幕句子原文（必填）
        position: 原始字幕位置/时间戳（可选，用于溯源）
        speaker: 发言人（可选，仅回显，不参与判定）

    Returns:
        dict: 见模块头部的输出格式说明
    """
    # ---- 失败路径：输入校验 ----
    if not isinstance(text, str) or not text.strip():
        return {
            "ok": False,
            "error_code": "INVALID_INPUT",
            "error_message": "text 字段缺失或非字符串，无法进行内容分类",
            "content_type": None,
            "confidence": None,
            "matched_keywords": [],
            "needs_human_confirmation": True,
            "position": position,
            "speaker": speaker,
            "reason": "输入无效：缺少有效文本，按铁律不臆测分类结果",
        }

    cleaned = text.strip()

    # ---- 命中检测 ----
    hit_decision = [k for k in DECISION_KEYWORDS if k in cleaned]
    hit_action = [k for k in ACTION_ITEM_KEYWORDS if k in cleaned]
    hit_discussion = [k for k in DISCUSSION_KEYWORDS if k in cleaned]

    # ---- 优先级：讨论特征强信号优先（铁律1：不把讨论当决定）----
    # 若句子同时命中讨论特征词，且决策信号来自弱表达（如仅"同意"未带"通过/决议"），
    # 视为讨论倾向，需人工确认。此处简化：讨论命中且无强决策词 → 讨论。
    strong_decision = any(
        k in cleaned for k in ("决定", "确定", "拍板", "通过", "批准",
                                "决议", "最终决定", "达成共识", "会议决定")
    )

    # ---- 分类决策 ----
    content_type: str
    confidence: str
    matched: list[str]
    reason: str
    needs_confirm = False

    if hit_discussion and not strong_decision:
        # 讨论倾向（且无强决策结论）→ 普通讨论
        content_type = "普通讨论"
        confidence = "low" if not (hit_decision or hit_action) else "medium"
        matched = hit_discussion
        reason = (
            "命中讨论特征词且未出现强决策结论词，"
            "按铁律1「不把讨论当决定」判定为普通讨论"
        )
        needs_confirm = True  # 讨论中含任务倾向的，需人工确认是否升级
    elif hit_decision:
        content_type = "决策"
        confidence = "high"
        matched = hit_decision
        reason = "命中决策类特征词，判定为正式决策"
    elif hit_action:
        content_type = "行动项"
        confidence = "high"
        matched = hit_action
        reason = "命中行动项类特征词，判定为待执行任务"
    else:
        # 无任何特征词 → 边界：默认讨论 + 低置信 + 人工确认
        content_type = "普通讨论"
        confidence = "low"
        matched = []
        reason = "未命中任何特征词，无法自动判定，降级为普通讨论并需人工确认"
        needs_confirm = True

    # ---- 溯源校验（铁律5）----
    if not position:
        needs_confirm = True
        reason += "；原始字幕位置缺失，不可追溯，须人工确认"

    return {
        "ok": True,
        "content_type": content_type,
        "confidence": confidence,
        "matched_keywords": matched,
        "needs_human_confirmation": needs_confirm,
        "position": position,
        "speaker": speaker,
        "reason": reason,
    }


# ----------------------------- I/O 适配 -----------------------------
def _normalize_input(raw: Any) -> dict[str, Any]:
    """把各种输入形态归一为 {text, position, speaker}。"""
    if isinstance(raw, str):
        # 纯字符串 → 当作 text
        return {"text": raw}
    if isinstance(raw, dict):
        return {
            "text": raw.get("text"),
            "position": raw.get("position"),
            "speaker": raw.get("speaker"),
        }
    return {"text": None}


def run_one(raw: Any) -> dict[str, Any]:
    """对外暴露的统一入口：吃任意输入，吐结构化结果。"""
    norm = _normalize_input(raw)
    result = classify_one(
        text=norm["text"],
        position=norm.get("position"),
        speaker=norm.get("speaker"),
    )
    # 回填原始输入文本，便于结果对照
    result["input_text"] = norm["text"] if isinstance(norm["text"], str) else None
    return result


# ----------------------------- CLI -----------------------------
def _cli() -> int:
    parser = argparse.ArgumentParser(
        description="会议内容分类器：判定单条字幕属于 决策/行动项/普通讨论",
    )
    parser.add_argument("text", nargs="?", help="直接传入一句话进行分类")
    parser.add_argument("--json", action="store_true",
                        help="从 stdin 读取单条 JSON 输入")
    parser.add_argument("--file", help="从 JSON 文件批量读取并分类")
    args = parser.parse_args()

    results: list[dict[str, Any]] = []

    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            data = json.load(f)
        items = data if isinstance(data, list) else [data]
        for it in items:
            # 支持测试样本格式 {id, desc, input:{...}}，也支持直接 {text,...}
            if isinstance(it, dict) and "input" in it:
                res = run_one(it["input"])
                res["test_id"] = it.get("id")
                res["test_desc"] = it.get("desc")
            else:
                res = run_one(it)
            results.append(res)
    elif args.json:
        raw = sys.stdin.read()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            print(json.dumps({
                "ok": False,
                "error_code": "INVALID_JSON",
                "error_message": f"stdin 不是合法 JSON：{e}",
            }, ensure_ascii=False, indent=2))
            return 2
        results.append(run_one(payload))
    elif args.text:
        results.append(run_one(args.text))
    else:
        parser.print_help()
        return 1

    print(json.dumps(results if len(results) > 1 else results[0],
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
