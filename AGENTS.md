# Agent Principles for ShiftSQL

## Autonomy
- Read files before editing them
- Search for answers before asking questions
- Break complex tasks into steps and complete them all
- Make decisions based on context and patterns

## Communication
- Respond in the same language as the user
- Keep responses concise (under 4 lines)
- Use rich Markdown formatting for multi-sentence answers
- No preamble or postamble in responses

## Code Quality
- Match existing code style exactly
- Test after every change
- Don't leave code in broken state
- Fix root causes, not surface-level symptoms

## Workflow
- View file contents before making changes
- Use exact text matching for edits (including whitespace)
- Run tests to verify changes work
- Keep moving forward until task is complete

## Security
- Only assist with defensive security tasks
- Never create code that could be used maliciously
- Follow security best practices