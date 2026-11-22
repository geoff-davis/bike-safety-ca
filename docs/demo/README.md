# Demo outputs

Everything here is made from made-up data and can be shown freely. Nothing
comes from a police record or from CDPH.

| File | What it is | How it was made |
|---|---|---|
| `crash_movement_map.html` | The crash movement map on the demo city: real Claremont streets (OpenStreetMap, © OpenStreetMap contributors, ODbL 1.0) and made-up crashes. One file; opens offline. | `python -m bike_safety_ca.demo --out <folder>`, then `python -m bike_safety_ca.report map --config config/demo_claremont.yaml --crashes <folder>/processed/crashes --processed <folder>/processed --out <out> --offline` |
| `hospital_sample.pdf` | A county hospital report on made-up counts for an invented county. | `python -m bike_safety_ca.hospital.sample --out <out> --pdf` |
| `../images/demo_crash_map.png`, `../images/demo_collision_diagram.png` | Screenshots of the map: the whole city, and the corner of Miramar Avenue and North Mills Avenue. | Headless Chrome at 1400 × 900 and 1400 × 820, the second opened at `crash_movement_map.html#34.12873,-117.70672,19`. |
| `../images/demo_ranking.png` | Every intersection in the demo city coloured by its rank. | `python docs/demo/ranking_figure.py . docs/images/demo_ranking.png` (builds the demo tables if missing) |
| `../images/sample_hospital_report.png` | Page 1 of the PDF. | `pdftoppm -r 100 -png -f 1 -l 1 -singlefile hospital_sample.pdf sample_hospital_report` |

Rebuild these after a change to the map or the report, so the front page
shows what the code makes now.
