def clean_code(code: str) -> str:
    """Remove excessive whitespace and normalize code."""
    return "\n".join(line.strip() for line in code.splitlines() if line.strip())