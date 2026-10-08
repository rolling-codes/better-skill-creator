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

**Anthropic's official skill ecosystem** (https://github.com/anthropics/skills) provides the essential workflow:
- Draft → Test → Evaluate → Compare → Optimize

**Better Skill Creator** extends this by:
- Adding explicit design analysis *before* building
- Separating triggering from quality as distinct evaluation problems
- Incorporating independent multi-agent review
- Treating model behavior as reusable development knowledge
- Enforcing rigorous quality gates across structure, behavior, triggers, and review
- Catching common failure modes early (template YAML errors, contradictory guidance, security gaps)

Think of it as: Anthropic's tool is the **optimization loop**; Better Skill Creator is the **complete development system** around it.

---

## Comparison Table

| Aspect | Anthropic's Skill Ecosystem | Better Skill Creator |
|--------|---------------------------|----------------------|
| **Workflow Start** | Existing draft or literal request | Design analysis: scope multiple interpretations first |
| **Scope Definition** | Implied from description | Explicit: outcome, boundaries, authorization, entailments |
| **Instructions** | Written early, iterated on | Written after design consensus |
| **Triggering Eval** | Yes, but part of description optimization | Separate from quality; includes positive + negative cases |
| **Model Behavior** | Evaluated per skill, per run | Treated as reusable knowledge; compared to baselines |
| **Quality Gates** | Structural check + lint | Structural + behavioral + trigger + review + security gates |
| **Review** | Author's own judgment | Independent multi-agent review (outcome, scope, architecture, completion) |
| **Authorization** | Not explicitly tracked | Explicit: required+authorized, required+unauthorized, optional, out-of-scope |
| **Variance Testing** | Supported; single eval possible | Emphasized: repeated runs to get trigger rates, not binary yes/no |
| **Finish Criteria** | "Instructions look good" | "Independent reviewers confirm evidence of completion" |
| **Template Validation** | Basic frontmatter check | Strict YAML parsing; catches list/string type mismatches |
| **Guidance Coherence** | Not checked systematically | Reference wiring validation ensures docs align with guidance |
| **Security Review** | Eval viewer has known issues (1982, 1961) | Built-in hardening for script breakout, DNS rebinding, CSRF |
| **Failure Mode Risk** | Describe → build → assume it works | Design → build → measure → review → iterate until gates pass |

---

## Known Issues Addressed

Better Skill Creator directly addresses several open issues in the official Anthropic skills repo:

1. **Template generation errors** (#1957)  
   - Official: `init_skill.py` emits `description: [TODO: ...]` which YAML parses as a list, then rejected  
   - Better Skill Creator: `quick_validate.py` catches type mismatches in frontmatter at gate time

2. **Design contradictions** (#1959)  
   - Official: pptx, web-artifacts-builder, pdf have conflicting design defaults  
   - Better Skill Creator: Design analysis phase explicitly identifies and resolves contradictions before building

3. **Unclear imperative rules** (#1960)  
   - Official: pdf/forms.md uses unconditional "zoom pass" and "shouted" ordering rules  
   - Better Skill Creator: Linter flags unmeasurable, imperative prose; reviewers catch vague directives

4. **Guidance misalignment** (#1967)  
   - Official: mcp-builder advises "concise" descriptions against Anthropic's tool-use guidance  
   - Better Skill Creator: Reference wiring validation and independent review catch guidance drift

5. **Security vulnerabilities** (#1961, #1982)  
   - Official: Eval viewer has script breakout, DNS rebinding, cross-origin POST issues  
   - Better Skill Creator: Hardened eval viewer with security gate; independent review for auth/permission issues

6. **Silent skill failures** (related to #1957)  
   - Official: DSH silently drops skills with invalid frontmatter  
   - Better Skill Creator: Packaging gate fails closed; diagnostics surface all issues before shipping

---

## Upside / Downside

### Anthropic's Official Skill Ecosystem

**Upside**
- Lightweight; good for simple, low-risk skills
- Fast feedback loop for description tuning
- Minimal setup; start immediately with an idea
- Excellent for prototyping and exploring triggering behavior
- Large public community and examples

**Downside**
- No explicit scope/boundary definition; easy to over- or under-scope
- Author as sole reviewer; confirmation bias risk
- Triggering and quality conflated in one optimization loop
- No model behavior baselines; rediscover the same behavior every iteration
- Authorization and permission gaps can be missed
- Template validation does not catch YAML type errors
- Guidance can drift from best practices without systematic checks
- Security issues in eval viewer require manual patches
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
- Catches common failure modes (YAML errors, guidance misalignment, security gaps)
- Hardened eval viewer with built-in security gates
- Reference wiring validation ensures docs consistency

**Downside**
- Higher overhead for very simple skills
- Requires more explicit up-front thinking before building
- Independent review takes additional time/coordination
- Model baseline collection requires investment across multiple skill projects
- More structure and process; less exploratory freedom
- Best ROI on substantial, reusable, or high-risk skills
- Steeper learning curve for teams new to design-first development

---

## When to Use Each

### Use Anthropic's Official Ecosystem for:
- Quick prototypes and exploration
- Low-risk, narrow-scope skills
- One-off solutions to a specific task
- Learning the tool and skill concepts
- Skills that will undergo internal review separately

### Use Better Skill Creator for:
- Production skills that will be distributed or reused
- Complex skills with multiple interpretations
- High-risk actions (file modification, external system changes, security-sensitive operations)
- Teams or organizations building skill libraries
- Skills that need to work reliably across multiple models
- Situations where evidence of completion is required
- Skills with authorization or permission boundaries
- Addressing the known issues in the official ecosystem

### Use Both for:
- Substantial skills: prototype with Anthropic's tool, then apply Better Skill Creator's rigor for production release
- Team handoff: author prototypes with lighter workflow, independent review via Better Skill Creator gates
- Security-sensitive work: use Anthropic's ecosystem for exploration, Better Skill Creator's gates for hardening

---

## Upstream Contribution Opportunities

Better Skill Creator could contribute upstream fixes to Anthropic's skills repo:

1. **YAML validation** — stricter frontmatter parsing to catch list/string mismatches
2. **Template generation** — fix `init_skill.py` to emit valid YAML descriptions
3. **Eval viewer security** — port hardened viewer with script breakout protection
4. **Guidance validation** — reference wiring checks to catch outdated or contradictory prose
5. **Design analysis toolkit** — shared design-analysis approach for identifying contradictions early

These could reduce friction for all skill creators using the official ecosystem.
