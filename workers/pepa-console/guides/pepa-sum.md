# pepa-sum

Summarises each paper into three documents: a **brief** with the same fields for every paper, a
**rundown** of the paper paragraph by paragraph, and **quotes** checked word for word against the
source. It needs an Anthropic key.

## How it works

The paper is read on your computer, its reference list removed, and its key phrases, names and
claims picked out. A language model writes the brief and the rundown from that, and chooses quotes
from passages found locally. A quote that does not appear in the paper exactly is dropped.

Every brief has the same fields: question and context, empirical context, literature drawn on,
methods, arguments, key conclusions, and discussion items.

## Use it

1. Put PDFs, markdown or text files in **Papers to summarise**. **Copy PDFs in** on **Library**
   puts them there too.
2. Run **summarize**. Papers already summarised are skipped unless **force** is ticked.
3. Open a file under **Summaries**. The buttons above it switch between the paper's brief,
   rundown, quotes and prepared text.

**clean** lists summaries that failed, so they can be redone.
