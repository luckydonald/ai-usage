- [x] If available, the graph hover/click info shall display the native unit, too.
- [x] Have the info panels have a badge with the graph color, so they are easy to recognize.
- [x] In the graph hover/click info, it shall use both the time relative to back then (where hovered) and the current clock time. This needs to be separated info with a nice gui design, while still staying compact. Maybe via icons?

## From the todo list

Source: `sync_todo` MCP, calendar `TODO: Today` (`calendar_id` 7). Each item ends with its todo `uid`.
To complete one: tick the box and call `mcp__sync_todo__complete_todo(calendar_id=7, uid=<uid>)`.

## Todos synced from CalDAV

- [x] those max-usage blocks are created once per data point it seems, hence overlapping a lot. • visible as a gradient when the usage is raising • fully opaque block once 100% are reached • it should only draw one, which should be by definition and context the maximum available one. #max_usage — `todo:5fe337f2-2e36-4775-8d16-632d7544207c` _(done)_
- [x] horizontal line marking the end of a block clearly — `todo:63a4e32b-a3db-4317-a4f4-b329b5b15fc4` _(done)_
- [x] in the crawler logs, log the crawler's name — `todo:6bea597f-f186-426b-bfc3-ee545c6d3fb1` _(done)_
  > - Not `[ai_usage.crawl] …` but `[ai_usage.crawl.claude.web_ai]`
  > - or what’s appropriate, don’t know the exact module names.
- [x] longer max-usage blocks should be layered behind smaller ones • it kinda should be enough if older entries are behind newer entries #max_usage — `todo:e3074f3c-4be6-4074-9ca9-8c033d65e1eb` _(done)_
- [ ] each increasing datapoint of a graph still draws it's own max-square on top of last point's max square — `todo:382d222f-3a08-4431-b907-b71d477702b7`
  > - This is a followup to `todo:e3074f3c-4be6-4074-9ca9-8c033d65e1eb`.
