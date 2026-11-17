"""The TDD evidence validator embedded in the exact-head publication helper."""

from __future__ import annotations

__all__: list[str] = ["tdd_lineage_gate_program_body", "tdd_lineage_gate_program_source"]

_PROGRAM_BODY = r"""import hashlib
import subprocess as s
import sys

g = lambda *a: s.check_output(("git", *a), text=True).strip()
e = lambda x: sys.exit("LIVESPEC_TDD_LINEAGE_REFUSED: " + x)
a = sys.argv[1:]
if len(a) > 1:
    sys.exit("usage: livespec-tdd-lineage-gate.py [base]")
v = ("rev-list", "--reverse", f"{a[0]}..HEAD") if a else (
    "rev-list", "--reverse", "HEAD", "--not", "--remotes=origin"
)
z = g(*v).split()
if a and not z:
    z = [g("rev-parse", "HEAD")]
for c in z:
    m = dict(
        x.split(": ", 1)
        for x in g("show", "-s", "--format=%B", c).splitlines()
        if x.startswith("TDD-") and ": " in x
    )
    q = ("TDD-Red-Parent-Reflog", "TDD-Green-Parent-Reflog")
    u = m.get("TDD-Red-Test-File-Checksum")
    t = m.get("TDD-Red-Test") or m.get("TDD-Red-Test-File")
    if not any(m.get(k) for k in q) and not (u and t):
        continue
    p = g("rev-parse", c + "^")
    for k in q:
        if m.get(k) and m[k] != p:
            e(c + " has " + k + " parent " + m[k] + ", not published parent " + p)
    if u and t:
        try:
            h = hashlib.sha256(s.check_output(("git", "show", c + ":" + t))).hexdigest()
        except s.CalledProcessError:
            e(c + " TDD Red test file " + t + " is absent from the commit")
        if u != "sha256:" + h:
            e(c + " TDD Red checksum does not match test file " + t)
"""


def tdd_lineage_gate_program_body() -> str:
    """The validator shared by direct tests and the materialized push program."""
    return _PROGRAM_BODY


def tdd_lineage_gate_program_source() -> str:
    """The standalone executable form used by the regression fixture."""
    return "#!/usr/bin/env python3\n" + tdd_lineage_gate_program_body()
