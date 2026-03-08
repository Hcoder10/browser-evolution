"""
Browser Agent Genome — 6 evolvable gene slots for browser navigation.

Each gene controls a different aspect of how the agent interacts with websites.
Natural selection finds the optimal combination across hostile environments.
"""

import copy
import random
import hashlib
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Gene:
    name: str
    content: str
    category: str


@dataclass
class Genome:
    id: str = ""
    generation: int = 0
    parent_ids: list[str] = field(default_factory=list)
    genes: list[Gene] = field(default_factory=list)
    mutation_history: list[str] = field(default_factory=list)
    fitness: float = 0.0
    alive: bool = True

    def __post_init__(self):
        if not self.id:
            self.id = hashlib.md5(f"{time.time()}-{random.random()}".encode()).hexdigest()[:8]

    def assemble_prompt(self) -> str:
        """Assemble all genes into a single system prompt."""
        sections = []
        for gene in self.genes:
            sections.append(f"## {gene.category.upper()}\n{gene.content}")
        return "\n\n".join(sections)

    def gene_signature(self) -> str:
        return " | ".join(f"{g.category}={g.name}" for g in self.genes)


# ══════════════════════════════════════════════════════════════════════════════
# GENE POOL 1: NAVIGATION STRATEGY
# How the agent plans and sequences multi-step browser actions
# ══════════════════════════════════════════════════════════════════════════════

NAVIGATION_GENES = [
    Gene(
        name="nav_sequential",
        category="navigation",
        content=(
            "Navigate step by step through the website. Complete one page fully before "
            "moving to the next. On each page: (1) identify what action is needed, "
            "(2) find the correct element, (3) interact with it, (4) wait for the page "
            "to load, (5) confirm you're on the expected next page."
        ),
    ),
    Gene(
        name="nav_goal_decompose",
        category="navigation",
        content=(
            "Break the overall task into sub-goals. For a checkout flow, your sub-goals are: "
            "1) Get the product into the cart, 2) Navigate to checkout, 3) Fill shipping info, "
            "4) Complete the order. For each sub-goal, scan the page for the most direct path. "
            "If the expected element isn't obvious, look for alternative paths (links in nav, "
            "footer links, breadcrumbs, sidebar)."
        ),
    ),
    Gene(
        name="nav_observe_first",
        category="navigation",
        content=(
            "Before taking ANY action on a new page, do a full scan: read all headings, "
            "buttons, links, and form elements. Build a mental map of the page structure. "
            "Identify the primary action (the one that advances your goal) vs secondary actions "
            "(distractions, alternatives). Only then click the primary action. Never rush."
        ),
    ),
]

# ══════════════════════════════════════════════════════════════════════════════
# GENE POOL 2: ELEMENT SELECTION
# How the agent identifies and chooses which elements to interact with
# ══════════════════════════════════════════════════════════════════════════════

ELEMENT_GENES = [
    Gene(
        name="elem_text_match",
        category="element_selection",
        content=(
            "Find interactive elements by their visible text. Look for buttons and links "
            "whose text matches your goal. For 'add to cart', look for buttons saying 'Add to Cart', "
            "'Buy', 'Purchase', 'Get', or similar commerce terms. For 'checkout', look for "
            "'Checkout', 'Proceed', 'Continue', 'Next', 'Pay'. Match intent, not exact words."
        ),
    ),
    Gene(
        name="elem_semantic",
        category="element_selection",
        content=(
            "Use semantic understanding to find elements. Don't just match text — understand "
            "the PURPOSE of each element from its context. A button inside a product card that's "
            "near a price is likely 'add to cart' even if it says something unusual. "
            "The most prominent button on a cart page is likely 'checkout'. Use visual hierarchy: "
            "primary actions are usually larger, more colorful, or more prominently placed."
        ),
    ),
    Gene(
        name="elem_structural",
        category="element_selection",
        content=(
            "Identify elements by page structure. The main call-to-action is typically: "
            "the last/rightmost button in a button group, the most visually distinct element, "
            "or the element closest to the price/total. For forms, look for submit buttons at "
            "the bottom. Ignore elements in headers, footers, and sidebars unless the main "
            "content area has no viable options."
        ),
    ),
]

