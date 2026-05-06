## 2024-05-24 - Jinja2 Template Compilation Bottleneck
**Learning:** Instantiating `Environment` and loading the `report.html` template in `modules/utils.py` inside the function `generate_premium_pdf` forces Jinja2 to re-read and re-compile the template on every PDF generation request.
**Action:** Move the `jinja2.Environment` instantiation and template loading to the module level so it is parsed once, avoiding repeated expensive I/O and CPU overhead.
