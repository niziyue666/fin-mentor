"""
A股智能分析系统 - Streamlit 网页界面
四象限仪表盘设计
"""
import streamlit as st
import os
import re
import sys
import pandas as pd
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 添加项目路径
project_root = os.path.dirname(os.path.abspath(__file__))
src_path = os.path.join(project_root, 'src', 'a_stock_analysis')
sys.path.insert(0, project_root)
sys.path.insert(0, src_path)
sys.path.insert(0, os.path.join(project_root, 'src'))

# 专业术语解释字典
TECH_TERMS = {
    "MA5": "（5日均线）最近5个交易日收盘价的平均值，反映短期趋势",
    "MA20": "（20日均线）最近20个交易日收盘价的平均值，反映中期趋势",
    "MA10": "（10日均线）最近10个交易日收盘价的平均值，反映中期趋势",
    "RSI": "（相对强弱指标）0-100的情绪温度计，70以上过热可能下跌，30以下超卖可能反弹",
    "MACD": "（指数平滑异同移动平均线）判断趋势动量的指标，金叉看涨，死叉看跌",
    "量比": "今日成交量/过去5日平均成交量，1为正常，<1缩量",
    "金叉": "短期均线/指标从下方穿过长期均线，是上涨信号",
    "死叉": "短期均线/指标从上方穿过长期均线，是下跌信号",
    "多头排列": "短期均线在长期均线上方，说明上涨趋势",
    "空头排列": "短期均线在长期均线下方，说明下跌趋势",
    "ROE": "（净资产收益率）股东投入的钱能赚多少回报，>15%算优秀",
    "PE": "（市盈率）股价/每股收益，越低越便宜",
    "PB": "（市净率）股价/每股净资产，<1可能低估",
    "毛利率": "(收入-成本)/收入，反映产品竞争力",
    "资产负债率": "总负债/总资产，<40%较安全",
    "EPS": "（每股收益）净利润/股本，越高越好",
    "净利润增速": "净利润同比增长幅度，越高说明盈利增长越快",
    "营收增速": "营业收入同比增长幅度，反映公司成长性",
}

# 生成术语tooltip的HTML
def get_term_tooltip_html():
    """生成术语tooltip的HTML和CSS"""
    terms_js = "{" + ",".join([f'"{k}":"{v}"' for k, v in TECH_TERMS.items()]) + "}"
    return f"""
<style>
.term-tooltip {{
    position: relative;
    display: inline-block;
    cursor: pointer;
    color: #ff6b6b;
    border-bottom: 1px dashed #ff6b6b;
}}
.term-tooltip .tooltip-text {{
    visibility: hidden;
    width: 280px;
    background-color: #333;
    color: #fff;
    text-align: left;
    border-radius: 6px;
    padding: 10px;
    position: absolute;
    z-index: 1000;
    bottom: 125%;
    left: 50%;
    margin-left: -140px;
    opacity: 0;
    transition: opacity 0.3s;
    font-size: 13px;
    line-height: 1.4;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
}}
.term-tooltip:hover .tooltip-text {{
    visibility: visible;
    opacity: 1;
}}
</style>
<script>
var termDefinitions = {terms_js};
function showTooltip(term) {{
    var def = termDefinitions[term];
    if (def) {{
        alert(term + "：" + def);
    }}
}}
</script>
"""
    return ""  # 先返回空，简化处理

def highlight_terms(text: str) -> str:
    """原样返回文本"""
    return text

def get_terms_in_text(text: str) -> list:
    """找出文本中出现的术语"""
    if not text:
        return []
    found = []
    for term in TECH_TERMS:
        # 支持中英文术语，term可能是中文或英文+数字
        if term in text:
            found.append((term, TECH_TERMS[term]))
    return found

def render_terms_legend(text: str):
    """渲染文本中出现的术语解释"""
    terms = get_terms_in_text(text)
    if terms:
        with st.expander("📚 术语解释", expanded=False):
            for term, meaning in terms:
                st.markdown(f"**{term}**：{meaning}")

def render_term_help():
    """渲染术语帮助按钮"""
    with st.expander("📚 点击查看专业术语解释"):
        cols = st.columns(2)
        for i, (term, meaning) in enumerate(TECH_TERMS.items()):
            with cols[i % 2]:
                st.markdown(f"**{term}**：{meaning}")

from datetime import datetime, timedelta

# 初始化tinyshare
import tinyshare as ts
TINYSHARE_TOKEN = "TZnsj62Vft6yb5Iwoa3uAit0e5biw8sn7ojoSm3O070QuojUrZRvtw3a446eb0b3"
ts.set_token(TINYSHARE_TOKEN)
pro = ts.pro_api()

# 初始化akshare
import akshare as ak


# ==================== 数据获取函数 ====================

def get_quote_data(stock_code):
    """获取实时行情"""
    try:
        if stock_code.endswith('.HK'):
            code = stock_code.replace('.HK', '')
            if len(code) == 4:
                code = '0' + code
            hk_code = f"{code}.HK"
            df = pro.daily(ts_code=hk_code, start_date=(datetime.now() - timedelta(days=5)).strftime('%Y%m%d'))
        else:
            df = pro.daily(ts_code=stock_code, start_date=(datetime.now() - timedelta(days=5)).strftime('%Y%m%d'))

        if df is None or df.empty:
            return None
        # 【关键修复】tushare返回的是降序（最新在前），需要按日期升序排序后取最后一条
        df = df.sort_values('trade_date').reset_index(drop=True)
        return df.iloc[-1].to_dict()
    except Exception as e:
        print(f"获取行情失败: {e}")
        return None


