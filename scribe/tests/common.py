from typing import Any


def create_test_note(
    *,
    header: str,
    body: str,
    meta: dict[str, Any] | None = None,
) -> str:
    """
    Create a test note with the given header, metadata, and body.
    
    Args:
        header: The header text (without the # prefix)
        body: The main content of the note
        meta: Optional metadata dictionary. Will use default test metadata if not provided.
    
    Returns:
        str: Formatted note content with header, metadata block, and body
    """
    if meta is None:
        meta = {
            "date": "November 1, 2024",
            "status": "draft",
        }
    
    # Convert metadata to YAML-style string
    meta_block = "\n".join(
        f"    {key}: {value}" for key, value in meta.items()
    )
    
    return f"""# {header}\n\nmeta:\n{meta_block}\n\n{body}"""
