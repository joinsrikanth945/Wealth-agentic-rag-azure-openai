# Adapted from Enterprise IT Support Agentic RAG Copilot by Bappy Ahmed (Apache-2.0).
# Modified by Sreekanth Dara, 2026.
import logging

def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )