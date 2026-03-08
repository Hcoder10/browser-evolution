"""
Fitness Scorers — 4 judges that determine if a browser agent organism survives.

2 heuristic scorers (fast, deterministic) + 2 MULTIMODAL LLM judge scorers (Gemini 3 Flash).
LLM judges receive actual screenshots from the browser session for grounded evaluation.
"""

import base64
import os
import re
import weave
from google import genai
from google.genai import types

_genai_client = None

def get_genai_client():
    global _genai_client
    if _genai_client is None:
        _genai_client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY", ""))
    return _genai_client

GEMINI_JUDGE_MODEL = "gemini-3-flash-preview"


def _screenshots_to_parts(screenshots: list[str], max_images: int = 8) -> list:
    """Convert base64 screenshot strings to Gemini Parts for multimodal input."""
    parts = []
    if not screenshots:
        return parts

    # Sample evenly if too many screenshots
    if len(screenshots) > max_images:
        step = len(screenshots) / max_images
        indices = [int(i * step) for i in range(max_images)]
    else:
        indices = list(range(len(screenshots)))

    for idx in indices:
        shot = screenshots[idx]
        if shot is None:
            continue
        try:
            img_bytes = base64.b64decode(shot)
            parts.append(types.Part.from_bytes(data=img_bytes, mime_type="image/png"))
            parts.append(types.Part.from_text(text=f"[Screenshot: step {idx + 1}]"))
        except Exception:
            continue

    return parts


# ── Scorer 1: Task Completion (Heuristic) — 35% weight ───────────────────────

@weave.op()
def score_task_completion(result: dict) -> float:
    """Did the agent actually complete the checkout? Binary but weighted by progress."""
    if result.get("success"):
        return 1.0

    steps_completed = result.get("steps_completed", [])

    step_scores = {
        "product_page": 0.1,
        "cart_page": 0.3,
        "checkout_page": 0.5,
        "success": 1.0,
    }

    best_score = 0.0
    for step in steps_completed:
        best_score = max(best_score, step_scores.get(step, 0.0))

    return best_score


# ── Scorer 2: Efficiency (Heuristic) — 15% weight ────────────────────────────

@weave.op()
def score_efficiency(result: dict) -> float:
    """Fewer actions = better. Penalize flailing."""
    total_actions = result.get("total_actions", 0)

    if total_actions == 0:
        return 0.0

    if total_actions <= 12:
        return 1.0
    elif total_actions <= 20:
        return 0.8
    elif total_actions <= 30:
        return 0.5
    elif total_actions <= 50:
        return 0.3
    else:
        return 0.1


# ── Scorer 3: Resilience (Multimodal LLM Judge) — 25% weight ─────────────────

@weave.op()
def score_resilience(result: dict, screenshots: list[str] | None = None) -> float:
    """Multimodal LLM judge: Reviews actual screenshots to assess obstacle handling."""
    client = get_genai_client()

    action_log = result.get("action_summary", "No actions recorded")
    errors = result.get("errors", [])
    mutation_level = result.get("mutation_level", 0)

    prompt_text = f"""You are a visual judge evaluating a browser automation agent's RESILIENCE.

You are given screenshots from the agent's actual browser session showing what it saw and did.

CONTEXT:
- The agent navigated a checkout flow on a hostile website at MUTATION LEVEL {mutation_level}/3
- Level 0 = normal site, Level 3 = very hostile (renamed buttons, popups, decoys, scrambled forms)
- The screenshots show the actual pages the agent encountered

AGENT'S ACTION LOG:
{action_log}

ERRORS ENCOUNTERED:
{errors if errors else "None"}

TASK RESULT: {"SUCCESS - completed checkout" if result.get("success") else "FAILED - did not complete checkout"}

Look at the screenshots carefully. Rate the agent's resilience on a 0-10 scale:
- 0-2: Agent was completely confused by the site's hostile elements
- 3-4: Agent tried but got stuck on popups, renamed buttons, or decoys
- 5-6: Agent handled some obstacles (e.g. dismissed popups) but missed others
- 7-8: Agent navigated most obstacles including renamed buttons and form changes
- 9-10: Agent handled ALL hostile elements smoothly — popups dismissed, decoys ignored, forms completed despite scrambling

Return ONLY a single number 0-10, nothing else."""

    try:
        # Build multimodal content: screenshots + text prompt
        content_parts = []

        if screenshots:
            img_parts = _screenshots_to_parts(screenshots)
            if img_parts:
                content_parts.append(types.Part.from_text(
                    text="Here are screenshots from the browser agent's session:"
                ))
                content_parts.extend(img_parts)

        content_parts.append(types.Part.from_text(text=prompt_text))

        response = client.models.generate_content(
            model=GEMINI_JUDGE_MODEL,
            contents=content_parts,
        )
        score_text = response.text.strip()
        match = re.search(r"(\d+(?:\.\d+)?)", score_text)
        if match:
            score = float(match.group(1))
            return min(score / 10.0, 1.0)
        return 0.5
    except Exception as e:
        print(f"    Warning: Resilience scorer failed: {e}")
        return 0.5


