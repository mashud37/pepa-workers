# pepa-review

Works with the papers pepa-sum has summarised: writes a literature review from an outline, finds
work a draft is missing, and maps how a field falls into themes. It needs an Anthropic key, and a
Gemini key for the index.

## How it works

Every brief is turned into a vector that captures its meaning, and stored in an index. Each task
finds the closest papers by meaning and by keyword, and a language model writes the review,
explains each gap, or names each theme.

## Use it

1. Run **index** once, and again after new papers are summarised. **Process papers** on
   **Library** does this too.
2. For a review, put an outline in **Outlines and drafts** (**Write a file** on its page) and run
   **review**. It asks which papers to use; tick **auto** to let it choose by similarity.
3. For gaps, put a draft in the same folder and run **gaps**.
4. **map** groups every paper into themes; **threadmap** splits one theme further.

Results are under **Reviews, gaps and maps**.
