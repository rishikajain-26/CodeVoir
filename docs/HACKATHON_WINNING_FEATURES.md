# Hackathon-Winning Features to Add Next

These features are designed to strengthen CodeVoir's story: interview, diagnose, teach, and prepare the user for opportunities.

## Highest-impact additions

1. **Skill Gap Heatmap**
   - Combine interview scores, quiz scores, and resume skills.
   - Show topic-level readiness such as React 72%, DSA 64%, System Design 42%.
   - Add a button on each weak skill: `Learn with Agent`.

2. **Mock Interview from Uploaded Source**
   - User uploads a PDF, docs URL, or GitHub repo.
   - CodeVoir generates questions from that source.
   - User answers; the agent scores and rewrites weak answers.

3. **Weak Answer Rewriter**
   - After any interview answer, show `Improve my answer`.
   - Output: weak answer, improved answer, what improved, and a follow-up question.

4. **Opportunity Preparation Agent**
   - On each hackathon/job/internship card, add `Prepare with AI`.
   - Output: why the user matches, missing skills, pitch, project idea, likely questions, and 3-day plan.

5. **GitHub README/Project Pitch Improver**
   - From an indexed repo, generate README sections, architecture summary, and interview pitch.
   - This is useful for hackathon teams and portfolio polishing.

6. **Concept Visualizer**
   - Generate Mermaid diagrams for auth flow, API flow, React rendering, database relations, etc.
   - Frontend can render Mermaid later; current version displays Mermaid code and a concept tree.

7. **Adaptive Quiz Mode**
   - Agent asks increasingly harder questions.
   - Wrong answer leads to simpler explanation and a retry.
   - Final score feeds into the Skill Gap Heatmap.

## UX upgrades already applied

- Sources moved to a compact right-side evidence panel.
- Duplicate PDF/URL citations are grouped.
- Visual notes render as cards.
- Flashcards render as reveal cards.
- Mind maps render as a concept tree with optional Mermaid flow text.
- Center workbench now focuses on actions/features instead of large citations.
