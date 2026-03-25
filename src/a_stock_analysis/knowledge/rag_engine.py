"""
RAG 检索增强生成引擎
用于从知识库中检索相关内容并增强 AI 回答
"""
import os
# 【关键修复】必须在import之前设置离线模式
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from pathlib import Path
from typing import List, Optional, Dict
from pathlib import Path

# LangChain imports
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_core.documents import Document
import re
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings


class RAGEngine:
    """RAG 检索引擎"""

    def __init__(self, persist_dir: str = None):
        """
        初始化 RAG 引擎

        Args:
            persist_dir: 向量数据库存储路径
        """
        # 获取知识库根目录
        self.knowledge_root = Path(__file__).parent
        self.raw_sources = self.knowledge_root / "raw_sources"
        self.vector_db_dir = persist_dir or str(self.knowledge_root / "vector_db")

        # 初始化 embedding 函数 (使用本地模型，不花钱)
        print("正在加载 embedding 模型...")
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )
        print("✓ Embedding 模型加载完成")

        # 初始化向量数据库
        self.vectorstore = None
        self._init_vectorstore()

        # 文档分割器 - 优化：优先按段落切，再按句子切
        # 原理：先用大分隔符，大的太长再用小分隔符，递归直到满足chunk_size
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,       # 目标chunk大小（约120-150 tokens）
            chunk_overlap=50,     # 重叠保持上下文连贯
            separators=[
                "\n\n",          # 1. 先按段落（双换行）
                "\n",            # 2. 再按单行
                "。",            # 3. 按中文句号
                "！|？",         # 4. 按中文感叹号/问号
                ". ",           # 5. 按英文句号+空格
                " ",             # 6. 最后按空格
            ],
            is_separator_regex=True  # 支持正则表达式
        )

    def _init_vectorstore(self):
        """初始化向量数据库"""
        os.makedirs(self.vector_db_dir, exist_ok=True)

        # 尝试加载已有数据库
        try:
            self.vectorstore = Chroma(
                persist_directory=self.vector_db_dir,
                embedding_function=self.embeddings
            )
            print(f"✓ 已加载现有向量数据库: {self.vector_db_dir}")
        except Exception as e:
            print(f"⚠ 无法加载现有数据库，将创建新的: {e}")
            self.vectorstore = Chroma(
                persist_directory=self.vector_db_dir,
                embedding_function=self.embeddings
            )

    def ingest_file(self, file_path: str, category: str = None, source_name: str = None) -> int:
        """
        导入单个文件到知识库

        Args:
            file_path: 文件路径
            category: 分类 (technical/financial/behavioral)
            source_name: 来源名称（可选，默认用文件名）

        Returns:
            导入的文档块数量
        """
        file_path = Path(file_path)
        source = source_name or file_path.stem
        category = category or self._guess_category(str(file_path))

        # 根据文件类型选择加载器
        if file_path.suffix.lower() == '.pdf':
            loader = PyPDFLoader(str(file_path))
            documents = loader.load()
        elif file_path.suffix.lower() == '.epub':
            # 使用 ebooklib 加载 EPUB
            documents = self._load_epub(str(file_path))
        elif file_path.suffix.lower() in ['.txt', '.md']:
            loader = TextLoader(str(file_path), encoding='utf-8')
            documents = loader.load()
        else:
            print(f"⚠ 不支持的文件类型: {file_path.suffix}")
            return 0

        # 分割文档
        splits = self.splitter.split_documents(documents)

        # 过滤空文档
        splits = [s for s in splits if s.page_content.strip()]
        if not splits:
            print(f"⚠ 文档为空: {file_path}")
            return 0

        # 添加元数据
        for split in splits:
            split.metadata.update({
                'source': source,
                'category': category,
                'file': str(file_path.name)
            })

        # 存入向量数据库
        try:
            self.vectorstore.add_documents(splits)
            print(f"✓ 已导入 {source}: {len(splits)} 个文档块")
            return len(splits)
        except Exception as e:
            print(f"⚠ 导入失败 {source}: {e}")
            # 尝试逐个添加
            success_count = 0
            for s in splits:
                try:
                    self.vectorstore.add_documents([s])
                    success_count += 1
                except:
                    pass
            print(f"✓ 成功导入 {success_count}/{len(splits)} 个文档块")
            return success_count

    def ingest_folder(self, folder_path: str, category: str = None) -> Dict[str, int]:
        """
        导入文件夹内所有支持的文件

        Args:
            folder_path: 文件夹路径
            category: 分类

        Returns:
            每个文件的导入结果
        """
        folder = Path(folder_path)
        results = {}

        for file_path in folder.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in ['.pdf', '.epub', '.txt', '.md']:
                count = self.ingest_file(str(file_path), category)
                results[file_path.name] = count

        return results

    def ingest_all(self) -> Dict[str, int]:
        """导入所有源文件"""
        results = {}

        # 遍历所有分类文件夹
        for category in ['technical', 'financial', 'behavioral']:
            category_folder = self.raw_sources / category
            if category_folder.exists():
                print(f"\n📚 导入 {category} 类书籍...")
                results[category] = self.ingest_folder(str(category_folder), category)

        return results

    def retrieve(self, query: str, category: str = None, top_k: int = 3) -> List[Document]:
        """
        检索相关知识

        Args:
            query: 查询内容
            category: 分类过滤（可选）
            top_k: 返回数量

        Returns:
            相关文档列表
        """
        # 构建过滤条件
        filter_dict = {'category': category} if category else None

        # 检索
        results = self.vectorstore.similarity_search(
            query,
            k=top_k,
            filter=filter_dict
        )

        return results

    def retrieve_with_score(self, query: str, category: str = None, top_k: int = 3, threshold: float = 0.5):
        """
        带相似度分数的检索

        Returns:
            (文档, 分数) 元组列表
        """
        filter_dict = {'category': category} if category else None

        results = self.vectorstore.similarity_search_with_score(
            query,
            k=top_k,
            filter=filter_dict
        )

        # 过滤低相似度结果
        filtered = [(doc, score) for doc, score in results if score < threshold]
        return filtered

    def format_results(self, results: List[Document], max_length: int = 500) -> str:
        """格式化检索结果"""
        if not results:
            return "未找到相关知识"

        formatted = []
        for i, doc in enumerate(results, 1):
            source = doc.metadata.get('source', '未知来源')
            category = doc.metadata.get('category', '未知分类')
            content = doc.page_content[:max_length]

            if len(doc.page_content) > max_length:
                content += "..."

            formatted.append(
                f"【{i}. {source} - {category}】\n{content}\n"
            )

        return "\n".join(formatted)

    def _load_epub(self, file_path: str) -> list:
        """使用 ebooklib 加载 EPUB 文件"""
        try:
            from ebooklib import epub

            book = epub.read_epub(file_path)
            documents = []

            # 获取书名
            title = book.get_metadata('DC', 'title')
            book_title = title[0][0] if title else Path(file_path).stem

            # 遍历所有内容
            for item in book.get_items():
                if item.get_type() == 9:  # 9 = HTML
                    content = item.get_content().decode('utf-8')
                    # 提取纯文本（去除HTML标签）
                    text = re.sub(r'<[^>]+>', ' ', content)
                    text = re.sub(r'\s+', ' ', text).strip()

                    if len(text) > 100:  # 过滤太短的内容
                        # 获取章节名称（从item名称）
                        item_name = item.get_name()

                        doc = Document(
                            page_content=text,
                            metadata={'source': book_title, 'chapter': item_name}
                        )
                        documents.append(doc)

            print(f"✓ 已加载 EPUB: {book_title}, {len(documents)} 个文档")
            return documents

        except Exception as e:
            print(f"⚠ 加载 EPUB 失败: {e}")
            return []

    def _guess_category(self, file_path: str) -> str:
        """根据文件路径猜测分类"""
        path_lower = file_path.lower()
        if 'technical' in path_lower or 'k线' in path_lower or '蜡烛图' in path_lower:
            return 'technical'
        elif 'financial' in path_lower or '财务' in path_lower or '估值' in path_lower or '投资' in path_lower:
            return 'financial'
        elif 'behavioral' in path_lower or '心理' in path_lower or '行为' in path_lower:
            return 'behavioral'
        return 'unknown'

    def get_stats(self) -> Dict:
        """获取知识库统计信息"""
        try:
            count = self.vectorstore._collection.count()
            return {
                'total_documents': count,
                'persist_dir': self.vector_db_dir
            }
        except Exception as e:
            return {'error': str(e)}


# 全局单例
_rag_engine: Optional[RAGEngine] = None


def get_rag_engine() -> RAGEngine:
    """获取全局 RAG 引擎实例"""
    global _rag_engine
    if _rag_engine is None:
        _rag_engine = RAGEngine()
    return _rag_engine


if __name__ == "__main__":
    # 测试导入
    print("=" * 50)
    print("RAG 知识库管理工具")
    print("=" * 50)

    engine = RAGEngine()
    stats = engine.get_stats()
    print(f"\n📊 当前知识库状态: {stats}")

    print("\n可用命令:")
    print("  python -m knowledge.rag_engine ingest_all  # 导入所有文件")
    print("  python -m knowledge.rag_engine query <问题>  # 测试检索")
