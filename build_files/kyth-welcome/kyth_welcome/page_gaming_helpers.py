"""Gaming page helpers — extracted from god-page for R5 split (S13)."""

from .services.gaming import DataWorker


def gaming_data_worker(key: str, fetch):
    """S13: thin wrapper so page_gaming.py doesn't inline DataWorker orchestration."""
    return DataWorker(key, fetch)
