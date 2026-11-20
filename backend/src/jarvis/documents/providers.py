from jarvis.core.config import Settings
from jarvis.documents.analysis import (
    AnalysisResult,
    AnalysisUnavailableError,
    DocumentAnalyzer,
    OpenAIDocumentAnalyzer,
)
from jarvis.documents.openwebui import OpenWebUIDocumentAnalyzer


class DisabledDocumentAnalyzer:
    async def analyze(self, *, filename: str, media_type: str, content: bytes) -> AnalysisResult:
        raise AnalysisUnavailableError("Document analysis is not enabled")


def create_document_analyzer(settings: Settings) -> DocumentAnalyzer:
    if settings.ai_provider == "openwebui":
        return OpenWebUIDocumentAnalyzer(settings)
    if settings.ai_provider == "openai":
        return OpenAIDocumentAnalyzer(settings)
    return DisabledDocumentAnalyzer()
