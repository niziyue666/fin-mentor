from crewai.tools import BaseTool
from typing import Any, Optional, Type, Dict, List
from pydantic import BaseModel, Field
import pandas as pd
from datetime import datetime, timedelta
import tinyshare as ts
import akshare as ak
import re
from collections import defaultdict

TINYSHARE_TOKEN = "TZnsj62Vft6yb5Iwoa3uAit0e5biw8sn7ojoSm3O070QuojUrZRvtw3a446eb0b3"
ts.set_token(TINYSHARE_TOKEN)
pro = ts.pro_api()


class NewsSentimentAnalyzer:
    """新闻去重与情绪分析器"""

    # 关键词词典
    POSITIVE_KEYWORDS = [
        "涨停", "大涨", "上涨", "增长", "盈利", "利润", "突破", "创新高", "业绩预增",
        "订单", "中标", "签约", "合作", "扩产", "产能", "景气", "景气度", "需求",
        "增持", "回购", "分红", "送转", "业绩", "超预期", "景气上行", "需求旺盛",
        "市场份额", "竞争力", "龙头", "壁垒", "护城河", "定价权", "提价"
    ]

    NEGATIVE_KEYWORDS = [
        "跌停", "大跌", "下跌", "亏损", "盈利", "下滑", "减持", "业绩预亏", "爆雷",
        "风险", "诉讼", "调查", "处罚", "监管", "问询", "函", "警示", "立案",
        "造假", "违规", "退市", "ST", "带帽", "担保", "质押", "冻结", "减持",
        "利空", "业绩变脸", "商誉", "存货", "应收", "债务", "流动性",
        # 白酒/茅台相关负面
        "批价下跌", "批价回落", "动销不畅", "库存积压", "压货", "甩货",
        "平价", "1499", "放货", "抛货", "跌价", "促销", "降价"
    ]

    POSITIVE_KEYWORDS = [
        "涨停", "大涨", "上涨", "增长", "盈利", "利润", "突破", "创新高", "业绩预增",
        "订单", "中标", "签约", "合作", "扩产", "产能", "景气", "景气度", "需求",
        "增持", "回购", "分红", "送转", "业绩", "超预期", "景气上行", "需求旺盛",
        "市场份额", "竞争力", "龙头", "壁垒", "护城河", "定价权", "提价",
        # 白酒/茅台相关正面
        "批价上涨", "动销良好", "需求旺盛", "供不应求", "涨价", "提价"
    ]

    # 权威来源权重
    AUTHORITY_WEIGHTS = {
        "交易所": 1.5, "证监会": 1.5, "证监会": 1.5, "公司公告": 1.4,
        "新华社": 1.3, "人民日报": 1.3,
        "第一财经": 1.2, "财新": 1.2, "华尔街日报": 1.2, "路透": 1.2, "彭博": 1.2,
        "证券时报": 1.15, "中国证券报": 1.15, "上海证券报": 1.15,
        "新浪财经": 1.1, "东方财富": 1.1, "同花顺": 1.1, "雪球": 1.0,
        "微博": 0.8, "公众号": 0.7, "论坛": 0.6
    }

    def __init__(self):
        pass

    def deduplicate(self, news_list: List[Dict]) -> List[Dict]:
        """新闻去重"""
        if not news_list:
            return []

        # S1: 记录原始条数
        raw_count = len(news_list)

        # S2: 标题精确去重
        seen_titles = {}
        for item in news_list:
            title = item.get('标题', '').strip()
            if title and title not in seen_titles:
                seen_titles[title] = item

        candidates = list(seen_titles.values())

        # S3: 标题模糊去重（相似度 >= 85%）
        to_remove = set()
        for i in range(len(candidates)):
            if i in to_remove:
                continue
            for j in range(i + 1, len(candidates)):
                if j in to_remove:
                    continue
                title_i = candidates[i].get('标题', '')
                title_j = candidates[j].get('标题', '')
                if self._similarity(title_i, title_j) >= 0.85:
                    # 保留权威来源或发布时间最早的
                    if self._get_authority(candidates[i].get('标题', '')) > \
                       self._get_authority(candidates[j].get('标题', '')):
                        to_remove.add(j)
                    else:
                        to_remove.add(i)

        deduplicated = [candidates[i] for i in range(len(candidates)) if i not in to_remove]

        # S5: 记录去重结果
        self.raw_count = raw_count
        self.dedup_count = len(deduplicated)

        return deduplicated

    def _similarity(self, s1: str, s2: str) -> float:
        """计算两个字符串的相似度（简单版）"""
        if not s1 or not s2:
            return 0.0
        # 去除标点后比较
        s1 = re.sub(r'[^\w\u4e00-\u9fff]', '', s1)
        s2 = re.sub(r'[^\w\u4e00-\u9fff]', '', s2)
        if not s1 or not s2:
            return 0.0

        # 简单相似度：共同字符数 / 总字符数
        set1 = set(s1)
        set2 = set(s2)
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union > 0 else 0.0

    def _get_authority(self, title: str) -> float:
        """获取来源权威性权重"""
        for source, weight in self.AUTHORITY_WEIGHTS.items():
            if source in title:
                return weight
        return 1.0

    def analyze(self, news_list: List[Dict]) -> Dict:
        """分析新闻情绪"""
        if not news_list:
            return {
                "sentiment_score": None,
                "sentiment_structure": "无信号",
                "dedup_count": "0/0",
                "key_events": [],
                "market_implication": "暂无相关新闻，无法判断市场情绪"
            }

        # 去重
        deduplicated = self.deduplicate(news_list)

        # 对每条新闻打标
        scored_news = []
        for item in deduplicated:
            title = item.get('标题', '')
            content = item.get('内容', '')
            full_text = f"{title} {content}"

            # 情绪极性
            polarity = self._get_polarity(full_text)

            # 影响层级
            level = self._get_level(full_text)

            # 紧迫程度
            urgency = self._get_urgency(item.get('时间', ''))

            # 计算权重
            weight = self._calculate_weight(item, urgency)

            scored_news.append({
                "title": title,
                "polarity": polarity,
                "level": level,
                "urgency": urgency,
                "weight": weight,
                "url": item.get('链接', ''),
                "time": item.get('时间', '')
            })

        # 计算综合情绪分
        total_score = sum(n['polarity'] * n['weight'] for n in scored_news)
        max_possible = sum(n['weight'] for n in scored_news)
        sentiment_score = int(total_score / max_possible * 100) if max_possible > 0 else 0

        # 判断情绪结构
        structure = self._get_structure(scored_news)

        # 生成通俗解读
        implication = self._generate_implication(sentiment_score, structure, scored_news)

        # 后续关注信号
        watch_list = self._get_watch_list(scored_news, structure)

        return {
            "sentiment_score": sentiment_score,
            "sentiment_structure": structure,
            "dedup_count": f"{self.raw_count}/{self.dedup_count}",
            "key_events": scored_news,
            "market_implication": implication,
            "watch_list": watch_list
        }

    def _get_polarity(self, text: str) -> int:
        """获取情绪极性：利好+1/中性0/利空-1"""
        pos_count = sum(1 for kw in self.POSITIVE_KEYWORDS if kw in text)
        neg_count = sum(1 for kw in self.NEGATIVE_KEYWORDS if kw in text)

        if pos_count > neg_count:
            return 1
        elif neg_count > pos_count:
            return -1
        return 0

    def _get_level(self, text: str) -> str:
        """影响层级"""
        company_kw = ["公司", "该企业", "上市公司", "集团", "股份"]
        industry_kw = ["行业", "板块", "产业", "赛道"]
        macro_kw = ["宏观", "经济", "GDP", "政策", "货币"]

        if any(kw in text for kw in company_kw):
            return "公司层面"
        elif any(kw in text for kw in industry_kw):
            return "行业层面"
        elif any(kw in text for kw in macro_kw):
            return "宏观层面"
        return "公司层面"

    def _get_urgency(self, time_str: str) -> str:
        """紧迫程度"""
        if not time_str:
            return "常规公告"

        # 简单判断：包含"突发"、"紧急"等词
        if any(kw in time_str for kw in ["突发", "紧急"]):
            return "突发事件"

        # 判断时间（简化：当天发布为突发）
        try:
            if "今天" in time_str or "今日" in time_str:
                return "突发事件"
        except:
            pass
        return "常规公告"

    def _calculate_weight(self, item: Dict, urgency: str) -> float:
        """计算权重"""
        weight = 1.0

        # 时效性
        time_str = item.get('时间', '')
        if "今天" in time_str or "今日" in time_str:
            weight *= 1.5
        elif "昨天" in time_str or "昨日" in time_str:
            weight *= 1.2

        # 来源权威性
        weight *= self._get_authority(item.get('标题', ''))

        # 紧迫程度
        if urgency == "突发事件":
            weight *= 1.3
        elif urgency == "持续跟踪":
            weight *= 1.1

        return weight

    def _get_structure(self, news: List[Dict]) -> str:
        """判断情绪结构"""
        if not news:
            return "无信号"

        polarities = [n['polarity'] for n in news]
        positive_count = sum(1 for p in polarities if p > 0)
        negative_count = sum(1 for p in polarities if p < 0)

        # 检查是否有单条重磅利空
        for n in news:
            if n['polarity'] == -1 and n['weight'] > 2.0:
                return "黑天鹅型"

        # 多条小利空持续累积
        if negative_count >= 3 and positive_count <= 1:
            return "趋势型"

        # 利空与利好拉扯
        if positive_count >= 2 and negative_count >= 2:
            return "博弈型"

        # 负面新闻已持续发酵超过3天（简化：有多条负面但权重不高）
        if negative_count >= 2:
            return "钝化型"

        # 无明显信号
        if positive_count == 0 and negative_count == 0:
            return "无信号"

        return "正常波动"

    def _generate_implication(self, score: int, structure: str, news: List[Dict]) -> str:
        """生成面向初学者的通俗解读"""
        lines = []

        # S1: 情绪总结
        score_desc = "偏正面" if score > 0 else "偏负面" if score < 0 else "中性"
        lines.append(f"情绪综合评分：{score}分（{score_desc}），属于「{structure}」结构。")

        # S2: 负面信号
        negative_news = [n for n in news if n['polarity'] == -1]
        if negative_news:
            lines.append("\n【负面信号】")
            for n in negative_news[:3]:
                lines.append(f"• {n['title']}（{n['level']}，{n['urgency']}）")
        else:
            lines.append("\n【负面信号】暂无明显利空消息。")

        # S3: 正面信号
        positive_news = [n for n in news if n['polarity'] > 0]
        if positive_news:
            lines.append("\n【正面信号】")
            for n in positive_news[:3]:
                lines.append(f"• {n['title']}（{n['level']}）")
        else:
            lines.append("\n【正面信号】暂无明显利好消息。")

        # S4: 结构解读
        structure_meanings = {
            "黑天鹅型": "有重大利空消息突然出现，不确定性较高，建议观望等待澄清。",
            "趋势型": "多条不利消息累积，趋势可能继续恶化，需要关注止跌信号。",
            "博弈型": "多空消息交织，市场存在分歧，短期波动可能加剧。",
            "钝化型": "利空消息已被市场消化，密切关注是否出现止跌反弹信号。",
            "无信号": "消息面平静，没有明显的利好或利空。",
            "正常波动": "消息面正常，股价处于常规波动状态。"
        }
        lines.append(f"\n【结构解读】{structure_meanings.get(structure, '')}")

        # S5: 建议关注
        watch = self._get_watch_list(news, structure)
        if watch:
            lines.append("\n【建议关注】")
            for w in watch:
                lines.append(f"• {w}")

        return "\n".join(lines)

    def _get_watch_list(self, news: List[Dict], structure: str) -> List[str]:
        """后续关注信号"""
        watches = []

        if structure == "黑天鹅型":
            watches.append("公司是否发布澄清公告")
            watches.append("监管部门是否介入调查")
        elif structure == "趋势型":
            watches.append("是否出现止跌K线形态")
            watches.append("成交量是否萎缩")
        elif structure == "博弈型":
            watches.append("关注成交量变化方向")
            watches.append("等待突破方向明确")
        elif structure == "钝化型":
            watches.append("是否出现反弹信号")
            watches.append("关注支撑位有效性")

        # 通用
        watches.append("下一期财报预告")

        return watches[:3]


