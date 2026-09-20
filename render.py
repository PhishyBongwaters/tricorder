"""render_tree / to_tree — extracted from core.py (SPEC_db_map Goal 5).

These methods assemble the map output string. Goal 5b adds optional
streaming via a writer parameter so --full output can go to a file
handle instead of building a giant in-RAM string.
"""

from collections import defaultdict
from io import StringIO
import os
from pathlib import Path
from typing import IO, List, Optional, Set, Tuple, Union

from grep_ast import TreeContext
from utils import Tag


def _cached_tree_context(self, abs_fname: str, rel_fname: str, code: str,
                       lois_0based: List[int]) -> TreeContext:
    """TreeContext for a file, cached per Tricorder but mtime-validated.

    The MCP server reuses one Tricorder per root across tool calls, so a
    cache keyed by filename alone would render stale code after the file
    is edited between calls. Rebuild when the mtime moved.

    Pinned grep-ast==0.9.0 API: LOIs are 0-based, registered with
    add_lines_of_interest, expanded with add_context, rendered with
    format(). Both add_* calls accumulate, so per-render LOI state is
    reset here — otherwise a reused tree leaks lines from previous
    renders' LOIs.
    """
    try:
        mtime = os.stat(abs_fname).st_mtime
    except OSError:
        mtime = None
    entry = self.tree_context_cache.get(rel_fname)
    if entry is None or entry[0] != mtime:
        entry = (mtime, TreeContext(rel_fname, code, color=False))
        self.tree_context_cache[rel_fname] = entry
    tc = entry[1]
    tc.lines_of_interest = set(lois_0based)
    tc.show_lines = set()
    tc.add_context()
    return tc


def render_tree(
    self,  # Tricorder — bound method, first arg is the instance
    abs_fname: str,
    rel_fname: str,
    lois: List[int],
    writer: Optional[IO[str]] = None,
) -> Union[str, None]:
    """Render a code snippet with specific lines of interest.

    When writer is provided, writes the rendered text to it and returns None.
    When writer is None (default), returns the rendered string (backward compat).
    """
    code = self.read_text_func_internal(abs_fname)
    if not code:
        if writer is None:
            return ""
        return None

    # T0 mode (context_lines == 0): just render definition lines directly
    # TreeContext renders the full file with scope annotations, bloating
    # token cost 36x for large repos. Skip it when no context is needed.
    if self.context_lines == 0:
        lines = code.splitlines()
        result_lines = [rel_fname]
        for loi in sorted(set(lois)):
            if 1 <= loi <= len(lines):
                result_lines.append(f"  {loi}: {lines[loi-1]}")
        result = "\n".join(result_lines)
        if writer is not None:
            writer.write(result)
            return None
        return result

    # T1 mode: use TreeContext for context rendering
    try:
        # grep-ast LOIs are 0-based; render_tree callers pass 1-based.
        lois_0based = [loi - 1 for loi in sorted(set(lois)) if loi >= 1]
        tree_context = _cached_tree_context(self, abs_fname, rel_fname, code,
                                            lois_0based)
        result = tree_context.format()
        if writer is not None:
            writer.write(result)
            return None
        return result
    except Exception:
        # Fallback to simple line extraction
        lines = code.splitlines()
        result_lines = [f"{rel_fname}:"]

        for loi in sorted(set(lois)):
            if 1 <= loi <= len(lines):
                result_lines.append(f"{loi:4d}: {lines[loi-1]}")

        result = "\n".join(result_lines)
        if writer is not None:
            writer.write(result)
            return None
        return result


def _render_body(
    self,
    abs_fname: str,
    rel_fname: str,
    lois: List[int],
    writer: Optional[IO[str]] = None,
) -> Union[str, None]:
    """Render just the body lines (no filename header).

    Used by the streaming path in to_tree where the filename header
    is written separately. When writer is None, returns body lines
    joined by newlines (without the filename header line).
    """
    code = self.read_text_func_internal(abs_fname)
    if not code:
        if writer is None:
            return ""
        return None

    if self.context_lines == 0:
        lines = code.splitlines()
        result_lines = []
        for loi in sorted(set(lois)):
            if 1 <= loi <= len(lines):
                result_lines.append(f"  {loi}: {lines[loi-1]}")
        result = "\n".join(result_lines)
        if writer is not None:
            writer.write(result)
            return None
        return result

    try:
        lois_0based = [loi - 1 for loi in sorted(set(lois)) if loi >= 1]
        tree_context = _cached_tree_context(self, abs_fname, rel_fname, code,
                                            lois_0based)
        result = tree_context.format()
        if writer is not None:
            writer.write(result)
            return None
        return result
    except Exception:
        lines = code.splitlines()
        result_lines = []
        for loi in sorted(set(lois)):
            if 1 <= loi <= len(lines):
                result_lines.append(f"{loi:4d}: {lines[loi-1]}")
        result = "\n".join(result_lines)
        if writer is not None:
            writer.write(result)
            return None
        return result


