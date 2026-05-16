"""FileCortex Core - AI-powered workspace orchestration and file management."""

__version__ = "6.3.3"

from .actions import ActionBridge, FileOps
from .config import DataManager, get_app_dir, logger
from .context import ContextFormatter, NoiseReducer
from .duplicate import DuplicateWorker
from .file_io import FileUtils
from .format_utils import FormatUtils
from .search import SearchWorker, search_generator
from .security import PathValidator

try:
    from .gui import BatchRenameWindow, DuplicateFinderWindow, PathCollectionDialog
except ImportError:
    BatchRenameWindow = None
    DuplicateFinderWindow = None
    PathCollectionDialog = None

__all__ = [
    "DataManager",
    "FileUtils",
    "SearchWorker",
    "FileOps",
    "ActionBridge",
    "PathValidator",
    "ContextFormatter",
    "FormatUtils",
    "DuplicateWorker",
    "search_generator",
    "NoiseReducer",
    "logger",
    "get_app_dir",
    "BatchRenameWindow",
    "DuplicateFinderWindow",
    "PathCollectionDialog",
]