# ══════════════════════════════════════════════════════════════════════════════
# GENE POOL 3: ERROR RECOVERY
# What the agent does when something goes wrong
# ══════════════════════════════════════════════════════════════════════════════

RECOVERY_GENES = [
    Gene(
        name="recovery_retry",
        category="error_recovery",
        content=(
            "If an action fails or doesn't produce the expected result: "
            "1) Try the same element again (it may not have loaded). "
            "2) If it fails twice, look for an alternative element with similar purpose. "
            "3) If the page seems stuck, try scrolling to reveal hidden elements. "
            "4) As a last resort, go back and try the previous step again."
        ),
    ),
    Gene(
        name="recovery_diagnostic",
        category="error_recovery",
        content=(
            "When something unexpected happens, diagnose before acting: "
            "- Wrong page? Check the URL and page title. Navigate back if needed. "
            "- Element not found? The page may have a different layout. Scroll and look for "
            "  alternatives with similar meaning. "
            "- Popup blocking? Look for close/dismiss buttons (X, 'Close', 'No thanks', "
            "  'Dismiss', clicking outside). Clear the blocker first, then retry. "
            "- Form error? Read error messages and correct the specific field."
        ),
    ),
    Gene(
        name="recovery_adaptive",
        category="error_recovery",
        content=(
            "Maintain awareness of your progress. If you've been on the same page for more "
            "than 2 actions without advancing, switch strategies: "
            "- If clicking buttons doesn't work, try links or text elements. "
            "- If the expected flow doesn't exist, look for unconventional paths. "
            "- If forms won't submit, check for hidden required fields or unchecked boxes. "
            "Never repeat the same failing action more than twice."
        ),
    ),
]

# ══════════════════════════════════════════════════════════════════════════════
# GENE POOL 4: DISTRACTION HANDLING
# How the agent deals with popups, banners, overlays, and decoys
# ══════════════════════════════════════════════════════════════════════════════

DISTRACTION_GENES = [
    Gene(
        name="distract_dismiss_fast",
        category="distraction_handling",
        content=(
            "Immediately dismiss any popup, modal, overlay, or banner that appears. "
            "Look for: X buttons, 'Close', 'No thanks', 'Dismiss', 'Maybe Later', "
            "'Not Now', 'Skip'. Click the dismiss option and return to your main task. "
            "Do not read popup content. Do not engage with offers. Speed is key."
        ),
    ),
    Gene(
        name="distract_assess_then_dismiss",
        category="distraction_handling",
        content=(
            "When a popup or overlay appears: (1) Quickly assess if it's blocking your task "
            "(does it cover the main content?). (2) If blocking, find the dismiss button — look "
            "for 'X', 'Close', negative options like 'No thanks' or 'Maybe Later'. (3) If not "
            "blocking, ignore it and continue. (4) Watch for cookie banners at the top/bottom "
            "of the page — these often have an 'Accept' button that must be clicked."
        ),
    ),
    Gene(
        name="distract_systematic_clear",
        category="distraction_handling",
        content=(
            "Before attempting any action on a new page, systematically check for and clear "
            "ALL overlays and distractions: "
            "1) Check for modals/popups (fixed position overlays) → dismiss them "
            "2) Check for cookie banners (top or bottom bars) → accept/dismiss "
            "3) Check for chat widgets (bottom-right corner) → minimize/close "
            "4) Check for notification bars (top of page) → dismiss "
            "Only after the page is clear, proceed with your actual task. "
            "For each distraction, prefer the most negative/dismissive option available."
        ),
    ),
]

# ══════════════════════════════════════════════════════════════════════════════
# GENE POOL 5: FORM INTERACTION
# How the agent fills out forms and handles input fields
# ══════════════════════════════════════════════════════════════════════════════

