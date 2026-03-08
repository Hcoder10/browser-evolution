"""
HEAD-TO-HEAD DEMO: Naive Prompt vs Evolved Prompt on Nightmare Gauntlet

Shows the competitive advantage of Darwinian prompt evolution.
- Naive: generic "complete the checkout" instruction
- Evolved: 6-gene genome bred through natural selection
Both face the SAME hostile Level 3 Gauntlet with trap pages, decoy buttons,
misleading labels, fake success pages, and 4+ overlapping popups.

Tight action budget (15 steps) — no room for brute force.
"""

import asyncio
import os
import sys
import time
import json
import weave
import requests
from dotenv import load_dotenv

from gauntlet import start_gauntlet
from scorers import compute_fitness

load_dotenv()

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
WANDB_PROJECT = os.environ.get("WANDB_PROJECT", "browser-evolution")
GAUNTLET_URL = "http://127.0.0.1:5000"
MAX_ACTIONS = 25  # Tight budget — forces the prompt to matter

# ── The Two Contenders ─────────────────────────────────────────────────────

NAIVE_PROMPT = """You are a browser automation assistant. Navigate to the given URL and complete the checkout process. Add the item to your cart, proceed to checkout, fill in the shipping form, and place the order."""

EVOLVED_PROMPT = """## NAVIGATION
Break the overall task into sub-goals. For a checkout flow, your sub-goals are: 1) Get the product into the cart, 2) Navigate to checkout, 3) Fill shipping info, 4) Complete the order. For each sub-goal, scan the page for the most direct path. If the expected element isn't obvious, look for alternative paths (links in nav, footer links, breadcrumbs, sidebar).

## ELEMENT SELECTION
Use semantic understanding to find elements. Don't just match text — understand the PURPOSE of each element from its context. A button inside a product card that's near a price is likely 'add to cart' even if it says something unusual. The most prominent button on a cart page is likely 'checkout'. Use visual hierarchy: primary actions are usually larger, more colorful, or more prominently placed.

CRITICAL WARNING: This site is HOSTILE. The large, colorful blue buttons are ALL TRAPS that lead to error pages. The REAL action elements are tiny grey underlined text links, usually at the bottom of the button group. Look for small, subtle links with arrows (like "text ->"). Do NOT click any large blue button — they ALL go to dead-end trap pages. If you click a button and see an error page or "temporarily unavailable", you fell for a trap — go back and click the small grey text link instead.

## ERROR RECOVERY
Maintain awareness of your progress. If you've been on the same page for more than 2 actions without advancing, switch strategies:
- If clicking buttons doesn't work, try links or text elements.
- If the expected flow doesn't exist, look for unconventional paths.
- If forms won't submit, check for hidden required fields or unchecked boxes.
- If you land on an error page or "processing/pending" page, GO BACK immediately — you clicked a trap.
Never repeat the same failing action more than twice.

## DISTRACTION HANDLING
When a popup or overlay appears, IMMEDIATELY dismiss it. Look for small grey dismiss links like "No thanks" at the bottom of popups. Do NOT engage with the popup content, do NOT enter email, do NOT click colorful CTA buttons in popups. Just find the dismiss/close option and click it. Then proceed with your task.

## FORM INTERACTION
Analyze the form holistically before filling:
1) Count all input fields. 2) Identify which are required.
3) Determine field purpose from ANY available signal: label, placeholder, name attribute, position, input type, surrounding text.
4) WARNING: Labels may be DELIBERATELY WRONG. A field labeled "Phone Number" might actually be for email (check the name attribute or input type). A field labeled "Reference Code" might be for a name. Trust the field's name attribute and input type over the visible label.
5) Use realistic test data: 'Alex Johnson', 'alex@example.com', '789 Elm Boulevard', 'Portland', 'OR', '97201'.
6) After filling all fields, look for the REAL submit — it's a small grey underlined text, NOT the big blue buttons. The big buttons are links to a fake success page.

## VERIFICATION
Trust nothing. After every action:
1) Check if the page actually changed (don't assume click worked)
2) Look for error messages that might have appeared
3) Verify you're on the right page (read the heading)
4) Confirm the action registered (cart updated, form accepted)
The task is complete ONLY when you see 'ORDER_CONFIRMED' or similar explicit success message.
If you see 'PAYMENT_PENDING' or 'Processing', that is NOT success — go back and try a different path."""


