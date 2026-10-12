"""Word what a paid step will cost from the JSON a worker's --estimate prints.
Every Explore page shows these words before its Run button.
"""
from web import jobs


def dollars_words(dollars):
    """An amount at list price in words, such as "under $0.01" or "about $0.42"."""
    if dollars < 0.01:
        return "under $0.01"
    return f"about ${dollars:.2f}"


def cost_words(estimate):
    """One sentence on what a step costs: tokens and model for a model call, lookups for OpenAlex."""
    if estimate.get("model") == "OpenAlex":
        if not estimate["works"]:
            return "Every paper is already looked up."
        return f"{estimate['works']:,} works to look up, covering {estimate['papers']:,} papers, since a book's chapters share one lookup: {estimate['by_doi']:,} by a DOI printed in the paper or held in your export, and {estimate['by_search']:,} by a title search on Crossref. Both are free."
    tokens = estimate.get("tokens", 0) + estimate.get("input_tokens", 0) + estimate.get("output_tokens", 0)
    if estimate["dollars"] == 0:
        return "Runs on your computer, at no cost."
    if estimate["dollars"] is None:
        return f"About {tokens:,} tokens with {estimate['model']}, whose price is not known here."
    price = dollars_words(estimate["dollars"])
    if estimate.get("upto"):
        return f"Up to {tokens:,} tokens with {estimate['model']}: {price.replace('about', 'at most')} at list price."
    return f"About {tokens:,} tokens with {estimate['model']}: {price} at list price."


def estimate(app_name, command_name, flags):
    """What a paid step will cost, as the worker's estimate plus "words", or None when the worker could not say."""
    reply = jobs.json_reply(app_name, command_name, flags + ["--estimate"])
    if reply is None:
        return None
    reply["words"] = cost_words(reply)
    if "paid_upto" in reply:
        reply["paid_words"] = dollars_words(reply["paid_upto"]).replace("about", "at most")
    return reply
