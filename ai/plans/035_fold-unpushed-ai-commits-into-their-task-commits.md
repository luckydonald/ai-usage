# Fold unpushed `ai:` commits into their task commits

## Context
`mane` is 47 commits ahead of `origin/mane` (base `cff288f`). Many are hook-made noise: `ai: updated prompt`, `ai: save plan …`, `ai: save decision …`, TODO syncs. Per the user's request and the lplp style cleanup procedure, fold them into their task commits. This explicit request authorizes the history rewrite.

User overrides to the skill defaults:
- ALL plan commits are folded, including the existing `ai: Plan:` / `ai: Plan update:` ones (no code in them).
- TODO commits (`ai: synced todos…`, `ai: purged completed todos…`, `[ai-usage] [docs] ai/todo: sync…`) fold into the **previous** task.
- Prompt / plan / decision commits fold **forward** into the task execution they started. Prompts sit before the work, so this matches how the style amends them into the work commit. The one trailing prompt (`fc485d7`) folds back.

## Method
Plain `rebase -i` with forward folding would reorder commits and hit `ai/query.md` conflicts. Instead, use a conflict-free tree rebuild:
1. Back up: `git branch backup/pre-fold-mane HEAD`.
2. Chain contiguous groups. For each group, `git commit-tree <tree of group's last commit> -p <previous new commit> -F <anchor message>`. The anchor's original message is kept (`git log -1 --format=%B <anchor>` into the scratchpad dir, passed with `-F`). Author and date come from the anchor via `GIT_AUTHOR_*` env.
3. Special case: `d19ca43` (todo sync) belongs to `b82af68`. Its group tree is `b82af68`'s tree with `ai/todo.md` taken from `d19ca43`. That is built via a temp index (`GIT_INDEX_FILE`, `read-tree`, then `update-index --cacheinfo`).
4. `git reset --hard <new tip>` only after verification. The tree must be identical to the old HEAD.

## Resulting groups (chronological, 47 → 18 commits)
Anchor in **bold**; its message is kept.
1. `d8a6e71` + **`36af1af`** (provider login)
2. **`fb81396`**
3. **`fa41430`**
4. **`020e6dd`**
5. `95fd413` + `199ec7c` (plans) + **`d45999a`** (claude-usage-app-api)
6. **`b82af68`** + `d19ca43` (todo sync, todo.md only)
7. `d047a64` `364ae9b` `172fbd2` `7b05d84` `24d8485` `0c692fe` `dc550b5` + **`8fffb0a`** (graph)
8. **`5be87c5`**
9. **`1838437`**
10. **`97ee624`**
11. **`ecc7669`**
12. **`adf8cdf`** + `48810a8` `37cef9a` `694e6d1` `8910ad5` (todos)
13. `3cd8489` `2e35061` `f46fd7e` + **`5ca717e`** (run.sh)
14. **`9e23e68`** + `ea36eab` `e26f4ee` (todos)
15. **`3610b0e`**
16. `56642d3` `cf749c3` `9b6b169` `3e22edb` `07b8e6c` `a433441` `0eaea78` + **`6ab113a`** (instance lock; plan 034 and its prompts)
17. **`67b2b26`**
18. `ba4d054` + **`991d157`** + `fc485d7` (provider icons)

Judgment calls:
- Plan 031 plus its prompts go forward into the `8fffb0a` group, not with `d19ca43`.
- `fc485d7` is the current session's prompt. The hook will create a fresh one on the next prompt.

## Verification
- `git diff backup/pre-fold-mane HEAD` is empty (identical final tree).
- `git log --oneline origin/mane..HEAD` shows 18 commits and no `ai: updated prompt`, `save plan`, `save decision` or `synced todos` entries.
- `git status` is clean. Backup branch kept until the user okays deletion.
