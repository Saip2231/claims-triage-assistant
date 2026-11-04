"""Mini Claims Triage Assistant: a deterministic claims-triage engine.

The pipeline is: extract a claim from a PDF/TXT file, run six pure check
functions against the reference workbook, combine the results by priority,
and explain the decision with templates that cite the uploaded policy.
No LLM is used anywhere.
"""

__version__ = "0.1.0"
