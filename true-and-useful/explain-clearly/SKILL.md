---
name: explain-clearly
description: Explain technical things in plain English — lead with the impact, drop the jargon, spell out why it matters. Use whenever you're explaining a bug, a fix, a design, a tradeoff, a piece of code, an error, or how something works in chat. Trigger on "explain", "what does this do", "why is this happening", "walk me through", "ELI5", "in plain english", "what's going on here", or any time you catch yourself about to write a jargon-heavy explanation.
---

# Explain Clearly

The reader is technical and wants to understand the *why* (and what/how etc) fast without wading through terminology. When you explain anything technical, the goal is: the user reads it once and gets it.

**Lead with the big picture** – what it means for him / the customer / the team / whatever is most relevant. Then explain the mechanism when appropriate.

Most bad explanations bury the impact under the mechanism. Flip it. Say what breaks, what changes, or what the user can now do — then, only if it helps, how it works underneath.

## How to write it

1. **Impact first.** Start with the consequence, not the cause. "This could break workflows that are mid-run when you deploy" before "the command sequence changes on replay."
2. **No internal jargon as if it's common knowledge.** If a term is load-bearing, define it in the same breath the first time: "Temporal replays workflows deterministically: it re-runs the function and checks each step matches what already happened." Don't drop "guarded patch" or "replay-unsafe" naked and move on.
3. **Plain phrases over abstraction nouns.** "in the same file as" not "colocated with." "the same list copied in two places" not "a verbatim duplicate." "happens at the same time" not "concurrent execution."
4. **Name a code identifier only when the user would need to go find it** — and only once. Describe everything else by what it does.
5. **One idea per sentence.** If a sentence has two "and"s and a "which," split it.
6. **Teach the why, don't just hand the user the what.** They're learning. A one-line "this matters because X" is worth more than three lines of correct-but-opaque detail.
7. **Match length to the question.** A quick "why" gets 2-4 sentences. A design walkthrough gets more. Don't pad to look thorough; don't compress a real explanation into a cryptic line.

## Smell test before you send

Read it back as if you were saying it out loud at the user's desk. Any phrase you'd never actually say to a person, rewrite it. No em dashes. No "leverage," "facilitate," "underlying mechanism," "in order to." If you used a term he hasn't seen, did you define it right there?

## Do the work

Don't tell him to "verify X in the codebase" if you can just go read it and tell him the answer. Don't hand him a term to go google. Resolve the ambiguity yourself, then explain the resolved version.

## Example

Same finding, written two ways.

<jargony>
The diff drops `agent-app` from the `getFlags` activity input array and makes `appAgentDelegateHeader.init({...})` unconditional. Any `agentExecutorWorkflow` execution started on the old code and replayed after deploy will produce a different command sequence and throw `NonDeterministicWorkflowError`.
</jargony>

<plain>
This change could get workflows stuck if they're running when you deploy.

Why: these workflows (Temporal) work by replaying — when one resumes, the system re-runs its code from the start and checks that each step matches what already happened. Your change alters those steps (you removed a flag from one call and made an init run every time instead of only sometimes). So a workflow that started on the old code won't match after the deploy, and it errors out and gets stuck.

Fix: wrap the change in `patched(...)` so old runs take the old path and new runs take the new one. There's an example of this at `Agent/flow.ts:136`.
</plain>

The plain version is a bit longer, and that's fine — it leads with the stakes, defines the one term that matters, and tells the user what to do.
