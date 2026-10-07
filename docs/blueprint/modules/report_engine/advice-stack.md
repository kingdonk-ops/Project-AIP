# Report engine & published records — Tech stack advisor


- **note**: WeasyPrint is lightweight and good for tabular reports but weaker on complex CSS. Gotenberg (Chromium) handles landscape coating/DFT reports with inlined photos more reliably. Render in worker jobs and store the PDF as a document.
