from datetime import datetime

import pytest

from scribe.backup import backup_file


def test_backup_file(tmp_path):
    """Test normal backup functionality."""
    test_file = tmp_path / "test.md"
    content = "test content"
    test_file.write_text(content)

    backup_path = backup_file(test_file)

    # Verify backup was created
    assert backup_path.exists()
    assert backup_path.read_text() == content
    assert ".scribe_backups" in str(backup_path)
    assert datetime.now().strftime("%Y%m%d") in backup_path.name


def test_prevent_recursive_backup(tmp_path):
    """Test that we cannot backup files that are already in a backup directory."""
    # Create a file in the backup directory
    backup_dir = tmp_path / ".scribe_backups"
    backup_dir.mkdir()
    test_file = backup_dir / "test.md"
    test_file.write_text("test content")

    # Attempt to backup should raise ValueError
    with pytest.raises(ValueError) as exc:
        backup_file(test_file)
    assert "Cannot backup a file that is already in a backup directory" in str(exc.value)
