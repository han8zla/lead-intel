from contextlib import contextmanager
from typing import Iterator

from core.intelligence_store import IntelligenceStore
from utils.logger import get_logger


logger = get_logger(__name__)


class AuditTrail:
    """Small application-facing facade over persistent analysis audit events."""

    def __init__(self, store: IntelligenceStore):
        self.store = store

    def event(
        self,
        run_id: str,
        lead_id: int,
        name: str,
        *,
        stage: str | None = None,
        severity: str = "INFO",
        message: str | None = None,
        **attributes,
    ) -> None:
        self.store.record_event(
            run_id,
            lead_id,
            name,
            stage=stage,
            severity=severity,
            message=message,
            attributes=attributes,
        )
        logger.info(
            "audit.event",
            run_id=run_id,
            lead_id=lead_id,
            event=name,
            stage=stage,
            severity=severity,
            **attributes,
        )

    @contextmanager
    def stage(
        self,
        run_id: str,
        lead_id: int,
        name: str,
        **attributes,
    ) -> Iterator[None]:
        self.event(run_id, lead_id, f"{name}.started", stage=name, **attributes)
        try:
            yield
        except Exception as exc:
            self.event(
                run_id,
                lead_id,
                f"{name}.failed",
                stage=name,
                severity="ERROR",
                message=str(exc),
                error_type=type(exc).__name__,
                **attributes,
            )
            raise
        else:
            self.event(run_id, lead_id, f"{name}.completed", stage=name, **attributes)
