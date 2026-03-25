from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Optional, Type

from knowledge.base import KnowledgeBase
from knowledge.rag_engine import get_rag_engine


class KnowledgeQuerySchema(BaseModel):
    """知识查询工具输入参数"""
    keyword: str = Field(..., description="查询的金融术语或知识点，如：PE、MACD、ROE等")
    category: Optional[str] = Field(None, description="分类：技术分析(technical)、财务分析(financial)、情绪分析(behavioral)")


class KnowledgeQueryTool(BaseTool):
    """金融知识查询工具"""

    name: str = "KnowledgeQueryTool"
    description: str = "查询金融专业术语的解释、公式和应用场景，帮助理解分析中涉及的专业概念"
    args_schema: Type[BaseModel] = KnowledgeQuerySchema

    def _run(self, keyword: str, category: str = None):
        """查询知识点"""
        try:
            # 优先使用 RAG 检索
            rag = get_rag_engine()
            results = rag.retrieve(keyword, category=category, top_k=3)

            if results:
                # 使用 RAG 结果
                return rag.format_results(results, max_length=600)
            else:
                # 回退到原有知识库
                kb = KnowledgeBase()
                if category:
                    result = kb.search_in_category(keyword, category)
                else:
                    result = kb.search(keyword)
                return result
        except Exception as e:
            return f"查询知识时发生错误: {str(e)}"


class QuickExplainSchema(BaseModel):
    """快速解释工具输入参数"""
    term: str = Field(..., description="金融术语，如：PE、MACD、KDJ、金叉、死叉等")


class QuickExplainTool(BaseTool):
    """快速术语解释工具"""

    name: str = "QuickExplainTool"
    description: str = "快速解释金融专业术语的简要含义，适合快速查询"
    args_schema: Type[BaseModel] = QuickExplainSchema

    def _run(self, term: str):
        """快速解释术语"""
        try:
            # 优先使用 RAG 检索
            rag = get_rag_engine()
            results = rag.retrieve(term, top_k=2)

            if results:
                return rag.format_results(results, max_length=400)
            else:
                # 回退到原有知识库
                kb = KnowledgeBase()
                explanation = kb.get_keyword_explanation(term)
                return explanation
        except Exception as e:
            return f"解释术语时发生错误: {str(e)}"


class RAGQuerySchema(BaseModel):
    """RAG 知识检索工具输入参数"""
    query: str = Field(..., description="查询内容，可以是完整的问题或关键词")
    category: Optional[str] = Field(None, description="分类过滤：technical/financial/behavioral")
    top_k: int = Field(3, description="返回结果数量")


class RAGQueryTool(BaseTool):
    """RAG 知识检索工具 - 基于向量检索的深度知识查询"""

    name: str = "RAGQueryTool"
    description: str = "从知识库中检索相关内容，用于深入理解某个概念或问题。可以检索书籍、教程等原始资料中的内容。"
    args_schema: Type[BaseModel] = RAGQuerySchema

    def _run(self, query: str, category: str = None, top_k: int = 3):
        """RAG 检索"""
        try:
            rag = get_rag_engine()
            results = rag.retrieve(query, category=category, top_k=top_k)
            return rag.format_results(results, max_length=800)
        except Exception as e:
            return f"RAG检索时发生错误: {str(e)}"


class ResourceRecommendSchema(BaseModel):
    """学习资源推荐工具输入参数"""
    topic: str = Field(..., description="学习主题：技术分析、财务分析、估值、情绪分析、投资策略。多个主题用逗号分隔")


class ResourceRecommendTool(BaseTool):
    """学习资源推荐工具"""

    name: str = "ResourceRecommendTool"
    description: str = "推荐金融学习的书籍和课程资源，支持单个或多个主题查询"
    args_schema: Type[BaseModel] = ResourceRecommendSchema

    def _run(self, topic: str):
        """推荐学习资源"""
        try:
            kb = KnowledgeBase()

            # 映射主题到资源分类
            topic_map = {
                "技术分析": "technical_analysis",
                "技术": "technical_analysis",
                "财务": "financial_analysis",
                "财务分析": "financial_analysis",
                "估值": "valuation",
                "情绪": "sentiment_analysis",
                "情绪分析": "sentiment_analysis",
                "投资": "investment_strategy",
                "投资策略": "investment_strategy"
            }

            # 支持多个主题（用逗号分隔）
            topics = [t.strip() for t in topic.split(",")]

            result = "# 学习资源推荐\n\n"

            for t in topics:
                category = topic_map.get(t, t)
                resources = kb.get_resources(category)

                if resources:
                    result += f"## {t}\n\n"

                    if "books" in resources:
                        result += "### 书籍推荐\n"
                        for book in resources["books"]:
                            result += f"- **{book['name']}** - {book['author']}\n"
                            result += f"  - {book['desc']}\n"
                            result += f"  - 难度：{book['level']}\n\n"

                    if "courses" in resources:
                        result += "### 课程推荐\n"
                        for course in resources["courses"]:
                            result += f"- **{course['name']}** ({course['platform']})\n"
                            result += f"  - {course['desc']}\n\n"
                else:
                    result += f"## {t}\n未找到相关资源\n\n"

            # 添加 RAG 知识库中的相关内容
            rag = get_rag_engine()
            stats = rag.get_stats()
            if stats.get('total_documents', 0) > 0:
                result += "\n---\n📚 **已加载知识库资源**\n"
                result += f"当前知识库共有 {stats['total_documents']} 个文档片段\n"

                # 检索相关内容
                rag_results = rag.retrieve(topic, top_k=2)
                if rag_results:
                    result += "\n### 相关知识片段\n"
                    result += rag.format_results(rag_results, max_length=300)

            return result
        except Exception as e:
            return f"推荐资源时发生错误: {str(e)}"
