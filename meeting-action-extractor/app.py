# -*- coding: utf-8 -*-
"""
会议决策行动项提取工具 - Web 应用
M1-M4 基础版全链路 Demo
"""

import os
import sys
import json
import tempfile
import uuid
from datetime import datetime

# 确保项目根目录在 path 中
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from flask import Flask, request, jsonify, render_template, send_file, session

from modules.m1_preprocessor import preprocess_subtitle, SubtitleSegment
from modules.m2_extractor import extract, ExtractionResult
from modules.m3_validator import validate
from modules.m4_output import export_csv, export_excel, get_summary, results_to_dicts

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB
app.secret_key = 'meeting-action-extractor-demo'

# 临时目录
TEMP_DIR = os.path.join(PROJECT_ROOT, 'exports')
os.makedirs(TEMP_DIR, exist_ok=True)

# 示例数据目录
SAMPLE_DIR = os.path.join(PROJECT_ROOT, 'sample_data')
# 用户上传的 .md 文件目录
INBOX_DIR = r'D:\先行区\.dumate\inbox'


@app.route('/')
def index():
    """主页"""
    samples = []
    if os.path.isdir(SAMPLE_DIR):
        for f in sorted(os.listdir(SAMPLE_DIR)):
            if f.endswith(('.srt', '.txt')):
                samples.append(f)
    return render_template('index.html', samples=samples)


@app.route('/api/sample/<filename>')
def get_sample(filename):
    """获取 sample_data 目录下指定示例文件的内容"""
    safe_name = os.path.basename(filename)
    file_path = os.path.join(SAMPLE_DIR, safe_name)
    if not os.path.exists(file_path):
        return jsonify({"error": "文件不存在"}), 404

    for encoding in ['utf-8', 'utf-8-sig', 'gbk', 'utf-16']:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
            return jsonify({"content": content, "filename": safe_name})
        except UnicodeDecodeError:
            continue
    return jsonify({"error": "无法读取文件"}), 500


@app.route('/api/inbox-files')
def get_inbox_files():
    """获取 .dumate/inbox 目录下的 .md 字幕文件列表"""
    files = []
    if os.path.isdir(INBOX_DIR):
        for f in sorted(os.listdir(INBOX_DIR)):
            if f.endswith('.md') and not f.endswith('(1).md'):
                # 提取友好名称
                name_map = {
                    '01-product-planning.md': '01 产品版本规划会',
                    '02-client-delivery-risk.md': '02 客户项目交付风险会',
                    '03-sales-handoff.md': '03 销售与实施交接会',
                    '04-incident-review.md': '04 线上事故复盘会',
                    '05-cross-team-weekly.md': '05 跨部门项目周会',
                }
                files.append({
                    "filename": f,
                    "label": name_map.get(f, f),
                })
    return jsonify({"files": files})


@app.route('/api/inbox-content/<filename>')
def get_inbox_content(filename):
    """获取 .dumate/inbox 目录下指定 .md 文件的内容"""
    safe_name = os.path.basename(filename)
    file_path = os.path.join(INBOX_DIR, safe_name)
    if not os.path.exists(file_path):
        return jsonify({"error": "文件不存在"}), 404

    for encoding in ['utf-8', 'utf-8-sig', 'gbk', 'utf-16']:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
            return jsonify({"content": content, "filename": safe_name})
        except UnicodeDecodeError:
            continue
    return jsonify({"error": "无法读取文件"}), 500


