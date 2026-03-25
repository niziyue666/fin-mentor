# 🤖 Fin-Mentor Pro

> 基于 CrewAI 的 A 股智能投资分析系统

---

## ✨ 功能特性

| 特性 | 说明 |
|------|------|
| 🤖 多智能体协作 | 5 个 AI Agent：市场分析师 → 财务分析师 → 情绪分析师 → 投资顾问 → 追问导师 |
| 📊 四象限仪表盘 | Q1 技术面 · Q2 财务面 · Q3 情绪面 · Q4 投资建议 |
| 📈 实时数据 | A 股实时行情（tinyshare + akshare-one） |
| 📚 RAG 知识库 | 根据数据特征触发相关知识，分析更精准 |
| 💬 追问系统 | 直接传递报告内容给 AI，支持深入追问 |

---

## 🛠 技术栈

- **Web**: Streamlit
- **多智能体**: CrewAI
- **数据源**: tinyshare · akshare-one
- **RAG**: Chroma + sentence-transformers
- **LLM**: LiteLLM（支持 Moonshot / OpenAI / Claude 等）

---

## 🚀 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 填写你的 API Key

# 3. 启动
streamlit run app.py
```

---

## 📁 项目结构

```
stock_analysis_a_stock/
├── app.py                      # Streamlit Web 入口
├── requirements.txt             # 依赖
├── .env.example               # 环境变量示例
├── assets/                    # 演示视频
└── src/a_stock_analysis/
    ├── crew.py               # CrewAI 团队配置
    ├── config/
    │   ├── agents.yaml       # Agent 角色定义
    │   └── tasks.yaml        # 任务 prompt
    ├── tools/                 # 工具集
    │   ├── a_stock_data_tool.py    # 行情数据（MA、RSI等）
    │   ├── financial_tool.py        # 财务分析（ROE、PE等）
    │   ├── market_sentiment_tool.py # 情绪分析（资金流向、新闻）
    │   ├── knowledge_tool.py        # RAG 知识库检索
    │   └── calculator_tool.py       # 安全计算
    └── knowledge/
        └── raw_sources/      # RAG 知识文档
```

---

## 🤖 Agent 职责

| Agent | 职责 |
|-------|------|
| 市场分析师 | 技术面分析（K线、均线、RSI、趋势判断） |
| 财务分析师 | 财务分析（ROE、毛利率、PE/PB、估值） |
| 情绪分析师 | 情绪面分析（资金流向、新闻舆情、市场情绪） |
| 投资顾问 | 综合研判，给出投资评级和建议 |
| 追问导师 | 根据报告内容回答用户追问 |

---

## 📖 核心流程

```
输入股票代码 → Q1 技术分析 → Q2 财务分析 → Q3 情绪分析 → Q4 综合建议 → 用户追问
```

---

## ⚠️ 免责声明

本系统仅供学习研究使用，不构成投资建议。投资有风险，入市需谨慎。