FORM_GENES = [
    Gene(
        name="form_label_match",
        category="form_interaction",
        content=(
            "Fill forms by matching field labels to appropriate data: "
            "- Name fields → 'John Doe' (first: 'John', last: 'Doe') "
            "- Email → 'john.doe@example.com' "
            "- Address → '123 Main Street' "
            "- City → 'San Francisco' "
            "- State → 'CA' "
            "- Zip/Postal → '94102' "
            "Read each field's label or placeholder text to determine what data to enter."
        ),
    ),
    Gene(
        name="form_placeholder_match",
        category="form_interaction",
        content=(
            "When filling forms, pay attention to placeholder text and field context, not "
            "just labels. Fields may have no labels but have placeholder hints. "
            "Use these standard test values: "
            "- Any name field → 'Jane Smith' "
            "- Email → 'jane.smith@test.com' "
            "- Street/Address → '456 Oak Avenue' "
            "- City → 'Austin' "
            "- State/Province → 'TX' "
            "- Zip/Postal code → '73301' "
            "Fill ALL visible input fields before submitting. Check for hidden required fields."
        ),
    ),
    Gene(
        name="form_contextual",
        category="form_interaction",
        content=(
            "Analyze the form holistically before filling: "
            "1) Count all input fields. 2) Identify which are required. "
            "3) Determine field purpose from ANY available signal: label, placeholder, "
            "   name attribute, position, input type, surrounding text. "
            "4) Use realistic test data: 'Alex Johnson', 'alex@example.com', "
            "   '789 Elm Boulevard', 'Portland', 'OR', '97201'. "
            "5) After filling all fields, verify no field is empty before submitting. "
            "6) If submission fails, look for fields you missed or error messages."
        ),
    ),
]

# ══════════════════════════════════════════════════════════════════════════════
# GENE POOL 6: VERIFICATION
# How the agent confirms task completion
# ══════════════════════════════════════════════════════════════════════════════

VERIFICATION_GENES = [
    Gene(
        name="verify_url",
        category="verification",
        content=(
            "After each major action, verify progress by checking: "
            "- Did the URL change to the expected next page? "
            "- Cart page URL should contain 'cart'. Checkout should contain 'checkout'. "
            "- Success/confirmation should contain 'success', 'confirm', or 'thank'. "
            "If the URL didn't change after clicking, the action may have failed."
        ),
    ),
    Gene(
        name="verify_content",
        category="verification",
        content=(
            "Verify task completion by looking for confirmation signals on the page: "
            "- After adding to cart: look for cart icon update, 'Added!' message, or cart count "
            "- After checkout: look for 'Order confirmed', 'Thank you', order number "
            "- Success indicators: green checkmarks, confirmation numbers, 'ORDER_CONFIRMED' text "
            "The task is ONLY complete when you see explicit confirmation, not just when you "
            "click the final button."
        ),
    ),
    Gene(
        name="verify_defensive",
        category="verification",
        content=(
            "Trust nothing. After every action: "
            "1) Check if the page actually changed (don't assume click worked) "
            "2) Look for error messages that might have appeared "
            "3) Verify you're on the right page (read the heading) "
            "4) Confirm the action registered (cart updated, form accepted) "
            "The task is complete ONLY when you see 'ORDER_CONFIRMED' or similar "
            "explicit success message. If in doubt, it didn't work."
        ),
    ),
]

# ══════════════════════════════════════════════════════════════════════════════
# GENE POOLS REGISTRY
# ══════════════════════════════════════════════════════════════════════════════

GENE_POOLS = {
    "navigation": NAVIGATION_GENES,
    "element_selection": ELEMENT_GENES,
    "error_recovery": RECOVERY_GENES,
    "distraction_handling": DISTRACTION_GENES,
    "form_interaction": FORM_GENES,
    "verification": VERIFICATION_GENES,
}

GENE_ORDER = ["navigation", "element_selection", "error_recovery", "distraction_handling", "form_interaction", "verification"]


def create_random_genome(generation: int = 0) -> Genome:
    """Create a genome with one random gene from each pool."""
    genes = []
    for category in GENE_ORDER:
        pool = GENE_POOLS[category]
        genes.append(copy.deepcopy(random.choice(pool)))
    return Genome(generation=generation, genes=genes)


def create_initial_population(size: int = 4) -> list[Genome]:
    """Create a diverse initial population."""
    population = []
    for _ in range(size):
        genome = create_random_genome(generation=0)
        population.append(genome)
    return population


# Total possible combinations: 3×3×3×3×3×3 = 729 unique genomes
TOTAL_COMBINATIONS = 1
for pool in GENE_POOLS.values():
    TOTAL_COMBINATIONS *= len(pool)
