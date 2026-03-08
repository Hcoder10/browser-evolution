"""
Darwinian Browser Evolution — Main Loop (v2: Multimodal Judges + Browserbase)

Evolves browser agent prompts through natural selection on The Gauntlet.
Each generation: evaluate organisms → cull the weak → breed survivors → mutate the site.

v2 Changes:
- Screenshots captured at every step for multimodal LLM judging
- Gemini 3 Flash judges that SEE what the agent did (not just text logs)
- Optional Browserbase cloud sessions with video replay URLs
- All traced in W&B Weave for full evolutionary observability.
"""

import asyncio
import os
import sys
import time
import json
import weave
import requests
from google import genai as genai_module
from dotenv import load_dotenv

from genome import Genome, create_initial_population, create_random_genome
from evolution import crossover, mutate, llm_mutate_gene, breed_children, cull, tournament_select
from scorers import compute_fitness, SCORER_WEIGHTS
from gauntlet import start_gauntlet

# ── Load env ──────────────────────────────────────────────────────────────────
load_dotenv()

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
WANDB_PROJECT = os.environ.get("WANDB_PROJECT", "browser-evolution")

# Browserbase (optional — set these for cloud browser + video replay)
BROWSERBASE_API_KEY = os.environ.get("BROWSERBASE_API_KEY", "")
BROWSERBASE_PROJECT_ID = os.environ.get("BROWSERBASE_PROJECT_ID", "")
USE_BROWSERBASE = bool(BROWSERBASE_API_KEY and BROWSERBASE_PROJECT_ID)

# ── Evolution Config ──────────────────────────────────────────────────────────
GAUNTLET_URL = "http://127.0.0.1:5000"
INITIAL_POPULATION = 4
CHILDREN_PER_GENERATION = 6
SURVIVAL_RATE = 0.5
NUM_GENERATIONS = 4
LLM_MUTATION_RATE = 0.2
STANDARD_MUTATION_RATE = 0.3
MAX_ACTIONS = 50


# ── Browserbase Session Manager ──────────────────────────────────────────────

def create_browserbase_session():
    """Create a Browserbase cloud session with recording enabled."""
    if not USE_BROWSERBASE:
        return None, None

    from browserbase import Browserbase

    bb = Browserbase(api_key=BROWSERBASE_API_KEY)
    session = bb.sessions.create(
        project_id=BROWSERBASE_PROJECT_ID,
        browser_settings={"recordSession": True, "logSession": True},
    )
    replay_url = f"https://browserbase.com/sessions/{session.id}"
    return session, replay_url


# ── Browser Agent Runner ──────────────────────────────────────────────────────

