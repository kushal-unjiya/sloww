from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine

from src.config import get_settings
from src.graph.state import GraphState
from src.shared.db import qualify_table
from src.shared.logging import get_logger, timer

logger = get_logger("sloww.inference.chat.repository")


@dataclass(frozen=True)
class RetrievalCacheRepository:
    engine: AsyncEngine

    async def insert_turn_audit(
        self,
        *,
        user_id: str | None,
        state: GraphState,
    ) -> None:
        t = timer()
        schema = get_settings().db_schema
        table = qualify_table(schema=schema, table="retrieval_cache")

        payload: dict[str, Any] = {
            "raw_query": state.raw_query,
            "normalized_query": state.normalized_query,
            "expanded_query": state.expanded_query,
            "intent": state.intent.model_dump() if state.intent else None,
            "retrieved_chunks": [c.model_dump() for c in state.retrieved_chunks],
            "retrieval_coverage": state.retrieval_coverage,
            "execution_plan": state.execution_plan.model_dump() if state.execution_plan else None,
            "loop_count": state.loop_count,
            "aggregator_output": state.aggregator_output.model_dump() if state.aggregator_output else None,
            "final_response": state.final_response.model_dump() if state.final_response else None,
        }

        sql = (
            text(
                f"""
            INSERT INTO {table}
              (request_id, notebook_id, user_id, payload_json)
            VALUES
              (:request_id, :notebook_id, :user_id, :payload_json)
            """
            ).bindparams(bindparam("payload_json", type_=JSONB()))
        )
        # Fresh connection + explicit transaction avoids sticky invalid transactions (DBAPI f405).
        async with self.engine.connect() as conn:
            async with conn.begin():
                await conn.execute(
                    sql,
                    {
                        "request_id": state.request_id,
                        "notebook_id": state.notebook_id,
                        "user_id": user_id,
                        "payload_json": payload,
                    },
                )

        logger.info(
            "retrieval_cache_inserted",
            extra={"event": "retrieval_cache_inserted", "latency_ms": t.ms()},
        )

