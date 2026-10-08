# Skill Development Workflows: Default vs. Topic-Specific

## Anthropic's Official Skill Creator vs. Better Skill Creator

### Similarities

Both approaches share a common foundation:

- **Outcome-focused development** — start with the user's actual need, not implementation details
- **Test-driven iteration** — use realistic prompts to validate behavior
- **Baseline comparison** — measure improvement against a control (no-skill or previous version)
- **Trigger evaluation** — recognize that descriptions can undertrigger or overtrigger
- **Incremental refinement** — multiple evaluation rounds, not a single pass
- **Measurable evidence** — prefer data over assumption

### Relationship

**Anthropic's official skill-creator** provides the essential workflow:
- Draft → Test → Evaluate → Compare → Optimize

**Better Skill Creator** extends this by:
- Adding explicit design analysis *before* building
- Separating triggering from quality as distinct evaluation problems
- Incorporating independent multi-agent review
- Treating model behavior as reusable development knowledge
- Enforcing rigorous quality gates across structure, behavior, triggers, and review

Think of it as: Anthropic's tool is the **optimization loop**; Better Skill Creator is the **complete development system** around it.

---

## Comparison Table

| Aspect | Anthropic's Skill Creator | Better Skill Creator |
|--------|---------------------------|----------------------|
| **Workflow Start** | Existing draft or literal request | Design analysis: scope multiple interpretations first |
| **Scope Definition** | Implied from description | Explicit: outcome, boundaries, authorization, entailments |
| **Instructions** | Written early, iterated on | Written after design consensus |
| **Triggering Eval** | Yes, but part of description optimization | Separate from quality; includes positive + negative cases |
| **Model Behavior** | Evaluated per skill, per run | Treated as reusable knowledge; compared to baselines |
| **Quality Gates** | Structural check + lint | Structural + behavioral + trigger + review gates |
| **Review** | Author's own judgment | Independent multi-agent review (outcome, scope, architecture, completion) |
| **Authorization** | Not explicitly tracked | Explicit: required+authorized, required+unauthorized, optional, out-of-scope |
| **Variance Testing** | Supported; single eval possible | Emphasized: repeated runs to get trigger rates, not binary yes/no |
| **Finish Criteria** | "Instructions look good" | "Independent reviewers confirm evidence of completion" |
| **Failure Mode Risk** | Describe → build → assume it works | Design → build → measure → review → iterate until gates pass |

---

## Upside / Downside

### Anthropic's Official Skill Creator

**Upside**
- Lightweight; good for simple, low-risk skills
- Fast feedback loop for description tuning
- Minimal setup; start immediately with an idea
- Excellent for prototyping and exploring triggering behavior

**Downside**
- No explicit scope/boundary definition; easy to over- or under-scope
- Author as sole reviewer; confirmation bias risk
- Triggering and quality conflated in one optimization loop
- No model behavior baselines; rediscover the same behavior every iteration
- Authorization and permission gaps can be missed
- Difficult to apply rigorously to high-stakes or complex skills

### Better Skill Creator

**Upside**
- Explicit design phase catches scope/boundary mismatches early
- Independent review reduces blind spots
- Triggering and quality as separate, measurable problems
- Model behavior baselines save time and reduce rework
- Authorization explicitly tracked; security and permission gaps caught
- Quality gates enforce reproducibility and rigor
- Scales to complex skills and multi-skill systems
- Evidence-based rather than assumption-based

**Downside**
- Higher overhead for very simple skills
- Requires more explicit up-front thinking before building
- Independent review takes additional time/coordination
- Model baseline collection requires investment across multiple skill projects
- More structure and process; less exploratory freedom
- Best ROI on substantial, reusable, or high-risk skills

---

## When to Use Each

### Use Anthropic's Official Skill Creator for:
- Quick prototypes and exploration
- Low-risk, narrow-scope skills
- One-off solutions to a specific task
- Learning the tool and skill concepts

### Use Better Skill Creator for:
- Production skills that will be distributed or reused
- Complex skills with multiple interpretations
- High-risk actions (file modification, external system changes)
- Teams or organizations building skill libraries
- Skills that need to work reliably across multiple models
- Situations where evidence of completion is required

### Use Both for:
- Substantial skills: prototype with Anthropic's tool, then apply Better Skill Creator's rigor for production release
- Team handoff: author prototypes with lighter workflow, independent review via Better Skill Creator gates
