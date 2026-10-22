from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from uuid import UUID

from sqlalchemy import Engine, create_engine, text

from jarvis.core.config import Settings
from jarvis.documents.models import DocumentAnalysis, ExtractedDeadline, ExtractedFact


class PostgreSQLDocumentAnalysisRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._engine_instance: Engine | None = None

    async def create(self, analysis: DocumentAnalysis) -> DocumentAnalysis:
        return await asyncio.to_thread(self._create, analysis)

    async def latest(self, household_id: UUID, document_id: UUID) -> DocumentAnalysis | None:
        return await asyncio.to_thread(self._latest, household_id, document_id)

    def _engine(self) -> Engine:
        if self._engine_instance is None:
            self._engine_instance = create_engine(
                self._settings.sqlalchemy_url(),
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=5,
                connect_args={"connect_timeout": 5},
            )
        return self._engine_instance

    def _create(self, analysis: DocumentAnalysis) -> DocumentAnalysis:
        with self._engine().begin() as connection:
            row = connection.execute(
                text(
                    """
                    INSERT INTO document_analyses (
                        id, document_id, household_id, source_sha256, provider, model,
                        document_type, summary, facts, deadlines, suggested_actions,
                        missing_information
                    ) VALUES (
                        :id, :document_id, :household_id, :source_sha256, :provider, :model,
                        :document_type, :summary, CAST(:facts AS jsonb), CAST(:deadlines AS jsonb),
                        CAST(:suggested_actions AS jsonb), CAST(:missing_information AS jsonb)
                    )
                    ON CONFLICT (document_id, source_sha256)
                    DO UPDATE SET document_id = EXCLUDED.document_id
                    RETURNING id, document_id, household_id, source_sha256, provider, model,
                              document_type, summary, facts, deadlines, suggested_actions,
                              missing_information, created_at
                    """
                ),
                {
                    "id": analysis.id,
                    "document_id": analysis.document_id,
                    "household_id": analysis.household_id,
                    "source_sha256": analysis.source_sha256,
                    "provider": analysis.provider,
                    "model": analysis.model,
                    "document_type": analysis.document_type,
                    "summary": analysis.summary,
                    "facts": json.dumps([asdict(item) for item in analysis.facts]),
                    "deadlines": json.dumps([asdict(item) for item in analysis.deadlines]),
                    "suggested_actions": json.dumps(analysis.suggested_actions),
                    "missing_information": json.dumps(analysis.missing_information),
                },
            ).one()
        return self._from_row(row)

    def _latest(self, household_id: UUID, document_id: UUID) -> DocumentAnalysis | None:
        with self._engine().connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT id, document_id, household_id, source_sha256, provider, model,
                           document_type, summary, facts, deadlines, suggested_actions,
                           missing_information, created_at
                    FROM document_analyses
                    WHERE household_id = :household_id AND document_id = :document_id
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                    """
                ),
                {"household_id": household_id, "document_id": document_id},
            ).first()
        return self._from_row(row) if row else None

    @staticmethod
    def _from_row(row) -> DocumentAnalysis:
        value = row._mapping
        return DocumentAnalysis(
            id=value["id"],
            document_id=value["document_id"],
            household_id=value["household_id"],
            source_sha256=bytes(value["source_sha256"]),
            provider=value["provider"],
            model=value["model"],
            document_type=value["document_type"],
            summary=value["summary"],
            facts=tuple(ExtractedFact(**item) for item in value["facts"]),
            deadlines=tuple(ExtractedDeadline(**item) for item in value["deadlines"]),
            suggested_actions=tuple(value["suggested_actions"]),
            missing_information=tuple(value["missing_information"]),
            created_at=value["created_at"],
        )
