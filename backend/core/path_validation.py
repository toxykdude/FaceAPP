"""
File path validation to prevent path traversal attacks.
Ensures all file paths used in FileResponse are within allowed directories.
"""
import os

# Allowed base directories for file access
ALLOWED_DIRS = [
    "/var/lib/powerhouse/snapshots",
    "/var/lib/powerhouse/member-photos",
    "/var/lib/powerhouse/uploads",
    "/var/lib/powerhouse/biometric_data",
]


def validate_path(file_path: str) -> str:
    """
    Validate and canonicalize a file path.
    
    Resolves symlinks and ensures the path is within allowed directories.
    Raises ValueError if path traversal is detected.
    
    Args:
        file_path: The file path to validate
        
    Returns:
        Canonicalized absolute path
        
    Raises:
        ValueError: If path is outside allowed directories
    """
    if not file_path:
        raise ValueError("Empty file path")
    
    # Canonicalize: resolve symlinks, remove .., etc.
    canonical = os.path.realpath(file_path)
    
    # Check the canonical path is within at least one allowed directory
    for allowed_dir in ALLOWED_DIRS:
        allowed_real = os.path.realpath(allowed_dir)
        if canonical.startswith(allowed_real + os.sep) or canonical == allowed_real:
            return canonical
    
    raise ValueError(f"Path outside allowed directories: {file_path}")


def is_safe_path(file_path: str) -> bool:
    """Check if path is safe without raising."""
    try:
        validate_path(file_path)
        return True
    except ValueError:
        return False