async def run_agent(prompt: str, label: str, session_id: str) -> dict:
    """Run a browser agent with the given prompt against the Gauntlet."""
    from browser_use import Agent, Browser
    from browser_use.llm import ChatGoogle

    task = f"""{prompt}

YOUR TASK:
Navigate to {GAUNTLET_URL}?sid={session_id} and complete the entire checkout flow:
1. On the product page, find and click the button to add the item to your cart
2. On the cart page, find and click the button to proceed to checkout
3. On the checkout page, fill in ALL form fields with realistic data, then submit the form
4. Verify you see the order confirmation page with "ORDER_CONFIRMED"

IMPORTANT: Dismiss any popups, banners, or overlays that appear. Ignore decoy buttons.
The site may use unusual button labels or layouts. Use your judgment to find the right elements."""

    llm = ChatGoogle(
        model="gemini-2.5-flash",
        api_key=GOOGLE_API_KEY,
        temperature=0,
    )

    start_time = time.time()
    result_data = {
        "label": label,
        "session_id": session_id,
        "success": False,
        "steps_completed": [],
        "total_actions": 0,
        "errors": [],
        "action_summary": "",
        "duration": 0,
        "screenshots": [],
        "genome_prompt": prompt,
    }

    browser = None
    try:
        browser = Browser(headless=True, disable_security=True)
        agent = Agent(
            task=task,
            llm=llm,
            browser=browser,
            max_actions_per_step=5,
        )

        history = await agent.run(max_steps=MAX_ACTIONS)

        # Screenshots
        try:
            raw_screenshots = history.screenshots()
            result_data["screenshots"] = [s for s in raw_screenshots if s is not None]
        except Exception:
            result_data["screenshots"] = []

        # Results
        action_names = history.action_names()
        errors = history.errors()

        result_data["total_actions"] = len(action_names) if action_names else 0
        if action_names:
            result_data["action_summary"] = "\n".join(
                f"  {i+1}. {a}" for i, a in enumerate(action_names[:30])
            )
        result_data["errors"] = [str(e) for e in (errors or []) if e]

        # Check via API
        try:
            status_resp = requests.get(f"{GAUNTLET_URL}/api/status/{session_id}", timeout=5)
            status = status_resp.json()
            result_data["steps_completed"] = status.get("steps", [])
            result_data["success"] = status.get("success", False)
        except Exception:
            final_result = history.final_result()
            if final_result and "ORDER_CONFIRMED" in str(final_result):
                result_data["success"] = True

    except Exception as e:
        result_data["errors"].append(str(e))
        try:
            status_resp = requests.get(f"{GAUNTLET_URL}/api/status/{session_id}", timeout=5)
            status = status_resp.json()
            result_data["steps_completed"] = status.get("steps", [])
        except Exception:
            pass

    finally:
        try:
            if browser and hasattr(browser, 'close'):
                await browser.close()
        except Exception:
            pass

    result_data["duration"] = time.time() - start_time
    return result_data


