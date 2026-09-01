"""
Tests for HookScorer 0-100 Virality Engine.
"""

from processor.hook_scorer import HookScorer, HookCandidate


def test_hook_scorer_initialization():
    scorer = HookScorer(min_hook_score=80)
    assert scorer.min_hook_score == 80


def test_deduplicate_candidates():
    scorer = HookScorer()
    candidates = [
        HookCandidate(
            start_ms=0,
            end_ms=30000,
            hook_score=88,
            title="Clip 1",
            hook_text="Hook 1",
            reasoning="Strong hook"
        ),
        HookCandidate(
            start_ms=10000,  # Overlaps with Clip 1
            end_ms=40000,
            hook_score=72,
            title="Clip 2",
            hook_text="Hook 2",
            reasoning="Moderate hook"
        ),
        HookCandidate(
            start_ms=60000,  # Non-overlapping
            end_ms=90000,
            hook_score=92,
            title="Clip 3",
            hook_text="Hook 3",
            reasoning="Insane climax"
        )
    ]

    deduped = scorer._deduplicate_candidates(candidates)
    assert len(deduped) == 2
    assert deduped[0].hook_score == 88
    assert deduped[1].hook_score == 92


def test_heuristic_fallback():
    scorer = HookScorer()
    text = "OMG NO WAY! That clutch was completely insane bro!"
    clips = scorer._heuristic_fallback(text, start_sec=0.0, end_sec=30.0, streamer_name="TestStreamer")
    assert len(clips) == 1
    assert clips[0].hook_score >= 70
    assert "TestStreamer" in clips[0].title
