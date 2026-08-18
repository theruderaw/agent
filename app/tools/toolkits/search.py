# app/tools/toolkits/search.py

from typing import TypedDict

from tavily import TavilyClient
from app.tools.base import Toolkit


class SearchResult(TypedDict):
    title: str
    url: str
    content: str
    score: float


class SearchResults(TypedDict):
    query: str
    answer: str
    results: list[SearchResult]
    response_time: float


class SearchTools(Toolkit):
    namespace = "search"
    skills = "research-skills.md"
    

    def __init__(self):
        self.client = TavilyClient()

    def search(self, query: str, max_results: int = 5) -> SearchResults:
        """Run a web search for the given query and return the top matching results, along with a synthesized answer."""

        response = self.client.search(
            query=query,
            max_results=max_results,
        )

        return response