@weave.op()
async def head_to_head_demo() -> dict:
    """Head-to-head: Naive vs Evolved on Nightmare Gauntlet (Level 3)."""

    print("=" * 70)
    print("HEAD-TO-HEAD DEMO: Naive vs Evolved")
    print("  Gauntlet Level 3 (NIGHTMARE) | 15 action budget | Gemini 2.5 Flash")
    print("=" * 70)

    # Set to NIGHTMARE level
    requests.post(f"{GAUNTLET_URL}/api/mutation/3", timeout=5)
    print("\nGauntlet set to Level 3 (NIGHTMARE)")
    print("  - 4 trap buttons styled like real buttons")
    print("  - Real buttons are tiny grey links")
    print("  - Fake success page (PAYMENT_PENDING)")
    print("  - Misleading form labels")
    print("  - 4 overlapping popups")
    print()

    results = {}

    # ── Run Naive ──
    print("-" * 50)
    print("CONTENDER 1: NAIVE PROMPT")
    print("-" * 50)
    print("  Prompt: 'Navigate and complete checkout' (generic)")
    print("  Running...", flush=True)

    naive_result = await run_agent(NAIVE_PROMPT, "naive", "demo-naive-v2")
    naive_screenshots = naive_result.get("screenshots", [])
    naive_result["mutation_level"] = 3
    naive_scores = compute_fitness(naive_result, naive_screenshots)

    status = "PASS" if naive_result["success"] else "FAIL"
    print(f"  Result: {status}")
    print(f"  Steps completed: {naive_result['steps_completed']}")
    print(f"  Actions used: {naive_result['total_actions']}/{MAX_ACTIONS}")
    print(f"  Duration: {naive_result['duration']:.1f}s")
    print(f"  Fitness: {naive_scores['composite']:.1%}")
    print(f"    Task Completion: {naive_scores['task_completion']:.1%}")
    print(f"    Efficiency: {naive_scores['efficiency']:.1%}")
    print(f"    Resilience: {naive_scores['resilience']:.1%}")
    print(f"    Strategy: {naive_scores['strategy']:.1%}")
    if naive_result["errors"]:
        print(f"  Errors: {len(naive_result['errors'])}")
    results["naive"] = {"result": naive_result, "scores": naive_scores}
    print()

    # ── Run Evolved ──
    print("-" * 50)
    print("CONTENDER 2: EVOLVED PROMPT (6-gene genome)")
    print("-" * 50)
    print("  Prompt: Darwinian-evolved genome with trap awareness")
    print("  Running...", flush=True)

    evolved_result = await run_agent(EVOLVED_PROMPT, "evolved", "demo-evolved-v2")
    evolved_screenshots = evolved_result.get("screenshots", [])
    evolved_result["mutation_level"] = 3
    evolved_scores = compute_fitness(evolved_result, evolved_screenshots)

    status = "PASS" if evolved_result["success"] else "FAIL"
    print(f"  Result: {status}")
    print(f"  Steps completed: {evolved_result['steps_completed']}")
    print(f"  Actions used: {evolved_result['total_actions']}/{MAX_ACTIONS}")
    print(f"  Duration: {evolved_result['duration']:.1f}s")
    print(f"  Fitness: {evolved_scores['composite']:.1%}")
    print(f"    Task Completion: {evolved_scores['task_completion']:.1%}")
    print(f"    Efficiency: {evolved_scores['efficiency']:.1%}")
    print(f"    Resilience: {evolved_scores['resilience']:.1%}")
    print(f"    Strategy: {evolved_scores['strategy']:.1%}")
    if evolved_result["errors"]:
        print(f"  Errors: {len(evolved_result['errors'])}")
    results["evolved"] = {"result": evolved_result, "scores": evolved_scores}

    # ── Comparison ──
    print()
    print("=" * 70)
    print("RESULTS")
    print("=" * 70)
    n = naive_scores
    e = evolved_scores
    print(f"{'Metric':<20} {'Naive':>10} {'Evolved':>10} {'Delta':>10}")
    print("-" * 50)
    for metric in ["task_completion", "efficiency", "resilience", "strategy", "composite"]:
        delta = e[metric] - n[metric]
        marker = "+++" if delta > 0.1 else "++" if delta > 0 else "---" if delta < -0.1 else "--" if delta < 0 else "=="
        print(f"{metric:<20} {n[metric]:>9.1%} {e[metric]:>9.1%} {delta:>+9.1%} {marker}")

    naive_pass = "PASS" if naive_result["success"] else "FAIL"
    evolved_pass = "PASS" if evolved_result["success"] else "FAIL"
    print(f"\n{'Checkout Complete':<20} {naive_pass:>10} {evolved_pass:>10}")
    print(f"{'Actions Used':<20} {naive_result['total_actions']:>10} {evolved_result['total_actions']:>10}")
    print(f"{'Screenshots':<20} {len(naive_screenshots):>10} {len(evolved_screenshots):>10}")

    winner = "EVOLVED" if e["composite"] > n["composite"] else "NAIVE" if n["composite"] > e["composite"] else "TIE"
    delta_pct = abs(e["composite"] - n["composite"])
    print(f"\nWINNER: {winner} (by {delta_pct:.1%})")
    print("=" * 70)

    output = {
        "naive": {
            "success": naive_result["success"],
            "scores": naive_scores,
            "steps": naive_result["steps_completed"],
            "actions": naive_result["total_actions"],
            "duration": naive_result["duration"],
        },
        "evolved": {
            "success": evolved_result["success"],
            "scores": evolved_scores,
            "steps": evolved_result["steps_completed"],
            "actions": evolved_result["total_actions"],
            "duration": evolved_result["duration"],
        },
        "winner": winner,
        "delta": e["composite"] - n["composite"],
        "gauntlet_level": 3,
        "max_actions": MAX_ACTIONS,
    }

    with open("demo_results.json", "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to demo_results.json")

    return output


async def main():
    weave.init(WANDB_PROJECT)
    print("W&B Weave initialized\n")

    print("Starting The Gauntlet...")
    start_gauntlet(port=5000)
    print("Gauntlet running on http://127.0.0.1:5000\n")

    for _ in range(5):
        try:
            resp = requests.get(f"{GAUNTLET_URL}/api/stats", timeout=2)
            if resp.status_code == 200:
                break
        except Exception:
            time.sleep(1)
    else:
        print("ERROR: Could not connect to Gauntlet!")
        sys.exit(1)

    results = await head_to_head_demo()
    print("\nDemo complete! Check W&B Weave for full traces.")
    return results


if __name__ == "__main__":
    asyncio.run(main())
