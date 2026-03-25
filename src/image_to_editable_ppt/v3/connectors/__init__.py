"""Connector evidence extraction and late connector resolution for v3."""

from .attach import ConnectorAttachmentBridge, attach_connector_evidence
from .evidence import OrthogonalConnectorEvidenceExtractor, extract_connector_evidence
from .ports import OrthogonalPortGenerator, generate_ports
from .solve import ConnectorCandidateSolver, resolve_connector_candidates

__all__ = [
    "ConnectorAttachmentBridge",
    "ConnectorCandidateSolver",
    "OrthogonalConnectorEvidenceExtractor",
    "OrthogonalPortGenerator",
    "attach_connector_evidence",
    "extract_connector_evidence",
    "generate_ports",
    "resolve_connector_candidates",
]
