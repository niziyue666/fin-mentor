from typing import List
from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from tools.a_stock_data_tool import AStockDataTool
from tools.financial_tool import FinancialAnalysisTool
from tools.market_sentiment_tool import MarketSentimentTool
from tools.calculator_tool import CalculatorTool
from tools.knowledge_tool import KnowledgeQueryTool
from tools.q1_knowledge_tool import Q1KnowledgeTool
from tools.q2_knowledge_tool import Q2KnowledgeTool
from tools.q3_knowledge_tool import Q3KnowledgeTool
from tools.q4_knowledge_tool import Q4KnowledgeTool
from tools.report_vector_tool import ReportVectorTool, ReportSearchTool

import os
from dotenv import load_dotenv
load_dotenv()

# 从环境变量读取模型配置
model_name = os.getenv("OPENAI_MODEL_NAME", "gpt-4o")
api_key = os.getenv("OPENAI_API_KEY")
base_url = os.getenv("OPENAI_BASE_URL")
temperature = float(os.getenv("TEMPERATURE", "0.8"))
max_tokens = int(os.getenv("MAX_TOKENS", "14000"))

from crewai import LLM

# 使用 OpenAI 兼容格式调用
llm = LLM(
    model=f"openai/{model_name}",
    api_key=api_key,
    base_url=base_url,
    temperature=temperature,
    max_tokens=max_tokens,
)

@CrewBase
class AStockAnalysisCrew:
    agents_config = 'config/agents.yaml'
    tasks_config = 'config/tasks.yaml'

    @agent
    def a_stock_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config['a_stock_analyst'],
            verbose=True,
            llm=llm,
            tools=[
                AStockDataTool(),
                FinancialAnalysisTool(),
                MarketSentimentTool(),
                CalculatorTool(),
                Q1KnowledgeTool(),
                KnowledgeQueryTool(),
            ]
        )

    @task
    def market_analysis(self) -> Task:
        return Task(
            config=self.tasks_config['market_analysis'],
            agent=self.a_stock_analyst(),
        )

    @agent
    def financial_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config['financial_analyst'],
            verbose=True,
            llm=llm,
            tools=[
                AStockDataTool(),
                FinancialAnalysisTool(),
                CalculatorTool(),
                KnowledgeQueryTool(),
                Q2KnowledgeTool(),
            ]
        )

    @task
    def financial_analysis(self) -> Task:
        return Task(
            config=self.tasks_config['financial_analysis'],
            agent=self.financial_analyst(),
        )

    @agent
    def market_sentiment_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['market_sentiment_analyst'],
            verbose=True,
            llm=llm,
            tools=[
                AStockDataTool(),
                MarketSentimentTool(),
                KnowledgeQueryTool(),
                Q3KnowledgeTool(),
            ]
        )

    @task
    def sentiment_analysis(self) -> Task:
        return Task(
            config=self.tasks_config['sentiment_analysis'],
            agent=self.market_sentiment_agent(),
        )

    @agent
    def investment_advisor(self) -> Agent:
        return Agent(
            config=self.agents_config['investment_advisor'],
            verbose=True,
            llm=llm,
            tools=[
                CalculatorTool(),
                KnowledgeQueryTool(),
                Q4KnowledgeTool(),
            ]
        )

    @task
    def investment_recommendation(self) -> Task:
        return Task(
            config=self.tasks_config['investment_recommendation'],
            agent=self.investment_advisor(),
        )

    @agent
    def followup_tutor(self) -> Agent:
        return Agent(
            config=self.agents_config['followup_tutor'],
            verbose=True,
            llm=llm,
            tools=[
                # 追问只允许检索工具，禁止获取新数据！
                ReportSearchTool(),      # 检索研报
                KnowledgeQueryTool(),     # 检索知识库
            ]
        )

    @task
    def followup_qa(self) -> Task:
        return Task(
            config=self.tasks_config['followup_qa'],
            agent=self.followup_tutor(),
        )

    @crew
    def crew(self) -> Crew:
        """创建A股分析团队 - 使用顺序模式"""
        # 显式创建任务并设置依赖关系
        market_task = self.market_analysis()
        financial_task = self.financial_analysis()
        sentiment_task = self.sentiment_analysis()
        investment_task = self.investment_recommendation()

        # 设置上下文依赖：后面的任务可以访问前面任务的结果
        financial_task.context = [market_task]
        sentiment_task.context = [financial_task, market_task]  # 可以访问 Q1 和 Q2
        investment_task.context = [sentiment_task, financial_task, market_task]  # 可以访问 Q1、Q2、Q3

        return Crew(
            agents=self.agents,
            tasks=[market_task, financial_task, sentiment_task, investment_task],
            process=Process.sequential,
            verbose=True,
            output_log_file="crew_output.log",
        )
