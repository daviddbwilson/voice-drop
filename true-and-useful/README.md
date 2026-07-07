# true-and-useful

A small collection of [Claude](https://claude.com/claude-code) skills that are, ideally, both true and useful.

A skill is a folder with a `SKILL.md` inside it. The YAML front matter (`name` + `description`) tells Claude when to reach for the skill; the Markdown body tells it what to do. Claude reads the description to decide relevance, then loads the body when the skill fires.

## Skills

| Skill | What it does |
|-------|--------------|
| [`explain-clearly`](explain-clearly/SKILL.md) | Explain technical things in plain English — lead with the impact, drop the jargon, spell out why it matters. |

## Using a skill

**Claude Code** — drop a skill folder into a discovered skills directory:

```bash
# user-level (available in every project)
mkdir -p ~/.claude/skills
cp -R explain-clearly ~/.claude/skills/

# or project-level (checked in, shared with your team)
mkdir -p .claude/skills
cp -R explain-clearly .claude/skills/
```

Claude picks it up automatically the next time it runs. Confirm with `/skills` (or invoke directly with `/explain-clearly`).

**Claude apps** — upload the skill folder in Settings → Capabilities → Skills.

## License

[MIT](LICENSE) © 2026 David Wilson
