# 会议决策行动项提取工具

## 项目简介

基于会议字幕的决策与行动项自动提取工具，覆盖从字幕导入到结构化结果导出的完整链路。

**赛道**：会议决策到任务执行自动化

## 系统架构

```
字幕文件 → M1 预处理 → M2 LLM识别 → M3 合规校验 → M4 结果输出 → CSV/Excel
```

| 模块 | 职责 | 核心能力 |
|------|------|---------|
| M1 字幕预处理 | 解析字幕文件，归一化文本，绑定时间戳与行号 | SRT/纯文本解析、发言人提取、语义段落切分 |
| M2 决策与行动项识别 | 区分正式决策、行动项、普通讨论，抽取实体 | LLM大模型提取（支持规则兜底）、责任人/截止时间识别、位置锚定 |
| M3 合规校验与标记 | 校验信息完整性，过滤非正式结论，标记待确认项 | 完整性校验、业务规则过滤、人工确认标记、溯源绑定 |
| M4 结果输出 | 导出结构化表格，支持溯源跳转 | CSV/Excel导出、溯源上下文展示、统计概览 |

## 输出字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| content_type | 枚举 | 是 | 内容类型：正式决策/行动项/普通讨论 |
| description | 文本 | 是 | 决策或任务的结构化描述 |
| owner | 文本 | 否* | 责任人姓名（缺失时标记需人工确认） |
| deadline | 日期 | 否* | 截止时间 YYYY-MM-DD（缺失时标记需人工确认） |
| source_location | 文本 | 是 | 原始字幕行号与时间区间 |
| needs_review | 布尔 | 是 | 是否需要人工确认 |

## 快速开始

### 1. 安装依赖

```bash
pip install flask openai pandas openpyxl
```

### 2. 启动 Web 应用

**方式一：批处理脚本（Windows）**

```bash
双击 start.bat
```

**方式二：命令行启动**

```bash
python app.py
```

启动后访问 http://127.0.0.1:5000

### 3. 使用 LLM 大模型提取（可选）

如需启用 LLM 提取模式（准确率更高），设置以下环境变量：

```bash
# Windows CMD
set OPENAI_API_KEY=your_api_key
set OPENAI_BASE_URL=your_endpoint    # 可选，如使用千帆等兼容接口
set OPENAI_MODEL=qwen-plus           # 可选，默认 qwen-plus

# Git Bash
export OPENAI_API_KEY=your_api_key
export OPENAI_BASE_URL=your_endpoint
export OPENAI_MODEL=qwen-plus
```

未配置 API Key 时，工具自动降级为规则模式运行。

### 4. 使用示例

1. 打开 Web 界面
2. 点击示例字幕按钮加载测试数据，或上传自己的 .srt/.txt 字幕文件
3. 点击"开始提取"
4. 查看 M1-M4 各模块处理状态和提取结果
5. 导出 CSV 或 Excel 格式结果

## 业务合规规则

- 不得把讨论意见当作正式决定
- 不得虚构责任人和截止时间
- 信息不完整时必须标记需人工确认
- 未经本人确认不得替他人作出承诺
- 所有提取结果可追溯到原始会议内容

## 项目结构

```
meeting-action-extractor/
  app.py                    # Flask Web 应用主入口
  run.py                    # 一键启动脚本
  start.bat                 # Windows 启动脚本
  test_pipeline.py          # 全链路测试脚本
  modules/
    __init__.py
    m1_preprocessor.py      # M1 字幕预处理模块
    m2_extractor.py         # M2 LLM识别模块
    m3_validator.py         # M3 合规校验模块
    m4_output.py            # M4 结果输出模块
  templates/
    index.html              # Web 界面
  sample_data/
    meeting_sample_01.srt   # 示例字幕（产品周会）
    meeting_sample_02.srt   # 示例字幕（项目启动会）
    meeting_sample_03.txt   # 示例字幕（纯文本格式）
  exports/                  # 导出结果目录
```

## 技术选型

| 方面 | 选型 | 说明 |
|------|------|------|
| Web 框架 | Flask 3.x | 轻量级，适合 Demo |
| LLM 接入 | OpenAI SDK | 兼容千帆/OpenAI等接口 |
| 数据处理 | pandas | CSV/Excel 导出 |
| 字幕解析 | 自研 | 支持 SRT 和纯文本格式 |
| 兜底方案 | 规则引擎 | LLM 不可用时自动降级 |