def get_daily_data(stock_code, days=60):
    """获取日线数据"""
    try:
        if stock_code.endswith('.HK'):
            code = stock_code.replace('.HK', '')
            if len(code) == 4:
                code = '0' + code
            hk_code = f"{code}.HK"
            df = pro.hk_daily(ts_code=hk_code, start_date=(datetime.now() - timedelta(days=days)).strftime('%Y%m%d'))
        else:
            df = pro.daily(ts_code=stock_code, start_date=(datetime.now() - timedelta(days=days)).strftime('%Y%m%d'))

        if df is None or df.empty:
            return None
        return df.sort_values('trade_date')
    except Exception as e:
        print(f"获取日线失败: {e}")
        return None


def get_financial_data(stock_code):
    """获取财务数据"""
    try:
        if stock_code.endswith('.HK'):
            code = stock_code.replace('.HK', '')
            if len(code) == 4:
                code = '0' + code
            hk_code = f"{code}.HK"
            df = pro.fina_indicator(ts_code=hk_code, limit=10)
        else:
            df = pro.fina_indicator(ts_code=stock_code, limit=10)

        if df is None or df.empty:
            return None
        # 按日期升序排序
        df = df.sort_values('end_date').reset_index(drop=True)
        # 去重（相同日期只保留一行）
        df = df.drop_duplicates(subset=['end_date'], keep='last')

        # 【修复】使用income接口获取营业收入，避免op_income为负的问题
        try:
            income_df = pro.income(ts_code=stock_code, limit=10)
            if not income_df.empty:
                income_df = income_df.sort_values('end_date').reset_index(drop=True)
                income_df = income_df.drop_duplicates(subset=['end_date'], keep='last')
                # 将营业收入合并到df中
                income_dict = dict(zip(income_df['end_date'], income_df['total_revenue']))
                df['op_income'] = df['end_date'].map(income_dict).fillna(df['op_income'])
        except:
            pass

        # 返回最近8个季度
        return df.tail(8)
    except Exception as e:
        print(f"获取财务失败: {e}")
        return None


def get_annual_eps(stock_code):
    """获取年度EPS用于计算静态PE"""
    try:
        df = pro.fina_indicator(ts_code=stock_code, limit=10)
        if df is None or df.empty:
            return None
        # 按日期排序
        df = df.sort_values('end_date').reset_index(drop=True)

        # 找2024年度数据
        annual_data = df[df['end_date'] == 20241231]
        if not annual_data.empty:
            return annual_data.iloc[0]['eps']

        # 如果没有2024年报，尝试用最新季度 * 4 估算年度EPS
        latest = df.iloc[-1]
        quarterly_eps = latest.get('eps', 0) or 0
        if quarterly_eps > 0:
            # 假设Q3数据，估算全年：Q1*4 或 Q3*1.33
            end_date = str(latest.get('end_date', ''))
            if '0930' in end_date:  # Q3
                return quarterly_eps * 1.33
            elif '0630' in end_date:  # Q2
                return quarterly_eps * 2
            elif '0331' in end_date:  # Q1
                return quarterly_eps * 4

        return None
    except:
        return None


def get_historical_pe(stock_code):
    """获取历史TTM PE（2023、2024、当前）"""
    try:
        # 获取财务数据
        df = pro.fina_indicator(ts_code=stock_code, limit=20)
        if df is None or df.empty:
            return {}
        df = df.sort_values('end_date').reset_index(drop=True)

        # 构建EPS字典
        eps_dict = {}
        for _, row in df.iterrows():
            end_date = row.get('end_date', 0)
            eps = row.get('eps', 0)
            if end_date and eps:
                eps_dict[end_date] = eps

        # TTM EPS 计算（注意：end_date是字符串类型）
        # 2023年末TTM = 2023年年度EPS
        ttm_2023 = eps_dict.get('20231231', None)
        # 2024年末TTM = 2024年年度EPS
        ttm_2024 = eps_dict.get('20241231', None)
        # 当前TTM = 2024Q2+Q3+Q4 + 2025Q1 = 2024年度 - Q1_2024 + Q1_2025
        ttm_current = None
        if ttm_2024:
            q1_2024 = eps_dict.get('20240331', 0)
            q1_2025 = eps_dict.get('20250331', 0)
            if q1_2024 and q1_2025:
                ttm_current = ttm_2024 - q1_2024 + q1_2025

        # 获取各年年末股价
        prices = {}
        try:
            # 2023年末
            quote_2023 = pro.daily(ts_code=stock_code, start_date='20231201', end_date='20231231')
            if not quote_2023.empty:
                quote_2023 = quote_2023.sort_values('trade_date').reset_index(drop=True)
                prices[2023] = quote_2023.iloc[-1]['close']

            # 2024年末
            quote_2024 = pro.daily(ts_code=stock_code, start_date='20241201', end_date='20241231')
            if not quote_2024.empty:
                quote_2024 = quote_2024.sort_values('trade_date').reset_index(drop=True)
                prices[2024] = quote_2024.iloc[-1]['close']

            # 2025年末
            quote_2025 = pro.daily(ts_code=stock_code, start_date='20251201', end_date='20251231')
            if not quote_2025.empty:
                quote_2025 = quote_2025.sort_values('trade_date').reset_index(drop=True)
                prices[2025] = quote_2025.iloc[-1]['close']

            # 当前
            quote_now = pro.daily(ts_code=stock_code, start_date=(datetime.now() - timedelta(days=5)).strftime('%Y%m%d'),
                                  end_date=datetime.now().strftime('%Y%m%d'))
            if not quote_now.empty:
                quote_now = quote_now.sort_values('trade_date').reset_index(drop=True)
                prices['current'] = quote_now.iloc[-1]['close']
        except:
            pass

        # 计算TTM PE（需要2025年末的TTM EPS）
        # 2025年末TTM = 2024Q2+Q3+Q4 + 2025Q1 = 2024年度 - Q1_2024 + Q1_2025
        ttm_2025 = None
        if ttm_2024:
            q1_2024_val = eps_dict.get('20240331', 0)
            q1_2025_val = eps_dict.get('20250331', 0)
            if q1_2024_val and q1_2025_val:
                ttm_2025 = ttm_2024 - q1_2024_val + q1_2025_val

        # 计算TTM PE
        result = {}
        if ttm_2023 and 2023 in prices:
            result[2023] = prices[2023] / ttm_2023
        if ttm_2024 and 2024 in prices:
            result[2024] = prices[2024] / ttm_2024
        if ttm_2025 and 2025 in prices:
            result[2025] = prices[2025] / ttm_2025
        if ttm_current and 'current' in prices:
            result['current'] = prices['current'] / ttm_current

        return result
    except:
        return {}