def to_tree(
    self,  # Tricorder — bound method, first arg is the instance
    tags: List[Tuple[float, Tag]],
    chat_rel_fnames: Set[str],
    untagged_files: Optional[List[str]] = None,
    writer: Optional[IO[str]] = None,
) -> Union[str, None]:
    """Convert ranked tags to formatted tree output.

    When writer is provided, streams chunks to it and returns None.
    When writer is None (default), returns the full string (backward compat).
    """
    if not tags:
        if writer is None:
            return ""
        return None

    # Group tags by file
    file_tags = defaultdict(list)
    for rank, tag in tags:
        file_tags[tag.rel_fname].append((rank, tag))

    # Sort files by importance (max rank of their tags)
    sorted_files = sorted(
        file_tags.items(),
        key=lambda x: max(rank for rank, tag in x[1]),
        reverse=True
    )

    # Pre-compute line counts for files we're about to render
    file_abs_paths = {rel: str(self.root / rel) for rel, _ in sorted_files}
    file_line_counts = {}
    for rel, abs_path in file_abs_paths.items():
        code = self.read_text_func_internal(abs_path)
        if code:
            file_line_counts[rel] = len(code.splitlines())

    # ponytail: stream directly to writer when provided — skip the
    # tree_parts list entirely. This is the memory win for --full.
    if writer is not None:
        grouped_files = defaultdict(list)
        for rel_fname, file_tag_list in sorted_files:
            grouped_files[Path(rel_fname).parent.as_posix()].append((rel_fname, file_tag_list))

        first_group = True
        for group_name, files_in_group in sorted(grouped_files.items(), key=lambda item: (item[0] != '.', item[0])):
            if not first_group:
                writer.write("\n\n")
            first_group = False

            header = "root" if group_name == "." else group_name
            writer.write(f"{header}/\n")

            first_file = True
            for rel_fname, file_tag_list in files_in_group:
                if not first_file:
                    writer.write("\n\n")
                first_file = False

                lois = [tag.line for rank, tag in file_tag_list]
                if self.context_lines > 0:
                    expanded_lois = []
                    for loi in lois:
                        for offset in range(-self.context_lines, self.context_lines + 1):
                            expanded_lois.append(max(1, loi + offset))
                    lois = sorted(set(expanded_lois))

                abs_fname = str(self.root / rel_fname)
                max_rank = max(rank for rank, tag in file_tag_list)

                # Write header + rank_line + separator BEFORE body
                # Non-streaming format: f"{first_line}\n{rank_line}\n\n" + body
                # rank_line ends with \n when present, or is "" when absent.
                lc = file_line_counts.get(rel_fname)
                if lc:
                    writer.write(f"{rel_fname} ({lc} lines)\n")
                else:
                    writer.write(f"{rel_fname}\n")

                rank_line = f"(Rank value: {max_rank:.4f})\n"
                if len(set(rank for rank, _ in file_tag_list)) == 1 and all(
                    max(r for r, _ in file_tags) == max_rank for _, file_tags in sorted_files
                ):
                    rank_line = ""
                writer.write(rank_line)
                writer.write("\n\n")

                # Write body (no filename header — that's the caller's job)
                _render_body(self, abs_fname, rel_fname, lois, writer)
        return None

    # Non-streaming path (backward compat): build in RAM
    tree_parts = []
    grouped_files = defaultdict(list)
    for rel_fname, file_tag_list in sorted_files:
        grouped_files[Path(rel_fname).parent.as_posix()].append((rel_fname, file_tag_list))

    for group_name, files_in_group in sorted(grouped_files.items(), key=lambda item: (item[0] != '.', item[0])):
        group_parts = []
        for rel_fname, file_tag_list in files_in_group:
            lois = [tag.line for rank, tag in file_tag_list]
            if self.context_lines > 0:
                expanded_lois = []
                for loi in lois:
                    for offset in range(-self.context_lines, self.context_lines + 1):
                        expanded_lois.append(max(1, loi + offset))
                lois = sorted(set(expanded_lois))

            abs_fname = str(self.root / rel_fname)
            max_rank = max(rank for rank, tag in file_tag_list)
            # Body only (no filename header — it is written above). _render_body
            # is the shared path with the streaming branch; render_tree's
            # first line is NOT a filename header on the TreeContext path
            # (grep-ast==0.9.0 format() emits code lines only), so the old
            # rendered_lines[1:] surgery silently dropped one context line.
            body = _render_body(self, abs_fname, rel_fname, lois)
            if not body:
                continue

            lc = file_line_counts.get(rel_fname)
            if lc:
                first_line = f"{rel_fname} ({lc} lines)"
            else:
                first_line = rel_fname
            rank_line = f"(Rank value: {max_rank:.4f})\n"
            if len(set(rank for rank, _ in file_tag_list)) == 1 and all(
                max(r for r, _ in file_tags) == max_rank for _, file_tags in sorted_files
            ):
                rank_line = ""
            group_parts.append(
                f"{first_line}\n{rank_line}\n\n" + body
            )

        if group_parts:
            header = "root" if group_name == "." else group_name
            tree_parts.append(f"{header}/\n" + "\n\n".join(group_parts))

    return "\n\n".join(tree_parts)
