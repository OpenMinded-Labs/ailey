# -*- coding: utf-8 -*-
"""
Simple file chunker for code-agenting MVP.

Splits large source files into manageable chunks by top-level definitions
or by fixed-window fallback. Returns chunks with start/end line indices and
context to present to the coder model.
"""
from __future__ import annotations
import os
import re
from dataclasses import dataclass
from typing import List


@dataclass
class Chunk:
    id: int
    start_line: int
    end_line: int
    context: str


def _split_by_definitions(lines: List[str]) -> List[int]:
    """Return indices (0-based) of lines that start a top-level definition.

    Looks for Python 'def'/'class', JS/TS 'function'/'export' etc. If none are
    found, returns an empty list.
    """
    pattern = re.compile(r'^(def |class |async def |export |function |const |let |var )')
    indices = [i for i, l in enumerate(lines) if pattern.match(l.lstrip())]
    return indices


def chunk_file(project_root: str, rel_path: str, max_chunk_lines: int = 200, overlap: int = 10) -> List[Chunk]:
    """Create chunks for a file at project_root/rel_path.

    Args:
        project_root: repo root path
        rel_path: file path relative to project_root
        max_chunk_lines: target maximum lines per chunk
        overlap: number of overlapping context lines between chunks

    Returns:
        list of Chunk objects. If file does not exist, returns empty list.
    """
    full_path = os.path.join(project_root, rel_path)
    if not os.path.exists(full_path):
        return []

    with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
        text = f.read()

    lines = text.splitlines()
    n = len(lines)

    # Try to split by top-level definitions first
    def_indices = _split_by_definitions(lines)
    chunks = []

    if def_indices and len(def_indices) > 1:
        # Build chunks as groups of consecutive definitions keeping size under max_chunk_lines
        current = 0
        chunk_id = 1
        while current < n:
            # Determine chunk start at nearest definition <= current
            start = current
            # advance end until size would exceed max_chunk_lines
            end = min(n, start + max_chunk_lines)
            # try to extend to end of last definition inside range
            # if there is a definition boundary after start, respect it
            chunk_lines = lines[start:end]
            # produce context with overlap
            context_start = max(0, start - overlap)
            context_end = min(n, end + overlap)
            context = '\n'.join(lines[context_start:context_end])
            chunks.append(Chunk(id=chunk_id, start_line=start + 1, end_line=end, context=context))
            chunk_id += 1
            current = end
    else:
        # Fallback: fixed window chunks with small overlap
        chunk_id = 1
        start = 0
        while start < n:
            end = min(n, start + max_chunk_lines)
            context_start = max(0, start - overlap)
            context_end = min(n, end + overlap)
            context = '\n'.join(lines[context_start:context_end])
            chunks.append(Chunk(id=chunk_id, start_line=start + 1, end_line=end, context=context))
            chunk_id += 1
            start = end - overlap  # overlap for next chunk

    return chunks
