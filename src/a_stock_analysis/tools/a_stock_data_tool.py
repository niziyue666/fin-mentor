from crewai.tools import BaseTool
from typing import Any, Optional, Type
from pydantic import BaseModel, Field
import pandas as pd
from datetime import datetime, timedelta
import tinyshare as ts

TINYSHARE_TOKEN = "TZnsj62Vft6yb5Iwoa3uAit0e5biw8sn7ojoSm3O070QuojUrZRvtw3a446eb0b3"
ts.set_token(TINYSHARE_TOKEN)
pro = ts.pro_api()


class AStockDataToolSchema(BaseModel):
    """股票数据工具输入参数"""
    stock_code: str = Field(..., description="股票代码，如：000001.SZ（深交所）、600519.SH（上交所）或00700.HK（港股）")
    data_type: str = Field(..., description="数据类型：quote（实时行情）、daily（日线数据）、financial（财务数据）、sector（板块数据）")


class AStockDataTool(BaseTool):
    name: str = "AStockDataTool"
    description: str = "获取A股和港股的实时行情、历史数据、财务信息等，支持上交所、深交所和港股"
    args_schema: Type[BaseModel] = AStockDataToolSchema

    def _run(self, stock_code: str, data_type: str = "quote", **kwargs) -> Any:
        """获取A股数据"""
        try:
            if data_type == "quote":
                return self._get_real_time_quote(stock_code)
            elif data_type == "daily":
                return self._get_daily_data(stock_code)
            elif data_type == "financial":
                return self._get_financial_data(stock_code)
            elif data_type == "sector":
                return self._get_sector_data()
            else:
                raise ValueError(f"不支持的数据类型: {data_type}")
        except Exception as e:
            return f"获取数据时发生错误: {str(e)}"

    def _get_real_time_quote(self, stock_code: str) -> str:
        """获取实时行情数据"""
        try:
            # 判断是否为港股
            if stock_code.endswith('.HK'):
                return self._get_hk_real_time_quote(stock_code)

            # 提取A股股票代码部分，处理不同格式
            if stock_code.endswith('.SZ') or stock_code.endswith('.SH'):
                code = stock_code.split('.')[0]
            elif len(stock_code) > 2 and (stock_code[:2] == 'sz' or stock_code[:2] == 'sh' or
                                         stock_code[:2] == 'SZ' or stock_code[:2] == 'SH'):
                # 处理sh600519或sz000001格式
                code = stock_code[2:]
            else:
                # 直接使用传入的代码
                code = stock_code

            # 使用tushare获取A股实时数据（通过日线数据模拟）
            # 获取当日和前几天的日线数据，取最新的一条
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=5)).strftime('%Y%m%d')

            df = pro.daily(ts_code=stock_code, start_date=start_date, end_date=end_date)

            if df.empty:
                return f"未找到股票 {stock_code} 的实时数据"

            # 取最新一条数据
            row = df.iloc[0]

            # 计算涨跌数据
            pre_close = row.get('pre_close', 0)
            close = row.get('close', 0)
            change = close - pre_close
            pct_chg = (change / pre_close * 100) if pre_close else 0

            result = f"股票：{stock_code}\n"
            result += f"当前价格：{close:.2f}\n"
            result += f"涨跌额：{change:.2f}\n"
            result += f"涨跌幅：{pct_chg:.2f}%\n"
            result += f"昨收：{pre_close:.2f}\n"
            result += f"今开：{row.get('open', 0):.2f}\n"
            result += f"最高：{row.get('high', 0):.2f}\n"
            result += f"最低：{row.get('low', 0):.2f}\n"
            result += f"成交量：{int(row.get('vol', 0)):,}\n"
            result += f"成交额：{int(row.get('amount', 0)):,}\n"

            return result

        except Exception as e:
            return f"获取实时行情失败: {str(e)}"

    def _get_hk_real_time_quote(self, stock_code: str) -> str:
        """获取港股实时行情数据"""
        try:
            # 提取港股代码，去掉.HK后缀
            code = stock_code.replace('.HK', '')
            # 港股代码格式需要转换，tushare使用5位数字代码
            if len(code) == 4:
                code = '0' + code

            # 获取港股日线数据，取最新的一条
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=5)).strftime('%Y%m%d')

            # tushare港股代码格式
            hk_code = f"{code}.HK"
            df = pro.hk_daily(ts_code=hk_code, start_date=start_date, end_date=end_date)

            if df.empty:
                return f"未找到港股 {stock_code} 的实时数据"

            # 取最新一条数据
            row = df.iloc[0]

            # 计算涨跌停相关数据
            pre_close = row.get('pre_close', 0)
            close = row.get('close', 0)
            change = close - pre_close
            pct_chg = (change / pre_close * 100) if pre_close else 0

            result = f"港股：{stock_code}\n"
            result += f"当前价格：{close:.2f}港币\n"
            result += f"涨跌额：{change:.2f}港币\n"
            result += f"涨跌幅：{pct_chg:.2f}%\n"
            result += f"昨收：{pre_close:.2f}港币\n"
            result += f"今开：{row.get('open', 0):.2f}港币\n"
            result += f"最高：{row.get('high', 0):.2f}港币\n"
            result += f"最低：{row.get('low', 0):.2f}港币\n"
            result += f"成交量：{int(row.get('vol', 0)):,}\n"
            result += f"成交额：{int(row.get('amount', 0)):,}\n"

            return result

        except Exception as e:
            return f"获取港股实时行情失败: {str(e)}"

    def _get_daily_data(self, stock_code: str, period: str = "daily") -> str:
        """获取历史K线数据"""
        try:
            # 判断是否为港股
            if stock_code.endswith('.HK'):
                return self._get_hk_daily_data(stock_code)
            
            # 确定A股市场类型
            if stock_code.endswith('.SZ'):
                market = "sz"
            elif stock_code.endswith('.SH'):
                market = "sh"
            else:
                return "无效的股票代码格式"

            code = stock_code.split('.')[0]

            # 获取历史数据（最近60天，确保有足够数据计算MA20）
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=60)).strftime('%Y%m%d')

            df = pro.daily(ts_code=stock_code, start_date=start_date, end_date=end_date)

            if df.empty:
                return f"未找到股票 {stock_code} 的历史数据"

            # 【关键修复】按日期升序排列（tushare默认是降序）
            df = df.sort_values('trade_date').reset_index(drop=True)

            # 计算技术指标
            df['MA5'] = df['close'].rolling(window=5).mean()
            df['MA10'] = df['close'].rolling(window=10).mean()
            df['MA20'] = df['close'].rolling(window=20).mean()

            # 获取最近的数据
            recent_data = df.tail(10)

            result = f"""
股票 {stock_code} 最近10个交易日数据：
{'日期':<12} {'开盘':<8} {'最高':<8} {'最低':<8} {'收盘':<8} {'涨跌幅':<8} {'成交量':<12}
{'-'*80}
"""

            for _, row in recent_data.iterrows():
                result += f"{row['trade_date']:<12} {row['open']:<8.2f} {row['high']:<8.2f} {row['low']:<8.2f} {row['close']:<8.2f} {row['pct_chg']:<8.2f}% {row['vol']:<12,}\n"

            # 技术分析（排序后iloc[-1]是最新的）
            latest = df.iloc[-1]
            prev_ma5 = df.iloc[-6]['MA5'] if len(df) > 5 else None
            current_ma5 = df.iloc[-1]['MA5']
            current_ma10 = df.iloc[-1]['MA10']
            current_ma20 = df.iloc[-1]['MA20']

            # 计算RSI（相对强弱指标）
            def calculate_rsi(prices, period=14):
                """计算RSI"""
                delta = prices.diff()
                gain = delta.where(delta > 0, 0)
                loss = -delta.where(delta < 0, 0)
                avg_gain = gain.rolling(window=period).mean()
                avg_loss = loss.rolling(window=period).mean()
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
                return rsi

            df['RSI'] = calculate_rsi(df['close'], 14)
            current_rsi = df.iloc[-1]['RSI']

            result += f"\n技术分析：\n"
            result += f"当前价格：{latest['close']:.2f}\n"
            result += f"MA5：{current_ma5:.2f}\n"
            result += f"MA10：{current_ma10:.2f}\n"
            result += f"MA20：{current_ma20:.2f}\n"
            result += f"RSI(14)：{current_rsi:.1f}\n"

            # 判断金叉死叉
            if len(df) >= 2:
                prev = df.iloc[-2]
                prev_ma5 = prev['MA5']
                prev_ma20 = prev['MA20']
                current_price = latest['close']
                # 金叉：MA5上穿MA20，死叉：MA5下穿MA20
                if pd.notna(current_ma5) and pd.notna(current_ma20) and pd.notna(prev_ma5) and pd.notna(prev_ma20):
                    if prev_ma5 <= prev_ma20 and current_ma5 > current_ma20:
                        result += "均线信号：MA5上穿MA20，形成金叉（短期转强）\n"
                    elif prev_ma5 >= prev_ma20 and current_ma5 < current_ma20:
                        result += "均线信号：MA5下穿MA20，形成死叉（短期转弱）\n"
                    elif current_ma5 > current_ma20 and current_price > current_ma5:
                        result += "均线信号：MA5>MA20>现价，标准多头排列\n"
                    elif current_ma5 > current_ma20 and current_price > current_ma20:
                        result += "均线信号：MA5>MA20，现价在MA20上方，强势整理\n"
                    elif current_ma5 > current_ma20 and current_price < current_ma20:
                        result += "均线信号：MA5>MA20，但现价<MA20，均线多头但跌破MA20\n"
                    elif current_ma5 < current_ma20:
                        result += "均线信号：MA5<MA20，保持空头排列\n"

            if prev_ma5 and current_ma5:
                if latest['close'] > current_ma5 > prev_ma5:
                    result += "趋势：短期上升趋势\n"
                elif latest['close'] < current_ma5 < prev_ma5:
                    result += "趋势：短期下降趋势\n"
                else:
                    result += "趋势：震荡整理\n"

            return result

        except Exception as e:
            return f"获取历史数据失败: {str(e)}"

    def _get_hk_daily_data(self, stock_code: str) -> str:
        """获取港股历史K线数据"""
        try:
            # 提取港股代码，去掉.HK后缀
            code = stock_code.replace('.HK', '')
            # 港股代码格式需要转换，tushare使用5位数字代码
            if len(code) == 4:
                code = '0' + code

            # 获取历史数据（最近60天，确保有足够数据计算MA20）
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=60)).strftime('%Y%m%d')

            # tushare港股代码格式
            hk_code = f"{code}.HK"
            df = pro.hk_daily(ts_code=hk_code, start_date=start_date, end_date=end_date)

            if df.empty:
                return f"未找到港股 {stock_code} 的历史数据"

            # 按日期升序排列
            df = df.sort_values('trade_date').reset_index(drop=True)

            # 计算技术指标
            df['MA5'] = df['close'].rolling(window=5).mean()
            df['MA10'] = df['close'].rolling(window=10).mean()
            df['MA20'] = df['close'].rolling(window=20).mean()

            # 获取最近的数据
            recent_data = df.tail(10)

            result = f"""
港股 {stock_code} 最近10个交易日数据：
{'日期':<12} {'开盘':<8} {'最高':<8} {'最低':<8} {'收盘':<8} {'涨跌幅':<8} {'成交量':<12}
{'-'*80}
"""

            for _, row in recent_data.iterrows():
                result += f"{row['trade_date']:<12} {row['open']:<8.2f} {row['high']:<8.2f} {row['low']:<8.2f} {row['close']:<8.2f} {row['pct_chg']:<8.2f}% {row['vol']:<12,}\n"

            # 技术分析
            latest = df.iloc[-1]
            prev_ma5 = df.iloc[-6]['MA5'] if len(df) > 5 else None
            current_ma5 = df.iloc[-1]['MA5']

            result += f"\n技术分析：\n"
            result += f"当前价格：{latest['close']:.2f}港币\n"
            result += f"MA5：{current_ma5:.2f}港币\n"
            result += f"MA10：{df.iloc[-1]['MA10']:.2f}港币\n"
            result += f"MA20：{df.iloc[-1]['MA20']:.2f}港币\n"

            if prev_ma5 and current_ma5:
                if latest['close'] > current_ma5 > prev_ma5:
                    result += "趋势：短期上升趋势\n"
                elif latest['close'] < current_ma5 < prev_ma5:
                    result += "趋势：短期下降趋势\n"
                else:
                    result += "趋势：震荡整理\n"

            return result

        except Exception as e:
            return f"获取港股历史数据失败: {str(e)}"

    def _get_financial_data(self, stock_code: str) -> str:
        """获取财务数据"""
        try:
            # 判断是否为港股
            if stock_code.endswith('.HK'):
                return self._get_hk_financial_data(stock_code)

            code = stock_code.split('.')[0]

            # 使用tushare获取财务指标
            try:
                # fina_indicator提供财务指标数据
                df = pro.fina_indicator(ts_code=stock_code, limit=10)  # 多取几年数据
            except Exception as e:
                return f"获取财务数据失败: {str(e)}"

            if df.empty:
                return f"未找到股票 {stock_code} 的财务数据"

            # 按日期排序（从老到新）
            df = df.sort_values('end_date').reset_index(drop=True)

            # 获取最新年度财务数据（不是季度预测）
            # 找到最新的年度数据（end_date以1231结尾）
            yearly_data = df[df['end_date'].astype(str).str.endswith('1231')]
            if not yearly_data.empty:
                latest_year = yearly_data.iloc[-1]
            else:
                latest_year = df.iloc[0]

            # 获取当前股价计算PE/PB
            try:
                quote = pro.daily(ts_code=stock_code, start_date=(datetime.now() - timedelta(days=5)).strftime('%Y%m%d'),
                                end_date=datetime.now().strftime('%Y%m%d'))
                current_price = quote.iloc[0]['close'] if not quote.empty else 0
            except:
                current_price = 0

            # 计算PE和PB
            pe = None
            pb = None
            if current_price > 0 and 'bps' in latest_year and pd.notna(latest_year.get('bps')):
                pb = current_price / latest_year['bps']
            if current_price > 0 and 'eps' in latest_year and pd.notna(latest_year.get('eps')):
                pe = current_price / latest_year['eps']

            # 构建结果字符串
            result = f"股票 {stock_code} 主要财务指标：\n\n"

            # 基础信息
            result += f"【数据期】{latest_year.get('end_date', 'N/A')}\n\n"

            result += "盈利能力：\n"
            # 每股收益
            if 'eps' in df.columns and pd.notna(latest_year.get('eps')):
                result += f"  每股收益(EPS)：{latest_year['eps']:.2f}元\n"
            # 净资产收益率
            if 'roe' in df.columns and pd.notna(latest_year.get('roe')):
                result += f"  净资产收益率(ROE)：{latest_year['roe']:.2f}%\n"
            # 销售毛利率
            if 'grossprofit_margin' in df.columns and pd.notna(latest_year.get('grossprofit_margin')):
                result += f"  销售毛利率：{latest_year['grossprofit_margin']:.2f}%\n"
            # 净利润率
            if 'netprofit_margin' in df.columns and pd.notna(latest_year.get('netprofit_margin')):
                result += f"  净利润率：{latest_year['netprofit_margin']:.2f}%\n"

            # 估值指标
            if current_price > 0:
                result += f"\n估值指标：\n"
                result += f"  当前股价：{current_price:.2f}元\n"
                if pe:
                    result += f"  市盈率(PE)：{pe:.1f}倍\n"
                if pb:
                    result += f"  市净率(PB)：{pb:.2f}倍\n"

            result += "\n偿债能力：\n"
            # 资产负债率
            if 'debt_to_assets' in df.columns and pd.notna(latest_year.get('debt_to_assets')):
                result += f"  资产负债率：{latest_year['debt_to_assets']:.2f}%\n"
            # 流动比率
            if 'current_ratio' in df.columns and pd.notna(latest_year.get('current_ratio')):
                result += f"  流动比率：{latest_year['current_ratio']:.2f}\n"

            # 成长能力（使用正确的字段名 netprofit_yoy, or_yoy）
            result += "\n成长能力：\n"
            # 获取近3年年度数据
            if len(yearly_data) >= 1:
                result += "  近年净利润增速：\n"
                for i, (_, row) in enumerate(yearly_data.tail(3).iterrows()):
                    yoy = row.get('netprofit_yoy')
                    if pd.notna(yoy):
                        result += f"    {row.get('end_date', '')}: {yoy:.1f}%\n"

            if len(yearly_data) >= 1:
                result += "  近年营收增速：\n"
                for i, (_, row) in enumerate(yearly_data.tail(3).iterrows()):
                    yoy = row.get('or_yoy')
                    if pd.notna(yoy):
                        result += f"    {row.get('end_date', '')}: {yoy:.1f}%\n"

            return result

        except Exception as e:
            return f"获取财务数据失败: {str(e)}"

    def _get_hk_financial_data(self, stock_code: str) -> str:
        """获取港股财务数据"""
        try:
            # 提取港股代码，去掉.HK后缀
            code = stock_code.replace('.HK', '')
            # 港股代码格式需要转换，tushare使用5位数字代码
            if len(code) == 4:
                code = '0' + code

            # tushare港股代码格式
            hk_code = f"{code}.HK"

            # 使用tushare获取港股财务指标
            try:
                df = pro.fina_indicator(ts_code=hk_code, limit=5)
            except Exception as e:
                return f"获取港股财务数据失败: {str(e)}"

            if df.empty:
                return f"未找到港股 {stock_code} 的财务数据（tushare港股财务数据可能有限）"

            # 获取最新的财务数据
            latest_data = df.iloc[0]

            # 构建结果字符串
            result = f"港股 {stock_code} 主要财务指标：\n\n"
            result += "盈利能力：\n"

            # 每股收益
            if 'eps' in df.columns and pd.notna(latest_data.get('eps')):
                result += f"  每股收益：{latest_data['eps']:.3f}港币\n"

            # 净资产收益率
            if 'roe' in df.columns and pd.notna(latest_data.get('roe')):
                result += f"  净资产收益率：{latest_data['roe']:.2f}%\n"

            # 毛利率
            if 'grossprofit_margin' in df.columns and pd.notna(latest_data.get('grossprofit_margin')):
                result += f"  毛利率：{latest_data['grossprofit_margin']:.2f}%\n"

            result += "\n偿债能力：\n"
            # 资产负债率
            if 'debt_to_assets' in df.columns and pd.notna(latest_data.get('debt_to_assets')):
                result += f"  资产负债率：{latest_data['debt_to_assets']:.2f}%\n"

            # 流动比率
            if 'current_ratio' in df.columns and pd.notna(latest_data.get('current_ratio')):
                result += f"  流动比率：{latest_data['current_ratio']:.2f}\n"

            result += "\n成长能力：\n"
            # 净利润同比增长率
            if 'netprofit_growth_rate' in df.columns and pd.notna(latest_data.get('netprofit_growth_rate')):
                result += f"  净利润增长率：{latest_data['netprofit_growth_rate']:.2f}%\n"

            # 营业收入同比增长率
            if 'operate_income_growth_rate' in df.columns and pd.notna(latest_data.get('operate_income_growth_rate')):
                result += f"  营业收入增长率：{latest_data['operate_income_growth_rate']:.2f}%\n"

            # 添加报告期信息
            if 'report_date' in df.columns:
                result += f"\n报告期：{latest_data['report_date']}\n"

            return result

        except Exception as e:
            return f"获取港股财务数据失败: {str(e)}"

    def _get_sector_data(self) -> str:
        """获取行业板块数据"""
        try:
            # 使用tushare获取同花顺行业板块数据
            df = pro.ths_index()

            if df.empty:
                return "暂无行业板块数据"

            # 构建结果字符串
            result = "行业板块列表：\n\n"

            # 使用name列获取板块名称
            for i, row in df.head(20).iterrows():
                sector_name = row.get('name', '未知板块')
                count = row.get('count', 0)
                result += f"{i+1}. {sector_name} ({int(count)}只股票)\n"

            return result

        except Exception as e:
            return f"获取行业板块数据失败: {str(e)}"
