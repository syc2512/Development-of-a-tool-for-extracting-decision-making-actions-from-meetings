# -*- coding: utf-8 -*-
"""全链路测试脚本：验证 M1-M4 基础版功能"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from modules.m1_preprocessor import preprocess_subtitle
from modules.m2_extractor import extract
from modules.m3_validator import validate
from modules.m4_output import get_summary, export_csv, results_to_dicts

def test_pipeline():
    print("=" * 60)
    print("  全链路测试: M1 -> M2 -> M3 -> M4")
    print("=" * 60)

    # 测试文件
    test_file = os.path.join(PROJECT_ROOT, 'sample_data', 'meeting_sample_01.srt')
    print(f"\n[输入] {test_file}")

    # === M1 ===
    print("\n--- M1: 字幕预处理 ---")
    segments = preprocess_subtitle(test_file)
    print(f"解析段落数: {len(segments)}")
    for seg in segments[:5]:
        time_info = f"[{seg.start_time}]" if seg.start_time else ""
        speaker = f"{seg.speaker}: " if seg.speaker else ""
        print(f"  #{seg.index} {time_info} {speaker}{seg.normalized_text[:50]}")
    print(f"  ... (共 {len(segments)} 段)")

    assert len(segments) > 0, "M1 解析失败: 无段落"

    # === M2 (规则模式) ===
    print("\n--- M2: 识别提取 (规则模式) ---")
    results = extract(segments, use_llm=False)
    print(f"提取结果数: {len(results)}")
    for r in results:
        print(f"  [{r.content_type}] {r.description[:40]}... | owner={r.owner} | deadline={r.deadline}")

    assert len(results) > 0, "M2 提取失败: 无结果"

    # === M3 ===
    print("\n--- M3: 合规校验 ---")
    results = validate(results)
    review_count = sum(1 for r in results if r.needs_review)
    print(f"校验后结果数: {len(results)}")
    print(f"需人工确认: {review_count} 条")
    for r in results:
        review_tag = "[需确认]" if r.needs_review else "[通过]"
        print(f"  {review_tag} [{r.content_type}] owner={r.owner or '(空)'} deadline={r.deadline or '(空)'}")

    # === M4 ===
    print("\n--- M4: 结果输出 ---")
    summary = get_summary(results)
    print(f"统计概览:")
    print(f"  总数: {summary['total']}")
    print(f"  正式决策: {summary['decisions']}")
    print(f"  行动项: {summary['actions']}")
    print(f"  普通讨论: {summary['discussions']}")
    print(f"  需人工确认: {summary['needs_review']}")
    print(f"  缺失责任人: {summary['missing_owner']}")
    print(f"  缺失截止时间: {summary['missing_deadline']}")
    print(f"  平均置信度: {summary['avg_confidence']}")

    # 导出测试
    csv_path = os.path.join(PROJECT_ROOT, 'exports', 'test_output.csv')
    export_csv(results, csv_path, include_extended=True)
    print(f"\nCSV导出: {csv_path}")

    # === 验证业务规则 ===
    print("\n--- 业务规则校验 ---")
    # 规则1: 不得虚构责任人
    for r in results:
        if r.content_type in ("正式决策", "行动项") and not r.owner:
            assert r.needs_review, f"违规: 责任人缺失但未标记确认 - {r.description[:30]}"
    print("[OK] 规则1: 责任人缺失时已标记人工确认")

    # 规则2: 不得虚构截止时间
    for r in results:
        if r.content_type == "行动项" and not r.deadline:
            assert r.needs_review, f"违规: 截止时间缺失但未标记确认 - {r.description[:30]}"
    print("[OK] 规则2: 截止时间缺失时已标记人工确认")

    # 规则3: 6项核心字段完整
    for r in results:
        assert r.content_type, "字段缺失: content_type"
        assert r.description, "字段缺失: description"
        assert hasattr(r, 'owner'), "字段缺失: owner"
        assert hasattr(r, 'deadline'), "字段缺失: deadline"
        assert r.source_location, "字段缺失: source_location"
        assert isinstance(r.needs_review, bool), "字段缺失: needs_review"
    print("[OK] 规则3: 6项核心字段完整输出")

    # 规则4: 可追溯性
    for r in results:
        assert r.source_location, f"溯源失败: 无 source_location"
    print("[OK] 规则4: 所有结果均可追溯到原始字幕位置")

    print("\n" + "=" * 60)
    print("  全链路测试通过!")
    print("=" * 60)
    return True


def test_txt_format():
    """测试纯文本格式字幕"""
    print("\n" + "=" * 60)
    print("  纯文本格式测试")
    print("=" * 60)

    test_file = os.path.join(PROJECT_ROOT, 'sample_data', 'meeting_sample_03.txt')
    print(f"\n[输入] {test_file}")

    segments = preprocess_subtitle(test_file)
    print(f"解析段落数: {len(segments)}")
    for seg in segments[:5]:
        time_info = f"[{seg.start_time}]" if seg.start_time else ""
        speaker = f"{seg.speaker}: " if seg.speaker else ""
        print(f"  #{seg.index} {time_info} {speaker}{seg.normalized_text[:50]}")

    results = extract(segments, use_llm=False)
    results = validate(results)
    summary = get_summary(results)

    print(f"\n提取结果: {summary['total']} 条")
    print(f"  正式决策: {summary['decisions']}, 行动项: {summary['actions']}, 讨论: {summary['discussions']}")
    print(f"  需确认: {summary['needs_review']}")

    print("  [OK] 纯文本格式测试通过")
    return True


if __name__ == '__main__':
    try:
        test_pipeline()
        test_txt_format()
        print("\n所有测试通过!")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"\n测试失败: {e}")
        sys.exit(1)
