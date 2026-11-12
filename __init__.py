"""Paquete de dominio del simulador AgroVIA."""

from .scoring_contracts import (  # noqa: F401
	DashScoringRequest,
	build_scoring_input_v1,
	calcular_score_desde_dash_payload,
	request_from_dash_payload,
	score_to_dash_payload,
)
from .scoring_v1 import (  # noqa: F401
	BonificacionActiva,
	PenalizacionActiva,
	ScoreBreakdownV1,
	ScoringInputV1,
	asignar_tier,
	calcular_score_v1,
)
