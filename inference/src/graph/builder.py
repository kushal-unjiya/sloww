from __future__ import annotations

from dataclasses import dataclass

from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncEngine

from src.config import Settings
from src.generation.modules import AggregatorModule, CitedSummaryModule, NormalTextModule, VisualizerModule
from src.generation.nodes import (
    Aggregator,
    CitedSummaryGenerator,
    GenerationModules,
    NormalTextGenerator,
    ResponseAssembler,
    Visualizer,
)
from src.graph.edges import after_base_query_processor, after_generation, after_orchestrator
from src.graph.state import GraphState
from src.orchestration.modules import (
    CoverageScorer,
    HyDEExpander,
    IntentClassifier,
    OrchestratorModule,
    OrchestrationModules,
)
from src.orchestration.nodes import BaseQueryProcessor, Orchestrator
from src.retrieval.dense import QdrantRetriever
from src.retrieval.fusion import ReciprocallRankFusion
from src.retrieval.nodes import RetrievalDeps, RetrievalEngine
from src.retrieval.reranker import CrossEncoderReranker
from src.retrieval.sparse import BM25Retriever
from src.shared.clients.embedding_client import EmbeddingClient
from src.shared.clients.llm_client import LLMClient
from src.shared.clients.qdrant_client import QdrantClientWrapper


@dataclass(frozen=True)
class GraphConfig:
    settings: Settings
    llm_client: LLMClient
    llm_router: LLMClient
    embedding_client: EmbeddingClient
    qdrant_client: QdrantClientWrapper
    pg_engine: AsyncEngine
    cross_encoder: CrossEncoderReranker


class ChatGraphBuilder:
    def __init__(self, *, config: GraphConfig) -> None:
        self._config = config

    def build(self):
        settings = self._config.settings

        orchestration_modules = OrchestrationModules(
            hyde=HyDEExpander(llm=self._config.llm_router),
            intent=IntentClassifier(llm=self._config.llm_router),
            planner=OrchestratorModule(llm=self._config.llm_router),
            coverage=CoverageScorer(llm=self._config.llm_router),
        )

        generation_modules = GenerationModules(
            aggregator=AggregatorModule(llm=self._config.llm_client),
            cited=CitedSummaryModule(llm=self._config.llm_client),
            normal=NormalTextModule(llm=self._config.llm_client),
            visualizer=VisualizerModule(llm=self._config.llm_client),
        )

        retrieval_deps = RetrievalDeps(
            dense=QdrantRetriever(
                settings=settings,
                embedding_client=self._config.embedding_client,
                qdrant_client=self._config.qdrant_client,
                top_k=25,
            ),
            sparse=BM25Retriever(engine=self._config.pg_engine, top_k=25),
            fusion=ReciprocallRankFusion(),
            reranker=self._config.cross_encoder,
        )

        graph = StateGraph(GraphState)

        graph.add_node(
            "base_query_processor",
            BaseQueryProcessor(modules=orchestration_modules, settings=settings),
        )
        graph.add_node("retrieval_engine", RetrievalEngine(deps=retrieval_deps))
        graph.add_node("orchestrator", Orchestrator(modules=orchestration_modules, settings=settings))
        graph.add_node("aggregator", Aggregator(modules=generation_modules))
        graph.add_node(
            "cited_summary_generator",
            CitedSummaryGenerator(
                modules=generation_modules,
                max_assert_retries=settings.citation_assert_retries,
            ),
        )
        graph.add_node("normal_text_generator", NormalTextGenerator(modules=generation_modules))
        graph.add_node("visualizer", Visualizer(modules=generation_modules))
        graph.add_node("response_assembler", ResponseAssembler())

        graph.set_entry_point("base_query_processor")

        graph.add_conditional_edges("base_query_processor", after_base_query_processor)
        graph.add_edge("retrieval_engine", "orchestrator")
        graph.add_conditional_edges("orchestrator", after_orchestrator)
        graph.add_edge("aggregator", "cited_summary_generator")
        graph.add_conditional_edges("cited_summary_generator", after_generation)
        graph.add_edge("normal_text_generator", "response_assembler")
        graph.add_edge("visualizer", "response_assembler")
        graph.add_edge("response_assembler", END)

        return graph.compile()
