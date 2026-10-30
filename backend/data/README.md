# Local plant knowledge base

`plant_profiles.json` ships with starter notes and common aliases for a small set of plants. It is a local file, so the app does not need a separate botanical database service for these entries. These notes are not a comprehensive or expert-verified growing guide and intentionally do not claim universal species-specific soil-moisture percentages. Verify local horticultural guidance and calibrate the actual sensors before using any profile for automatic irrigation.

## Local searchable plant knowledge database

The bundled `plant_profiles.json` is a compact offline-first starter catalog (36 entries). It is **curated starter guidance**, not a verbatim import of any external dataset and not a source of numeric irrigation thresholds. The backend seeds it into the SQLite `plant_knowledge` table on startup, so it can be searched locally without internet access.

### External references and optional full import

- [OpenPlantDB](https://github.com/cwfrazier1/openplantdb): public-domain CC0 dataset with crop growing information. Its upstream dataset is large, so the entire upstream file is not bundled in this prototype. Import it from an internet-connected machine by running `python scripts/import_openplantdb.py --download` from the `backend/` directory. This will download the upstream JSON under `backend/data/external/` and import records into the local SQLite knowledge table.
- [USDA PLANTS downloads](https://plants.sc.egov.usda.gov/downloads): reference for names and taxonomy, not universal irrigation targets.
- [FAO AQUASTAT crop water requirement](https://www.fao.org/aquastat/en/data-analysis/irrig-water-use/irrig-water-requirement/): crop water needs depend on crop stage and climate.
- [FAO irrigated crop calendars](https://www.fao.org/aquastat/en/databases/crop-calendar/): country/crop calendar reference; coverage and reliability vary.

The `plant_knowledge` records store the source name, URL, license, aliases, and original data JSON. Imported external profiles are for informational use. They do not automatically change a plant's moisture thresholds or enable pump control.