class MarketSentimentToolSchema(BaseModel):
    """市场情绪工具输入参数"""
    stock_code: str = Field(..., description="股票代码，如：000001.SZ或600519.SH")
    sentiment_type: str = Field(..., description="情绪类型：flow（资金流向）、news（新闻情绪）、technical（技术情绪）")


class MarketSentimentTool(BaseTool):
    name: str = "MarketSentimentTool"
    description: str = "分析A股市场情绪，包括资金流向、新闻情绪和技术情绪"
    args_schema: Type[BaseModel] = MarketSentimentToolSchema

    def _run(self, stock_code: str, sentiment_type: str = "flow", **kwargs) -> Any:
        """执行市场情绪分析"""
        try:
            if sentiment_type == "flow":
                return self._analyze_capital_flow(stock_code)
            elif sentiment_type == "news":
                return self._analyze_news_sentiment(stock_code)
            elif sentiment_type == "technical":
                return self._analyze_technical_sentiment(stock_code)
            elif sentiment_type == "market":
                return self._analyze_market_sentiment()
            else:
                raise ValueError(f"不支持的情绪类型: {sentiment_type}")
        except Exception as e:
            return f"市场情绪分析失败: {str(e)}"

    def _analyze_market_sentiment(self) -> str:
        """分析市场整体情绪"""
        try:
            import akshare as ak
            result = """
市场整体情绪分析：

"""
            try:
                df = ak.stock_zh_a_spot()
                if not df.empty:
                    # 计算市场广度指标
                    advancers = len(df[df['涨跌幅'] > 0])
                    decliners = len(df[df['涨跌幅'] < 0])
                    total = advancers + decliners
                    breadth_ratio = advancers / total if total > 0 else 0.5

                    result += f"上涨股票：{advancers}只\n"
                    result += f"下跌股票：{decliners}只\n"
                    result += f"市场广度：{breadth_ratio:.2f}\n"

                    # 恐慌贪婪指数简化版
                    if breadth_ratio > 0.7:
                        fear_greed = "贪婪"
                    elif breadth_ratio > 0.5:
                        fear_greed = "乐观"
                    elif breadth_ratio > 0.3:
                        fear_greed = "中性"
                    elif breadth_ratio > 0.2:
                        fear_greed = "恐慌"
                    else:
                        fear_greed = "极度恐慌"

                    result += f"市场情绪：{fear_greed}\n"
            except Exception as e:
                result += f"市场情绪获取失败：{str(e)}\n"

            return result

        except Exception as e:
            return f"市场情绪分析失败: {str(e)}"

    def _analyze_capital_flow(self, stock_code: str) -> str:
        """分析资金流向"""
        try:
            result = f"""
股票 {stock_code} 资金流向分析：
"""

            # 只获取个股数据分析资金流向（akshare不稳定）
            result += "=== 个股资金流向分析 ===\n"
            try:
                end_date = datetime.now().strftime('%Y%m%d')
                start_date = (datetime.now() - timedelta(days=5)).strftime('%Y%m%d')

                df = pro.daily(ts_code=stock_code, start_date=start_date, end_date=end_date)

                if not df.empty and len(df) >= 2:
                    df = df.sort_values('trade_date')

                    latest = df.iloc[-1]
                    prev = df.iloc[-2]

                    volume_ratio = latest['vol'] / df['vol'].rolling(window=5).mean().iloc[-1] if df['vol'].rolling(window=5).mean().iloc[-1] > 0 else 1
                    price_change = (latest['close'] - prev['close']) / prev['close'] * 100 if prev['close'] > 0 else 0

                    result += f"量比：{volume_ratio:.2f}倍\n"
                    result += f"价格变动：{price_change:+.2f}%\n"

                    if volume_ratio > 1.5 and price_change > 2:
                        flow_status = "💰 资金积极流入"
                    elif volume_ratio > 1.2 and price_change > 0:
                        flow_status = "📈 资金温和流入"
                    elif volume_ratio < 0.8 and price_change < -1:
                        flow_status = "📉 资金流出"
                    elif volume_ratio > 1.5 and price_change < 0:
                        flow_status = "🔄 资金分歧较大"
                    else:
                        flow_status = "➡️ 资金流向平稳"

                    result += f"资金流向：{flow_status}\n"

            except Exception as e:
                result += f"个股资金分析失败: {str(e)}\n"

            return result

        except Exception as e:
            return f"资金流向分析失败: {str(e)}"

    def _analyze_news_sentiment(self, stock_code: str) -> str:
        """分析新闻情绪，返回文本"""
        try:
            import akshare as ak
            news_list = []

            # 从股票代码提取数字部分（如 600519.SH -> 600519）
            code = stock_code.split('.')[0]

            # 使用akshare获取个股新闻，取30条
            if code.isdigit():
                try:
                    df = ak.stock_news_em(symbol=code)
                    if df is not None and not df.empty:
                        # 获取前30条新闻
                        news_items = df.head(30)
                        for _, row in news_items.iterrows():
                            title = row.get('新闻标题', row.get('标题', '无标题'))
                            pub_time = row.get('发布时间', row.get('时间', ''))
                            url = row.get('原文链接', row.get('链接', ''))

                            news_list.append({
                                "标题": str(title) if pd.notna(title) else "无标题",
                                "时间": str(pub_time) if pd.notna(pub_time) else "",
                                "链接": str(url) if pd.notna(url) else ""
                            })
                except Exception as e:
                    pass

            # 构建文本结果供AI分析
            result = f"""
股票 {stock_code} 新闻舆情分析：

请仔细阅读以下{len(news_list)}条新闻标题，分析每条是利好、利空还是中性：

"""
            for i, item in enumerate(news_list, 1):
                result += f"{i}. 【{item['时间']}】{item['标题']}\n"

            if not news_list:
                result += "未获取到该股票的最新新闻。\n"

            result += "\n【重要】请基于以上新闻标题，分析市场情绪，给出你的判断。\n"
            result += "注意：你需要自己阅读每条新闻标题，判断是利好还是利空，不需要调用任何工具。\n"
            result += "下面的技术面数据仅供参考，不是新闻！\n"

            # 使用tushare获取技术面情绪分析（分开，避免混淆）
            result += "\n\n=== 参考：技术面数据（非新闻）===\n"
            try:
                end_date = datetime.now().strftime('%Y%m%d')
                start_date = (datetime.now() - timedelta(days=5)).strftime('%Y%m%d')

                df = pro.daily(ts_code=stock_code, start_date=start_date, end_date=end_date)

                if not df.empty:
                    df = df.sort_values('trade_date')

                    up_days = 0
                    down_days = 0
                    for _, row in df.iterrows():
                        if row['pct_chg'] > 0:
                            up_days += 1
                            down_days = 0
                        elif row['pct_chg'] < 0:
                            down_days += 1
                            up_days = 0

                    avg_volume = df['vol'].mean()
                    latest_volume = df.iloc[-1]['vol']
                    volume_trend = latest_volume / avg_volume if avg_volume > 0 else 1

                    total_change = df['pct_chg'].sum()
                    positive_days = len(df[df['pct_chg'] > 0])
                    total_days = len(df)

                    result += f"连续上涨天数：{up_days}天\n"
                    result += f"连续下跌天数：{down_days}天\n"
                    result += f"5日涨跌合计：{total_change:+.2f}%\n"
                    result += f"上涨天数：{positive_days}/{total_days}天\n"

                    if up_days >= 3 and volume_trend > 1:
                        sentiment = "🔥 乐观"
                    elif down_days >= 3:
                        sentiment = "😰 悲观"
                    elif total_change > 3:
                        sentiment = "😊 偏多"
                    elif total_change < -3:
                        sentiment = "😟 偏空"
                    else:
                        sentiment = "😐 中性"

                    result += f"\n技术面情绪：{sentiment}\n"

            except Exception as e:
                result += f"\n情绪分析获取失败: {str(e)}\n"

            result += """
=== 风险提示 ===
• 注意市场整体情绪波动风险
• 建议结合基本面分析决策
• 新闻情绪仅供参考，不构成投资建议
"""

            return result

        except Exception as e:
            return f"新闻情绪分析失败: {str(e)}"

    def _analyze_technical_sentiment(self, stock_code: str) -> str:
        """分析技术情绪"""
        try:
            # 使用tushare获取历史数据
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=60)).strftime('%Y%m%d')

            df = pro.daily(ts_code=stock_code, start_date=start_date, end_date=end_date)

            if df.empty:
                return f"未找到股票 {stock_code} 的历史数据"

            # 按日期排序
            df = df.sort_values('trade_date')

            result = f"""
股票 {stock_code} 技术情绪分析：

=== 技术指标分析 ===
"""

            # 计算技术指标
            df['MA5'] = df['close'].rolling(window=5).mean()
            df['MA10'] = df['close'].rolling(window=10).mean()
            df['MA20'] = df['close'].rolling(window=20).mean()
            df['MA30'] = df['close'].rolling(window=30).mean()

            # RSI计算
            df['RSI'] = self._calculate_rsi(df['close'], 14)

            # MACD计算
            df['EMA12'] = df['close'].ewm(span=12, adjust=False).mean()
            df['EMA26'] = df['close'].ewm(span=26, adjust=False).mean()
            df['MACD'] = df['EMA12'] - df['EMA26']
            df['SIGNAL'] = df['MACD'].ewm(span=9, adjust=False).mean()
            df['HIST'] = df['MACD'] - df['SIGNAL']

            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) >= 2 else df.iloc[-1]

            # 价格趋势
            ma20 = latest['MA20'] if pd.notna(latest['MA20']) else latest['close']
            ma5 = latest['MA5'] if pd.notna(latest['MA5']) else latest['close']

            price_trend = "📈 上升趋势" if latest['close'] > ma20 and ma5 > ma20 else \
                        "📉 下降趋势" if latest['close'] < ma20 and ma5 < ma20 else \
                        "➡️ 震荡走势"

            result += f"价格趋势：{price_trend}\n"
            result += f"当前价格：{latest['close']:.2f}\n"
            result += f"MA5：{ma5:.2f}\n"
            result += f"MA20：{ma20:.2f}\n"

            # RSI分析
            rsi_value = latest['RSI'] if pd.notna(latest['RSI']) else 50
            if rsi_value > 70:
                rsi_sentiment = "⚠️ 超买状态"
            elif rsi_value < 30:
                rsi_sentiment = "💡 超卖状态"
            elif rsi_value > 60:
                rsi_sentiment = "🔥 强势区域"
            elif rsi_value < 40:
                rsi_sentiment = "❄️ 弱势区域"
            else:
                rsi_sentiment = "😐 正常区域"

            result += f"RSI(14)：{rsi_value:.2f} ({rsi_sentiment})\n"

            # MACD分析
            macd_val = latest['MACD']
            signal_val = latest['SIGNAL']
            prev_macd = prev['MACD']
            prev_signal = prev['SIGNAL']

            macd_signal = "📈 金叉信号" if macd_val > signal_val and prev_macd <= prev_signal else \
                         "📉 死叉信号" if macd_val < signal_val and prev_macd >= prev_signal else \
                         "➡️ 持续" if macd_val > signal_val else "⬇️ 持续"

            result += f"MACD：{macd_signal}\n"

            result += "\n=== 成交量分析 ===\n"

            # 成交量分析
            avg_volume = df['vol'].rolling(window=5).mean().iloc[-1]
            current_volume = latest['vol']
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1

            volume_sentiment = "🔥 放量" if volume_ratio > 1.5 else \
                              "📊 均量" if 0.8 <= volume_ratio <= 1.5 else \
                              "📉 缩量"

            result += f"成交量：{volume_sentiment} ({volume_ratio:.2f}倍)\n"

            result += "\n=== 综合技术情绪 ===\n"

            # 综合评分
            score = 0
            if latest['close'] > ma20:
                score += 2
            if 30 <= rsi_value <= 70:
                score += 1
            if macd_val > signal_val:
                score += 1
            if volume_ratio > 1:
                score += 1

            if score >= 4:
                overall_sentiment = "🟢 强势看多"
            elif score >= 2:
                overall_sentiment = "🟡 偏多"
            elif score >= 0:
                overall_sentiment = "🟠 偏空"
            else:
                overall_sentiment = "🔴 弱势"

            result += f"综合评分：{score}/5 分\n"
            result += f"技术情绪：{overall_sentiment}\n"

            result += "\n=== 操作建议 ===\n"
            if score >= 4:
                result += "• 技术形态强势，可考虑逢低建仓\n"
                result += "• 注意控制仓位，设置止损\n"
            elif score >= 2:
                result += "• 技术面偏多，谨慎看好\n"
                result += "• 建议结合基本面分析\n"
            elif score >= 0:
                result += "• 技术面偏空，观望为主\n"
                result += "• 等待更好的入场时机\n"
            else:
                result += "• 技术面弱势，建议规避\n"
                result += "• 如需操作，严格控制风险\n"

            return result

        except Exception as e:
            return f"技术情绪分析失败: {str(e)}"

    def _calculate_rsi(self, prices, period=14):
        """计算RSI指标"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
