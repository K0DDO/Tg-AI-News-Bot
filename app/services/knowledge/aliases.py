"""Canonical entity aliases + seed types/categories for Knowledge Graph linking."""

from __future__ import annotations

# alias (lower) → (canonical_name, node_type, semantic_categories)
ALIAS_MAP: dict[str, tuple[str, str, tuple[str, ...]]] = {
    # Companies / orgs
    "apple": ("Apple", "Company", ("Consumer Electronics", "AI", "Mobile", "Hardware")),
    "эппл": ("Apple", "Company", ("Consumer Electronics", "AI", "Mobile", "Hardware")),
    "google": ("Google", "Company", ("AI", "Search", "Cloud", "Software")),
    "гугл": ("Google", "Company", ("AI", "Search", "Cloud", "Software")),
    "microsoft": ("Microsoft", "Company", ("Software", "AI", "Cloud")),
    "майкрософт": ("Microsoft", "Company", ("Software", "AI", "Cloud")),
    "openai": ("OpenAI", "Company", ("AI", "LLM", "Software")),
    "open ai": ("OpenAI", "Company", ("AI", "LLM", "Software")),
    "опенаи": ("OpenAI", "Company", ("AI", "LLM", "Software")),
    "anthropic": ("Anthropic", "Company", ("AI", "LLM")),
    "nvidia": ("NVIDIA", "Company", ("AI", "Hardware", "GPU")),
    "нвидиа": ("NVIDIA", "Company", ("AI", "Hardware", "GPU")),
    "valve": ("Valve", "Company", ("Gaming", "Steam", "PC", "Linux")),
    "samsung": ("Samsung", "Company", ("Mobile", "Hardware", "Consumer Electronics")),
    "самсунг": ("Samsung", "Company", ("Mobile", "Hardware", "Consumer Electronics")),
    "meta": ("Meta", "Company", ("AI", "Social", "VR")),
    "tesla": ("Tesla", "Company", ("Automotive", "AI", "Hardware")),
    "amazon": ("Amazon", "Company", ("Cloud", "E-commerce", "AI")),
    "intel": ("Intel", "Company", ("Hardware", "CPU")),
    "amd": ("AMD", "Company", ("Hardware", "GPU", "CPU")),
    # People
    "tim cook": ("Tim Cook", "Person", ("Apple", "Business")),
    "sam altman": ("Sam Altman", "Person", ("OpenAI", "AI")),
    "сэм альтман": ("Sam Altman", "Person", ("OpenAI", "AI")),
    "jensen huang": ("Jensen Huang", "Person", ("NVIDIA", "AI")),
    "elon musk": ("Elon Musk", "Person", ("Tesla", "AI")),
    "илон маск": ("Elon Musk", "Person", ("Tesla", "AI")),
    # Products
    "iphone": ("iPhone", "Product", ("Apple", "Mobile", "Hardware")),
    "айфон": ("iPhone", "Product", ("Apple", "Mobile", "Hardware")),
    "iphone 18": ("iPhone 18", "Product", ("Apple", "Mobile", "Hardware")),
    "iphone 18 pro": ("iPhone 18 Pro", "Product", ("Apple", "Mobile", "Hardware")),
    "айфон 18": ("iPhone 18", "Product", ("Apple", "Mobile", "Hardware")),
    "айфон 18 pro": ("iPhone 18 Pro", "Product", ("Apple", "Mobile", "Hardware")),
    "macbook": ("MacBook", "Product", ("Apple", "Hardware", "Laptop")),
    "макбук": ("MacBook", "Product", ("Apple", "Hardware", "Laptop")),
    "chatgpt": ("ChatGPT", "Product", ("OpenAI", "AI", "LLM")),
    "чатгпт": ("ChatGPT", "Product", ("OpenAI", "AI", "LLM")),
    "chat gpt": ("ChatGPT", "Product", ("OpenAI", "AI", "LLM")),
    "claude": ("Claude", "Product", ("Anthropic", "AI", "LLM")),
    "gemini": ("Gemini", "Product", ("Google", "AI", "LLM")),
    "cursor": ("Cursor", "Product", ("AI", "Programming", "Software")),
    "курсор": ("Cursor", "Product", ("AI", "Programming", "Software")),
    "steam machine": ("Steam Machine", "Product", ("Valve", "Gaming", "PC")),
    "steam deck": ("Steam Deck", "Product", ("Valve", "Gaming", "PC")),
    "стим дек": ("Steam Deck", "Product", ("Valve", "Gaming", "PC")),
    "vision pro": ("Vision Pro", "Product", ("Apple", "VR", "Hardware")),
    "apple intelligence": ("Apple Intelligence", "Product", ("Apple", "AI")),
    "a20 pro": ("A20 Pro", "Product", ("Apple", "Hardware", "Chip")),
    "rtx": ("RTX", "Product", ("NVIDIA", "GPU", "Hardware")),
    # Technology / topics
    "llm": ("LLM", "Technology", ("AI", "Software")),
    "ai": ("AI", "Technology", ("Technology", "Software")),
    "ии": ("AI", "Technology", ("Technology", "Software")),
    "нейросети": ("AI", "Technology", ("Technology", "Software")),
    "нейросеть": ("AI", "Technology", ("Technology", "Software")),
    "artificial intelligence": ("AI", "Technology", ("Technology", "Software")),
    "cuda": ("CUDA", "Technology", ("NVIDIA", "GPU")),
    "python": ("Python", "Technology", ("Programming", "Software")),
    "ray tracing": ("Ray Tracing", "Technology", ("Graphics", "GPU")),
    "diffusion": ("Diffusion", "Technology", ("AI", "Image")),
    "gaming": ("Gaming", "Topic", ("Entertainment", "PC")),
    "гейминг": ("Gaming", "Topic", ("Entertainment", "PC")),
    "cybersecurity": ("Cybersecurity", "Topic", ("Security", "Software")),
    "programming": ("Programming", "Topic", ("Software", "Development")),
    "программирование": ("Programming", "Topic", ("Software", "Development")),
    # Countries / orgs
    "usa": ("USA", "Country", ("Geography",)),
    "сша": ("USA", "Country", ("Geography",)),
    "germany": ("Germany", "Country", ("Geography",)),
    "japan": ("Japan", "Country", ("Geography",)),
    "china": ("China", "Country", ("Geography",)),
    "китай": ("China", "Country", ("Geography",)),
    "russia": ("Russia", "Country", ("Geography",)),
    "россия": ("Russia", "Country", ("Geography",)),
    "nasa": ("NASA", "Organization", ("Space", "Science")),
    "eu": ("EU", "Organization", ("Politics",)),
}