def get_sector_data():
    """获取板块数据"""
    try:
        df = pro.ths_index()
        if df is None or df.empty:
            return None
        return df.head(20)
    except Exception as e:
        return None


def get_capital_flow():
    """获取资金流向"""
    try:
        df = ak.stock_sector_fund_flow_rank()
        if df is None or df.empty:
            return None
        return df.head(10)
    except Exception as e:
        return None


def get_market_news(stock_code=None):
    """获取相关新闻 - 支持按股票代码搜索"""
    try:
        # 如果提供了股票代码，优先搜索个股新闻
        if stock_code:
            # 从股票代码提取数字部分（如 600519.SH -> 600519）
            code = stock_code.split('.')[0]
            if code.isdigit():
                df = ak.stock_news_em(symbol=code)
                if df is not None and not df.empty:
                    # 重命名列以便统一处理
                    df = df.rename(columns={'新闻标题': '标题', '发布时间': '时间'})
                    return df.head(10)

        # 如果没有股票代码或搜索失败，获取市场热点新闻
        df = ak.stock_info_global_em()
        if df is None or df.empty:
            return None
        return df.head(10)
    except Exception as e:
        return None


# ==================== 图表绘制函数 ====================

def plot_kline(df, stock_code):
    """绘制K线图"""
    if df is None or df.empty:
        return None

    import plotly.graph_objects as go

    df = df.tail(60).copy()
    for col in ['open', 'high', 'low', 'close', 'vol']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['open', 'high', 'low', 'close'])

    if df.empty:
        return None

    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=df['trade_date'],
        open=df['open'], high=df['high'], low=df['low'], close=df['close'],
        name='K线', increasing_line_color='red', decreasing_line_color='green'
    ))

    df['MA5'] = df['close'].rolling(window=5).mean()
    df['MA10'] = df['close'].rolling(window=10).mean()
    df['MA20'] = df['close'].rolling(window=20).mean()

    for ma, color, width in [('MA5', 'yellow', 1.5), ('MA10', 'pink', 1.5), ('MA20', 'blue', 1.5)]:
        fig.add_trace(go.Scatter(x=df['trade_date'], y=df[ma], mode='lines', name=ma,
                                 line=dict(color=color, width=width)))

    fig.update_layout(title=f'{stock_code} K线走势', xaxis_rangeslider_visible=False,
                     height=350, template='plotly_dark', hovermode='x unified')
    return fig


def plot_financial_indicators(fin_df):
    """绘制财务指标图"""
    if fin_df is None or fin_df.empty:
        return None

    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import math

    # 使用end_date作为x轴标签，转换为季度
    if 'end_date' in fin_df.columns:
        x_labels = []
        for d in fin_df['end_date']:
            month = int(str(d)[4:6])
            quarter = math.ceil(month / 3)
            x_labels.append(str(d)[:4] + 'Q' + str(quarter))
    else:
        x_labels = [f"Q{i+1}" for i in range(len(fin_df))]

    fig = make_subplots(rows=1, cols=2, subplot_titles=('ROE (%)', '毛利率 (%)'), horizontal_spacing=0.15)

    if 'roe' in fin_df.columns:
        fig.add_trace(go.Bar(x=x_labels, y=fin_df['roe'], name='ROE', marker_color='#00CC96'), row=1, col=1)
    if 'grossprofit_margin' in fin_df.columns:
        fig.add_trace(go.Bar(x=x_labels, y=fin_df['grossprofit_margin'], name='毛利率', marker_color='#AB63FA'), row=1, col=2)

    fig.update_layout(height=300, template='plotly_dark', showlegend=False)
    return fig


def plot_capital_flow(flow_df):
    """绘制资金流向图"""
    if flow_df is None or flow_df.empty:
        return None

    import plotly.graph_objects as go

    names = flow_df.iloc[:8].apply(lambda x: x.get('名称', x.get('板块', '未知'))[:6], axis=1)
    flows = flow_df.iloc[:8].apply(lambda x: x.get('今日主力净流入-净额', x.get('主力净流入', 0)) or 0, axis=1)

    colors = ['#00CC96' if f > 0 else '#EF553B' for f in flows]

    fig = go.Figure(go.Bar(x=names, y=flows, marker_color=colors))
    fig.update_layout(title='行业资金流向 (万元)', height=300, template='plotly_dark')
    return fig


