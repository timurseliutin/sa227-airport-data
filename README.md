# sa227-airport-data

Airport and runway database for **SA227 Performance**, rebuilt for every 28-day AIRAC cycle.

- **United States:** FAA NASR 28-day subscription (APT CSV): runway lengths, declared distances (TORA, TODA, ASDA, LDA), displaced thresholds, runway end elevations, true alignment. Official, public domain.
- **Canada and Mexico:** [OurAirports](https://github.com/davidmegginson/ourairports-data) (Unlicense). Community data, **not an official source**; the app marks it so.
- **Magnetic variation:** World Magnetic Model 2025 at the cycle date.
- Runways 2,000 ft and longer; no water runways or helipads.

## Files
- `dist/manifest.json`: current and next cycle, with effective and expiry dates, file size and SHA-256. The app reads this.
- `dist/airports-<cycle>.json`: the database for one cycle (format in `tools/build_db.py`).

FAA posts each cycle 28 days before it becomes effective, so the next cycle is published early. The app downloads it ahead and switches on its effective date, even offline.

## How it updates
GitHub Actions (`.github/workflows/build.yml`) runs daily. When a cycle is missing it downloads NASR and OurAirports, builds, **checks** (counts, control airports and runways, value ranges) and commits. A failed check publishes nothing and the app keeps the data it has.
Run by hand: Actions › build-airport-data › Run workflow.

Not for navigation. Always check the current chart supplement and NOTAMs.
