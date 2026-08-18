# Research Skill

## Purpose

Search the web and fetch content from URLs to answer questions requiring current or external information.

## Tools

* `search:search` — run a web search query and return ranked results with a synthesized answer.
* `http:get` — fetch content from a specific URL.

## Workflow

### 1. Search

For questions about current events, news, facts, or any information that may not be in your training data:

1. Use `search:search` with a clear, specific query.
2. Review the returned results and synthesized answer.
3. Formulate a final answer based on the search results.

### 2. Fetch (optional)

If the search results reference a specific URL that needs detailed content:

1. Use `http:get` to fetch the full page.
2. Extract the relevant information.
3. Formulate a final answer.

## Guidelines

- Always prefer `search:search` over `http:get` for exploratory queries.
- Use specific, focused queries for better results.
- If the first search does not yield useful results, try reformulating the query.
- Synthesize findings into a clear final answer rather than dumping raw results.
