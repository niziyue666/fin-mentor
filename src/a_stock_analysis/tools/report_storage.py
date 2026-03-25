"""
报告存储工具 - 使用JSON文件存储，简单可靠
"""
import os
import json
from pathlib import Path
from typing import Optional
from pydantic import BaseModel


class ReportStorage:
    """简单可靠的研报存储"""

    def __init__(self, base_dir: str = "src/a_stock_analysis/knowledge/reports_json"):
        self.base_dir = Path(base_dir)
        os.makedirs(self.base_dir, exist_ok=True)

    def _get_stock_file(self, stock_code: str) -> Path:
        """获取股票报告文件路径"""
        # 统一格式：600519_SH.json
        filename = stock_code.replace(".", "_") + ".json"
        return self.base_dir / filename

    def save_report(self, stock_code: str, company_name: str,
                    q1: dict, q2: dict, q3: dict, q4: dict) -> str:
        """保存研报"""
        try:
            file_path = self._get_stock_file(stock_code)

            report_data = {
                "stock_code": stock_code,
                "company_name": company_name,
                "q1": q1,
                "q2": q2,
                "q3": q3,
                "q4": q4
            }

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2)

            return f"✅ 研报已存储: {stock_code} - {company_name}"

        except Exception as e:
            return f"❌ 存储失败: {str(e)}"

    def load_report(self, stock_code: str) -> Optional[dict]:
        """加载研报"""
        try:
            file_path = self._get_stock_file(stock_code)
            if not file_path.exists():
                return None

            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)

        except Exception as e:
            print(f"加载研报失败: {e}")
            return None

    def search_report(self, stock_code: str, query: str) -> str:
        """搜索研报内容"""
        report = self.load_report(stock_code)

        if not report:
            return f"未找到股票 {stock_code} 的研报，请先运行分析"

        # 简单关键词匹配
        query_lower = query.lower()
        results = []

        # 搜索各部分
        for section, data in [("Q1-市场技术分析", report.get('q1', {})),
                              ("Q2-财务分析", report.get('q2', {})),
                              ("Q3-情绪分析", report.get('q3', {})),
                              ("Q4-投资建议", report.get('q4', {}))]:
            if not data:
                continue

            # 检查关键词
            data_str = json.dumps(data, ensure_ascii=False).lower()
            if any(keyword in data_str for keyword in query_lower.split()):
                results.append(f"【{section}】\n{json.dumps(data, ensure_ascii=False, indent=2)}")

        if results:
            return "\n\n".join(results)
        else:
            # 没匹配到，返回完整报告
            return json.dumps(report, ensure_ascii=False, indent=2)


# 全局实例
_storage = None


def get_storage() -> ReportStorage:
    global _storage
    if _storage is None:
        _storage = ReportStorage()
    return _storage
