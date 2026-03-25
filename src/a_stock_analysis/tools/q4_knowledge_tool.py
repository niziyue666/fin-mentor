"""
Q4投资评级知识检索工具
根据Q1/Q2/Q3的结论触发对应知识章节，返回投资评级教学
"""
import json
import os
import re
from pathlib import Path
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Type


class Q4KnowledgeSchema(BaseModel):
    """Q4知识检索工具输入参数"""
    q1_trend: str = Field(..., description="Q1均线趋势结论：多头排列/强势整理/空头排列/死叉")
    q2_score: int = Field(..., description="Q2财务评分，0-100")
    q2_stock_type: str = Field(..., description="Q2股票类型：盈利股/亏损股")
    q3_sentiment: str = Field(..., description="Q3综合情绪判断：看多/观望/看空")
    q3_structure: str = Field(..., description="Q3情绪结构：黑天鹅型/趋势型/博弈型/钝化型/无明显信号")
    daily_change: float = Field(..., description="当日涨跌幅，小数形式，如 -0.05 表示跌5%")


class Q4KnowledgeTool(BaseTool):
    """Q4投资评级知识检索工具

    根据Q1/Q2/Q3的结论自动判断应该检索哪些知识章节。
    采用数据驱动触发机制，不是固定检索。
    """

    name: str = "Q4KnowledgeTool"
    description: str = "根据Q1/Q2/Q3的综合结论，自动检索对应的投资评级知识内容。" \
                       "用于Q4投资建议时获取专业评级框架，确保评级引用知识库而非自己编造。"
    args_schema: Type[BaseModel] = Q4KnowledgeSchema

    # 类级别的缓存
    _rules_cache: dict = {}

    def __init__(self, **data):
        super().__init__(**data)

    def model_post_init(self, __context):
        super().model_post_init(__context)
        # 知识库路径（只在第一次初始化时加载）
        if not hasattr(self, '_rules_loaded') or not self._rules_cache:
            self.__class__._rules_cache = self._load_rules()
            self.__class__._rules_loaded = True

    @property
    def rules(self):
        return self.__class__._rules_cache

    @property
    def knowledge_dir(self):
        return Path(__file__).parent.parent / "knowledge" / "raw_sources" / "strategy"

    @property
    def rules_file(self):
        return self.knowledge_dir / "q4_trigger_rules.json"

    @property
    def markdown_file(self):
        return self.knowledge_dir / "q4_strategy_knowledge.md"

    def _load_rules(self) -> dict:
        """加载触发规则JSON"""
        try:
            with open(self.rules_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载Q4规则失败: {e}")
            return {"triggers": [], "rating_definitions": {}}

    def _evaluate_condition(self, condition: str, data: dict) -> bool:
        """执行trigger条件判断"""
        try:
            # 使用eval执行Python表达式
            result = eval(condition, {"__builtins__": {}}, data)
            return bool(result)
        except Exception:
            return False

    def _get_triggered_sections(self, data: dict) -> list:
        """获取所有触发的章节"""
        triggered = []

        # 优先级顺序：critical > high > medium
        priority_order = {"critical": 0, "high": 1, "medium": 2}

        for trigger in self.rules.get("triggers", []):
            condition = trigger.get("condition", "")
            if self._evaluate_condition(condition, data):
                triggered.append({
                    "id": trigger.get("id"),
                    "name": trigger.get("name"),
                    "section": trigger.get("section"),
                    "priority": trigger.get("priority", "medium"),
                    "rating_hint": trigger.get("rating_hint"),
                    "note": trigger.get("note", "")
                })

        # 按优先级排序
        triggered.sort(key=lambda x: priority_order.get(x["priority"], 99))

        return triggered

    def _extract_section_content(self, section_name: str) -> str:
        """从Markdown文件中提取指定章节内容"""
        try:
            with open(self.markdown_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # 匹配章节：## §X 章节名
            pattern = rf"(##\s+{re.escape(section_name)}.*?)(?=\n##\s+§|\n---\n\*文件路径|\Z)"

            match = re.search(pattern, content, re.DOTALL)
            if match:
                return match.group(1).strip()

            # 模糊匹配
            for line in content.split('\n'):
                if section_name.replace("§", "§").replace(" ", "") in line:
                    idx = content.find(line)
                    remaining = content[idx:]
                    next_section = re.search(r'\n##\s+§', remaining[20:])
                    if next_section:
                        return remaining[:20 + next_section.start()].strip()
                    return remaining.strip()

            return f"未找到章节：{section_name}"

        except Exception as e:
            return f"读取知识库失败: {str(e)}"

    def _run(self, q1_trend: str, q2_score: int, q2_stock_type: str,
             q3_sentiment: str, q3_structure: str, daily_change: float):
        """执行知识检索"""

        # 构建数据字典
        data = {
            "q1_trend": q1_trend,
            "q2_score": q2_score,
            "q2_stock_type": q2_stock_type,
            "q3_sentiment": q3_sentiment,
            "q3_structure": q3_structure,
            "daily_change": daily_change
        }

        # 获取触发的章节
        triggered = self._get_triggered_sections(data)

        if not triggered:
            # 无触发，返回默认提示
            return "【提示】当前数据未触发特定评级章节，请根据通用评级框架进行分析。"

        # 处理冲突规则
        conflict_rules = self.rules.get("conflict_rules", [])

        # 检查冲突
        conflict_note = ""
        for rule in conflict_rules:
            conflict_ids = []
            for conflict_id in rule["conflict"].split("与"):
                conflict_id = conflict_id.strip().replace("（", "(").replace("）", ")")
                for t in triggered:
                    if conflict_id in f"{t['id']}（{t['name']}）":
                        conflict_ids.append(t['id'])

            if len(set(conflict_ids)) >= 2:
                conflict_note = f"\n\n【冲突处理】{rule['handling']}"
                break

        # 按优先级构建输出
        output_parts = []
        critical_warnings = []
        rating_hints = []

        for t in triggered:
            section_content = self._extract_section_content(t["section"])

            if t["priority"] == "critical":
                critical_warnings.append(f"【{t['name']}】{section_content.split('###')[0]}")
            else:
                output_parts.append(f"## {t['section']}\n{section_content}")

            if t.get("rating_hint"):
                rating_hints.append(t["rating_hint"])

        # 构建最终输出
        result = ""

        # 先输出critical警告
        if critical_warnings:
            result += "【⚠️ 重要警告】\n" + "\n".join(critical_warnings) + "\n\n"

        # 输出其他知识内容
        result += "\n\n".join(output_parts)

        # 添加冲突处理说明
        if conflict_note:
            result += conflict_note

        # 添加评级建议摘要
        if rating_hints:
            result += f"\n\n【评级建议】{', '.join(set(rating_hints))}"

        # 评级定义速查
        rating_defs = self.rules.get("rating_definitions", {})
        if rating_defs:
            result += "\n\n【评级定义】\n"
            for rating, desc in rating_defs.items():
                result += f"- {rating}: {desc}\n"

        # 添加触发的条件摘要
        triggered_summary = ", ".join([f"{t['id']}（{t['name']}）" for t in triggered])
        result += f"\n\n---\n*触发条件：{triggered_summary}*"

        return result
