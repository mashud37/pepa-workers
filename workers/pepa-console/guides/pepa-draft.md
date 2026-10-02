# pepa-draft

Drafts the sections of a paper from a pepa-plan outline and a pepa-review literature review, so an
idea can be read in prose before committing to it. It needs an Anthropic key, and the review index
pepa-review built.

## How it works

Each paragraph of the outline is assigned to a section. For every section, pepa-draft finds the
most relevant papers in the review index and, when given, passages of your own writing, and a
language model writes the prose.

## Use it

1. Copy an outline from pepa-plan and a review from pepa-review into **Plans and reviews**.
2. Run **sections** with the outline, to assign its paragraphs to sections.
3. Run **draft** with the review and the outline. The draft is under **Manuscripts**.
