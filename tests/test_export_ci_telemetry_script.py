"""Static regression tests for the CI telemetry export shell script."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / ".github" / "scripts" / "export-ci-telemetry.sh"


def test_growing_run_payload_reaches_jq_on_stdin() -> None:
    script = _SCRIPT.read_text(encoding="utf-8")

    assert '--argjson run "$run_json"' not in script
    assert ". as $run |" in script
    assert '\' <<<"$run_json")"' in script


def test_growing_job_accumulator_reaches_payload_jq_on_stdin() -> None:
    script = _SCRIPT.read_text(encoding="utf-8")

    assert '--argjson jobs "$job_spans"' not in script
    assert ". as $jobs |" in script
    assert '\' <<<"$job_spans" > "$payload_file"' in script


def test_bounded_run_span_stays_on_argv() -> None:
    script = _SCRIPT.read_text(encoding="utf-8")

    assert '--argjson run "$run_span"' in script
    assert "spans:([$run] + $jobs)" in script


def _job_span_block(script: str) -> str:
    start = script.index('--arg name "ci.job.$jname"')
    return script[start : script.index("status:{code:$code}}')", start)]


def test_job_span_carries_ci_event_and_git_branch() -> None:
    block = _job_span_block(_SCRIPT.read_text(encoding="utf-8"))

    assert 'run_branch="$(jq -r \'.headBranch // ""\' <<<"$run_json")"' in _SCRIPT.read_text(
        encoding="utf-8"
    )
    assert '--arg branch "$run_branch" --arg event "$run_event"' in block
    assert '{key:"git.branch",value:{stringValue:$branch}}' in block
    assert '{key:"ci.event",value:{stringValue:$event}}' in block


def test_job_and_run_spans_carry_run_attempt_and_job_span_carries_queue_ms() -> None:
    script = _SCRIPT.read_text(encoding="utf-8")
    block = _job_span_block(script)

    assert "--json databaseId,attempt," in script
    assert script.count('{key:"ci.run_attempt",value:{intValue:($run_attempt|tostring)}}') == 2
    assert '{key:"ci.run_attempt",value:{intValue:($run_attempt|tostring)}}' in block
    assert '{key:"ci.job.queue_ms",value:{intValue:($jqueue|tostring)}}' in block
    assert "jqueue_ms=$(( (jstart - jcreated) / 1000000 ))" in script
