"""
研报向量库工具
用于存储和检索股票分析报告，支持追问时精准获取相关上下文
"""
import os
import json
from pathlib import Path
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Type, Optional, List, Dict

# LangChain imports
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document


# 全局变量
_embeddings = None


def get_embeddings():
    """获取embedding模型（全局单例）"""
    global _embeddings
    if _embeddings is None:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        _embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )
    return _embeddings


def get_persist_dir():
    """获取向量库存储目录"""
    return Path(__file__).parent.parent / "knowledge" / "vector_db" / "reports"


class StoreReportSchema(BaseModel):
    """存储研报输入参数"""
    stock_code: str = Field(..., description="股票代码，如：600519.SH")
    company_name: str = Field(..., description="公司名称，如：贵州茅台")
    q1_content: str = Field(..., description="Q1市场技术分析JSON数据")
    q2_content: str = Field(..., description="Q2财务分析JSON数据")
    q3_content: str = Field(..., description="Q3情绪分析JSON数据")
    q4_content: str = Field(..., description="Q4投资建议JSON数据")
    q1_reasoning: str = Field("", description="Q1分析推理过程")
    q2_reasoning: str = Field("", description="Q2分析推理过程")
    q3_reasoning: str = Field("", description="Q3分析推理过程")
    q4_reasoning: str = Field("", description="Q4分析推理过程")


class SearchReportSchema(BaseModel):
    """检索研报输入参数"""
    stock_code: str = Field(..., description="股票代码")
    query: str = Field(..., description="用户问题")
    top_k: int = Field(2, description="返回相关段落数量")


class ReportVectorTool(BaseTool):
    """研报向量库工具

    用于存储股票分析报告，并在追问时根据问题检索相关段落。
    """

    name: str = "ReportVectorTool"
    description: str = "存储和检索股票分析报告。" \
                       "store_report: 存储分析报告；search_report: 根据问题检索相关研报段落"
    args_schema: Type[BaseModel] = StoreReportSchema

    def _run(self, stock_code: str, company_name: str,
             q1_content: str, q2_content: str,
             q3_content: str, q4_content: str,
             q1_reasoning: str = "", q2_reasoning: str = "",
             q3_reasoning: str = "", q4_reasoning: str = ""):
        """存储研报到向量库"""
        try:
            persist_dir = get_persist_dir()
            persist_path = str(persist_dir / stock_code.replace(".", "_"))

            # 【修复】先删除旧数据，再存储新数据
            import shutil
            if os.path.exists(persist_path):
                shutil.rmtree(persist_path)
                print(f"已删除旧研报: {stock_code}")

            os.makedirs(persist_path, exist_ok=True)

            embeddings = get_embeddings()
            vectorstore = Chroma(
                persist_directory=persist_path,
                embedding_function=embeddings
            )

            # 构建文档块：拆分成 data 和 reasoning 两个独立chunk
            chunks = []

            # Q1 数据块
            chunks.append({
                "module": "Q1_data",
                "title": "市场技术分析数据",
                "content": q1_content,
                "chunk_type": "data",
                "keywords": "均线、RSI、量比、趋势、技术面、多头、空头、收盘价"
            })
            # Q1 推理块
            if q1_reasoning:
                chunks.append({
                    "module": "Q1_reasoning",
                    "title": "市场技术分析推理",
                    "content": q1_reasoning,
                    "chunk_type": "reasoning",
                    "keywords": "为什么、逻辑、分析过程、趋势判断、均线信号"
                })

            # Q2 数据块
            chunks.append({
                "module": "Q2_data",
                "title": "财务分析数据",
                "content": q2_content,
                "chunk_type": "data",
                "keywords": "ROE、PE、PB、毛利率、净利润、财务评分、估值、资产负债率"
            })
            # Q2 推理块
            if q2_reasoning:
                chunks.append({
                    "module": "Q2_reasoning",
                    "title": "财务分析推理",
                    "content": q2_reasoning,
                    "chunk_type": "reasoning",
                    "keywords": "为什么、逻辑、分析过程、财务评分、估值判断"
                })

            # Q3 数据块
            chunks.append({
                "module": "Q3_data",
                "title": "情绪分析数据",
                "content": q3_content,
                "chunk_type": "data",
                "keywords": "资金流向、情绪、新闻、舆情、市场情绪、技术面情绪、RSI、MACD"
            })
            # Q3 推理块
            if q3_reasoning:
                chunks.append({
                    "module": "Q3_reasoning",
                    "title": "情绪分析推理",
                    "content": q3_reasoning,
                    "chunk_type": "reasoning",
                    "keywords": "为什么、逻辑、分析过程、情绪判断、新闻解读"
                })

            # Q4 数据块
            chunks.append({
                "module": "Q4_data",
                "title": "投资建议数据",
                "content": q4_content,
                "chunk_type": "data",
                "keywords": "投资评级、买入、卖出、持有、建议、风险、目标价"
            })
            # Q4 推理块
            if q4_reasoning:
                chunks.append({
                    "module": "Q4_reasoning",
                    "title": "投资建议推理",
                    "content": q4_reasoning,
                    "chunk_type": "reasoning",
                    "keywords": "为什么、逻辑、分析过程、投资评级、评级理由、综合判断"
                })

            documents = []
            for chunk in chunks:
                # 将关键词加入内容，辅助检索
                full_content = f"""【{chunk['title']}】
关键词：{chunk['keywords']}

{chunk['content']}"""

                doc = Document(
                    page_content=full_content,
                    metadata={
                        "stock_code": stock_code,
                        "company_name": company_name,
                        "module": chunk["module"],
                        "keywords": chunk["keywords"]
                    }
                )
                documents.append(doc)

            # 存储到向量库
            vectorstore.add_documents(documents)

            return f"✅ 研报已存储到向量库（股票：{stock_code}，{company_name}）\n包含模块：Q1、Q2、Q3、Q4"

        except Exception as e:
            import traceback
            return f"存储研报失败: {str(e)}\n{traceback.format_exc()}"


class ReportSearchTool(BaseTool):
    """研报检索工具 - 专门用于追问时检索"""

    name: str = "ReportSearchTool"
    description: str = "根据用户问题检索已存储的股票研报相关段落，用于回答追问"
    args_schema: Type[BaseModel] = SearchReportSchema

    def _run(self, stock_code: str, query: str, top_k: int = 2):
        """检索研报"""
        try:
            persist_dir = get_persist_dir()
            persist_path = str(persist_dir / stock_code.replace(".", "_"))

            if not os.path.exists(persist_path):
                return f"未找到股票 {stock_code} 的研报，请先运行分析"

            embeddings = get_embeddings()
            vectorstore = Chroma(
                persist_directory=persist_path,
                embedding_function=embeddings
            )

            # 检索
            results = vectorstore.similarity_search(
                query,
                k=top_k
            )

            if not results:
                return "未找到相关研报内容"

            # 格式化输出
            output_parts = []
            for i, doc in enumerate(results, 1):
                module = doc.metadata.get("module", "未知")
                title = doc.metadata.get("title", "未命名")
                content = doc.page_content[:800]  # 限制长度

                output_parts.append(
                    f"【{module} - {title}】\n{content}\n"
                )

            return "\n\n---\n\n".join(output_parts)

        except Exception as e:
            import traceback
            return f"检索研报失败: {str(e)}\n{traceback.format_exc()}"
