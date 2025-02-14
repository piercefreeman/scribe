from datetime import datetime
from pathlib import Path
from shutil import copy2


def backup_file(file_path: Path) -> Path:
    """
    Creates a backup of a file in a hidden .scribe_backups directory.
    Returns the path to the backup file.
    
    Will not backup files that are already in a .scribe_backups directory
    to prevent recursive backups.
    """
    # Don't backup files that are already in a backup directory
    if ".scribe_backups" in file_path.parts:
        raise ValueError(f"Cannot backup a file that is already in a backup directory: {file_path}")

    # Create backup directory if it doesn't exist
    backup_dir = file_path.parent / ".scribe_backups"
    backup_dir.mkdir(exist_ok=True)

    # Create backup filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"{file_path.stem}_{timestamp}{file_path.suffix}"
    backup_path = backup_dir / backup_filename

    # Copy the file
    copy2(file_path, backup_path)
    return backup_path 