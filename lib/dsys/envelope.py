"""JSON output envelope for the dsys CLI."""

TOOL_VERSION = "0.1.0"


def envelope(command, profile, exit_code, data=None, error=None) -> dict:
    """Build the single JSON envelope printed to stdout in --format json mode.

    error is None on success, otherwise {"message": ...}.
    """
    return {
        "tool": "dsys",
        "tool_version": TOOL_VERSION,
        "command": command,
        "profile": profile,
        "exit_code": exit_code,
        "error": error,
        "data": data,
    }
