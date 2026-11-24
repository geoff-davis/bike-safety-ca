# Held-back cities

These cities are set aside to test the ranking and were not used to develop
it. Each was put in `selection/` or `final_test/` by
`bike_safety_ca.checks.assignment`, from a hash of its Census place code.

- `selection/`: a model may be chosen on these.
- `final_test/`: scored once, after the choice is written down. Do not run
  any scoring check on these before then.

They are in subfolders so that commands which read every config in `config/`
(`checks.cities`, `checks.candidates`) do not pick them up. Building a city's
street and crash tables is not scoring it.
