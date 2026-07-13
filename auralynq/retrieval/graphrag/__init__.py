"""GraphRAG community summaries — corpus-wide sensemaking over the KG.

Beyond PathRAG's *local* path search, GraphRAG (Edge et al., 2024) detects
communities of related entities and LLM-summarizes each into a theme, so broad
"what are the main topics / how do these connect" questions can be answered by
map-reducing over community summaries. Community detection is pure ``networkx``
(no new dependency); summarization reuses the configured LLM.
"""

from auralynq.retrieval.graphrag.communities import (
    Community,
    build_communities,
    detect_communities,
    load_communities,
    save_communities,
)

__all__ = [
    "Community",
    "build_communities",
    "detect_communities",
    "load_communities",
    "save_communities",
]