async def run_browser_agent(genome: Genome, session_id: str, gauntlet_url: str) -> dict:
    """Run a single browser agent organism against The Gauntlet.
    Captures screenshots at every step for multimodal judging."""
    from browser_use import Agent, Browser
    from browser_use.browser.session import BrowserSession
    from browser_use.browser import BrowserProfile
    from browser_use.llm import ChatGoogle

    genome_prompt = genome.assemble_prompt()

    task = f"""{genome_prompt}

YOUR TASK:
Navigate to {gauntlet_url}?sid={session_id} and complete the entire checkout flow:
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
        "session_id": session_id,
        "genome_id": genome.id,
        "genome_prompt": genome_prompt,
        "success": False,
        "steps_completed": [],
        "total_actions": 0,
        "errors": [],
        "action_summary": "",
        "duration": 0,
        "mutation_level": 0,
        "screenshots": [],
        "replay_url": None,
    }

    browser = None
    bb_session = None

    try:
        # Create browser — Browserbase cloud or local
        if USE_BROWSERBASE:
            bb_session, replay_url = create_browserbase_session()
            result_data["replay_url"] = replay_url
            print(f"[cloud] ", end="", flush=True)

            browser_session = BrowserSession(
                cdp_url=bb_session.connect_url,
                browser_profile=BrowserProfile(
                    keep_alive=False,
                    wait_between_actions=1.5,
                ),
                keep_alive=False,
                initialized=False,
            )
            await browser_session.start()

            agent = Agent(
                task=task,
                llm=llm,
                browser_session=browser_session,
                max_actions_per_step=5,
            )
        else:
            browser = Browser(headless=True, disable_security=True)
            agent = Agent(
                task=task,
                llm=llm,
                browser=browser,
                max_actions_per_step=5,
            )

        history = await agent.run(max_steps=MAX_ACTIONS)

        # Extract screenshots from history (base64 PNGs)
        try:
            raw_screenshots = history.screenshots()
            result_data["screenshots"] = [s for s in raw_screenshots if s is not None]
        except Exception:
            result_data["screenshots"] = []

        # Extract results from history
        action_names = history.action_names()
        urls = history.urls()
        errors = history.errors()
        final_result = history.final_result()

        result_data["total_actions"] = len(action_names) if action_names else 0
        if action_names:
            result_data["action_summary"] = "\n".join(
                f"  {i+1}. {a}" for i, a in enumerate(action_names[:30])
            )
        result_data["errors"] = [str(e) for e in (errors or []) if e]

        # Check success via Gauntlet API
        try:
            status_resp = requests.get(f"{gauntlet_url}/api/status/{session_id}", timeout=5)
            status = status_resp.json()
            result_data["steps_completed"] = status.get("steps", [])
            result_data["success"] = status.get("success", False)
        except Exception:
            if final_result and "ORDER_CONFIRMED" in str(final_result):
                result_data["success"] = True

    except Exception as e:
        result_data["errors"].append(str(e))
        try:
            status_resp = requests.get(f"{gauntlet_url}/api/status/{session_id}", timeout=5)
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


# ── Evaluate Genome ───────────────────────────────────────────────────────────

@weave.op()
async def evaluate_genome(genome: Genome, mutation_level: int) -> dict:
    """Evaluate a single genome against The Gauntlet.
    Screenshots are captured and sent to Gemini 3 Flash multimodal judges."""
    session_id = f"org-{genome.id}-gen{genome.generation}-ml{mutation_level}"

    # Set mutation level
    try:
        requests.post(f"{GAUNTLET_URL}/api/mutation/{mutation_level}", timeout=5)
    except Exception as e:
        print(f"    Warning: Could not set mutation level: {e}")

    # Run the browser agent (captures screenshots)
    result = await run_browser_agent(genome, session_id, GAUNTLET_URL)
    result["mutation_level"] = mutation_level

    # Extract screenshots for judges (don't store in Weave result — too large)
    screenshots = result.get("screenshots", [])
    num_screenshots = len(screenshots)

    # Score with multimodal judges (screenshots + text)
    scores = compute_fitness(result, screenshots)

    return {
        "genome_id": genome.id,
        "generation": genome.generation,
        "genes": genome.gene_signature(),
        "mutation_history": genome.mutation_history,
        "success": result["success"],
        "steps_completed": result["steps_completed"],
        "total_actions": result["total_actions"],
        "duration": result["duration"],
        "scores": scores,
        "fitness": scores["composite"],
        "errors": result["errors"],
        "num_screenshots": num_screenshots,
        "replay_url": result.get("replay_url"),
    }


# ── Main Evolution Loop ───────────────────────────────────────────────────────

@weave.op()
async def run_darwinian_evolution() -> dict:
    """The main Darwinian evolution loop. Survival of the fittest browser agents.
    Now with multimodal Gemini 3 Flash judges that see actual browser screenshots."""

    print("=" * 70)
    print("DARWINIAN BROWSER EVOLUTION v2")
    print("  Multimodal Judges | Gemini 3 Flash | Screenshot-Grounded Scoring")
    print("=" * 70)
    print(f"   Population: {INITIAL_POPULATION} -> breed {CHILDREN_PER_GENERATION}/gen")
    print(f"   Survival Rate: {SURVIVAL_RATE:.0%} (harsh culling)")
    print(f"   Generations: {NUM_GENERATIONS}")
    print(f"   LLM Mutation: {LLM_MUTATION_RATE:.0%} (Gemini-powered)")
    print(f"   Agent Brain: gemini-2.5-flash")
    print(f"   Judge Model: gemini-3-flash-preview (multimodal)")
    print(f"   Browser: {'Browserbase (cloud + replay)' if USE_BROWSERBASE else 'Local Playwright'}")
    print(f"   Gauntlet URL: {GAUNTLET_URL}")
    print("=" * 70)

    all_results = []
    lineage = []
    extinction_log = []

    # ── Generation 0: Create initial population ──
    print(f"\n{'=' * 50}")
    print(f"  GENERATION 0 -- Primordial Soup")
    print(f"{'=' * 50}")

    population = create_initial_population(INITIAL_POPULATION)
    mutation_level = 0

    for gen in range(NUM_GENERATIONS):
        mutation_level = min(gen, 3)

        if gen > 0:
            print(f"\n{'=' * 50}")
            print(f"  GENERATION {gen} -- Mutation Level {mutation_level}")
            print(f"{'=' * 50}")

            survivor_pairs = [(g, r) for g, r in zip(population, gen_results) if g.alive]
            children = breed_children(
                survivor_pairs,
                CHILDREN_PER_GENERATION,
                gen,
                STANDARD_MUTATION_RATE,
                LLM_MUTATION_RATE,
            )
            population = [g for g in population if g.alive] + children
            print(f"  Population: {len(population)} organisms ({len(children)} new children)")

        print(f"\n  Evaluating {len(population)} organisms against The Gauntlet (level {mutation_level})...")
        print()

        gen_results = []
        for i, genome in enumerate(population):
            print(f"    [{i+1}/{len(population)}] Organism {genome.id[:8]}... ", end="", flush=True)
            result = await evaluate_genome(genome, mutation_level)
            gen_results.append(result)
            all_results.append(result)
            lineage.append(result)

            status = "PASS" if result["success"] else "FAIL"
            fitness_bar = "#" * int(result["fitness"] * 20) + "." * (20 - int(result["fitness"] * 20))
            screenshots_info = f"{result['num_screenshots']} screenshots"
            replay_info = f" | replay: {result['replay_url']}" if result.get("replay_url") else ""
            print(f"{status} fitness={result['fitness']:.1%} [{fitness_bar}] ({screenshots_info}{replay_info})")
            if result["errors"]:
                print(f"         Warning: {len(result['errors'])} error(s)")

        # ── CULLING ──
        survivors, dead = cull(population, gen_results, SURVIVAL_RATE)

        print(f"\n  CULLING -- {len(dead)} organisms go EXTINCT:")
        for genome, result in dead:
            print(f"    DEAD {genome.id[:8]} (fitness: {result['fitness']:.1%}) -- {genome.gene_signature()[:60]}...")
            extinction_log.append({
                "genome_id": genome.id,
                "generation": gen,
                "fitness": result["fitness"],
                "genes": genome.gene_signature(),
            })

        print(f"\n  SURVIVORS ({len(survivors)}):")
        for genome, result in survivors:
            badges = []
            if any("llm_evolve" in m for m in genome.mutation_history):
                badges.append("AI-MUTANT")
            if any("mutate(" in m for m in genome.mutation_history):
                badges.append("MUTANT")
            badge_str = " ".join(badges)
            print(f"    OK {genome.id[:8]} fitness={result['fitness']:.1%} {badge_str}")

        population = [g for g, _ in survivors]
        gen_results_for_breeding = [r for _, r in survivors]

        fitnesses = [r["fitness"] for _, r in survivors]
        all_fitnesses = [r["fitness"] for r in gen_results]
        print(f"\n  Gen {gen} Stats:")
        print(f"     Tested: {len(gen_results)} | Survived: {len(survivors)} | Extinct: {len(dead)}")
        print(f"     Best: {max(all_fitnesses):.1%} | Avg: {sum(all_fitnesses)/len(all_fitnesses):.1%} | Worst: {min(all_fitnesses):.1%}")
        print(f"     Survivor Avg: {sum(fitnesses)/len(fitnesses):.1%}")

        gen_results = gen_results_for_breeding

    # ── Final Champion ──
    champion_result = max(all_results, key=lambda r: r["fitness"])
    champion_genome = None
    for g in population:
        if g.id == champion_result["genome_id"]:
            champion_genome = g
            break

    print("\n" + "=" * 70)
    print("CHAMPION GENOME")
    print("=" * 70)
    print(f"  ID: {champion_result['genome_id']}")
    print(f"  Generation: {champion_result['generation']}")
    print(f"  Fitness: {champion_result['fitness']:.1%}")
    print(f"  Success: {champion_result['success']}")
    print(f"  Genes: {champion_result['genes']}")
    print(f"\n  Score Breakdown:")
    for scorer, score in champion_result["scores"].items():
        if scorer != "composite":
            weight = SCORER_WEIGHTS.get(scorer, 0)
            print(f"    {scorer}: {score:.1%} (weight: {weight:.0%})")
    print(f"    COMPOSITE: {champion_result['fitness']:.1%}")

    print(f"\n  Mutations: {champion_result.get('mutation_history', [])}")

    # ── Summary ──
    print("\n" + "=" * 70)
    print("EVOLUTION SUMMARY")
    print("=" * 70)
    print(f"  Total organisms evaluated: {len(all_results)}")
    print(f"  Total extinctions: {len(extinction_log)}")
    print(f"  Generations: {NUM_GENERATIONS}")
    print(f"  Champion fitness: {champion_result['fitness']:.1%}")
    print(f"  Judge model: gemini-3-flash-preview (multimodal, screenshot-grounded)")
    print(f"  Browser: {'Browserbase (cloud)' if USE_BROWSERBASE else 'Local Playwright'}")

    output = {
        "champion": champion_result,
        "all_results": all_results,
        "extinction_log": extinction_log,
        "config": {
            "initial_population": INITIAL_POPULATION,
            "children_per_generation": CHILDREN_PER_GENERATION,
            "survival_rate": SURVIVAL_RATE,
            "num_generations": NUM_GENERATIONS,
            "llm_mutation_rate": LLM_MUTATION_RATE,
            "judge_model": "gemini-3-flash-preview",
            "agent_model": "gemini-2.5-flash",
            "browser": "browserbase" if USE_BROWSERBASE else "local_playwright",
        },
    }

    with open("evolution_results.json", "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n  Results saved to evolution_results.json")
    return output


# ── Entry Point ───────────────────────────────────────────────────────────────

async def main():
    weave.init(WANDB_PROJECT)
    print("W&B Weave initialized")

    print("Starting The Gauntlet...")
    start_gauntlet(port=5000)
    print("Gauntlet running on http://127.0.0.1:5000")

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

    results = await run_darwinian_evolution()

    print("\nEvolution complete! Check W&B Weave for full traces.")
    return results


if __name__ == "__main__":
    asyncio.run(main())
