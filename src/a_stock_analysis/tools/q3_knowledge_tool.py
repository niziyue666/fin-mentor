"""
Q3情绪分析知识检索工具
根据市场情绪数据触发对应知识章节，返回情绪分析教学
"""
import json
import os
import re
from pathlib import Path
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Type, Optional


class Q3KnowledgeSchema(BaseModel):
    """Q3知识检索工具输入参数"""
    sentiment_score: float = Field(..., description="综合情绪分，-100到100")
    sentiment_structure: str = Field(..., description="情绪结构类型：黑天鹅型/趋势型/博弈型/钝化型/无明显信号")
    has_regulatory_news: bool = Field(..., description="是否含监管介入/高管被查新闻")
    has_policy_news: bool = Field(..., description="是否含行业政策/监管变化新闻")
    has_earnings_news: bool = Field(..., description="是否含业绩/财报相关新闻")
    retained_news_count: int = Field(..., description="去重后保留的有效新闻数量")
    raw_news_count: int = Field(..., description="去重前原始新闻数量")
    negative_days: int = Field(..., description="负面情绪持续天数")
    market_breadth: float = Field(..., description="市场广度，上涨股数/总股数，0-1")
    days_since_event: int = Field(0, description="黑天鹅事件发生距今天数")


class Q3KnowledgeTool(BaseTool):
    """Q3情绪分析知识检索工具

    根据市场情绪数据自动判断应该检索哪些知识章节。
    采用数据驱动触发机制，不是固定检索。
    """

    name: str = "Q3KnowledgeTool"
    description: str = "根据市场情绪数据（情绪分、情绪结构、新闻类型等），自动检索对应的情绪分析知识内容。" \
                       "用于Q3情绪分析时获取专业解读，确保分析引用知识库而非自己编造。"
    args_schema: Type[BaseModel] = Q3KnowledgeSchema

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
        return Path(__file__).parent.parent / "knowledge" / "raw_sources" / "sentiment"

    @property
    def rules_file(self):
        return self.knowledge_dir / "q3_trigger_rules.json"

    @property
    def markdown_file(self):
        return self.knowledge_dir / "q3_sentiment_knowledge.md"

    def _load_rules(self) -> dict:
        """加载触发规则JSON"""
        try:
            with open(self.rules_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载Q3规则失败: {e}")
            return {"triggers": [], "forced_output_rules": [], "dedup_output_rules": {}}

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
                    "note": trigger.get("note", "")
                })

        # 按优先级排序
        triggered.sort(key=lambda x: priority_order.get(x["priority"], 99))

        return triggered

    def _get_forced_outputs(self, triggered: list, data: dict) -> list:
        """获取强制输出内容"""
        forced_rules = self.rules.get("forced_output_rules", [])
        triggered_ids = [t["id"] for t in triggered]

        forced_outputs = []
        for rule in forced_rules:
            trigger = rule.get("trigger", "")
            for tid in triggered_ids:
                if tid in trigger:
                    text = rule.get("forced_text", "")
                    # 替换占位符
                    text = text.replace("{retained_news_count}", str(data.get("retained_news_count", 0)))
                    text = text.replace("{market_breadth}", str(data.get("market_breadth", 0)))
                    forced_outputs.append(text)

        return forced_outputs

    def _get_dedup_info(self, data: dict) -> str:
        """获取去重信息"""
        raw = data.get("raw_news_count", 0)
        retained = data.get("retained_news_count", 0)

        if raw == 0:
            return ""

        dedup_rate = (raw - retained) / raw if raw > 0 else 0

        info = f"共获取{raw}条原始新闻，去重后保留{retained}条有效新闻（去重率{dedup_rate:.0%}）"

        if dedup_rate > 0.6:
            info += "。大量重复转载，独立信息来源有限，情绪判断权重降低"

        return info

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

    def _run(self, sentiment_score: float, sentiment_structure: str,
             has_regulatory_news: bool, has_policy_news: bool, has_earnings_news: bool,
             retained_news_count: int, raw_news_count: int, negative_days: int,
             market_breadth: float, days_since_event: int = 0):
        """执行知识检索"""

        # 构建数据字典
        data = {
            "sentiment_score": sentiment_score,
            "sentiment_structure": sentiment_structure,
            "has_regulatory_news": has_regulatory_news,
            "has_policy_news": has_policy_news,
            "has_earnings_news": has_earnings_news,
            "retained_news_count": retained_news_count,
            "raw_news_count": raw_news_count,
            "negative_days": negative_days,
            "market_breadth": market_breadth,
            "days_since_event": days_since_event
        }

        # 获取触发的章节
        triggered = self._get_triggered_sections(data)

        if not triggered:
            # 无触发，返回默认提示
            return "【提示】当前情绪数据无特殊信号，使用标准情绪分析框架。\n\n" \
                   f"【情绪概况】当前情绪分{sentiment_score}，情绪结构为「{sentiment_structure}」"

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

        # 获取强制输出
        forced_outputs = self._get_forced_outputs(triggered, data)

        # 获取去重信息
        dedup_info = self._get_dedup_info(data)

        # 按优先级构建输出
        output_parts = []
        critical_warnings = []

        for t in triggered:
            section_content = self._extract_section_content(t["section"])

            if t["priority"] == "critical":
                critical_warnings.append(f"【{t['name']}】{section_content.split('###')[0]}")
            else:
                output_parts.append(f"## {t['section']}\n{section_content}")

        # 构建最终输出
        result = ""

        # 先输出critical警告
        if critical_warnings:
            result += "【⚠️ 重要警告】\n" + "\n".join(critical_warnings) + "\n\n"

        # 输出强制输出内容
        for forced in forced_outputs:
            result += f"【强制提示】{forced}\n\n"

        # 输出去重信息
        if dedup_info:
            result += f"【去重情况】{dedup_info}\n\n"

        # 输出其他知识内容
        result += "\n\n".join(output_parts)

        # 添加冲突处理说明
        if conflict_note:
            result += conflict_note

        # 添加触发的条件摘要
        triggered_summary = ", ".join([f"{t['id']}（{t['name']}）" for t in triggered])
        result += f"\n\n---\n*触发条件：{triggered_summary}*"

        return result