@app.route('/api/process-inbox', methods=['POST'])
def process_inbox():
    """
    直接处理 .dumate/inbox 目录下的 .md 字幕文件
    输入：文件名
    输出：全链路提取结果
    """
    try:
        filename = request.json.get('filename', '')
        if not filename:
            return jsonify({"error": "请指定文件名"}), 400

        safe_name = os.path.basename(filename)
        file_path = os.path.join(INBOX_DIR, safe_name)
        if not os.path.exists(file_path):
            return jsonify({"error": f"文件不存在: {safe_name}"}), 404

        use_llm = request.json.get('use_llm', False)

        # === M1: 字幕预处理 ===
        m1_start = datetime.now()
        segments = preprocess_subtitle(file_path)
        m1_time = (datetime.now() - m1_start).total_seconds()

        if not segments:
            return jsonify({"error": "未能从输入中解析出有效字幕内容"}), 400

        m1_result = {
            "status": "ok",
            "segment_count": len(segments),
            "time_cost": f"{m1_time:.3f}s",
            "segments": [s.to_dict() for s in segments],
        }

        # === M2: 识别提取 ===
        m2_start = datetime.now()
        results = extract(segments, use_llm=use_llm)
        m2_time = (datetime.now() - m2_start).total_seconds()

        m2_result = {
            "status": "ok",
            "result_count": len(results),
            "time_cost": f"{m2_time:.3f}s",
            "results": [r.to_dict() for r in results],
        }

        # === M3: 合规校验 ===
        m3_start = datetime.now()
        results = validate(results)
        m3_time = (datetime.now() - m3_start).total_seconds()

        m3_result = {
            "status": "ok",
            "time_cost": f"{m3_time:.3f}s",
            "needs_review_count": sum(1 for r in results if r.needs_review),
        }

        # === M4: 结果输出 ===
        m4_start = datetime.now()
        summary = get_summary(results)
        rows = results_to_dicts(results)
        m4_time = (datetime.now() - m4_start).total_seconds()

        m4_result = {
            "status": "ok",
            "time_cost": f"{m4_time:.3f}s",
            "summary": summary,
        }

        # 保存结果到session供导出使用
        session['last_results'] = json.dumps([r.to_dict() for r in results], ensure_ascii=False)

        return jsonify({
            "success": True,
            "filename": safe_name,
            "modules": {
                "m1": m1_result,
                "m2": m2_result,
                "m3": m3_result,
                "m4": m4_result,
            },
            "results": rows,
            "summary": summary,
            "total_time": f"{m1_time + m2_time + m3_time + m4_time:.3f}s",
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/process', methods=['POST'])
def process():
    """
    全链路处理：M1 -> M2 -> M3 -> M4
    输入：字幕文件 或 纯文本内容
    输出：提取结果 + 统计概览 + 各模块处理状态
    """
    try:
        # 获取输入
        file = request.files.get('file')
        text_content = request.form.get('text_content', '').strip()
        use_llm = request.form.get('use_llm', 'true') == 'true'

        if not file and not text_content:
            return jsonify({"error": "请上传文件或粘贴字幕文本"}), 400

        # 保存到临时文件
        if file:
            # 检测文件格式
            filename = file.filename or 'input.txt'
            ext = os.path.splitext(filename)[1].lower()
            if ext not in ('.srt', '.txt', '.md'):
                return jsonify({"error": "仅支持 .srt / .txt / .md 格式文件"}), 400

            tmp_name = f"{uuid.uuid4().hex}{ext}"
            tmp_path = os.path.join(TEMP_DIR, tmp_name)
            file.save(tmp_path)
        else:
            # 纯文本输入，保存为临时txt
            tmp_name = f"{uuid.uuid4().hex}.txt"
            tmp_path = os.path.join(TEMP_DIR, tmp_name)
            with open(tmp_path, 'w', encoding='utf-8') as f:
                f.write(text_content)

        # === M1: 字幕预处理 ===
        m1_start = datetime.now()
        segments = preprocess_subtitle(tmp_path)
        m1_time = (datetime.now() - m1_start).total_seconds()

        if not segments:
            return jsonify({"error": "未能从输入中解析出有效字幕内容"}), 400

        m1_result = {
            "status": "ok",
            "segment_count": len(segments),
            "time_cost": f"{m1_time:.3f}s",
            "segments": [s.to_dict() for s in segments],
        }

        # === M2: LLM识别 ===
        m2_start = datetime.now()
        results = extract(segments, use_llm=use_llm)
        m2_time = (datetime.now() - m2_start).total_seconds()

        m2_result = {
            "status": "ok",
            "result_count": len(results),
            "time_cost": f"{m2_time:.3f}s",
            "results": [r.to_dict() for r in results],
        }

        # === M3: 合规校验 ===
        m3_start = datetime.now()
        results = validate(results)
        m3_time = (datetime.now() - m3_start).total_seconds()

        m3_result = {
            "status": "ok",
            "time_cost": f"{m3_time:.3f}s",
            "needs_review_count": sum(1 for r in results if r.needs_review),
        }

        # === M4: 结果输出 ===
        m4_start = datetime.now()
        summary = get_summary(results)
        rows = results_to_dicts(results)
        m4_time = (datetime.now() - m4_start).total_seconds()

        m4_result = {
            "status": "ok",
            "time_cost": f"{m4_time:.3f}s",
            "summary": summary,
        }

        # 保存结果到session供导出使用
        session['last_results'] = json.dumps([r.to_dict() for r in results], ensure_ascii=False)

        # 清理临时文件
        try:
            os.remove(tmp_path)
        except OSError:
            pass

        return jsonify({
            "success": True,
            "modules": {
                "m1": m1_result,
                "m2": m2_result,
                "m3": m3_result,
                "m4": m4_result,
            },
            "results": rows,
            "summary": summary,
            "total_time": f"{m1_time + m2_time + m3_time + m4_time:.3f}s",
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/export', methods=['POST'])
def export():
    """导出结果为CSV或Excel"""
    try:
        fmt = request.json.get('format', 'csv')
        results_json = session.get('last_results')

        if not results_json:
            return jsonify({"error": "没有可导出的结果，请先执行提取"}), 400

        data = json.loads(results_json)
        results = []
        for item in data:
            results.append(ExtractionResult(
                content_type=item.get('content_type', ''),
                description=item.get('description', ''),
                owner=item.get('owner', ''),
                deadline=item.get('deadline', ''),
                source_location=item.get('source_location', ''),
                needs_review=item.get('needs_review', False),
                confidence=item.get('confidence', 0),
                raw_text=item.get('raw_text', ''),
            ))

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        if fmt == 'excel':
            output_path = os.path.join(TEMP_DIR, f'提取结果_{timestamp}.xlsx')
            export_excel(results, output_path)
            return send_file(output_path, as_attachment=True,
                           download_name=f'提取结果_{timestamp}.xlsx')
        else:
            output_path = os.path.join(TEMP_DIR, f'提取结果_{timestamp}.csv')
            export_csv(results, output_path, include_extended=True)
            return send_file(output_path, as_attachment=True,
                           download_name=f'提取结果_{timestamp}.csv')

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/env-check')
def env_check():
    """检查环境配置"""
    api_key = os.environ.get('OPENAI_API_KEY', '')
    base_url = os.environ.get('OPENAI_BASE_URL', '')
    model = os.environ.get('OPENAI_MODEL', 'qwen-plus')

    return jsonify({
        "llm_available": bool(api_key),
        "model": model,
        "base_url": base_url or "(默认)",
    })


if __name__ == '__main__':
    print("=" * 60)
    print("  会议决策行动项提取工具 - Demo")
    print("  赛道: 会议决策到任务执行自动化")
    print("  模块: M1(预处理) -> M2(LLM识别) -> M3(合规校验) -> M4(结果输出)")
    print("=" * 60)

    # 环境检查
    api_key = os.environ.get('OPENAI_API_KEY', '')
    if api_key:
        model = os.environ.get('OPENAI_MODEL', 'qwen-plus')
        print(f"  [OK] LLM 已配置: {model}")
    else:
        print("  [!] 未检测到 OPENAI_API_KEY，将使用规则兜底模式")
        print("      设置方法: set OPENAI_API_KEY=your_key")
        print("      可选: set OPENAI_BASE_URL=your_endpoint")
        print("      可选: set OPENAI_MODEL=qwen-plus")

    print(f"\n  访问地址: http://127.0.0.1:5000")
    print("=" * 60)

    # 尝试用 waitress 启动，否则回退到 Flask dev server
    try:
        import waitress
        waitress.serve(app, host='127.0.0.1', port=5000)
    except ImportError:
        print("\n  [ waitress 未安装，使用内置服务器 ]")
        print("  建议执行: pip install waitress")
        print("=" * 60)
        app.run(host='127.0.0.1', port=5000, debug=True)
