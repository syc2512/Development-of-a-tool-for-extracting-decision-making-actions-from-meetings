# -*- coding: utf-8 -*-
"""
M1 - 字幕预处理模块
职责：解析字幕文件，归一化文本，绑定时间戳与行号
支持格式：SRT、纯文本
"""

import re
import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class SubtitleSegment:
    """格式化后的字幕段落"""
    index: int                    # 段落序号(从1开始)
    raw_text: str                 # 原始文本
    normalized_text: str          # 归一化后文本
    start_time: Optional[str] = None  # 开始时间戳 (SRT格式时存在)
    end_time: Optional[str] = None    # 结束时间戳 (SRT格式时存在)
    line_start: int = 0           # 原始文件起始行号
    line_end: int = 0             # 原始文件结束行号
    speaker: Optional[str] = None # 发言人(如有)

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "raw_text": self.raw_text,
            "normalized_text": self.normalized_text,
            "start_time": self.start_time or "",
            "end_time": self.end_time or "",
            "line_start": self.line_start,
            "line_end": self.line_end,
            "speaker": self.speaker or "",
        }


def parse_srt(content: str) -> List[SubtitleSegment]:
    """解析SRT格式字幕文件"""
    segments = []
    # 按空行分割块
    blocks = re.split(r'\n\s*\n', content.strip())
    line_offset = 1

    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) < 2:
            continue

        # 第一行是序号
        idx_line = lines[0].strip()
        if not idx_line.isdigit():
            continue
        seg_index = int(idx_line)

        # 第二行是时间戳
        time_line = lines[1].strip()
        time_match = re.match(
            r'(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})',
            time_line
        )
        if not time_match:
            continue
        start_time = time_match.group(1).replace(',', '.')
        end_time = time_match.group(2).replace(',', '.')

        # 第三行及之后是文本
        text_lines = lines[2:] if len(lines) > 2 else []
        raw_text = '\n'.join(text_lines).strip()

        # 提取发言人
        speaker = None
        speaker_match = re.match(r'^([^:：]{1,20})[：:]\s*(.*)', raw_text)
        if speaker_match:
            speaker = speaker_match.group(1).strip()
            raw_text = speaker_match.group(2).strip()

        # 归一化：去除多余空白，保留中文标点
        normalized_text = re.sub(r'\s+', ' ', raw_text).strip()

        # 计算行号
        block_lines = content[:content.find(block)].count('\n') + 1
        line_start = block_lines
        line_end = line_start + len(lines) - 1

        segments.append(SubtitleSegment(
            index=seg_index,
            raw_text=raw_text,
            normalized_text=normalized_text,
            start_time=start_time,
            end_time=end_time,
            line_start=line_start,
            line_end=line_end,
            speaker=speaker,
        ))

    return segments


def parse_plain_text(content: str) -> List[SubtitleSegment]:
    """解析纯文本格式字幕（带时间戳或无时间戳）"""
    segments = []
    lines = content.strip().split('\n')

    # 匹配 [YYYY-MM-DD HH:MM] 格式的时间戳
    pattern_date_time = re.compile(
        r'^\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\]\s*(.*)$'
    )
    # 匹配 [HH:MM:SS] 格式的时间戳（如 .md 会议字幕）
    pattern_time_only = re.compile(
        r'^\[(\d{2}:\d{2}:\d{2})\]\s*(.*)$'
    )
    # 尝试匹配 发言人: 内容 格式
    pattern_speaker = re.compile(r'^([^:：]{1,20})[：:]\s*(.*)$')

    # 非字幕行的特征：Markdown 标题、引用、列表项、元数据
    skip_prefixes = ('#', '>', '- ', '|', '```', '---')

    seg_index = 0
    for i, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue

        # 跳过非字幕行（Markdown 标题、引用、列表、表格等）
        if any(line.startswith(p) for p in skip_prefixes):
            continue

        # 如果行没有时间戳且不像字幕内容（太短或不含中文标点），跳过
        has_time = pattern_date_time.match(line) or pattern_time_only.match(line)
        if not has_time:
            # 检查是否像字幕行（含发言人: 或有足够内容）
            if not pattern_speaker.match(line) or len(line) < 5:
                continue

        seg_index += 1
        start_time = None
        speaker = None
        text = line

        # 先尝试提取日期时间戳
        m_dt = pattern_date_time.match(line)
        if m_dt:
            start_time = m_dt.group(1)
            text = m_dt.group(2)
        else:
            # 再尝试提取纯时间戳
            m_t = pattern_time_only.match(line)
            if m_t:
                start_time = m_t.group(1)
                text = m_t.group(2)

        # 再尝试提取发言人
        m_speaker = pattern_speaker.match(text)
        if m_speaker:
            speaker = m_speaker.group(1).strip()
            text = m_speaker.group(2).strip()

        # 归一化
        normalized_text = re.sub(r'\s+', ' ', text).strip()

        segments.append(SubtitleSegment(
            index=seg_index,
            raw_text=line,
            normalized_text=normalized_text,
            start_time=start_time,
            end_time=None,
            line_start=i,
            line_end=i,
            speaker=speaker,
        ))

    return segments


def preprocess_subtitle(file_path: str) -> List[SubtitleSegment]:
    """
    M1 主入口：字幕预处理
    输入：字幕文件路径
    输出：格式化后的段落列表
    """
    # 检测编码并读取
    content = None
    for encoding in ['utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'utf-16']:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
            break
        except (UnicodeDecodeError, UnicodeError):
            continue

    if content is None:
        raise ValueError(f"无法解码文件: {file_path}")

    # 根据扩展名和内容判断格式
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.srt':
        return parse_srt(content)
    elif ext in ('.txt', '.md'):
        return parse_plain_text(content)
    else:
        # 尝试自动检测
        if re.search(r'\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->', content):
            return parse_srt(content)
        else:
            return parse_plain_text(content)
