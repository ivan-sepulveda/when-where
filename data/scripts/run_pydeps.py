#!/usr/bin/env python3
"""
Draw the import graph of this repo's Python, using pydeps as the engine.

    python run_pydeps.py                # every target, SVGs into "Claude outputs/dependency-graphs"
    python run_pydeps.py --list         # just show what it would analyse, and stop
    python run_pydeps.py --only multiple backend.app
    python run_pydeps.py --open         # macOS: open each SVG when it's done

WHAT THIS ADDS OVER TYPING `pydeps` YOURSELF
--------------------------------------------
Three things, and the first one is the reason this file exists.

1. `pydeps data/scripts/multiple` SILENTLY PRODUCES AN EMPTY GRAPH. Not an
   error, not a warning worth noticing, exit code 0 -- a 606-byte SVG with
   nothing in it. pydeps analyses a MODULE or a PACKAGE, and
   data/scripts/multiple is neither: 62 loose scripts with no __init__.py.

   The obvious fix -- drop an __init__.py in and call it a package -- is worse,
   because it produces a graph that is WRONG rather than empty. These scripts
   import each other flatly (`from chef_trips import UNKNOWN_CARRIER`), which
   resolves when you run them the way they are meant to be run, from inside
   their own directory. Treat that directory as a package and those imports
   stop resolving, so the chef cluster and the rec-sys cluster vanish and you
   are left with a picture of which files import pandas. Measured: 23 nodes, of
   which the interesting ones were absent.

   So this script does what actually works -- runs pydeps once per entry point
   FROM INSIDE the directory, where the flat imports resolve, and merges the
   results into one graph. That is what `--show-deps` (pydeps' JSON output) is
   for.

2. It finds the targets itself, and treats the two kinds differently. A
   directory with __init__.py (backend/app) is a real package and goes to
   pydeps whole. A directory of loose scripts (all six under data/scripts) gets
   the per-entry-point treatment above.

3. It tells you what the graph MEANS in text, not just in a picture: how many
   files import nothing local, which clusters exist, and any import cycles.

WHAT IT WILL NOT SHOW YOU, AND THIS MATTERS FOR THIS REPO
---------------------------------------------------------
Import edges are not how data/scripts is actually wired. Of the 62 files in
data/scripts/multiple, 39 -- 63% -- import nothing local at all, and the real
coupling runs through FILES ON DISK: build_conference_trips.py writes
conference_traveler.json, which build_trips_enhanced.py reads, which writes
trips_enhanced.json, which build_travelers.py reads. That is 62 producer ->
consumer edges over 89 data files, and every one of them is invisible to
pydeps, because it lives in a path constant rather than an import statement.
Getting THAT order wrong is what silently produces stale output.

This script prints the ratio at the end so the sparse picture is not
mistaken for a simple codebase. The data-flow graph is a separate job.

REQUIREMENTS
    pip install pydeps
    Graphviz, for the `dot` binary  (brew install graphviz)
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Directories never worth walking into.
SKIP_DIRS = {"__pycache__", "venv", ".venv", "node_modules", ".git",
             "_to_delete", ".ipynb_checkpoints", "build", "dist"}

DEFAULT_OUT = Path("Claude outputs") / "dependency-graphs"

# How wide to let pydeps wander from an entry point. 2 is enough for a repo
# whose deepest local chain is build_x -> chef_traveler -> chef_trips, and it
# keeps third-party trees (pandas pulling in half of numpy) out of the way.
MAX_BACON = 2

# One pydeps subprocess per entry point. The cost is mostly interpreter
# startup, so it parallelises, but not away: expect a minute or two for
# data/scripts/multiple's 62 files. Lower this if it saturates your machine.
WORKERS = 16


# --------------------------------------------------------------------------
# Preflight
# --------------------------------------------------------------------------

def preflight() -> None:
    """Both dependencies, checked before any work, with the fix in the error.

    pydeps without Graphviz fails deep inside a subprocess with a message about
    `dot` that is easy to misread as a pydeps bug, so it is worth catching
    here."""
    problems = []
    try:
        import pydeps  # noqa: F401
    except ImportError:
        problems.append(
            f"pydeps is not installed for this interpreter ({sys.executable}).\n"
            f"    {sys.executable} -m pip install pydeps"
        )
    if shutil.which("dot") is None:
        problems.append(
            "Graphviz's `dot` is not on PATH -- pydeps renders through it.\n"
            "    brew install graphviz"
        )
    if problems:
        sys.exit("Cannot run:\n\n  " + "\n\n  ".join(problems) + "\n")


def find_repo_root(start: Path) -> Path:
    for d in [start, *start.parents]:
        if (d / ".git").exists():
            return d
    return start


# --------------------------------------------------------------------------
# Target discovery
# --------------------------------------------------------------------------

class Target:
    """One thing to graph.

    kind == "package": has __init__.py, so pydeps can take it whole.
    kind == "scripts": loose files, so each is its own entry point and the
                       results get merged -- see the module docstring."""

    def __init__(self, path: Path, root: Path):
        self.path = path
        self.rel = path.relative_to(root)
        self.files = sorted(p for p in path.glob("*.py") if p.name != "__init__.py")
        self.kind = "package" if (path / "__init__.py").exists() else "scripts"
        self.name = str(self.rel).replace("/", ".")

    def __repr__(self) -> str:
        return f"<{self.name} {self.kind} {len(self.files)} files>"


def discover(root: Path) -> list[Target]:
    targets = []
    for d in sorted(root.rglob("*")):
        if not d.is_dir() or any(part in SKIP_DIRS for part in d.parts):
            continue
        if any(p.name != "__init__.py" for p in d.glob("*.py")):
            targets.append(Target(d, root))
    return targets


# --------------------------------------------------------------------------
# Running pydeps
# --------------------------------------------------------------------------

def pydeps_json(entry: Path, cwd: Path) -> dict:
    """pydeps --show-deps for one entry point, run from `cwd`.

    THE cwd IS THE WHOLE TRICK for the loose-script directories: it puts the
    script's own directory on sys.path, which is the condition under which
    `from chef_trips import ...` resolves. Run it from the repo root instead
    and those edges quietly disappear."""
    # --no-output, and it is not optional. WITHOUT IT pydeps still renders a
    # default .svg next to every module it analyses, even in --show-deps JSON
    # mode -- which for data/scripts/multiple means 62 stray SVGs dropped into
    # the user's source directory. Caught the first time this ran for real.
    cmd = [sys.executable, "-m", "pydeps", str(entry.name),
           "--noshow", "--no-output", "--show-deps", "--max-bacon", str(MAX_BACON)]
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        return {}
    # pydeps prints warnings to stdout above the JSON on some versions, so
    # start at the first brace rather than trusting the whole stream.
    start = proc.stdout.find("{")
    if start < 0:
        return {}
    try:
        return json.loads(proc.stdout[start:])
    except json.JSONDecodeError:
        return {}


def local_graph(target: Target, quiet: bool = False) -> tuple[set, set]:
    """(nodes, edges) restricted to modules that live in this target.

    A node counts as local if its name matches a .py file in the directory.
    That is deliberately not `path is not None` -- pydeps reports path: null
    for some modules it resolved perfectly well by name, and dropping those
    would lose real edges."""
    local_names = {f.stem for f in target.files}
    nodes: set[str] = set()
    edges: set[tuple[str, str]] = set()

    def norm(n: str) -> str:
        n = re.sub(r"\.py$", "", n)
        return n.split(".")[-1]

    if target.kind == "package":
        entries = [target.path]
        cwd = target.path.parent
    else:
        entries = target.files
        cwd = target.path

    def one(entry: Path) -> dict:
        return pydeps_json(entry, cwd)

    # Only animate when someone is watching -- piped into a file or a pager,
    # \r does not erase and every step ends up on the same line.
    show_progress = not quiet and len(entries) > 1 and sys.stdout.isatty()

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(one, e): e for e in entries}
        for i, fut in enumerate(concurrent.futures.as_completed(futures), 1):
            results.append(fut.result())
            if show_progress:
                print(f"\r    {i}/{len(entries)} entry points", end="", flush=True)
    if show_progress:
        print("\r" + " " * 40 + "\r", end="")

    for data in results:
        for raw_name, info in data.items():
            name = norm(raw_name)
            if name not in local_names:
                continue
            nodes.add(name)
            for imported in info.get("imports") or []:
                dst = norm(imported)
                if dst in local_names and dst != name:
                    nodes.add(dst)
                    edges.add((name, dst))
    return nodes, edges


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def to_dot(target: Target, nodes: set, edges: set, include_isolated: bool) -> str:
    """Graphviz source.

    Isolated files are OFF by default and the reason is aspect ratio, not
    tidiness: 32 unconnected boxes stack into a single 3,000pt column and
    squash the part you actually came to look at into the top eighth of the
    image. They are never silently dropped -- they are counted in the console
    output and written out in full to <target>.isolated.txt, and --isolated
    puts them back in the picture."""
    has_edge = {a for a, _ in edges} | {b for _, b in edges}
    isolated = sorted({f.stem for f in target.files} - has_edge) if include_isolated else []
    lines = [
        f'digraph "{target.name}" {{',
        '  graph [rankdir=LR, bgcolor="transparent", fontname="Helvetica",'
        ' splines=spline, nodesep=0.35, ranksep=0.9];',
        '  node  [shape=box, style="rounded,filled", fontname="Helvetica",'
        ' fontsize=11, penwidth=0, margin="0.14,0.09"];',
        '  edge  [color="#8a8f98", penwidth=1.1, arrowsize=0.7];',
    ]
    # Anything imported by something else is a shared module -- the thing you
    # want to spot, and the thing you have to be careful editing.
    imported = {b for _, b in edges}
    for n in sorted(has_edge):
        fill = "#2a78d6" if n in imported else "#dce6f5"
        font = "white" if n in imported else "#12233d"
        lines.append(f'  "{n}" [fillcolor="{fill}", fontcolor="{font}"];')
    for a, b in sorted(edges):
        lines.append(f'  "{a}" -> "{b}";')
    if isolated:
        lines.append('  subgraph cluster_isolated {')
        lines.append('    label="imports nothing local, imported by nothing local";')
        lines.append('    fontname="Helvetica"; fontsize=10; fontcolor="#6b7280";')
        lines.append('    color="#d6dae1"; style="rounded";')
        for n in isolated:
            lines.append(f'    "{n}" [fillcolor="#f2f4f7", fontcolor="#6b7280"];')
        lines.append("  }")
    lines.append("}")
    return "\n".join(lines)


def render(dot_source: str, out_svg: Path) -> None:
    out_svg.parent.mkdir(parents=True, exist_ok=True)
    out_svg.with_suffix(".dot").write_text(dot_source, encoding="utf-8")
    proc = subprocess.run(["dot", "-Tsvg", "-o", str(out_svg)],
                          input=dot_source, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"dot failed for {out_svg.name}:\n{proc.stderr}")


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def find_cycles(nodes: set, edges: set) -> list[list[str]]:
    """Import cycles, which are the one thing in here that is a real defect."""
    adj: dict[str, list[str]] = {n: [] for n in nodes}
    for a, b in edges:
        adj.setdefault(a, []).append(b)
    cycles, stack, on_stack, seen = [], [], set(), set()

    def walk(n: str) -> None:
        seen.add(n)
        stack.append(n)
        on_stack.add(n)
        for m in adj.get(n, []):
            if m not in seen:
                walk(m)
            elif m in on_stack:
                cycles.append(stack[stack.index(m):] + [m])
        stack.pop()
        on_stack.discard(n)

    for n in sorted(nodes):
        if n not in seen:
            walk(n)
    return cycles


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Draw this repo's Python import graphs with pydeps.")
    ap.add_argument("--out", type=Path, default=None,
                    help=f"output directory (default: {DEFAULT_OUT})")
    ap.add_argument("--only", nargs="*", metavar="NAME",
                    help="analyse only these targets (see --list for names)")
    ap.add_argument("--list", action="store_true",
                    help="show what would be analysed, then stop")
    ap.add_argument("--isolated", action="store_true",
                    help="also draw files with no local imports either way "
                         "(off by default -- they make the SVG very tall)")
    ap.add_argument("--open", action="store_true",
                    help="macOS: open each SVG when it is written")
    args = ap.parse_args()

    root = find_repo_root(Path(__file__).resolve().parent)
    targets = discover(root)
    if args.only:
        wanted = set(args.only)
        targets = [t for t in targets if t.name in wanted or str(t.rel) in wanted]
        if not targets:
            sys.exit(f"No target matched {args.only}. Run --list to see the names.")

    if args.list:
        print(f"repo root: {root}\n")
        for t in targets:
            print(f"  {t.name:<28} {t.kind:<8} {len(t.files):>3} files")
        return

    preflight()
    out_dir = (args.out or (root / DEFAULT_OUT)).resolve()
    print(f"repo root: {root}")
    print(f"output:    {out_dir}\n")

    grand_files = grand_isolated = 0
    summary = []

    for t in targets:
        print(f"{t.name}  ({t.kind}, {len(t.files)} files)")
        nodes, edges = local_graph(t)
        svg = out_dir / f"{t.name}.svg"
        render(to_dot(t, nodes, edges, args.isolated), svg)

        connected = {a for a, _ in edges} | {b for _, b in edges}
        isolated_names = sorted({f.stem for f in t.files} - connected)
        isolated = len(isolated_names)
        if isolated_names:
            (out_dir / f"{t.name}.isolated.txt").write_text(
                "\n".join(isolated_names) + "\n", encoding="utf-8")
        grand_files += len(t.files)
        grand_isolated += isolated
        shared = sorted({b for _, b in edges},
                        key=lambda n: (-sum(1 for _, y in edges if y == n), n))
        cycles = find_cycles(nodes, edges)

        print(f"    {len(edges)} import edge(s), "
              f"{isolated}/{len(t.files)} file(s) with no local imports either way")
        if shared:
            top = ", ".join(f"{n} (x{sum(1 for _, y in edges if y == n)})"
                            for n in shared[:4])
            print(f"    shared: {top}")
        if cycles:
            for c in cycles[:3]:
                print(f"    CYCLE: {' -> '.join(c)}")
        where = svg.relative_to(root) if svg.is_relative_to(root) else svg
        print(f"    -> {where}"
              + (f"   (+ {svg.stem}.isolated.txt)" if isolated else ""))
        summary.append((t.name, len(t.files), len(edges), isolated))

        if args.open and sys.platform == "darwin":
            subprocess.run(["open", str(svg)], check=False)

    (out_dir / "summary.json").write_text(json.dumps(
        [{"target": n, "files": f, "import_edges": e, "isolated": i}
         for n, f, e, i in summary], indent=2), encoding="utf-8")

    print(f"\n{grand_files} Python files, {grand_isolated} of them "
          f"({grand_isolated / grand_files:.0%}) import nothing local and are "
          "imported by nothing local.")
    print("Import edges are not how data/scripts is wired -- the real coupling "
          "runs through JSON/CSV files on disk, which no import graph can see. "
          "See this file's docstring.")


if __name__ == "__main__":
    main()