# ── Scorer 4: Strategy Quality (Multimodal LLM Judge) — 25% weight ───────────

@weave.op()
def score_strategy(result: dict, screenshots: list[str] | None = None) -> float:
    """Multimodal LLM judge: Reviews screenshots to assess strategic coherence."""
    client = get_genai_client()

    action_log = result.get("action_summary", "No actions recorded")
    genome_prompt = result.get("genome_prompt", "No prompt available")

    prompt_text = f"""You are a visual judge evaluating a browser automation agent's STRATEGY QUALITY.

You are given screenshots from the agent's actual browser session showing what it saw and did.

AGENT'S EVOLVED GENOME (its instructions):
{genome_prompt[:500]}

AGENT'S ACTION LOG:
{action_log}

TASK RESULT: {"SUCCESS" if result.get("success") else "FAILED"}

Look at the screenshots. The sequence shows how the agent progressed through the site.
Rate the agent's strategy on a 0-10 scale:
- 0-2: Random clicking, no coherent approach visible in screenshots
- 3-4: Basic approach but inefficient — repeated same pages, missed obvious elements
- 5-6: Reasonable strategy with some missteps visible in the screenshots
- 7-8: Clear, purposeful progression through the flow with good obstacle handling
- 9-10: Optimal strategy — efficient path, correct element identification, methodical form filling

Return ONLY a single number 0-10, nothing else."""

    try:
        content_parts = []

        if screenshots:
            img_parts = _screenshots_to_parts(screenshots)
            if img_parts:
                content_parts.append(types.Part.from_text(
                    text="Here are screenshots from the browser agent's session:"
                ))
                content_parts.extend(img_parts)

        content_parts.append(types.Part.from_text(text=prompt_text))

        response = client.models.generate_content(
            model=GEMINI_JUDGE_MODEL,
            contents=content_parts,
        )
        score_text = response.text.strip()
        match = re.search(r"(\d+(?:\.\d+)?)", score_text)
        if match:
            score = float(match.group(1))
            return min(score / 10.0, 1.0)
        return 0.5
    except Exception as e:
        print(f"    Warning: Strategy scorer failed: {e}")
        return 0.5


# ── Composite Fitness ─────────────────────────────────────────────────────────

SCORER_WEIGHTS = {
    "task_completion": 0.35,
    "efficiency": 0.15,
    "resilience": 0.25,
    "strategy": 0.25,
}

@weave.op()
def compute_fitness(result: dict, screenshots: list[str] | None = None) -> dict:
    """Run all 4 scorers and compute weighted composite fitness.
    LLM judges receive screenshots for multimodal grounded evaluation."""
    scores = {
        "task_completion": score_task_completion(result),
        "efficiency": score_efficiency(result),
        "resilience": score_resilience(result, screenshots),
        "strategy": score_strategy(result, screenshots),
    }

    composite = sum(scores[k] * SCORER_WEIGHTS[k] for k in SCORER_WEIGHTS)
    scores["composite"] = composite

    return scores
