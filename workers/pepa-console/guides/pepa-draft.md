# pepa-draft

Drafts the sections of a paper from a pepa-plan outline and a pepa-review literature review, so an
idea can be read in prose before committing to it. It needs an Anthropic key, and the review index
pepa-review built.

## How it works

Each paragraph of the outline is assigned to a section. For every section, pepa-draft finds the
most relevant papers in the review index and, when given, passages of your own writing, and a
language model writes the prose.

## Use it

1. On **Draft › First draft**, choose an outline and a literature review. Each paragraph of the
   outline goes into the section its move belongs to.
2. The draft opens when it is written, with the papers it drew on beside it.

On its app page, **sections** assigns paragraphs to sections by hand, and **draft** works from files
in **Plans and reviews**.
