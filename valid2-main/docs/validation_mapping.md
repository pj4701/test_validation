# Validation Mapping

| UI Validation | Required inputs | Core comparison |
|---|---|---|
| Actuals Validation | Sales, Item, UOM, Target | Expected ActualRaw vs o9 ActualRaw |
| UOM Conversion Validation | UOM Source, Item, UOM Target | Expected conversion vs target UOM Conversion |
| o9 Compare Past ASP | ASP Source, ASP Past Target | ASP + Revenue |
| ASP Override Current & Future | ASP Override Source, Current/Future Target, Demand Domain Mapping, Rejection | ASP override + rejection analysis |

## Shared execution contract

Each validator exposes:

```python
run_validation(files, output_dir="outputs", log_callback=None)
```

and returns:

```text
ValidationResult
  name
  output_file
  records
  passed
  failed
  match_pct
  details
```