# Strong known relationships (from_canonical, to_canonical, edge_type)
SEED_EDGES: tuple[tuple[str, str, str], ...] = (
    ("Apple", "iPhone", "CREATED"),
    ("Apple", "MacBook", "CREATED"),
    ("Apple", "Vision Pro", "CREATED"),
    ("Apple", "Apple Intelligence", "CREATED"),
    ("Apple", "A20 Pro", "PRODUCES"),
    ("Apple", "AI", "RELATED_TO"),
    ("OpenAI", "ChatGPT", "CREATED"),
    ("OpenAI", "AI", "RELATED_TO"),
    ("Anthropic", "Claude", "CREATED"),
    ("Google", "Gemini", "CREATED"),
    ("Google", "AI", "RELATED_TO"),
    ("NVIDIA", "CUDA", "CREATED"),
    ("NVIDIA", "RTX", "PRODUCES"),
    ("NVIDIA", "AI", "RELATED_TO"),
    ("Valve", "Steam Machine", "CREATED"),
    ("Valve", "Steam Deck", "CREATED"),
    ("Valve", "Gaming", "RELATED_TO"),
    ("iPhone", "Apple", "PART_OF"),
    ("iPhone 18 Pro", "iPhone", "SUCCESSOR_OF"),
    ("iPhone 18", "iPhone", "SUCCESSOR_OF"),
    ("iPhone 18 Pro", "Apple", "PART_OF"),
    ("ChatGPT", "OpenAI", "PART_OF"),
    ("Claude", "Anthropic", "PART_OF"),
    ("Cursor", "AI", "USES"),
    ("Cursor", "Programming", "RELATED_TO"),
    ("Sam Altman", "OpenAI", "WORKS_AT"),
    ("Tim Cook", "Apple", "WORKS_AT"),
    ("Jensen Huang", "NVIDIA", "WORKS_AT"),
)


def slugify(name: str) -> str:
    s = (name or "").strip().lower()
    out = []
    for ch in s:
        if ch.isalnum() or ch in {"-", "_"}:
            out.append(ch)
        elif ch.isspace() or ch in {".", "/", "+"}:
            out.append("-")
    slug = "-".join(p for p in "".join(out).split("-") if p)
    return slug[:240] or "node"
