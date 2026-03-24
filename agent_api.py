"""
Browser Agent API — Railway deployment.

Runs browser-use agents with Playwright against a remote Gauntlet URL.
POST /run with a prompt to test against the hostile website.
"""

import asyncio
import os
import time
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
WANDB_PROJECT = os.environ.get("WANDB_PROJECT", "browser-evolution")
DEFAULT_GAUNTLET_URL = os.environ.get("GAUNTLET_URL", "https://browser-evolution.vercel.app")

# Initialize Weave (optional — only if WANDB_API_KEY is set)
try:
    import weave
    if os.environ.get("WANDB_API_KEY"):
        weave.init(WANDB_PROJECT)
except Exception:
    pass


async def _run_agent(prompt: str, gauntlet_url: str, level: int, max_steps: int, session_id: str = None) -> dict:
    """Run a browser-use agent against the gauntlet."""
    from browser_use import Agent, Browser
    from browser_use.llm import ChatGoogle

    if not session_id:
        session_id = f"api-{int(time.time())}"

    task = f"""{prompt}

YOUR TASK:
Navigate to {gauntlet_url}/?sid={session_id}&level={level} and complete the entire checkout flow:
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
    result = {
        "session_id": session_id,
        "success": False,
        "steps_completed": [],
        "total_actions": 0,
        "errors": [],
        "duration": 0,
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

        history = await agent.run(max_steps=max_steps)

        action_names = history.action_names()
        errors = history.errors()

        result["total_actions"] = len(action_names) if action_names else 0
        result["errors"] = [str(e) for e in (errors or []) if e]

        # Check via Gauntlet API
        try:
            status_resp = requests.get(f"{gauntlet_url}/api/status/{session_id}", timeout=5)
            status = status_resp.json()
            result["steps_completed"] = status.get("steps", [])
            result["success"] = status.get("success", False)
        except Exception:
            final_result = history.final_result()
            if final_result and "ORDER_CONFIRMED" in str(final_result):
                result["success"] = True

    except Exception as e:
        result["errors"].append(str(e))

    finally:
        try:
            if browser and hasattr(browser, 'close'):
                await browser.close()
        except Exception:
            pass

    result["duration"] = round(time.time() - start_time, 1)
    return result


@app.route("/")
def index():
    return jsonify({
        "service": "browser-evolution-agent",
        "endpoints": {
            "POST /run": "Run a browser agent against the gauntlet",
        },
        "params": {
            "prompt": "The agent prompt (required)",
            "gauntlet_url": f"Gauntlet URL (default: {DEFAULT_GAUNTLET_URL})",
            "level": "Gauntlet difficulty 0-3 (default: 3)",
            "max_steps": "Max agent steps (default: 25)",
        },
    })


@app.route("/run", methods=["POST"])
def run_agent():
    data = request.get_json(force=True)
    prompt = data.get("prompt", "")
    if not prompt:
        return jsonify({"error": "prompt is required"}), 400

    gauntlet_url = data.get("gauntlet_url", DEFAULT_GAUNTLET_URL)
    level = int(data.get("level", 3))
    max_steps = int(data.get("max_steps", 25))
    session_id = data.get("session_id", None)

    result = asyncio.run(_run_agent(prompt, gauntlet_url, level, max_steps, session_id))
    return jsonify(result)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, threaded=True)
