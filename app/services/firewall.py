from __future__ import annotations

from typing import Iterable

from app.models import ChatResponse, Detection, PrivacyMode, Transformation
from app.services.cloud_llm import CloudLLMClient
from app.services.detectors import HybridPIIDetector
from app.services.file_parser import ParsedFile, chunk_text
from app.services.local_llm import LocalLLMClient
from app.services.outbound_guard import OutboundPrivacyGuard
from app.services.privacy_logger import PrivacySafeLogger
from app.services.sanitizer import SmartSanitizer
from app.services.web_search import SecureWebSearchClient


class PrivacyFirewallService:
    def __init__(
        self,
        detector: HybridPIIDetector,
        sanitizer: SmartSanitizer,
        local_llm: LocalLLMClient,
        cloud_llm: CloudLLMClient,
        web_search: SecureWebSearchClient,
        outbound_guard: OutboundPrivacyGuard,
        privacy_logger: PrivacySafeLogger,
    ) -> None:
        self.detector = detector
        self.sanitizer = sanitizer
        self.local_llm = local_llm
        self.cloud_llm = cloud_llm
        self.web_search = web_search
        self.outbound_guard = outbound_guard
        self.privacy_logger = privacy_logger

    async def process(
        self, session_id: str, message: str, mode: PrivacyMode, use_web_search: bool
    ) -> ChatResponse:
        return await self._process_text(session_id, message, mode, use_web_search, artifacts=[])

    async def process_file(
        self,
        session_id: str,
        parsed_file: ParsedFile,
        mode: PrivacyMode,
        use_web_search: bool,
        message: str = "",
    ) -> ChatResponse:
        label = self._safe_file_label(1, parsed_file.extension)
        preface = (
            f"User request: {message.strip()}\n\n"
            if message.strip()
            else "User request: Analyze the attached file while preserving privacy.\n\n"
        )
        combined = (
            f"{preface}"
            f"Local file context:\n"
            f"- File label: {label}\n"
            f"- File type: {parsed_file.extension or parsed_file.media_type}\n"
            f"- Parser: {parsed_file.parser}\n\n"
            f"Extracted file content:\n{parsed_file.extracted_text}"
        )
        return await self._process_text(session_id, combined, mode, use_web_search, artifacts=[parsed_file.artifact])

    async def process_files(
        self,
        session_id: str,
        parsed_files: list[ParsedFile],
        mode: PrivacyMode,
        use_web_search: bool,
        message: str = "",
    ) -> ChatResponse:
        request = message.strip() or "Analyze the local file collection while preserving privacy."
        manifest = "\n".join(
            f"- {self._safe_file_label(index + 1, item.extension)} [{item.extension or item.media_type}] via {item.parser}"
            for index, item in enumerate(parsed_files)
        )
        combined = (
            f"User request: {request}\n\n"
            f"Local file set manifest:\n{manifest}\n\n"
            + "\n\n".join(
                f"File: {self._safe_file_label(index + 1, item.extension)}\n"
                f"Parser: {item.parser}\n"
                f"Content:\n{item.extracted_text}"
                for index, item in enumerate(parsed_files)
            )
        )
        artifacts = [item.artifact for item in parsed_files]
        return await self._process_text(session_id, combined, mode, use_web_search, artifacts=artifacts)

    async def _process_text(
        self,
        session_id: str,
        message: str,
        mode: PrivacyMode,
        use_web_search: bool,
        artifacts,
    ) -> ChatResponse:
        sanitized_text, detections, transformations = self._sanitize_in_chunks(session_id, message, mode)
        refined_prompt, local_refiner_used = await self.local_llm.refine_prompt(sanitized_text, mode)
        refined_prompt = self.outbound_guard.trim(refined_prompt)
        residual_risk = self.outbound_guard.inspect(sanitized_text, refined_prompt, mode)

        search_result = None
        if use_web_search:
            safe_query, _ = await self.local_llm.generalize_web_query(sanitized_text)
            search_result = await self.web_search.search(safe_query)
            if search_result.results:
                enriched_prompt = (
                    f"{refined_prompt}\n\nSanitized web research excerpts:\n"
                    + "\n".join(
                        f"- {item['title']}: {item['content'][:240]} ({item['url']})"
                        for item in search_result.results
                    )
                )
                refined_prompt = self.outbound_guard.trim(enriched_prompt)
                residual_risk = self.outbound_guard.inspect(sanitized_text, refined_prompt, mode)

        cloud_used = False
        provider = "local"
        if mode == PrivacyMode.FULLY_LOCAL or residual_risk.blocked:
            answer, local_answer_used = await self.local_llm.answer_locally(refined_prompt)
            local_used = local_refiner_used or local_answer_used
            if residual_risk.blocked:
                provider = "local_privacy_block"
        else:
            try:
                answer = await self.cloud_llm.answer(refined_prompt)
                cloud_used = True
                local_used = local_refiner_used
                provider = "cloud"
            except Exception:
                answer, local_answer_used = await self.local_llm.answer_locally(refined_prompt)
                local_used = local_refiner_used or local_answer_used
                provider = "local_fallback"

        response = ChatResponse(
            session_id=session_id,
            mode=mode,
            original_input=message,
            sanitized_input=sanitized_text,
            refined_prompt=refined_prompt,
            answer=answer,
            transformations=transformations,
            detections=detections,
            search=search_result,
            artifacts=artifacts,
            residual_risk=residual_risk,
            provider=provider,
            local_llm_used=local_used,
            cloud_llm_used=cloud_used,
        )
        self.privacy_logger.firewall_result(response)
        return response

    def _sanitize_in_chunks(
        self, session_id: str, message: str, mode: PrivacyMode
    ) -> tuple[str, list[Detection], list[Transformation]]:
        chunks = chunk_text(message)
        if not chunks:
            return message, [], []

        sanitized_chunks = []
        detections: list[Detection] = []
        transformations: list[Transformation] = []
        offset = 0
        for chunk in chunks:
            chunk_detections = self.detector.detect(chunk)
            adjusted = [
                Detection(
                    entity_type=item.entity_type,
                    start=item.start + offset,
                    end=item.end + offset,
                    value=item.value,
                    score=item.score,
                    source=item.source,
                )
                for item in chunk_detections
            ]
            result = self.sanitizer.sanitize(session_id, chunk, chunk_detections, mode)
            sanitized_chunks.append(result.sanitized_text)
            detections.extend(adjusted)
            transformations.extend(result.transformations)
            offset += len(chunk)

        return "\n\n".join(sanitized_chunks), self._dedupe_detections(detections), transformations

    def _dedupe_detections(self, detections: list[Detection]) -> list[Detection]:
        seen = set()
        unique = []
        for item in detections:
            key = (item.entity_type, item.start, item.end, item.value)
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique

    def _safe_file_label(self, index: int, extension: str) -> str:
        suffix = extension.lstrip(".").upper() if extension else "FILE"
        return f"Document_{self._alpha_index(index)}_{suffix}"

    def _alpha_index(self, index: int) -> str:
        value = index
        chars = []
        while value > 0:
            value, remainder = divmod(value - 1, 26)
            chars.append(chr(ord("A") + remainder))
        return "".join(reversed(chars))
