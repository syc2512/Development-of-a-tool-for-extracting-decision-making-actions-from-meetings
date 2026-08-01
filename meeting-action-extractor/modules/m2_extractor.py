# -*- coding: utf-8 -*-
"""
M2 - 决策与行动项识别模块
职责：区分正式决策、行动项、普通讨论，抽取实体（责任人、截止时间），位置锚定
技术方案：LLM 大模型提取
"""

import json
import os
import re
from typing import List, Optional
from dataclasses import dataclass, field

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from modules.m1_preprocessor import SubtitleSegment


@dataclass
class ExtractionResult:
    """单条提取结果"""
    content_type: str           # 正式决策 / 行动项 / 普通讨论
    description: str            # 决策或任务的结构化描述
    owner: str                  # 责任人 (可能为空)
    deadline: str               # 截止时间 YYYY-MM-DD (可能为空)
    source_location: str        # 原始字幕位置 (行号+时间区间)
    needs_review: bool = False  # 是否需要人工确认
    confidence: float = 1.0     # 置信度
    raw_text: str = ""          # 对应的原始字幕文本

    def to_dict(self) -> dict:
        return {
            "content_type": self.content_type,
            "description": self.description,
            "owner": self.owner,
            "deadline": self.deadline,
            "source_location": self.source_location,
            "needs_review": self.needs_review,
            "confidence": self.confidence,
            "raw_text": self.raw_text,
        }


# LLM 系统提示词
SYSTEM_PROMPT = """你是一个会议内容分析专家。你的任务是从会议字幕中提取结构化的决策和行动项信息。

## 提取规则

1. **内容类型分类**（三选一）：
   - "正式决策"：会议中明确达成的决定或结论，通常由主持人/领导拍板
   - "行动项"：需要会后执行的具体任务，通常有明确的执行动作
   - "普通讨论"：意见交流、建议、想法等非正式内容，不构成决策或任务

2. **关键原则**：
   - 不得把讨论意见当作正式决定
   - 不得虚构责任人和截止时间（字幕中未明确提及的，留空）
   - 未经本人确认不得替他人作出承诺
   - 如果信息不完整或不确定，标记 needs_review=true

3. **字段说明**：
   - content_type: 内容类型
   - description: 简洁的结构化描述（不超过100字）
   - owner: 责任人姓名（从字幕中提取，未提及则为空字符串）
   - deadline: 截止时间，统一为 YYYY-MM-DD 格式（未提及则为空字符串）
   - source_index: 对应的字幕段落序号
   - confidence: 置信度 0-1

4. **截止时间处理**：
   - "下周五" -> 根据上下文推断具体日期
   - "8月15日" -> "2026-08-15"
   - "本周三" -> 根据上下文推断
   - "本周内" -> 当周日
   - 如果无法确定具体日期，留空并标记 needs_review=true

## 输出格式

返回JSON数组，每个元素代表一条提取结果：
```json
[
  {
    "content_type": "正式决策",
    "description": "优先推进支付模块重构",
    "owner": "李明",
    "deadline": "2026-08-08",
    "source_index": 4,
    "confidence": 0.95
  }
]
```

注意：只返回JSON数组，不要包含其他文字说明。"""


def _build_user_prompt(segments: List[SubtitleSegment]) -> str:
    """构建用户提示词，将字幕段落格式化输入"""
    lines = ["以下是会议字幕内容，请提取其中的决策和行动项：\n"]
    for seg in segments:
        time_info = f"[{seg.start_time}]" if seg.start_time else ""
        speaker_info = f"{seg.speaker}: " if seg.speaker else ""
        lines.append(f"[段落{seg.index}] {time_info} {speaker_info}{seg.normalized_text}")

    lines.append("\n请分析以上内容，提取所有正式决策和行动项。对于普通讨论，如果包含潜在的任务或决策信号也请提取并标注为普通讨论。")
    return '\n'.join(lines)


