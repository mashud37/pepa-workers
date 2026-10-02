# pepa-read

Searches every paper pepa-prep has prepared and pepa-sum has summarised, and keeps literature
lists for pepa-review. Nothing leaves your computer.

## How it works

pepa-read builds a search index of titles, authors and every section of each brief, and ranks
matches by relevance. A search can target one section: `methods:interviews author:smith` finds
papers by Smith that used interviews.

## Use it

1. Run **index** after new papers are summarised. **Process papers** on **Library** does this too.
2. Open **Search** and press **Start**.
3. Search, open a result, and add it to a literature list. **list-export** writes a list that
   pepa-review can use.
