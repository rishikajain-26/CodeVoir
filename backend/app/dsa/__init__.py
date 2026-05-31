"""DSA interview LangGraph aligned to the architecture diagram.

Layers (see nodes/):
  ingestion  -> audio_ingest, code_stream_ingest, session_loader
  signals    -> speech/editor/silence extractors, behaviour_aggregator
  evaluation -> explanation_listener .. eval_aggregator, timeline_builder
  memory     -> turn/behaviour writers, session_state_updater
  output     -> followup_generator, hint_calibrator, response_composer
  report     -> transcript_analyser, radar_chart_builder, hiring_recommender
  intent     -> resolve_candidate_intent (contextual routing)
  router     -> turn_router conditional edges
"""

from app.dsa.graph import DSA_GRAPH, build_dsa_graph, run_dsa_turn
from app.dsa.state import DSAState

__all__ = ["DSAState", "DSA_GRAPH", "build_dsa_graph", "run_dsa_turn"]
