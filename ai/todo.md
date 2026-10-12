- [x] If available, the graph hover/click info shall display the native unit, too.
- [x] Have the info panels have a badge with the graph color, so they are easy to recognize.
- [x] In the graph hover/click info, it shall use both the time relative to back then (where hovered) and the current clock time. This needs to be separated info with a nice gui design, while still staying compact. Maybe via icons?

## From the todo list

Source: `sync_todo` MCP, calendar `TODO: Today` (`calendar_id` 7). Each item ends with its todo `uid`.
To complete one: tick the box and call `mcp__sync_todo__complete_todo(calendar_id=7, uid=<uid>)`.

