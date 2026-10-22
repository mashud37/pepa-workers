# pepa-review

Works with the papers pepa-sum has summarised: maps how a field falls into themes, answers
questions about it, writes a literature review from an outline, finds work a draft is missing, and
looks papers up on OpenAlex for their citations. It needs a key for its model and an embedding
model, both chosen on **Models**.

## How it works

Every brief is turned into a vector that captures its meaning, and stored in an index. Each task
finds the closest papers by meaning and by keyword, and a language model names each theme, answers
the question, writes the review or explains each gap. Every result is kept, and shows its cost
before it runs.

## Use it

1. **Update review index** on **Library** builds the index; run it again after new papers are
   summarised.
2. **Explore › Map** sorts every paper, or one list's papers, into themes. Open a theme for what it
   discusses, its papers and the themes beside it; a theme of six or more papers can be mapped in
   detail.
3. **Explore › Ask** answers a question from the closest papers; follow-up questions keep the same
   papers.
4. **Explore › Reviews** writes a review from your outline, from a list's papers or from the papers
   closest to the outline. The papers it drew on are listed beside it, to add to a list or export
   as references.
5. **Look up citations** on **Library** finds each paper on OpenAlex for free: by the DOI printed
   in it, in your Zotero library, then by a title search on Crossref. **Explore › Citations**
   connects Zotero or keeps an export file, shows the most cited papers and how each was found,
   and offers a paid title search for papers the free sources miss, at a cost shown first.
   Reviews then build their debates around the most cited papers.
6. **Draft › Check for gaps** checks a text against the whole library, a list or a theme, and lists
   the papers it should engage.
