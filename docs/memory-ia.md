# Memory — Information Architecture

How a memory works in Vera today, the layers it lives in, and the three
dimensions the Mind view uses to place it in space. Everything here maps to
real code; layers marked *proposed* do not exist yet.

## The life of one memory

1. **Birth** — you say something real. `memory.record()` appends one line to
   `memory.jsonl` (owner-only, 0600): timestamp, your prompt, a 240-char gist
   of her answer, the model used. Scripted/internal prompts are never recorded
   (`record=False`) — she learns from you, not from her own boilerplate.
2. **Typing** — `mem_types.classify()` tags it emotion / task / opinion /
   knowledge. Rule-based, no model call, inspectable.
3. **Listening** — `shadow.observe()` checks the same words for tasks you
   mentioned or finished, and updates the day ledger.
4. **Connection** — `brain.landscape()` links it to related memories by shared
   content words (Jaccard overlap). Its `heat` = how connected it is.
5. **Recall** — on every turn, `memory.recall(query)` scores all memories by
   content-word overlap (weighted by word length, nudged by recency) and folds
   the top hits into her system prompt via `context_for()`. No embeddings,
   O(n), fully explainable: you can always see *why* she remembered it.
6. **Expression** — the Mind view renders it as a labeled node; patterns()
   distills recurring topics and active hours into her standing self-knowledge.

## Layers (the architecture)

| Layer | Human analogue | Store | Status |
|---|---|---|---|
| Moment | working memory | current session turns | exists (in-process) |
| Episodes | episodic memory | `memory.jsonl` | exists — source of truth |
| Day ledger | prospective memory | `shadow.jsonl` | exists |
| Rhythms | implicit/temporal | derived from timestamps | exists |
| Reflections | inner voice | soul store | exists |
| Reconsolidation | strengthening | `strength.json` sidecar | exists — every episode folded into her real thinking gets stronger; recall favours the well-worn (never deletes) |
| Date recall | hippocampal time-travel | rule-based date parser | exists — "what happened on july 1", "yesterday", "3 days ago", "earlier today" surface that day's episodes |
| Distilled facts | semantic memory | — | *proposed*: idle-time consolidation of episodes into stable facts with provenance links back to their episodes |

Principles (non-negotiable): episodes are append-only truth; every derived
layer must point back to the episodes it came from; no layer requires a model
call to *read*; nothing leaves the machine.

## How a human brain does it — and how she does

| Human mechanism | Her mechanism |
|---|---|
| The hippocampus encodes an *episode* — what, when, the gist, the feeling | `record()`: prompt, timestamp, gist, rule-typed emotion/task/opinion/knowledge |
| Recall is *reconstruction by association* — cues activate overlapping traces | `recall()`: content-word overlap between what you said and every stored episode |
| Each recall *re-writes* the memory a little stronger (reconsolidation) | `reinforce()`: episodes used in real thought bump `strength.json`; scoring favours them; the Mind pulls them toward her core |
| Unused memories fade in *priority*, not existence | strength only ever adds rank — nothing is deleted |
| You can travel to a day ("that Sunday…") — episodic time indexing | date-query recall: name a day, get its episodes |
| Sleep consolidates episodes into stable *semantic* knowledge | *proposed*: her idle reflection cycle distilling facts, each linked to its source episodes |
| Emotional salience makes memories vivid | memory types carry through every layer — colour, sector, recall context |

The differences are deliberate: a human brain forgets and confabulates; hers
keeps the append-only truth and can always show you exactly why a memory
surfaced. She is not a simulation of a brain — she is an *honest* one.

## The three dimensions

Every memory's position in the Mind is meaningful — three axes, all real:

```
ANGLE   — WHAT it is      type sector (emotion/task/opinion/knowledge),
                          related memories pulled together within the sector
RADIUS  — HOW STRONG      connectedness (heat): the strongest sit closest
                          to her core; one-off strays drift at the periphery
HEIGHT  — WHEN it formed  new memories float above the plane and settle
                          toward it as they age into the mass
```

So one glance answers: what kind of thing she knows (angle), how central it
is to who she's becoming with you (radius), and how fresh it is (height).
Drag orbits the mind to read depth; nothing about a memory's placement is
decorative.
