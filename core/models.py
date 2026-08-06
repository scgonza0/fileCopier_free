from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime


@dataclass
class FileInfo:
    path: Path
    name: str
    size: int
    modified: datetime
    is_dir: bool
    relative_path: str
    extension: str = ""
