"""
Genetic Operators — Crossover, Mutation, and Gemini-powered LLM Mutation.

Adapts the proven roblox-game-strategist evolution engine for browser agents.
Key change: Gemini 2.5 Flash replaces Mistral for LLM mutations.
"""

import copy
import random
import os
import weave
from google import genai

from genome import Gene, Genome, GENE_POOLS, GENE_ORDER

_genai_client = None

def get_genai_client():
    global _genai_client
    if _genai_client is None:
        _genai_client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY", ""))
    return _genai_client


# ── Crossover ─────────────────────────────────────────────────────────────────

@weave.op()
def crossover(parent_a: Genome, parent_b: Genome, generation: int) -> Genome:
    """Single-point crossover: genes 0..k from parent_a, k+1..n from parent_b."""
    crossover_point = random.randint(1, len(parent_a.genes) - 1)
    child_genes = []
    for i in range(len(parent_a.genes)):
        if i < crossover_point:
            child_genes.append(copy.deepcopy(parent_a.genes[i]))
        else:
            child_genes.append(copy.deepcopy(parent_b.genes[i]))

    child = Genome(
        generation=generation,
        parent_ids=[parent_a.id, parent_b.id],
        genes=child_genes,
    )
    child.mutation_history.append(
        f"crossover({parent_a.id[:8]}×{parent_b.id[:8]} at {crossover_point})"
    )
    return child


# ── Standard Mutation ─────────────────────────────────────────────────────────

@weave.op()
def mutate(genome: Genome, mutation_rate: float = 0.3) -> Genome:
    """Replace each gene with a random alternative from its pool at mutation_rate."""
    mutated = copy.deepcopy(genome)
    for i, gene in enumerate(mutated.genes):
        if random.random() < mutation_rate:
            pool = GENE_POOLS.get(gene.category, [])
            alternatives = [g for g in pool if g.name != gene.name]
            if alternatives:
                new_gene = copy.deepcopy(random.choice(alternatives))
                mutated.mutation_history.append(f"mutate({gene.name}→{new_gene.name})")
                mutated.genes[i] = new_gene
    return mutated


# ── LLM Mutation (Gemini) ─────────────────────────────────────────────────────

@weave.op()
def llm_mutate_gene(gene: Gene) -> Gene:
    """Use Gemini to rewrite a gene into an improved version."""
    client = get_genai_client()

    prompt = f"""You are an expert at optimizing browser automation instructions.

CURRENT INSTRUCTION ({gene.category}):
{gene.content}

Create an IMPROVED version of this instruction that is:
- More specific and actionable for a browser automation agent
- Better at handling unexpected website layouts and elements
- More robust against popups, renamed buttons, and form changes
- Concise but complete

Return ONLY the improved instruction text, nothing else. Keep it under 200 words."""

    response = client.models.generate_content(model="gemini-3-flash-preview", contents=prompt)
    new_content = response.text.strip()

    return Gene(
        name=f"{gene.name}_evolved",
        content=new_content,
        category=gene.category,
    )


# ── Tournament Selection ──────────────────────────────────────────────────────

@weave.op()
def tournament_select(population: list[dict], tournament_size: int = 2) -> dict:
    """Select a parent via tournament: pick k random, return the fittest."""
    tournament = random.sample(population, min(tournament_size, len(population)))
    return max(tournament, key=lambda x: x["fitness"])


# ── Breed Children ────────────────────────────────────────────────────────────

@weave.op()
def breed_children(
    survivors: list[tuple],  # [(genome, result), ...]
    num_children: int,
    generation: int,
    mutation_rate: float = 0.3,
    llm_mutation_rate: float = 0.2,
) -> list[Genome]:
    """Create children through crossover + mutation from survivors."""
    children = []
    survivor_dicts = [{"genome": g, "fitness": r["fitness"]} for g, r in survivors]

    for _ in range(num_children):
        # Select two parents
        parent_a_dict = tournament_select(survivor_dicts)
        parent_b_dict = tournament_select(survivor_dicts)

        # Avoid self-mating
        attempts = 0
        while parent_a_dict["genome"].id == parent_b_dict["genome"].id and attempts < 5:
            parent_b_dict = tournament_select(survivor_dicts)
            attempts += 1

        parent_a = parent_a_dict["genome"]
        parent_b = parent_b_dict["genome"]

        # Crossover
        child = crossover(parent_a, parent_b, generation)

        # Standard mutation
        child = mutate(child, mutation_rate)

        # LLM mutation (rare, powerful)
        if random.random() < llm_mutation_rate:
            gene_idx = random.randint(0, len(child.genes) - 1)
            original_gene = child.genes[gene_idx]
            try:
                evolved_gene = llm_mutate_gene(original_gene)
                child.genes[gene_idx] = evolved_gene
                child.mutation_history.append(
                    f"llm_evolve({original_gene.name}→{evolved_gene.name})"
                )
                print(f"    AI-mutated: {original_gene.name} -> {evolved_gene.name}")
            except Exception as e:
                print(f"    Warning: LLM mutation failed: {e}")

        children.append(child)

    return children


# ── Culling ───────────────────────────────────────────────────────────────────

def cull(
    population: list[Genome],
    results: list[dict],
    survival_rate: float = 0.5,
) -> tuple[list[tuple], list[tuple]]:
    """Kill the weak. Return (survivors, dead) as lists of (genome, result)."""
    paired = list(zip(population, results))
    paired.sort(key=lambda x: x[1]["fitness"], reverse=True)

    num_survivors = max(2, int(len(paired) * survival_rate))
    survivors = paired[:num_survivors]
    dead = paired[num_survivors:]

    # Mark dead genomes
    for genome, _ in dead:
        genome.alive = False

    return survivors, dead