def plot_price_trend(df):
    """绘制价格走势图"""
    if df is None or df.empty:
        return None

    import plotly.graph_objects as go

    df = df.tail(20).copy()
    df['close'] = pd.to_numeric(df['close'], errors='coerce')

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df['trade_date'], y=df['close'], mode='lines+markers',
                             name='收盘价', line=dict(color='#00CC96', width=2),
                             fill='tozeroy', fillcolor='rgba(0,204,150,0.2)'))
    fig.update_layout(title='收盘价走势', height=280, template='plotly_dark', hovermode='x unified')
    return fig


def plot_pe_history(hist_pe):
    """绘制历史PE走势折线图"""
    if not hist_pe or len(hist_pe) < 2:
        return None

    import plotly.graph_objects as go

    # 准备数据
    labels = []
    values = []

    if 2023 in hist_pe:
        labels.append('23末')
        values.append(hist_pe[2023])
    if 2024 in hist_pe:
        labels.append('24末')
        values.append(hist_pe[2024])
    if 2025 in hist_pe:
        labels.append('25末')
        values.append(hist_pe[2025])
    if 'current' in hist_pe:
        labels.append('当前')
        values.append(hist_pe['current'])

    if len(labels) < 2:
        return None

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=labels, y=values, mode='lines+markers+text',
                             name='TTM PE', line=dict(color='#FF6692', width=3),
                             text=[f'{v:.1f}' for v in values],
                             textposition='top center'))
    fig.update_layout(title='PE历史走势 (TTM)', height=250, template='plotly_dark',
                      hovermode='x unified', yaxis_title='PE倍数')
    return fig


# ==================== 运行分析 ====================

def run_analysis(company_name, stock_code, selected_features):
    """运行分析"""
    from a_stock_analysis.crew import AStockAnalysisCrew

    # 构建输入
    inputs = {
        'company_name': company_name,
        'stock_code': stock_code,
        'market': 'SH' if stock_code.endswith('.SH') else ('SZ' if stock_code.endswith('.SZ') else 'HK'),
        'selected_features': ','.join(selected_features)
    }

    # 创建 crew 实例
    crew_instance = AStockAnalysisCrew().crew()

    # kickoff 获取结果
    result = crew_instance.kickoff(inputs=inputs)

    # 获取所有任务输出
    all_outputs = []

    # 方法1: 从 result.tasks_output 获取 (如果 CrewAI 支持)
    if hasattr(result, 'tasks_output') and result.tasks_output:
        for task_output in result.tasks_output:
            if task_output:
                all_outputs.append(str(task_output))

    # 方法2: 从 crew_instance.tasks 获取每个任务的输出
    if not all_outputs and hasattr(crew_instance, 'tasks'):
        for task in crew_instance.tasks:
            if hasattr(task, 'output') and task.output:
                output_str = str(task.output)
                if output_str and output_str.strip():
                    all_outputs.append(output_str)

    # 方法3: 从 result 直接获取 (可能是最后一个任务)
    if not all_outputs:
        all_outputs = [str(result)]

    # 如果只有1个输出，尝试从中提取多个 JSON
    if len(all_outputs) == 1:
        import re
        combined = all_outputs[0]
        q_outputs = []
        for q_id in ['Q1', 'Q2', 'Q3', 'Q4']:
            pattern = f'"module_id"\\s*:\\s*"{q_id}"'
            matches = list(re.finditer(pattern, combined))
            for match in matches:
                start = combined.rfind('```', 0, match.start())
                if start == -1:
                    start = match.start()
                end = combined.find('```', match.end())
                if end == -1:
                    end = len(combined)
                q_outputs.append(combined[start:end].strip())
        if q_outputs:
            all_outputs = q_outputs

    # 合并所有输出
    combined_result = "\n\n".join(all_outputs)

    return combined_result


