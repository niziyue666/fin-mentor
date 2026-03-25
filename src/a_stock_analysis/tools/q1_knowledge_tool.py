"""
Q1市场技术分析知识检索工具
根据实时数据触发对应知识章节，返回教学内容
"""
import json
import os
import re
from pathlib import Path
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Type


class Q1KnowledgeSchema(BaseModel):
    """Q1知识检索工具输入参数"""
    price: float = Field(..., description="当前股价")
    ma5: float = Field(..., description="5日均线")
    ma20: float = Field(..., description="20日均线")
    rsi: float = Field(..., description="RSI指标，0-100")
    volume_ratio: float = Field(..., description="量比，今日成交量/5日平均成交量")
    daily_change: float = Field(..., description="当日涨跌幅，小数形式，如 -0.05 表示跌5%")


class Q1KnowledgeTool(BaseTool):
    """Q1市场技术分析知识检索工具

    根据实时技术指标数据，自动判断应该检索哪些知识章节。
    采用数据驱动触发机制，不是固定检索。
    """

    name: str = "Q1KnowledgeTool"
    description: str = "根据市场技术指标数据（MA均线、RSI、量比等），自动检索对应的知识内容。" \
                       "用于Q1市场分析时获取专业解读，确保分析引用知识库而非自己编造。"
    args_schema: Type[BaseModel] = Q1KnowledgeSchema

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
        return Path(__file__).parent.parent / "knowledge" / "raw_sources" / "technical"

    @property
    def rules_file(self):
        return self.knowledge_dir / "q1_trigger_rules.json"

    @property
    def markdown_file(self):
        return self.knowledge_dir / "q1_market_knowledge.md"

    def _load_rules(self) -> dict:
        """加载触发规则JSON"""
        try:
            with open(self.rules_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            return {"triggers": [], "default_fallback": {}}

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

    def _extract_section_content(self, section_name: str) -> str:
        """从Markdown文件中提取指定章节内容"""
        try:
            with open(self.markdown_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # 匹配章节：## §X 章节名 或 ## §X-XXX 章节名
            pattern = rf"(##\s+{re.escape(section_name)}.*?)(?=\n##\s+§|\n---\n\*文件路径|\Z)"

            match = re.search(pattern, content, re.DOTALL)
            if match:
                return match.group(1).strip()

            # 如果精确匹配失败，尝试模糊匹配
            for line in content.split('\n'):
                if section_name.replace("§", "§").replace(" ", "") in line:
                    # 找到章节标题，提取该章节
                    idx = content.find(line)
                    remaining = content[idx:]
                    # 找到下一个 ## 或文件结尾
                    next_section = re.search(r'\n##\s+§', remaining[20:])
                    if next_section:
                        return remaining[:20 + next_section.start()].strip()
                    return remaining.strip()

            return f"未找到章节：{section_name}"

        except Exception as e:
            return f"读取知识库失败: {str(e)}"

    def _run(self, price: float, ma5: float, ma20: float,
             rsi: float, volume_ratio: float, daily_change: float):
        """执行知识检索"""

        # 构建数据字典
        data = {
            "price": price,
            "ma5": ma5,
            "ma20": ma20,
            "rsi": rsi,
            "volume_ratio": volume_ratio,
            "daily_change": daily_change
        }

        # 获取触发的章节
        triggered = self._get_triggered_sections(data)

        if not triggered:
            # 无触发，使用默认章节
            fallback = self.rules.get("default_fallback", {})
            default_section = fallback.get("handling", "§3 多头排列趋势跟踪")
            # 从handling中提取章节名
            section_name = re.search(r"§\d+[^\s]+", default_section)
            if section_name:
                section_name = section_name.group()
            else:
                section_name = "§3 多头排列趋势跟踪"

            content = self._extract_section_content(section_name)
            return f"【默认分析框架】\n\n{content}"

        # 处理冲突规则
        conflict_rules = self.rules.get("conflict_rules", [])
        triggered_ids = [t["id"] for t in triggered]

        # 检查是否有冲突
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

        # 输出其他知识内容
        result += "\n\n".join(output_parts)

        # 添加冲突处理说明
        if conflict_note:
            result += conflict_note

        # 添加触发的条件摘要
        triggered_summary = ", ".join([f"{t['id']}（{t['name']}）" for t in triggered])
        result += f"\n\n---\n*触发条件：{triggered_summary}*"

        return result
