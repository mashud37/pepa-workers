# pepa-prep

Turns PDFs into clean text that the other workers can read: papers, whole books and scanned
volumes. It runs on your computer and calls no model.

## How it works

Each PDF takes one of three routes. A paper becomes one text file. A long PDF is treated as a book
and split into one file per chapter, using its bookmarks, its table of contents or its chapter
headings. A scan is read with Tesseract first. Headers, footers, page numbers and reference lists
are removed.

## Use it

1. Put PDFs in its **PDFs to prepare** folder: **Copy files here** on its page, or **Copy PDFs in**
   on **Library**.
2. Run **extract**.
3. The results are under **Prepared text**. Open any file to read it.

For books, **validate** grades the chapter files and **refine** repairs chapter boundaries it can
tell are wrong; tick **apply** to write the repairs.

**Mark chapters** beside a paper on **Library** shows every page. Tick where each chapter starts and
leave out pages nothing should read, such as an index; **Leave out as** records what they are, and
pages left out as Contents help find the chapters. Then prepare the paper again.

Scanned PDFs need Tesseract. On Windows, install it with `winget install UB-Mannheim.TesseractOCR`.