def parse_ai_json_result(result_text):
    """解析AI返回的JSON结果，分发到各象限"""
    import json
    import re

    report_sections = {
        'market': {},
        'financial': {},
        'sentiment': {},
        'investment': {}
    }

    try:
        result_text = str(result_text) if not isinstance(result_text, str) else result_text

        # 查找包含 "module_id": "QX" 的完整JSON对象
        for q_id, section in [('Q1', 'market'), ('Q2', 'financial'), ('Q3', 'sentiment'), ('Q4', 'investment')]:
            pattern = f'"module_id"\\s*:\\s*"{q_id}"'
            matches = list(re.finditer(pattern, result_text))

            for match in matches:
                start_pos = match.start()
                brace_start = result_text.rfind('{', 0, start_pos)
                if brace_start == -1:
                    continue

                brace_count = 0
                end_pos = brace_start
                for i in range(brace_start, len(result_text)):
                    if result_text[i] == '{':
                        brace_count += 1
                    elif result_text[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end_pos = i + 1
                            break

                json_str = result_text[brace_start:end_pos]
                try:
                    data = json.loads(json_str)
                    report_sections[section] = data
                except json.JSONDecodeError:
                    continue

    except Exception as e:
        print(f"JSON解析错误: {e}")

    return report_sections


# ==================== 页面配置 ====================

st.set_page_config(page_title="A股智能分析系统", page_icon="📈", layout="wide")

st.title("📈 Fin-Mentor Pro 智能投研系统")

# ==================== 侧边栏 ====================

with st.sidebar:
    st.header("📝 分析配置")

    company_name = st.text_input("公司名称", value="贵州茅台", key="company_input")
    stock_code = st.text_input("股票代码", value="600519.SH", key="stock_input")

    st.markdown("---")
    st.subheader("🎯 选择分析模块")

    market_analysis = st.checkbox("📈 市场分析", value=True, help="技术面 + 资金面 + 板块")
    financial_analysis = st.checkbox("💰 财务分析", value=True, help="盈利 + 偿债 + 成长 + 估值")
    sentiment_analysis = st.checkbox("😊 情绪分析", value=True, help="资金情绪 + 技术情绪 + 舆情")
    investment_advice = st.checkbox("💡 投资建议", value=True, help="综合评级 + 风险提示")

    st.markdown("---")
    st.markdown("**股票代码格式：**")
    st.markdown("- 上交所：600519.SH")
    st.markdown("- 深交所：000001.SZ")
    st.markdown("- 港股：00700.HK")

    analyze_button = st.button("🚀 开始分析", type="primary", use_container_width=True)


# ==================== 主逻辑 ====================

# 初始化 session_state 变量
if 'analysis_result' not in st.session_state:
    st.session_state.analysis_result = None
if 'quote_data' not in st.session_state:
    st.session_state.quote_data = None
if 'daily_data' not in st.session_state:
    st.session_state.daily_data = None
if 'fin_data' not in st.session_state:
    st.session_state.fin_data = None
if 'sector_data' not in st.session_state:
    st.session_state.sector_data = None
if 'flow_data' not in st.session_state:
    st.session_state.flow_data = None
if 'news_data' not in st.session_state:
    st.session_state.news_data = None
if 'current_company' not in st.session_state:
    st.session_state.current_company = None
if 'current_code' not in st.session_state:
    st.session_state.current_code = None


# 处理分析请求
if analyze_button:
    if not company_name or not stock_code:
        st.error("请输入公司名称和股票代码")
    else:
        # 获取数据
        with st.spinner("正在获取数据..."):
            quote_data = get_quote_data(stock_code)
            daily_data = get_daily_data(stock_code)
            fin_data = get_financial_data(stock_code)
            sector_data = get_sector_data()
            flow_data = get_capital_flow()
            news_data = get_market_news(stock_code)

        # 显示头部信息
        st.markdown("---")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("股票", f"{company_name}")
        with col2:
            price = quote_data.get('close', 0) if quote_data else 0
            st.metric("当前价", f"{price:.2f}")
        with col3:
            pct = quote_data.get('pct_chg', 0) if quote_data else 0
            st.metric("涨跌幅", f"{pct:.2f}%")
        with col4:
            vol = quote_data.get('vol', 0) if quote_data else 0
            st.metric("成交量", f"{int(vol):,}")

        # 运行AI分析
        with st.spinner("正在运行AI分析，请稍候..."):
            try:
                result = run_analysis(company_name, stock_code, [])
                report_sections = parse_ai_json_result(result)

                # Debug: 显示解析结果
                with st.expander("🔍 Debug: 解析结果", expanded=False):
                    st.write("解析到的sections:", list(report_sections.keys()))
                    for k, v in report_sections.items():
                        st.write(f"{k}: {v}")

                # 存储研报到向量库（拆分为data和reasoning两个chunk）
                try:
                    from src.a_stock_analysis.tools.report_vector_tool import ReportVectorTool
                    vector_tool = ReportVectorTool()

                    # 提取各模块JSON数据
                    q1_content = json.dumps(report_sections.get('market', {}), ensure_ascii=False) if report_sections.get('market') else ""
                    q2_content = json.dumps(report_sections.get('financial', {}), ensure_ascii=False) if report_sections.get('financial') else ""
                    q3_content = json.dumps(report_sections.get('sentiment', {}), ensure_ascii=False) if report_sections.get('sentiment') else ""
                    q4_content = json.dumps(report_sections.get('investment', {}), ensure_ascii=False) if report_sections.get('investment') else ""

                    # 提取各模块推理过程
                    q1_reasoning = report_sections.get('market', {}).get('analysis_reasoning', '') if report_sections.get('market') else ""
                    q2_reasoning = report_sections.get('financial', {}).get('analysis_reasoning', '') if report_sections.get('financial') else ""
                    q3_reasoning = report_sections.get('sentiment', {}).get('analysis_reasoning', '') if report_sections.get('sentiment') else ""
                    q4_reasoning = report_sections.get('investment', {}).get('analysis_reasoning', '') if report_sections.get('investment') else ""

                    if q1_content:  # 只有成功解析才存储
                        store_result = vector_tool._run(
                            stock_code=stock_code,
                            company_name=company_name,
                            q1_content=q1_content,
                            q2_content=q2_content,
                            q3_content=q3_content,
                            q4_content=q4_content,
                            q1_reasoning=q1_reasoning,
                            q2_reasoning=q2_reasoning,
                            q3_reasoning=q3_reasoning,
                            q4_reasoning=q4_reasoning
                        )
                        st.session_state.report_stored = True
                        print(f"研报存储结果: {store_result}")
                except Exception as e:
                    print(f"存储研报失败: {e}")
                    st.session_state.report_stored = False

                # 保存结果
                st.session_state.analysis_result = result
                st.session_state.report_sections = report_sections
                st.session_state.quote_data = quote_data
                st.session_state.daily_data = daily_data
                st.session_state.fin_data = fin_data
                st.session_state.sector_data = sector_data
                st.session_state.flow_data = flow_data
                st.session_state.news_data = news_data
                st.session_state.current_company = company_name
                st.session_state.current_code = stock_code

                st.rerun()

            except Exception as e:
                import traceback
                st.error(f"AI分析失败: {str(e)}")
                st.code(traceback.format_exc())


# 显示分析结果（如果有）
if st.session_state.analysis_result:
    # 恢复数据
    result = st.session_state.analysis_result
    report_sections = st.session_state.get('report_sections', {})
    quote_data = st.session_state.quote_data
    daily_data = st.session_state.daily_data
    fin_data = st.session_state.fin_data
    sector_data = st.session_state.sector_data
    flow_data = st.session_state.flow_data
    news_data = st.session_state.news_data
    company_name = st.session_state.current_company
    stock_code = st.session_state.current_code

    # 重新显示头部信息
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("股票", f"{company_name}")
    with col2:
        price = quote_data.get('close', 0) if quote_data else 0
        st.metric("当前价", f"{price:.2f}")
    with col3:
        pct = quote_data.get('pct_chg', 0) if quote_data else 0
        st.metric("涨跌幅", f"{pct:.2f}%")
    with col4:
        vol = quote_data.get('vol', 0) if quote_data else 0
        st.metric("成交量", f"{int(vol):,}")

    # Q1: 市场分析
    if market_analysis:
        st.markdown("---")
        st.markdown("## 📈 Q1: 市场技术与动能")

        col_chart, col_data = st.columns([2, 1])

        with col_chart:
            if daily_data is not None:
                fig_kline = plot_kline(daily_data, stock_code)
                if fig_kline:
                    st.plotly_chart(fig_kline, use_container_width=True)

        with col_data:
            st.markdown("### 关键指标")
            if daily_data is not None and len(daily_data) >= 20:
                # 计算MA5和MA20
                daily_data_copy = daily_data.copy()
                daily_data_copy['MA5'] = daily_data_copy['close'].rolling(window=5).mean()
                daily_data_copy['MA20'] = daily_data_copy['close'].rolling(window=20).mean()
                latest = daily_data_copy.iloc[-1]
                ma5 = latest.get('MA5', 0)
                ma20 = latest.get('MA20', 0)
                current_price = latest.get('close', 0)
                st.metric("当前价", f"{current_price:.2f}")
                st.metric("MA5", f"{ma5:.2f}")
                st.metric("MA20", f"{ma20:.2f}")
                trend = "多头" if ma5 > ma20 else "空头"
                st.metric("均线趋势", trend)

            st.caption("K线图展示股价走势，MA5/10/20为移动平均线")

        st.markdown("### 📝 分析解读")
        if report_sections.get('market', {}):
            market_data = report_sections['market']
            st.markdown(f"**趋势状态**: {market_data.get('trend_status', '未知')}")
            st.markdown(f"**资金流向**: {market_data.get('fund_flow', '暂无')}")
            st.markdown(f"**分析点评**: {market_data.get('analysis_text', '')}")

            # 显示触发条件（机会信号 vs 风险信号）
            trigger = market_data.get('trigger_conditions', {})
            if trigger:
                opportunity = trigger.get('机会信号', '')
                risk = trigger.get('风险信号', '')
                if opportunity or risk:
                    with st.expander("🚦 交易触发条件", expanded=True):
                        if opportunity:
                            st.markdown(f"**✅ 机会信号**: {opportunity}")
                        if risk:
                            st.markdown(f"**🔴 风险信号**: {risk}")
        else:
            st.info("请查看下方完整分析报告")

    # Q2: 财务分析
    if financial_analysis:
        st.markdown("---")
        st.markdown("## 💰 Q2: 财务健康度")

        # 计算PE和PB
        pe = 0
        pb = 0
        if fin_data is not None and not fin_data.empty:
            latest = fin_data.iloc[-1]
            end_date = latest.get('end_date', '')
            try:
                import tinyshare as ts
                token = "TZnsj62Vft6yb5Iwoa3uAit0e5biw8sn7ojoSm3O070QuojUrZRvtw3a446eb0b3"
                ts.set_token(token)
                pro = ts.pro_api()
                from datetime import datetime, timedelta
                quote = pro.daily(ts_code=stock_code, start_date=(datetime.now() - timedelta(days=5)).strftime('%Y%m%d'),
                                  end_date=datetime.now().strftime('%Y%m%d'))
                quote = quote.sort_values('trade_date').reset_index(drop=True)
                current_price = quote.iloc[-1]['close']
                bps = latest.get('bps', 0) or 0
                # 使用TTM EPS计算PE
                hist_pe = get_historical_pe(stock_code)
                pe = hist_pe.get('current', 0) if hist_pe else 0
                if pe == 0:
                    # 备用：使用年度EPS
                    annual_eps = get_annual_eps(stock_code)
                    if annual_eps:
                        pe = current_price / annual_eps
                pb = current_price / bps if bps else 0
            except:
                pass

            # 简洁的四列布局
            col1, col2, col3, col4 = st.columns(4)
            op_income = latest.get('op_income', 0) or 0
            or_yoy = latest.get('or_yoy', 0) or 0
            netprofit_yoy = latest.get('netprofit_yoy', 0) or 0

            # 获取经营现金流数据
            operating_cashflow = 0
            try:
                cashflow_df = pro.cashflow(ts_code=stock_code, limit=2)
                if not cashflow_df.empty:
                    cashflow_df = cashflow_df.sort_values('end_date').reset_index(drop=True)
                    operating_cashflow = cashflow_df.iloc[-1].get('n_cashflow_act', 0) or 0
            except:
                pass

            # 获取净利润（从income接口更准确）
            netprofit = 0
            try:
                income_df = pro.income(ts_code=stock_code, limit=2)
                if not income_df.empty:
                    income_df = income_df.sort_values('end_date').reset_index(drop=True)
                    netprofit = income_df.iloc[-1].get('n_income', 0) or 0
            except:
                pass

            with col1:
                st.markdown("**📈 盈利能力**")
                st.markdown(f"- 营业收入：{op_income/1e8:.1f}亿")
                st.markdown(f"- 净利润：{netprofit/1e8:.1f}亿")
                st.markdown(f"- 净利润率：{latest.get('netprofit_margin', 0):.1f}%")
                st.markdown(f"- EPS：{latest.get('eps', 0):.2f}元")

            with col2:
                # 计算环比（需要上一季度数据）
                or_qoq = 0
                if len(fin_data) >= 2:
                    prev = fin_data.iloc[-2]
                    curr = fin_data.iloc[-1]
                    curr_income = curr.get('op_income', 0) or 0
                    prev_income = prev.get('op_income', 0) or 0
                    if prev_income > 0:
                        or_qoq = (curr_income - prev_income) / prev_income * 100

                st.markdown("**📈 成长能力**")
                st.markdown(f"- 营收增速：{or_yoy:.1f}% (同比)")
                st.markdown(f"- 净利增速：{netprofit_yoy:.1f}% (同比)")
                if or_qoq != 0:
                    st.caption(f"环比 {or_qoq:+.1f}%")

            with col3:
                # 获取历史PE数据
                hist_pe = get_historical_pe(stock_code)

                st.markdown("**📊 估值指标**")
                # 处理PE为负的情况
                if pe < 0:
                    st.markdown("- PE（TTM）：不适用（亏损）")
                    st.caption("公司亏损，PE失效，建议参考PB")
                else:
                    st.markdown(f"- PE（TTM）：{pe:.1f}倍")
                    # 显示历史PE对比
                    if 2023 in hist_pe and 2024 in hist_pe and 2025 in hist_pe and 'current' in hist_pe:
                        pe_2023 = hist_pe[2023]
                        pe_2024 = hist_pe[2024]
                        pe_2025 = hist_pe[2025]
                        pe_now = hist_pe['current']
                        if pe_2023 and pe_2024 and pe_2025 and pe_now:
                            avg_pe = (pe_2023 + pe_2024 + pe_2025) / 3
                            pct = (pe_now - avg_pe) / avg_pe * 100
                            status = "↓偏低" if pct < 0 else "↑偏高"
                            st.caption(f"历史: {pe_2023:.0f}→{pe_2024:.0f}→{pe_2025:.0f}→{pe_now:.0f}倍 ({status}{abs(pct):.0f}%)")
                st.markdown(f"- PB：{pb:.2f}倍")

            with col4:
                st.markdown("**🏢 资产质量**")
                st.markdown(f"- ROE：{latest.get('roe', 0):.2f}%")
                st.markdown(f"- 毛利率：{latest.get('grossprofit_margin', 0):.2f}%")
                st.markdown(f"- 资产负债率：{latest.get('debt_to_assets', 0):.2f}%")
                st.markdown(f"- 经营现金流：{operating_cashflow/1e8:.1f}亿")

            # 显示PE历史走势折线图
            hist_pe = get_historical_pe(stock_code)
            if hist_pe:
                fig_pe = plot_pe_history(hist_pe)
                if fig_pe:
                    st.plotly_chart(fig_pe, use_container_width=True)

            st.caption(f"数据截至：{end_date}")

        st.markdown("### 📝 分析解读")
        if report_sections.get('financial', {}):
            financial_data = report_sections['financial']

            # 显示股票类型（盈利股/亏损股）
            stock_type = financial_data.get('股票类型', '')
            if stock_type:
                if '亏损' in stock_type:
                    st.markdown(f"**股票类型**: 🔴 {stock_type}")
                else:
                    st.markdown(f"**股票类型**: 🟢 {stock_type}")

            st.markdown(f"**估值水平**: {financial_data.get('valuation_level', '未知')}")
            st.markdown(f"**财务评分**: {financial_data.get('financial_score', '未知')}")

            # 显示维度得分详情
            dimension_scores = financial_data.get('dimension_scores', {})
            if dimension_scores:
                with st.expander("📊 评分维度详情", expanded=False):
                    for dim, score in dimension_scores.items():
                        st.markdown(f"• **{dim}**: {score}")

            # 显示免责声明（亏损股）
            disclaimer = financial_data.get('disclaimer', '')
            if disclaimer:
                st.info(f"⚠️ {disclaimer}")

            st.markdown(f"**趋势分析**: {financial_data.get('trend_analysis', '暂无')}")
            st.markdown(f"**分析点评**: {financial_data.get('analysis_text', '')}")

            # 显示谨慎信号
            caution = financial_data.get('caution_signal', '')
            if caution:
                st.warning(f"🛑 谨慎信号: {caution}")

            # 显示术语解释（放在最后）
            render_terms_legend(financial_data.get('analysis_text', ''))

    # Q3: 情绪分析
    if sentiment_analysis:
        st.markdown("---")
        st.markdown("## 😊 Q3: 博弈与情绪")

        if report_sections.get('sentiment', {}):
            sentiment_data = report_sections['sentiment']

            # 市场情绪
            market_sentiment = sentiment_data.get('市场情绪', {})
            if market_sentiment:
                st.markdown("### 🌍 市场情绪")
                market_status = market_sentiment.get('大盘状态', '-')
                market_mood = market_sentiment.get('市场情绪', '-')
                market_desc = market_sentiment.get('解读', '')
                st.markdown(f"**大盘状态**: {market_status} | **市场情绪**: {market_mood}")
                if market_desc:
                    st.caption(market_desc)
                st.divider()

            # 个股新闻情绪
            s1 = sentiment_data.get('S1_情绪总结', '')
            s2 = sentiment_data.get('S2_负面信号', '')
            s3 = sentiment_data.get('S3_正面信号', '')
            s4 = sentiment_data.get('S4_结构解读', '')
            s5 = sentiment_data.get('S5_建议关注', '')
            news_count = sentiment_data.get('news_count', '')

            if s1 or s2 or s3 or s4 or s5:
                st.markdown("### 📰 个股新闻情绪")
                # 显示新闻数量
                if news_count:
                    st.caption(f"共获取 {news_count} 条新闻")
                if s1:
                    st.markdown(f"**【S1 情绪总结】** {s1}")
                if s2:
                    st.markdown(f"**【S2 负面信号】** {s2}")
                if s3:
                    st.markdown(f"**【S3 正面信号】** {s3}")
                if s4:
                    st.markdown(f"**【S4 结构解读】** {s4}")
                if s5:
                    st.markdown(f"**【S5 建议关注】** {s5}")

            # 技术面分析
            tech_analysis = sentiment_data.get('技术面分析', '')
            if tech_analysis:
                st.markdown("### 📈 技术面情绪分析")
                st.markdown(tech_analysis)
                render_terms_legend(tech_analysis)

            # 综合判断
            overall = sentiment_data.get('综合判断', '')
            if overall:
                st.markdown("### 🎯 综合判断")
                st.markdown(f"**{overall}**")

    # Q4: 投资建议
    if investment_advice:
        st.markdown("---")
        st.markdown("## 💡 Q4: 导师最终策")

        st.success("✅ 分析完成！")
        if report_sections.get('investment', {}):
            investment_data = report_sections['investment']
            st.markdown(f"**投资评级**: {investment_data.get('investment_rating', '未知')}")

            st.markdown("**核心投研逻辑**:")
            core_logic = investment_data.get('core_logic', '')
            if isinstance(core_logic, list):
                for logic in core_logic:
                    st.write(f"- {logic}")
            else:
                st.markdown(core_logic)

            st.markdown("**知识点回顾**:")
            learning = investment_data.get('learning_summary', '')
            if isinstance(learning, list):
                for item in learning:
                    st.write(f"- {item}")
            else:
                st.markdown(learning)
        else:
            st.markdown(str(result))

    # 原始数据
    with st.expander("📊 原始数据"):
        st.markdown("### 财务数据")
        if fin_data is not None:
            st.dataframe(fin_data)

    # ========== 追问功能 ==========
    st.markdown("---")
    st.markdown("## 💬 追问助教")

    # 初始化追问历史
    if 'followup_history' not in st.session_state:
        st.session_state.followup_history = []

    # 保存当前报告到session
    if 'current_report' not in st.session_state:
        st.session_state.current_report = ""
    st.session_state.current_report = str(result)

    # 追问输入框（独立于主分析流程）
    col1, col2 = st.columns([4, 1])
    with col1:
        followup_question = st.text_input("有什么想问的？", placeholder="例如：为什么给这个评级？RSI是什么？", key="followup_input", label_visibility="collapsed")
    with col2:
        ask_button = st.button("提问", key="followup_btn")

    # 获取当前股票代码
    current_stock_code = st.session_state.get('current_code', '')

    # 处理追问（不 rerun，直接显示）
    if ask_button and followup_question:
        with st.spinner("助教思考中..."):
            try:
                from a_stock_analysis.crew import AStockAnalysisCrew
                from crewai import Task

                crew = AStockAnalysisCrew()
                followup_agent = crew.followup_tutor()

                followup_task = Task(
                    description=f"用户关于 {current_stock_code} 的追问：{followup_question}\n\n请先调用 ReportSearchTool 检索相关研报内容，再回答用户问题。",
                    agent=followup_agent,
                    expected_output="先调用ReportSearchTool检索研报，然后基于检索结果回答问题"
                )

                followup_result = followup_agent.execute_task(followup_task)
                st.session_state.followup_history.append((followup_question, str(followup_result)))

            except Exception as e:
                import traceback
                st.error(f"追问失败: {str(e)}")
                st.code(traceback.format_exc())

    # 显示追问历史
    for i, (q, a) in enumerate(st.session_state.followup_history):
        st.markdown(f"**你**: {q}")
        st.markdown(f"**助教**: {a}")
        st.markdown("---")

else:
    # 欢迎界面
    st.markdown("""
    ### 👋 欢迎使用 Fin-Mentor Pro 智能投研系统

    本系统采用**四象限仪表盘**设计，帮你系统化分析股票：

    | 象限 | 内容 | 说明 |
    |------|------|------|
    | Q1 | 市场技术 | K线、均线、趋势 |
    | Q2 | 财务健康 | ROE、毛利率、估值 |
    | Q3 | 情绪博弈 | 资金流向、量价关系 |
    | Q4 | 投资建议 | 综合评级、风险提示 |

    ### 🚀 使用方法

    1. 在左侧输入股票代码（如 600519.SH）
    2. 点击"开始分析"
    3. 等待AI分析完成（约1-2分钟）
    4. 查看四象限分析结果

    ### ⚠️ 注意

    - 首次运行可能需要更长时间（加载知识库）
    - 如遇问题请刷新页面重试
    """)
