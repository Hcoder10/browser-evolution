# Browser Evolution

**Darwinian natural selection breeds AI browser agents that survive hostile websites.**

Built for the [Gemini/DeepMind BrowserUse Competition](https://wandb.ai/carpediemhari-n-a/browser-evolution/weave).

> Can evolution teach an AI to avoid traps, dismiss popups, ignore decoy buttons, and complete checkout on a website that's actively fighting it?

## The Idea

Most browser agents use hand-written prompts. When they encounter a hostile website (misleading buttons, popup overlays, fake success pages), they fail. What if we evolved the prompt instead of writing it?

**Browser Evolution** breeds browser agent prompts through Darwinian natural selection:
1. **Spawn** a population of random 6-gene browser agent genomes
2. **Evaluate** each organism against "The Gauntlet" — a hostile e-commerce site that mutates
3. **Judge** performance using multimodal Gemini 3 Flash (sees actual browser screenshots)
4. **Cull** the weak — bottom 50% go extinct
5. **Breed** survivors via crossover + mutation + LLM-powered gene evolution
6. **Repeat** as the website gets harder each generation

## Results

### Head-to-Head: Naive vs Evolved Prompt

Both agents face the **same** Level 3 Nightmare Gauntlet with a 25-step action budget.

| Metric | Naive Prompt | Evolved Genome | Delta |
|---|---|---|---|
| **Task Completion** | 50% | 100% | +50% |
| **Efficiency** | 50% | 80% | +30% |
| **Resilience** (LLM Judge) | 60% | 100% | +40% |
| **Strategy** (LLM Judge) | 30% | 90% | +60% |
| **Composite Fitness** | **47.5% FAIL** | **94.5% PASS** | **+47%** |

The naive agent clicked trap buttons, got stuck on fake success pages, and ran out of steps. The evolved agent dismissed the popup, avoided all 4 trap buttons, found the tiny grey links, handled misleading form labels, and completed checkout in 16 actions.

### Live Demo

- **Gauntlet (hostile website):** https://browser-evolution.vercel.app
- **Demo Dashboard:** https://browser-evolution.vercel.app/demo
- **Agent API:** https://browser-evolution-agent-production.up.railway.app
- **W&B Weave Traces:** https://wandb.ai/carpediemhari-n-a/browser-evolution/weave

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Evolution Loop                        │
│                                                         │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐          │
│  │  Spawn   │───>│ Evaluate │───>│   Cull   │          │
│  │ Genomes  │    │ vs Gaunt │    │ Weakest  │          │
│  └──────────┘    └──────────┘    └──────────┘          │
│       ^                               │                 │
│       │          ┌──────────┐         │                 │
│       └──────────│  Breed   │<────────┘                 │
│                  │ Children │                           │
│                  └──────────┘                           │
│                       │                                 │
│              ┌────────┼────────┐                        │
│              ▼        ▼        ▼                        │
│          Crossover  Mutation  LLM Mutation               │
│          (swap      (random   (Gemini rewrites          │
│           genes)     gene)     gene content)             │
└─────────────────────────────────────────────────────────┘

┌─────────────────────┐     ┌─────────────────────────────┐
│   The Gauntlet      │     │   Fitness Judges             │
│   (Flask website)   │     │                              │
│                     │     │  Task Completion (35%)       │
│  Level 0: Normal    │     │  - Heuristic checkpoint      │
│  Level 1: Renamed   │     │                              │
│  Level 2: Scrambled │     │  Efficiency (15%)            │
│  Level 3: Nightmare │     │  - Action count penalty      │
│   - Trap buttons    │     │                              │
│   - Fake success    │     │  Resilience (25%)            │
│   - Wrong labels    │     │  - Gemini 3 Flash + screenshots│
│   - Popup overlays  │     │                              │
└─────────────────────┘     │  Strategy (25%)              │
                            │  - Gemini 3 Flash + screenshots│
                            └─────────────────────────────┘
```

## The Genome — 6 Evolvable Genes

Each browser agent organism has a 6-gene genome. Each gene is drawn from a pool of 3 variants = **729 possible combinations**.

| Gene | What it controls | Example variants |
|---|---|---|
| **Navigation** | How the agent plans multi-step flows | Sequential, Goal Decomposition, Observe First |
| **Element Selection** | How it picks which element to click | Text Match, Semantic, Structural |
| **Error Recovery** | What it does when stuck | Retry, Diagnostic, Adaptive |
| **Distraction Handling** | How it deals with popups/overlays | Dismiss Fast, Assess Then Dismiss, Systematic Clear |
| **Form Interaction** | How it fills forms | Label Match, Placeholder Match, Contextual |
| **Verification** | How it confirms task completion | URL Check, Content Check, Defensive |

### Genetic Operators

- **Crossover:** Single-point crossover swaps genes between two parents
- **Standard Mutation (30%):** Randomly replaces a gene with another variant from its pool
- **LLM Mutation (20%):** Gemini 3 Flash **rewrites** a gene's content to be more robust — this is where evolution gets creative

## The Gauntlet — A Website That Fights Back

The Gauntlet is a hostile e-commerce site that gets harder as evolution progresses:

| Level | Difficulty | Features |
|---|---|---|
| 0 | Normal | Standard buttons, clean forms, no distractions |
| 1 | Renamed | Buttons renamed ("Buy Now" → "Continue"), 1 popup |
| 2 | Scrambled | Reversed form field order, no labels, cookie banner + popup |
| 3 | Nightmare | 4 trap buttons (large, blue, lead to dead ends), real buttons hidden as tiny grey links, misleading form labels ("Phone Number" = email field), fake success page (PAYMENT_PENDING), aggressive popup overlay |

## Fitness Scoring

Each organism is scored by 4 judges with weighted contributions:

| Scorer | Weight | Type | Description |
|---|---|---|---|
| Task Completion | 35% | Heuristic | Binary completion + partial credit for progress checkpoints |
| Efficiency | 15% | Heuristic | Fewer actions = better. Penalizes flailing (>30 actions) |
| Resilience | 25% | **Multimodal LLM** | Gemini 3 Flash reviews browser screenshots to assess obstacle handling |
| Strategy | 25% | **Multimodal LLM** | Gemini 3 Flash reviews screenshots to assess strategic coherence |

The LLM judges receive **actual screenshots** from the browser session via `types.Part.from_bytes()` for grounded, visual evaluation.

## Tech Stack

| Component | Technology |
|---|---|
| Agent Brain | Gemini 2.5 Flash (via [browser-use](https://github.com/browser-use/browser-use)) |
| LLM Judges | Gemini 3 Flash Preview (multimodal, screenshot-grounded) |
| LLM Mutation | Gemini 3 Flash Preview (rewrites gene content) |
| Evolution Engine | Custom Darwinian system (Python) |
| Hostile Website | Flask (4 mutation levels) |
| Browser | Playwright (local) or Browserbase (cloud with video replay) |
| Observability | [W&B Weave](https://wandb.ai/carpediemhari-n-a/browser-evolution/weave) — full trace lineage for every organism |
| Deployment | Vercel (gauntlet) + Railway (agent API with Docker/Playwright) |

## Project Structure

```
browser-evolution/
├── genome.py          # 6-gene genome system (729 combinations)
├── evolution.py       # Genetic operators: crossover, mutation, LLM mutation
├── scorers.py         # 4 fitness scorers (2 heuristic + 2 multimodal LLM)
├── gauntlet.py        # The Gauntlet hostile website (Flask, 4 levels)
├── evolve_main.py     # Main evolution loop
├── demo.py            # Head-to-head demo (naive vs evolved)
├── agent_api.py       # Railway agent API (POST /run)
├── Dockerfile         # Railway Docker config (Python + Playwright + Chromium)
├── api/index.py       # Vercel entry point
├── vercel.json        # Vercel config
├── requirements.txt        # Vercel dependencies (Flask only)
├── requirements-dev.txt    # Local development (all dependencies)
└── requirements-agent.txt  # Railway agent dependencies
```

## Quick Start

### Prerequisites

- Python 3.12+
- [Google AI API key](https://aistudio.google.com/apikey) (Gemini)
- [W&B account](https://wandb.ai) (for Weave tracing)

### Setup

```bash
git clone https://github.com/Hcoder10/browser-evolution.git
cd browser-evolution

python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

pip install -r requirements-dev.txt
playwright install chromium
```

Create a `.env` file:

```env
GOOGLE_API_KEY=your_gemini_api_key
WANDB_API_KEY=your_wandb_key
WANDB_PROJECT=browser-evolution

# Optional: Browserbase for cloud browser + video replay
BROWSERBASE_API_KEY=your_key
BROWSERBASE_PROJECT_ID=your_project_id
```

### Run Evolution

```bash
python evolve_main.py
```

This will:
1. Start The Gauntlet locally on port 5000
2. Spawn 4 random genomes
3. Run 4 generations of evolution (population grows via breeding)
4. Cull the weakest 50% each generation
5. Output the champion genome and save results

### Run Head-to-Head Demo

```bash
python demo.py
```

Runs a naive "complete the checkout" prompt vs the evolved 6-gene genome on Level 3 Nightmare mode, side by side.

### Deploy

**Gauntlet (Vercel):**
```bash
vercel --prod
```

**Agent API (Railway):**
```bash
railway up
```

Set Railway env vars: `GOOGLE_API_KEY`, `WANDB_API_KEY`, `WANDB_PROJECT`.

## How It Works — Key Insights

1. **Evolution finds what humans miss.** The evolved genome learned that "big blue buttons are ALL TRAPS" and to look for "tiny grey underlined text links" — a pattern no human would think to write in a prompt.

2. **LLM mutation is the secret weapon.** At a 20% rate, Gemini 3 Flash rewrites gene content to be more robust. This introduces creative adaptations that random gene swapping can't achieve.

3. **Multimodal judging grounds evaluation in reality.** Text-only judges can be fooled by action logs. Screenshot-grounded Gemini 3 Flash judges actually see what the agent saw and whether it handled it well.

4. **The Gauntlet co-evolves with agents.** As generations progress, the website gets harder (Level 0 → 3). This arms race prevents agents from overfitting to easy conditions.

## License

MIT
