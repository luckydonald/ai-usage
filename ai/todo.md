- [x] If available, the graph hover/click info shall display the native unit, too.
- [ ] Have the info panels have a badge with the graph color, so they are easy to recognize.
- [-] In the graph hover/click info, it shall use both the time relative to back then (where hovered) and the current clock time. This needs to be separated info with a nice gui design, while still staying compact. Maybe via icons?

## From the todo list

Source: `sync_todo` MCP, calendar `TODO: Today` (`calendar_id` 7). Each item ends with its todo `uid`.
To complete one: tick the box and call `mcp__sync_todo__complete_todo(calendar_id=7, uid=<uid>)`.

- [ ] #aiUsage those max-usage blocks are created once per data point it seems, hence overlapping a lot. — `todo:5fe337f2-2e36-4775-8d16-632d7544207c`
  > • visible as a gradient when the usage is raising
  > • fully opaque block once 100% are reached
  > • it should only draw one, which should be by definition and context the maximum available one.
  > #max_usage
- [ ] #aiUsage longer max-usage blocks should be layered behind smaller ones — `todo:e3074f3c-4be6-4074-9ca9-8c033d65e1eb`
  > • it kinda should be enough if older entries are behind newer entries
  > #max_usage
