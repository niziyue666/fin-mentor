"""
Q2财务分析知识检索工具
根据财务指标数据触发对应知识章节，返回财务分析教学
"""
import json
import os
import re
from pathlib import Path
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Type, Optional, List


class Q2KnowledgeSchema(BaseModel):
    """Q2知识检索工具输入参数"""
    net_profit: float = Field(..., description="净利润，负数为亏损")
    net_profit_last_q: float = Field(..., description="上季度净利润")
    consecutive_loss_q: int = Field(..., description="连续亏损季度数")
    net_profit_yoy: float = Field(..., description="净利润同比变化率，小数形式")
    debt_ratio: float = Field(..., description="资产负债率，小数形式")
    pe_ttm: Optional[float] = Field(None, description="PE(TTM)，亏损时为None")
    pe_percentile_3y: Optional[float] = Field(None, description="PE近3年历史分位，0-1")
    pb: float = Field(..., description="市净率PB")
    roe: float = Field(..., description="净资产收益率，小数形式")
    revenue_growth: float = Field(..., description="营收同比增速，小数形式")
    revenue_growth_q_list: List[float] = Field(default_factory=list, description="最近3个季度营收增速列表")
    receivable_ratio: float = Field(..., description="应收账款/营收，小数形式")
    cfo_to_net_profit: Optional[float] = Field(None, description="经营现金流/净利润")
    net_profit_qoq: float = Field(..., description="净利润环比变化率，小数形式")
    gross_margin: float = Field(..., description="毛利率，小数形式")


class Q2KnowledgeTool(BaseTool):
    """Q2财务分析知识检索工具

    根据财务指标数据自动判断应该检索哪些知识章节。
    采用数据驱动触发机制，不是固定检索。
    """

    name: str = "Q2KnowledgeTool"
    description: str = "根据财务指标数据（净利润、负债率、PE、ROE等），自动检索对应的财务分析知识内容。" \
                       "用于Q2财务分析时获取专业解读，确保分析引用知识库而非自己编造。"
    args_schema: Type[BaseModel] = Q2KnowledgeSchema

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
        return Path(__file__).parent.parent / "knowledge" / "raw_sources" / "financial"

    @property
    def rules_file(self):
        return self.knowledge_dir / "q2_trigger_rules.json"

    @property
    def markdown_file(self):
        return self.knowledge_dir / "q2_financial_knowledge.md"

    def _load_rules(self) -> dict:
        """加载触发规则JSON"""
        try:
            with open(self.rules_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"加载Q2规则失败: {e}")
            return {"triggers": [], "score_cap_rules": [], "forced_output_rules": []}

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

    def _get_score_cap(self, triggered: list) -> tuple:
        """获取评分上限"""
        score_cap_rules = self.rules.get("score_cap_rules", [])
        triggered_ids = [t["id"] for t in triggered]

        # 检查评分上限规则
        for rule in score_cap_rules:
            condition = rule.get("condition", "")
            if "T01" in condition and "T01" in triggered_ids:
                if "T04" in condition and "T04" in triggered_ids:
                    return rule.get("score_cap", 50), rule.get("reason", "")
                elif "T04" not in condition:
                    return rule.get("score_cap", 75), rule.get("reason", "")
            elif "T04" in condition and "T04" in triggered_ids:
                if "T01" not in condition:
                    return rule.get("score_cap", 60), rule.get("reason", "")

        return 100, ""

    def _get_forced_outputs(self, triggered: list) -> list:
        """获取强制输出内容"""
        forced_rules = self.rules.get("forced_output_rules", [])
        triggered_ids = [t["id"] for t in triggered]

        forced_outputs = []
        for rule in forced_rules:
            trigger = rule.get("trigger", "")
            for tid in triggered_ids:
                if tid in trigger:
                    forced_outputs.append(rule.get("forced_text", ""))

        return forced_outputs

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

    def _run(self, net_profit: float, net_profit_last_q: float, consecutive_loss_q: int,
             net_profit_yoy: float, debt_ratio: float, pb: float, roe: float,
             revenue_growth: float, receivable_ratio: float, net_profit_qoq: float,
             gross_margin: float, pe_ttm: Optional[float] = None,
             pe_percentile_3y: Optional[float] = None,
             revenue_growth_q_list: List[float] = None,
             cfo_to_net_profit: Optional[float] = None):
        """执行知识检索"""

        # 构建数据字典
        data = {
            "net_profit": net_profit,
            "net_profit_last_q": net_profit_last_q,
            "consecutive_loss_q": consecutive_loss_q,
            "net_profit_yoy": net_profit_yoy,
            "debt_ratio": debt_ratio,
            "pe_ttm": pe_ttm,
            "pe_percentile_3y": pe_percentile_3y,
            "pb": pb,
            "roe": roe,
            "revenue_growth": revenue_growth,
            "revenue_growth_q_list": revenue_growth_q_list or [],
            "receivable_ratio": receivable_ratio,
            "cfo_to_net_profit": cfo_to_net_profit,
            "net_profit_qoq": net_profit_qoq,
            "gross_margin": gross_margin
        }

        # 获取触发的章节
        triggered = self._get_triggered_sections(data)

        if not triggered:
            # 无触发，返回默认提示
            return "【提示】当前财务数据无特殊风险触发，使用标准财务分析框架。"

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

        # 获取评分上限
        score_cap, score_cap_reason = self._get_score_cap(triggered)

        # 获取强制输出
        forced_outputs = self._get_forced_outputs(triggered)

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

        # 输出其他知识内容
        result += "\n\n".join(output_parts)

        # 添加冲突处理说明
        if conflict_note:
            result += conflict_note

        # 添加评分上限说明
        if score_cap < 100:
            result += f"\n\n【评分上限】当前触发条件导致财务评分上限锁定为 {score_cap} 分\n原因：{score_cap_reason}"

        # 添加触发的条件摘要
        triggered_summary = ", ".join([f"{t['id']}（{t['name']}）" for t in triggered])
        result += f"\n\n---\n*触发条件：{triggered_summary}*"

        return result