def _extract_with_llm(segments: List[SubtitleSegment]) -> List[dict]:
    """使用LLM进行提取"""
    api_key = os.environ.get('OPENAI_API_KEY', '')
    base_url = os.environ.get('OPENAI_BASE_URL', '')
    model = os.environ.get('OPENAI_MODEL', 'qwen-plus')

    if not api_key:
        raise ValueError(
            "未检测到 OPENAI_API_KEY 环境变量。"
            "请设置后重试，或使用规则兜底模式。"
        )

    if OpenAI is None:
        raise ImportError("openai 库未安装")

    client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)

    user_prompt = _build_user_prompt(segments)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    raw_output = response.choices[0].message.content
    if raw_output is None:
        raw_output = ""
    raw_output = raw_output.strip()

    # 尝试解析JSON
    try:
        # 如果返回的是 {"results": [...]} 格式
        data = json.loads(raw_output)
        if isinstance(data, dict):
            # 尝试多种可能的key
            for key in ['results', 'items', 'data', 'extractions']:
                if key in data:
                    return data[key]
            # 如果只有一个key且值是列表
            for k, v in data.items():
                if isinstance(v, list):
                    return v
            return [data] if data else []
        elif isinstance(data, list):
            return data
    except json.JSONDecodeError:
        # 尝试从文本中提取JSON数组
        json_match = re.search(r'\[.*\]', raw_output, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        raise ValueError(f"LLM返回内容无法解析为JSON: {raw_output[:200]}")

    return []


def _extract_with_rules(segments: List[SubtitleSegment]) -> List[dict]:
    """规则兜底：基于关键词和模式的提取方案"""
    results = []

    # 决策关键词
    decision_keywords = [
        '决定', '拍板', '定了', '就这么', '统一', '确认了',
        '最终', '敲定', '决议', '通过'
    ]
    # 行动项关键词
    action_keywords = [
        '负责', '跟进', '完成', '安排', '推进', '开始',
        '你来', '你负责', '去做', '去搞', '提交', '准备',
        '收尾', '接入', '梳理', '评估', '编写', '制定'
    ]
    # 讨论关键词
    discussion_keywords = [
        '我觉得', '建议', '想法', '考虑', '要不要', '能不能',
        '可能', '应该', '不太好说', '先不急', '暂时'
    ]

    import datetime

    for seg in segments:
        text = seg.normalized_text
        if not text:
            continue

        content_type = None
        confidence = 0.5

        # 判断内容类型
        has_decision = any(kw in text for kw in decision_keywords)
        has_action = any(kw in text for kw in action_keywords)
        has_discussion = any(kw in text for kw in discussion_keywords)

        if has_decision and ('负责' in text or '由' in text):
            content_type = '正式决策'
            confidence = 0.75
        elif has_decision:
            content_type = '正式决策'
            confidence = 0.7
        elif has_action:
            content_type = '行动项'
            confidence = 0.65
        elif has_discussion:
            content_type = '普通讨论'
            confidence = 0.6
        else:
            # 如果没有明确信号，跳过
            continue

        # 提取责任人
        owner = ""
        if seg.speaker:
            # 尝试从文本中提取 "由XX负责" 或 "XX你来"
            m = re.search(r'由(.{1,10}?)(?:负责|跟进|来)', text)
            if m:
                owner = m.group(1).strip()
            else:
                m = re.search(r'(.{1,10}?)(?:你来|你负责|负责)', text)
                if m:
                    owner = m.group(1).strip()
                elif seg.speaker and content_type == '行动项':
                    owner = seg.speaker

        # 提取截止时间
        deadline = ""
        # 匹配 "X月X日" 格式
        m = re.search(r'(\d{1,2})月(\d{1,2})日', text)
        if m:
            month = int(m.group(1))
            day = int(m.group(2))
            deadline = f"2026-{month:02d}-{day:02d}"
        else:
            # 匹配 "本周X" / "下周X"
            week_days = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '日': 7, '天': 7}
            m = re.search(r'(本周|下周)([一二三四五六日天])', text)
            if m:
                prefix = m.group(1)
                day_name = m.group(2)
                target_weekday = week_days.get(day_name, 5)

                today = datetime.date.today()
                current_weekday = today.weekday() + 1  # 1=Monday

                if prefix == '本周':
                    days_ahead = target_weekday - current_weekday
                    if days_ahead <= 0:
                        days_ahead += 7
                else:  # 下周
                    days_ahead = 7 - current_weekday + target_weekday

                target_date = today + datetime.timedelta(days=days_ahead)
                deadline = target_date.strftime('%Y-%m-%d')
            else:
                # 匹配 "本周内" / "本周"
                if '本周内' in text or '本周' in text:
                    today = datetime.date.today()
                    days_ahead = 7 - today.weekday()  # 到周日
                    target_date = today + datetime.timedelta(days=days_ahead)
                    deadline = target_date.strftime('%Y-%m-%d')
                elif '本周三' in text or '这周三' in text:
                    today = datetime.date.today()
                    current_weekday = today.weekday() + 1
                    days_ahead = 3 - current_weekday
                    if days_ahead <= 0:
                        days_ahead += 7
                    target_date = today + datetime.timedelta(days=days_ahead)
                    deadline = target_date.strftime('%Y-%m-%d')

        # 是否需要人工确认
        needs_review = False
        if content_type in ('正式决策', '行动项'):
            if not owner or not deadline:
                needs_review = True

        results.append({
            "content_type": content_type,
            "description": text,
            "owner": owner,
            "deadline": deadline,
            "source_index": seg.index,
            "confidence": confidence,
            "needs_review": needs_review,
        })

    return results


def extract(segments: List[SubtitleSegment], use_llm: bool = True) -> List[ExtractionResult]:
    """
    M2 主入口：识别模块
    输入：M1输出的格式化段落列表
    输出：提取结果列表
    """
    raw_results = []

    if use_llm:
        try:
            raw_results = _extract_with_llm(segments)
        except Exception as e:
            print(f"[M2] LLM提取失败，降级到规则模式: {e}")
            raw_results = _extract_with_rules(segments)
    else:
        raw_results = _extract_with_rules(segments)

    # 转换为 ExtractionResult 对象，绑定位置信息
    results = []
    seg_map = {seg.index: seg for seg in segments}

    for item in raw_results:
        source_idx = item.get("source_index", 0)
        seg = seg_map.get(source_idx)

        if seg:
            time_range = ""
            if seg.start_time and seg.end_time:
                time_range = f"{seg.start_time}-{seg.end_time}"
            elif seg.start_time:
                time_range = seg.start_time
            source_location = f"L{seg.line_start}-L{seg.line_end}"
            if time_range:
                source_location += f" [{time_range}]"
            raw_text = seg.raw_text
        else:
            source_location = ""
            raw_text = ""

        # 确保 needs_review 有值
        needs_review = item.get("needs_review", False)

        results.append(ExtractionResult(
            content_type=item.get("content_type", "普通讨论"),
            description=item.get("description", ""),
            owner=item.get("owner", ""),
            deadline=item.get("deadline", ""),
            source_location=source_location,
            needs_review=needs_review,
            confidence=item.get("confidence", 0.5),
            raw_text=raw_text,
        ))

    return results
