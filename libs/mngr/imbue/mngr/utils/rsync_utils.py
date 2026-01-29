import deal


@deal.has()
def parse_rsync_output(
    # stdout from rsync command
    output: str,
    # Tuple of (files_transferred, bytes_transferred)
) -> tuple[int, int]:
    """Parse rsync output to extract transfer statistics.

    Parses the verbose output from rsync to count:
    - Number of files transferred (from the file list)
    - Bytes transferred (from the "sent X bytes" summary line)

    Returns a tuple of (files_transferred, bytes_transferred).
    """
    files_transferred = 0
    bytes_transferred = 0

    lines = output.strip().split("\n")

    # Count files from the output (non-empty, non-stat lines)
    for line in lines:
        line = line.strip()
        # Skip empty lines and stat summary lines
        if not line:
            continue
        if line.startswith("sending incremental file list"):
            continue
        if line.startswith("sent "):
            # Parse "sent X bytes  received Y bytes" line
            parts = line.split()
            for i, part in enumerate(parts):
                if part == "bytes" and i > 0:
                    try:
                        bytes_transferred = int(parts[i - 1].replace(",", ""))
                    except (ValueError, IndexError):
                        pass
                    break
            continue
        if line.startswith("total size"):
            continue
        # This is a file being transferred
        if not line.startswith(" "):
            files_transferred += 1

    return files_transferred, bytes_transferred
