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
   closest to the outline.
5. **Explore › Citations** looks the papers up on OpenAlex. A Zotero export makes the lookups exact,
   and free for each paper it gives a DOI for. Reviews then build their debates around the most
   cited papers.
6. For gaps, put a draft in **Outlines and drafts** and run **gaps** on the app page.
