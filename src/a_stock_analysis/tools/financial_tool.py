from crewai.tools import BaseTool
from typing import Any, Optional, Type
from pydantic import BaseModel, Field
import pandas as pd
from datetime import datetime, timedelta
import tinyshare as ts

TINYSHARE_TOKEN = "TZnsj62Vft6yb5Iwoa3uAit0e5biw8sn7ojoSm3O070QuojUrZRvtw3a446eb0b3"
ts.set_token(TINYSHARE_TOKEN)
pro = ts.pro_api()


class FinancialAnalysisToolSchema(BaseModel):
    """财务分析工具输入参数"""
    stock_code: str = Field(..., description="股票代码，如：000001.SZ或600519.SH")
    analysis_type: str = Field(..., description="分析类型：ratio（财务比率）、trend（趋势分析）、comparison（同业对比）")


class FinancialAnalysisTool(BaseTool):
    name: str = "FinancialAnalysisTool"
    description: str = "深度分析A股公司财务报表，包括财务比率、趋势分析和同业对比"
    args_schema: Type[BaseModel] = FinancialAnalysisToolSchema

    def _run(self, stock_code: str, analysis_type: str = "ratio", **kwargs) -> Any:
        """执行财务分析"""
        import traceback
        try:
            if analysis_type == "ratio":
                return self._analyze_financial_ratios(stock_code)
            elif analysis_type == "trend":
                return self._analyze_financial_trend(stock_code)
            elif analysis_type == "comparison":
                return self._compare_industry_peers(stock_code)
            elif analysis_type == "scoring":
                return self._calculate_financial_score(stock_code)
            else:
                raise ValueError(f"不支持的分析类型: {analysis_type}")
        except Exception as e:
            return f"财务分析失败: {str(e)}"

    def _analyze_financial_ratios(self, stock_code: str) -> str:
        """分析财务比率"""
        try:
            # 使用tushare获取财务指标
            df = pro.fina_indicator(ts_code=stock_code, limit=10)

            if df.empty:
                return f"未获取到股票 {stock_code} 的财务数据"

            # 【关键修复】按日期升序排序，取最新的年度数据
            df = df.sort_values('end_date').reset_index(drop=True)

            # 【修改】获取最新季度数据（去重后取最后一个）
            df = df.drop_duplicates(subset=['end_date'], keep='last')
            latest = df.iloc[-1]

            # 安全获取字段值（修正字段名）
            eps = latest.get('eps', 0) or 0
            roe = latest.get('roe', 0) or 0
            grossprofit_margin = latest.get('grossprofit_margin', 0) or 0
            debt_to_assets = latest.get('debt_to_assets', 0) or 0
            current_ratio = latest.get('current_ratio', 0) or 0
            quick_ratio = latest.get('quick_ratio', 0) or 0
            netprofit_margin = latest.get('netprofit_margin', 0) or 0

            # 【修复】营业收入使用income接口获取，避免op_income为负的问题
            op_income = 0
            try:
                income_df = pro.income(ts_code=stock_code, limit=5)
                if not income_df.empty:
                    income_df = income_df.sort_values('end_date').reset_index(drop=True)
                    income_df = income_df.drop_duplicates(subset=['end_date'], keep='last')
                    if len(income_df) > 0:
                        latest_income = income_df.iloc[-1]
                        op_income = latest_income.get('total_revenue', 0) or 0
            except:
                pass
            # 如果income接口失败， fallback到op_income
            if not op_income or op_income == 0:
                op_income = latest.get('op_income', 0) or 0

            ebit = latest.get('ebit', 0) or 0  # 息税前利润

            # 【关键修复】使用正确的字段名
            netprofit_yoy = latest.get('netprofit_yoy', 0) or 0
            or_yoy = latest.get('or_yoy', 0) or 0
            # 获取数据日期
            end_date = latest.get('end_date', '')

            # 【关键修复】从行情数据获取当前价格，计算TTM PE/PB
            current_price = 0
            pe = 0
            pb = 0

            # 【修复】使用TTM EPS计算PE
            # 构建EPS字典
            eps_dict = {}
            try:
                df_eps = pro.fina_indicator(ts_code=stock_code, limit=20)
                if df_eps is not None and not df_eps.empty:
                    df_eps = df_eps.sort_values('end_date').reset_index(drop=True)
                    for _, row in df_eps.iterrows():
                        ed = row.get('end_date', 0)
                        e = row.get('eps', 0)
                        if ed and e:
                            eps_dict[ed] = e
            except:
                pass

            # 计算TTM EPS
            ttm_eps = None
            if eps_dict.get('20241231'):  # 2024年度EPS
                q1_2024 = eps_dict.get('20240331', 0)
                q1_2025 = eps_dict.get('20250331', 0)
                if q1_2024 and q1_2025:
                    ttm_eps = eps_dict['20241231'] - q1_2024 + q1_2025

            try:
                quote_df = pro.daily(ts_code=stock_code, start_date=(datetime.now() - timedelta(days=5)).strftime('%Y%m%d'),
                                  end_date=datetime.now().strftime('%Y%m%d'))
                if not quote_df.empty:
                    quote_df = quote_df.sort_values('trade_date').reset_index(drop=True)
                    current_price = quote_df.iloc[-1]['close']
                    # 【修复】使用TTM EPS计算PE
                    if ttm_eps and ttm_eps > 0:
                        pe = current_price / ttm_eps
                    bps = latest.get('bps', 0) or 0
                    if bps and bps > 0:
                        pb = current_price / bps
            except:
                pass

            # 计算历史PE（TTM）
            hist_pe_2023 = 0
            hist_pe_2024 = 0
            hist_pe_2025 = 0
            hist_pe_avg = 0
            pe_comparison = ""
            try:
                # 获取各年年末股价
                prices = {}
                for year, start_d, end_d in [(2023, '20231201', '20231231'), (2024, '20241201', '20241231'), (2025, '20251201', '20251231')]:
                    q = pro.daily(ts_code=stock_code, start_date=start_d, end_date=end_d)
                    if not q.empty:
                        q = q.sort_values('trade_date').reset_index(drop=True)
                        prices[year] = q.iloc[-1]['close']

                # 计算各年末TTM EPS
                if eps_dict:
                    # 2023年末TTM = 2023年度EPS
                    ttm_2023 = eps_dict.get('20231231', 0)
                    if ttm_2023 and 2023 in prices:
                        hist_pe_2023 = prices[2023] / ttm_2023

                    # 2024年末TTM = 2024年度EPS
                    ttm_2024 = eps_dict.get('20241231', 0)
                    if ttm_2024 and 2024 in prices:
                        hist_pe_2024 = prices[2024] / ttm_2024

                    # 2025年末TTM = 2024年度 - Q1_2024 + Q1_2025
                    ttm_2025 = None
                    if ttm_2024:
                        q1_2024 = eps_dict.get('20240331', 0)
                        q1_2025 = eps_dict.get('20250331', 0)
                        if q1_2024 and q1_2025:
                            ttm_2025 = ttm_2024 - q1_2024 + q1_2025
                    if ttm_2025 and 2025 in prices:
                        hist_pe_2025 = prices[2025] / ttm_2025

                # 计算历史平均
                pe_values = [v for v in [hist_pe_2023, hist_pe_2024, hist_pe_2025] if v > 0]
                if pe_values:
                    hist_pe_avg = sum(pe_values) / len(pe_values)
                    if pe > 0:
                        pct = (pe - hist_pe_avg) / hist_pe_avg * 100
                        pe_comparison = f"{'偏低' if pct < 0 else '偏高'}{abs(pct):.0f}%"
            except:
                pass

            result = f"""
股票 {stock_code} 财务比率分析（数据截至：{end_date}）：

=== 核心财务数据 ===
• 营业收入：{op_income/1e8:.1f}亿元
• 息税前利润(EBIT)：{ebit/1e8:.1f}亿元
• 每股收益(EPS)：{eps:.2f}元
• 净利润率：{netprofit_margin:.1f}%

=== 盈利能力分析 ===
• 净资产收益率(ROE)：{roe:.2f}%
  行业平均水平：15.0%
  评价：{'优秀' if roe > 15 else '良好' if roe > 10 else '一般'}

• 销售毛利率：{grossprofit_margin:.2f}%
  评价：{'很高' if grossprofit_margin > 50 else '较高' if grossprofit_margin > 30 else '一般'}

=== 偿债能力分析 ===
• 资产负债率：{debt_to_assets:.2f}%
  安全水平：{'很低' if debt_to_assets < 30 else '适中' if debt_to_assets < 60 else '较高'}

• 流动比率：{current_ratio:.2f}
  偿债能力：{'很强' if current_ratio > 2 else '良好' if current_ratio > 1.5 else '一般'}

• 速动比率：{quick_ratio:.2f}
  短期偿债：{'优秀' if quick_ratio > 1 else '良好' if quick_ratio > 0.8 else '需关注'}

=== 成长能力分析 ===
• 营业收入同比增长(or_yoy)：{or_yoy:.2f}%
  成长性：{'高增长' if or_yoy > 20 else '稳健增长' if or_yoy > 10 else '增速放缓'}

• 净利润同比增长(netprofit_yoy)：{netprofit_yoy:.2f}%
  盈利增长：{'强劲' if netprofit_yoy > 30 else '良好' if netprofit_yoy > 15 else '一般'}

=== 估值分析（基于当前价 {current_price:.2f}元）===
• 市盈率(PE-TTM)：{f"{pe:.1f}倍（亏损）" if pe < 0 else f"{pe:.1f}倍"}
  估值水平：{'不适用（亏损）' if pe < 0 else '低估' if pe < 15 else '合理' if pe < 30 else '高估'}

• 市净率(PB)：{pb:.2f}倍
  估值评价：{'偏低' if pb < 1.5 else '合理' if pb < 3 else '偏高'}

=== 历史PE走势（TTM）===
{'公司处于亏损状态，PE指标失效，建议参考PB和PS进行估值判断' if pe < 0 else f'''
• 2023年末PE：{hist_pe_2023:.1f}倍
• 2024年末PE：{hist_pe_2024:.1f}倍
• 2025年末PE：{hist_pe_2025:.1f}倍
• 当前PE：{pe:.1f}倍
• 历史三年年均PE：{hist_pe_avg:.1f}倍
• 当前PE较历史均值：{pe_comparison}
'''}

=== 综合评分 ===
盈利能力：{'⭐⭐⭐⭐⭐' if roe > 20 else '⭐⭐⭐⭐' if roe > 15 else '⭐⭐⭐'}
偿债能力：{'⭐⭐⭐⭐⭐' if current_ratio > 2 and debt_to_assets < 40 else '⭐⭐⭐⭐' if current_ratio > 1.5 else '⭐⭐⭐'}
成长能力：{'⭐⭐⭐⭐⭐' if or_yoy > 30 else '⭐⭐⭐⭐' if or_yoy > 15 else '⭐⭐⭐'}
估值水平：{'不适用（亏损）' if pe < 0 else '⭐⭐⭐⭐⭐' if pe < 15 else '⭐⭐⭐⭐' if pe < 25 else '⭐⭐⭐'}

"""
            return result

        except Exception as e:
            return f"财务比率分析失败: {str(e)}"

    def _analyze_financial_trend(self, stock_code: str) -> str:
        """分析财务趋势"""
        try:
            # 使用tushare获取财务指标
            df = pro.fina_indicator(ts_code=stock_code, limit=10)

            if df.empty:
                return f"未获取到股票 {stock_code} 的财务数据"

            # 获取最近的数据
            recent_data = df.head(8)

            result = f"""
股票 {stock_code} 财务趋势分析（最近8个季度）：

{'季度':<15} {'每股收益':<10} {'净资产收益率':<12} {'营业收入增长':<12} {'净利润增长':<12}
{'-' * 75}
"""

            for i, (_, row) in enumerate(recent_data.iterrows()):
                quarter = f"Q{8-i}"
                eps = row.get('eps', 0) or 0
                roe = row.get('roe', 0) or 0
                income_growth = row.get('or_yoy', 0) or 0
                profit_growth = row.get('netprofit_growth_rate', 0) or 0
                result += f"{quarter:<15} {eps:<10.3f} {roe:<12.2f}% {income_growth:<12.2f}% {profit_growth:<12.2f}%\n"

            # 趋势分析
            eps_trend = recent_data['eps'].values
            roe_trend = recent_data['roe'].values

            result += "\n=== 趋势分析 ===\n"

            # EPS趋势
            eps_slope = (eps_trend[-1] - eps_trend[0]) / len(eps_trend) if len(eps_trend) > 1 and eps_trend[0] != 0 else 0
            result += f"每股收益趋势：{'↗️ 持续增长' if eps_slope > 0.05 else '→ 保持稳定' if abs(eps_slope) <= 0.05 else '↘️ 有所下降'}\n"

            # ROE趋势
            roe_slope = (roe_trend[-1] - roe_trend[0]) / len(roe_trend) if len(roe_trend) > 1 and roe_trend[0] != 0 else 0
            result += f"净资产收益率趋势：{'↗️ 持续改善' if roe_slope > 1 else '→ 保持稳定' if abs(roe_slope) <= 1 else '↘️ 有所下滑'}\n"

            # 波动性分析
            eps_mean = eps_trend.mean() if len(eps_trend) > 0 else 1
            eps_volatility = eps_trend.std() / eps_mean if eps_mean > 0 else 0
            result += f"业绩稳定性：{'非常稳定' if eps_volatility < 0.1 else '相对稳定' if eps_volatility < 0.2 else '波动较大'}\n"

            return result

        except Exception as e:
            return f"财务趋势分析失败: {str(e)}"

    def _compare_industry_peers(self, stock_code: str) -> str:
        """同业对比分析"""
        try:
            # 使用tushare获取财务指标
            target_df = pro.fina_indicator(ts_code=stock_code, limit=5)
            if target_df.empty:
                return f"未获取到股票 {stock_code} 的财务数据"

            target_latest = target_df.iloc[0]

            # 获取字段值
            roe = target_latest.get('roe', 0) or 0
            pe = target_latest.get('pe', 0) or 0
            pb = target_latest.get('pb', 0) or 0
            debt_to_assets = target_latest.get('debt_to_assets', 0) or 0

            # 简化的同业对比（基于行业平均数据）
            industry_avg_roe = 12.5
            industry_avg_pe = 18.0
            industry_avg_pb = 2.1
            industry_avg_debt_ratio = 45.0

            result = f"""
股票 {stock_code} 同业对比分析：

=== 核心指标对比 ===
指标             本公司         行业平均         差异           评价
------------------------------------------------------------------------------
净资产收益率     {roe:.2f}%      {industry_avg_roe:.2f}%      {roe - industry_avg_roe:+.2f}%      {'领先' if roe > industry_avg_roe else '落后'}
市盈率           {pe:.2f}倍       {industry_avg_pe:.2f}倍       {pe - industry_avg_pe:+.2f}倍      {'相对低估' if pe < industry_avg_pe else '相对高估'}
市净率           {pb:.2f}倍        {industry_avg_pb:.2f}倍        {pb - industry_avg_pb:+.2f}倍      {'相对低估' if pb < industry_avg_pb else '相对高估'}
资产负债率       {debt_to_assets:.2f}%      {industry_avg_debt_ratio:.2f}%      {debt_to_assets - industry_avg_debt_ratio:+.2f}%      {'较低' if debt_to_assets < industry_avg_debt_ratio else '较高'}

=== 竞争力评估 ===
"""

            # 综合竞争力评分
            roe_score = min(max((roe - industry_avg_roe) / industry_avg_roe * 10 if industry_avg_roe != 0 else 0, -5), 5)
            pe_score = min(max((industry_avg_pe - pe) / industry_avg_pe * 10 if industry_avg_pe != 0 else 0, -5), 5)
            debt_score = min(max((industry_avg_debt_ratio - debt_to_assets) / industry_avg_debt_ratio * 10 if industry_avg_debt_ratio != 0 else 0, -5), 5)

            total_score = roe_score + pe_score + debt_score

            result += f"盈利能力得分：{roe_score:+.1f} 分\n"
            result += f"估值吸引力得分：{pe_score:+.1f} 分\n"
            result += f"财务健康得分：{debt_score:+.1f} 分\n"
            result += f"综合得分：{total_score:+.1f} 分\n\n"

            if total_score > 5:
                result += "🏆 综合评价：公司具有较强的行业竞争力"
            elif total_score > 0:
                result += "👍 综合评价：公司具有一定竞争优势"
            elif total_score > -5:
                result += "📊 综合评价：公司竞争力一般"
            else:
                result += "⚠️ 综合评价：公司竞争力相对较弱"

            return result

        except Exception as e:
            return f"同业对比分析失败: {str(e)}"

    def _calculate_financial_score(self, stock_code: str) -> str:
        """计算财务评分（按详细规则）"""
        import sys
        try:
            # 从 income 接口获取净利润数据
            income_df = pro.income(ts_code=stock_code, limit=10)
            if income_df.empty:
                return '{"error": "未获取到财务数据"}'

            income_df = income_df.sort_values('end_date').reset_index(drop=True)
            income_df = income_df.drop_duplicates(subset=['end_date'], keep='last')

            # 获取最新几期数据
            latest_inc = income_df.iloc[-1] if len(income_df) >= 1 else None
            prev1_inc = income_df.iloc[-2] if len(income_df) >= 2 else None
            prev2_inc = income_df.iloc[-3] if len(income_df) >= 3 else None

            if latest_inc is None or (isinstance(latest_inc, pd.Series) and latest_inc.empty):
                return '{"error": "无财务数据"}'

            # 提取净利润数据 - 使用 n_income 字段（归属于母公司净利润）
            netprofit = float(latest_inc.get('n_income', 0)) if pd.notna(latest_inc.get('n_income', 0)) else 0
            end_date = str(latest_inc.get('end_date', ''))

            # 前几期净利润
            prev_netprofit = float(prev1_inc.get('n_income', 0)) if prev1_inc is not None and pd.notna(prev1_inc.get('n_income', 0)) else 0
            prev2_netprofit = float(prev2_inc.get('n_income', 0)) if prev2_inc is not None and pd.notna(prev2_inc.get('n_income', 0)) else 0


            # 从 fina_indicator 获取其他财务比率
            df = pro.fina_indicator(ts_code=stock_code, limit=10)
            if df.empty:
                return '{"error": "未获取到财务比率数据"}'

            df = df.sort_values('end_date').reset_index(drop=True)
            df = df.drop_duplicates(subset=['end_date'], keep='last')
            latest = df.iloc[-1] if len(df) >= 1 else None

            if latest is None or (isinstance(latest, pd.Series) and latest.empty):
                return '{"error": "无财务比率数据"}'

            roe = float(latest.get('roe', 0)) if pd.notna(latest.get('roe', 0)) else 0
            grossprofit_margin = float(latest.get('grossprofit_margin', 0)) if pd.notna(latest.get('grossprofit_margin', 0)) else 0
            netprofit_margin = float(latest.get('netprofit_margin', 0)) if pd.notna(latest.get('netprofit_margin', 0)) else 0
            debt_to_assets = float(latest.get('debt_to_assets', 0)) if pd.notna(latest.get('debt_to_assets', 0)) else 0
            or_yoy = float(latest.get('or_yoy', 0)) if pd.notna(latest.get('or_yoy', 0)) else 0
            netprofit_yoy = float(latest.get('netprofit_yoy', 0)) if pd.notna(latest.get('netprofit_yoy', 0)) else 0
            op_income = float(latest.get('op_income', 0)) if pd.notna(latest.get('op_income', 0)) else 0

            # 判断亏损状态
            is_profitable = netprofit > 0
            # 连续亏损判断
            consecutive_loss = 0
            if not is_profitable:
                if prev_netprofit < 0:
                    consecutive_loss = 1
                    if prev2_netprofit < 0:
                        consecutive_loss = 2


            # 获取经营现金流
            operating_cashflow = 0
            try:
                cashflow_df = pro.cashflow(ts_code=stock_code, limit=5)
                if not cashflow_df.empty:
                    cashflow_df = cashflow_df.sort_values('end_date').reset_index(drop=True)
                    latest_cf = cashflow_df.iloc[-1]
                    operating_cashflow = float(latest_cf.get('n_cashflow_act', 0)) if pd.notna(latest_cf.get('n_cashflow_act', 0)) else 0
            except:
                pass

            # 获取当前价格和估值
            current_price = 0
            pe = 0
            pb = 0

            # 计算 TTM EPS
            ttm_eps = None
            eps_dict = {}
            try:
                eps_df = pro.fina_indicator(ts_code=stock_code, limit=20)
                if eps_df is not None and not eps_df.empty:
                    eps_df = eps_df.sort_values('end_date').reset_index(drop=True)
                    for _, row in eps_df.iterrows():
                        ed = row.get('end_date', 0)
                        e = row.get('eps', 0)
                        if ed and e:
                            eps_dict[ed] = e
            except:
                pass

            # 计算 TTM EPS
            if eps_dict.get('20241231'):  # 2024年度EPS
                q1_2024 = eps_dict.get('20240331', 0)
                q1_2025 = eps_dict.get('20250331', 0)
                if q1_2024 and q1_2025:
                    ttm_eps = eps_dict['20241231'] - q1_2024 + q1_2025

            try:
                quote_df = pro.daily(ts_code=stock_code, start_date=(datetime.now() - timedelta(days=5)).strftime('%Y%m%d'),
                                  end_date=datetime.now().strftime('%Y%m%d'))
                if not quote_df.empty:
                    quote_df = quote_df.sort_values('trade_date').reset_index(drop=True)
                    current_price = quote_df.iloc[-1]['close']
                    bps = float(latest.get('bps', 0)) if pd.notna(latest.get('bps', 0)) else 0
                    if bps and bps > 0:
                        pb = current_price / bps
                    # 使用 TTM EPS 计算 PE
                    if ttm_eps and ttm_eps > 0:
                        pe = current_price / ttm_eps
            except:
                pass

            # 计算PS（市销率）
            ps = 0
            if op_income and op_income > 0:
                # 需要市值，这里简化处理
                pass

            # ========== 评分计算 ==========
            stock_type = "盈利股"
            if not is_profitable and consecutive_loss >= 2:
                stock_type = "亏损股（连续亏损）"
            elif not is_profitable:
                stock_type = "亏损股（单季亏损）"

            dimension_scores = {}
            total_score = 0
            max_score = 100
            warnings = []
            special_notes = []

            if is_profitable or (not is_profitable and consecutive_loss == 0):
                # ========== 盈利股模板（满分100分）==========

                # 维度一：盈利能力（30分）
                # ROE: ≥20%→15分, 15~20%→12分, 10~15%→8分, 5~10%→4分, <5%→1分
                if roe >= 20:
                    roe_score = 15
                elif roe >= 15:
                    roe_score = 12
                elif roe >= 10:
                    roe_score = 8
                elif roe >= 5:
                    roe_score = 4
                else:
                    roe_score = 1

                # 净利润率: ≥30%→10分, 20~30%→8分, 10~20%→5分, 5~10%→3分, <5%→1分
                if netprofit_margin >= 30:
                    npm_score = 10
                elif netprofit_margin >= 20:
                    npm_score = 8
                elif netprofit_margin >= 10:
                    npm_score = 5
                elif netprofit_margin >= 5:
                    npm_score = 3
                else:
                    npm_score = 1

                # 毛利率: ≥60%→5分, 40~60%→4分, 20~40%→2分, <20%→1分
                if grossprofit_margin >= 60:
                    gross_score = 5
                elif grossprofit_margin >= 40:
                    gross_score = 4
                elif grossprofit_margin >= 20:
                    gross_score = 2
                else:
                    gross_score = 1

                profitability_score = roe_score + npm_score + gross_score
                dimension_scores["盈利能力"] = f"{profitability_score}/30分 = ROE{roe}%→{roe_score}分 + 净利润率{netprofit_margin}%→{npm_score}分 + 毛利率{grossprofit_margin}%→{gross_score}分"

                # 维度二：成长能力（25分）
                # 营收增速: ≥20%→12分, 10~20%→9分, 5~10%→6分, 0~5%→3分, <0%→0分
                if or_yoy >= 20:
                    or_score = 12
                elif or_yoy >= 10:
                    or_score = 9
                elif or_yoy >= 5:
                    or_score = 6
                elif or_yoy >= 0:
                    or_score = 3
                else:
                    or_score = 0

                # 净利增速: ≥20%→8分, 10~20%→6分, 5~10%→4分, 0~5%→2分, <0%→0分
                if netprofit_yoy >= 20:
                    np_score = 8
                elif netprofit_yoy >= 10:
                    np_score = 6
                elif netprofit_yoy >= 5:
                    np_score = 4
                elif netprofit_yoy >= 0:
                    np_score = 2
                else:
                    np_score = 0

                # 趋势一致性（简化：近3期营收和净利同向）
                trend_score = 0
                if len(df) >= 3:
                    or_signs = [df.iloc[-i].get('or_yoy', 0) > 0 for i in range(1, 4)]
                    np_signs = [df.iloc[-i].get('netprofit_yoy', 0) > 0 for i in range(1, 4)]
                    if sum(or_signs) >= 2 and sum(np_signs) >= 2 and or_signs == np_signs:
                        trend_score = 5
                    elif sum(or_signs) >= 2 and sum(np_signs) >= 2:
                        trend_score = 3

                growth_score = or_score + np_score + trend_score
                dimension_scores["成长能力"] = f"{growth_score}/25分 = 营收增速{or_yoy}%→{or_score}分 + 净利增速{netprofit_yoy}%→{np_score}分 + 趋势一致性→{trend_score}分"

                # 维度三：估值合理性（20分）
                # PE分位（简化：当前PE vs 历史平均PE）
                pe_score = 0
                if pe > 0:
                    # 简化：假设历史PE在15-25倍之间
                    if pe <= 15:
                        pe_score = 12
                    elif pe <= 20:
                        pe_score = 9
                    elif pe <= 25:
                        pe_score = 6
                    else:
                        pe_score = 2

                # PB与ROE匹配度: ROE/PB ≥ 3→8分, 2~3→6分, 1~2→3分, <1→0分
                if pb > 0:
                    roe_pb_ratio = roe / pb
                    if roe_pb_ratio >= 3:
                        pb_score = 8
                    elif roe_pb_ratio >= 2:
                        pb_score = 6
                    elif roe_pb_ratio >= 1:
                        pb_score = 3
                    else:
                        pb_score = 0
                else:
                    pb_score = 0

                valuation_score = pe_score + pb_score
                dimension_scores["估值合理性"] = f"{valuation_score}/20分 = PE{pe:.1f}倍→{pe_score}分 + ROE/PB={roe/pb:.1f}→{pb_score}分"

                # 维度四：资产质量（15分）
                # 资产负债率: <30%→8分, 30~50%→6分, 50~65%→3分, >65%→0分
                if debt_to_assets < 30:
                    debt_score = 8
                elif debt_to_assets < 50:
                    debt_score = 6
                elif debt_to_assets < 65:
                    debt_score = 3
                else:
                    debt_score = 0
                    if debt_to_assets > 70:
                        warnings.append("负债率过高是硬伤，即使其他指标不错，整体风险仍然偏高")

                # 经营现金流/净利润: ≥120%→7分, 100~120%→5分, 80~100%→3分, <80%→1分
                if netprofit > 0:
                    cf_ratio = (operating_cashflow / netprofit) * 100 if operating_cashflow else 0
                    if cf_ratio >= 120:
                        cf_score = 7
                    elif cf_ratio >= 100:
                        cf_score = 5
                    elif cf_ratio >= 80:
                        cf_score = 3
                    else:
                        cf_score = 1
                else:
                    cf_score = 0

                asset_score = debt_score + cf_score
                dimension_scores["资产质量"] = f"{asset_score}/15分 = 资产负债率{debt_to_assets}%→{debt_score}分 + 经营现金流/净利润→{cf_score}分"

                # 维度五：行业相对表现（10分）
                # 简化：基于固定行业均值
                industry_avg_roe = 12.0
                industry_avg_gross = 30.0

                if roe >= industry_avg_roe * 1.5:
                    roe_industry_score = 5
                elif roe >= industry_avg_roe:
                    roe_industry_score = 3
                elif roe >= industry_avg_roe * 0.8:
                    roe_industry_score = 2
                else:
                    roe_industry_score = 0

                if grossprofit_margin >= industry_avg_gross * 1.5:
                    gross_industry_score = 5
                elif grossprofit_margin >= industry_avg_gross:
                    gross_industry_score = 3
                elif grossprofit_margin >= industry_avg_gross * 0.8:
                    gross_industry_score = 2
                else:
                    gross_industry_score = 0

                industry_score = roe_industry_score + gross_industry_score
                dimension_scores["行业相对表现"] = f"{industry_score}/10分 = ROE vs 行业→{roe_industry_score}分 + 毛利率 vs 行业→{gross_industry_score}分"

                # 总分
                total_score = profitability_score + growth_score + valuation_score + asset_score + industry_score

                # 负债率 > 70% 强制上限
                if debt_to_assets > 70:
                    total_score = min(total_score, 60)
                    warnings.append("负债率过高，总分上限锁定60分")

                # 评分区间含义
                if total_score >= 90:
                    score_range_meaning = "护城河深厚，财务质量顶尖，可重点关注"
                elif total_score >= 75:
                    score_range_meaning = "财务健康，有配置价值，结合技术面判断时机"
                elif total_score >= 60:
                    score_range_meaning = "基本面一般，需关注成长性或估值是否改善"
                else:
                    score_range_meaning = "财务存在明显短板，谨慎参与"

            else:
                # ========== 亏损股模板（满分75分）==========
                max_score = 75

                # 维度一：生存能力（30分）- 只评估经营现金流方向
                # 经营现金流方向（30分）：经营现金流为正→30分 / 为负但同比收窄→15分 / 持续恶化→0分
                if operating_cashflow > 0:
                    cf_dir_score = 30
                elif operating_cashflow < 0 and prev1 and prev1.get('netprofit', 0) < 0:
                    # 简化：亏损且经营现金流为负 = 15分
                    cf_dir_score = 15
                else:
                    cf_dir_score = 0

                survival_score = cf_dir_score
                dimension_scores["生存能力"] = f"{survival_score}/30分 = 经营现金流{'为正' if operating_cashflow > 0 else '为负（亏损中）'}→{cf_dir_score}分"

                # 维度二：亏损收窄速度（25分）
                # 净亏损收窄幅度
                loss_reduction = 0
                if prev_netprofit < 0 and netprofit < 0:
                    loss_reduction = (prev_netprofit - netprofit) / abs(prev_netprofit) * 100 if prev_netprofit != 0 else 0

                if loss_reduction > 50:
                    loss_score = 15
                elif loss_reduction >= 30:
                    loss_score = 10
                elif loss_reduction >= 10:
                    loss_score = 5
                else:
                    loss_score = 0

                # 毛利率趋势（简化）
                if len(df) >= 3:
                    gross_trends = [df.iloc[-i].get('grossprofit_margin', 0) for i in range(1, 4)]
                    if gross_trends[0] > gross_trends[1] > gross_trends[2]:
                        gross_trend_score = 10
                    elif gross_trends[0] > gross_trends[1]:
                        gross_trend_score = 5
                    else:
                        gross_trend_score = 0
                else:
                    gross_trend_score = 0

                loss_recovery_score = loss_score + gross_trend_score
                dimension_scores["亏损收窄速度"] = f"{loss_recovery_score}/25分 = 收窄幅度{loss_reduction}%→{loss_score}分 + 毛利率趋势→{gross_trend_score}分"

                # 维度三：营收质量（20分）
                # 营收增速
                if or_yoy >= 15:
                    or_loss_score = 10
                elif or_yoy >= 8:
                    or_loss_score = 7
                elif or_yoy >= 3:
                    or_loss_score = 4
                elif or_yoy >= 0:
                    or_loss_score = 2
                else:
                    or_loss_score = 0

                # 应收账款占营收比（简化）
                ar_score = 0  # 简化处理

                revenue_quality = or_loss_score + ar_score
                dimension_scores["营收质量"] = f"{revenue_quality}/20分 = 营收增速{or_yoy}%→{or_loss_score}分 + 应收账款→{ar_score}分"

                # 总分
                total_score = survival_score + loss_recovery_score + revenue_quality

                # 评分区间含义
                if total_score >= 60:
                    score_range_meaning = "改善信号明显，可小仓位关注，设好止损"
                elif total_score >= 40:
                    score_range_meaning = "有改善但不稳定，高风险，不建议现在参与"
                else:
                    score_range_meaning = "生存能力存疑，回避"

                special_notes.append("以上评分反映的是亏损改善趋势，不代表推荐买入。亏损股波动大、风险高，适合有经验的投资者小仓位参与，初学者建议观望。")

            # 构建JSON结果
            import json
            result = {
                "股票类型": stock_type,
                "数据截止日期": end_date,
                "关键财务指标": {
                    "净利润": f"{netprofit/1e8:.2f}亿元",
                    "ROE": f"{roe:.2f}%",
                    "毛利率": f"{grossprofit_margin:.2f}%",
                    "净利润率": f"{netprofit_margin:.2f}%",
                    "资产负债率": f"{debt_to_assets:.2f}%",
                    "PE": f"{pe:.1f}倍" if pe > 0 else "亏损",
                    "PB": f"{pb:.2f}倍",
                    "营收增速": f"{or_yoy:.2f}%",
                    "净利润增速": f"{netprofit_yoy:.2f}%"
                },
                "评分维度": dimension_scores,
                "总分": f"{total_score}/{max_score}分",
                "评分含义": score_range_meaning,
                "特别警告": warnings,
                "特别说明": special_notes
            }

            return json.dumps(result, ensure_ascii=False, indent=2)

        except Exception as e:
            import json
            import traceback
            import sys
            traceback.print_exc()
            return json.dumps({"error": f"财务评分计算失败: {str(e)}"}, ensure_ascii=False)
