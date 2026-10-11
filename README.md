# Klasifikasi Spasial Tutupan Lahan Jawa Timur

**Joni Kumar Meghwar · NIM 240411100234 · UTS PSD**

Streamlit dashboard and Sentinel-2 pipeline adapted from the UTS project in [Muhammad Ainul Fuady/PSD](https://github.com/muhammadainulfuady/PSD). Uses Joni's own `EastJawa_Data.geojson`; the friend's model, pixels, predictions and evaluation scores are not included.

**Current status:** the dashboard runs with your cleaned digitized polygons. Real satellite extraction and model training still need to be run using your Copernicus account. No real model accuracy is available yet. Public deployment has not been performed.

## Quick start on Windows

Extract this ZIP. Open PowerShell in the `Joni_PSD_UTS` folder. Python 3.11 or 3.12 is recommended.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run uts/deploy/app.py
```

This immediately opens your sample map and data quality report. To generate real model results:

```powershell
.\.venv\Scripts\python.exe uts/code/crawling.py --plan
.\.venv\Scripts\python.exe uts/code/crawling.py
.\.venv\Scripts\python.exe uts/code/pipeline.py train
.\.venv\Scripts\python.exe -m streamlit run uts/deploy/app.py
```

The crawling command prints a browser login link. Sign in with your own Copernicus Data Space account. Keep the terminal running until all jobs and downloads finish. The prepared plan has **18 tiles** and about **1,753 km² of download bounding boxes**; this is not the total area of the samples. Check the current processing credits in your account before submitting. `--plan` submits no remote jobs. The default date interval is 1 September to 1 October 2026 (exclusive end). Widen the interval if clouds cause missing pixels:

```powershell
.\.venv\Scripts\python.exe uts/code/crawling.py --start 2026-08-01 --end 2026-10-01
```

If you change dates, bands or source polygons, rename/remove the old `uts/data/csv/hasil_s2_piksel` output folder before a fresh extraction. Existing jobs can be resumed only with the same settings. Run `pipeline.py prepare` again only after replacing/redrawing the source data; it clears old dashboard model results to prevent stale metrics.

## What is included

- `uts/code/crawling.py` and `crawling.ipynb`: real Copernicus openEO extraction, cloud masking, median composite, tiled jobs and pixel CSV.
- `uts/code/pipeline.py` and `landuseCover.ipynb`: label normalization, geometry validation, EDA, polygon-level 70/30 split, StandardScaler + distance-weighted k-NN with k=5, metrics, model and six CSV exports.
- `uts/deploy/app.py`: warm orange dashboard with satellite maps, five class toggles, actual/predicted comparison, confusion matrix, permutation importance, training cross-validation and prediction filtering/downloads.
- Original and cleaned GeoJSON, geometry and overlap reports, sample summary, Leaflet sample map.
- CRISP-DM documents, deployment guide and GitHub Pages book configuration/workflow.

## Your data audit

| Class in uploaded file | Normalized class | Original | Usable |
|---|---|---:|---:|
| Air (`Type`) | Air | 50 | 50 |
| Building (`Class`) | Pemukiman | 50 | 48 |
| Farmland (`Class`) | Sawah | 50 | 49 |
| Mangroves (`Class`) | Hutan Mangrove | 50 | 50 |
| Forest (`Class`) | Hutan Non-Mangrove | 50 | 50 |
| Total | | 250 | 247 |

Original feature numbers **70, 71 and 148** have no recoverable polygon area. Redraw those locations in your digitization tool if you want all 250 valid polygons. Nine other polygons were repaired with `make_valid`. Original source bytes are preserved. The cleaned output may contain MultiPolygons after repair. Fifteen pairs of polygons overlap; extraction removes shared pixel observations to avoid assigning one physical pixel to multiple polygons. Tiny polygons may use an all-touched pixel fallback and can include mixed boundary pixels.

Fifty samples per class is a starting point, not a guarantee of a good model. Evaluate your actual held-out results, improve digitization if needed, and keep the final test set independent. Nearby polygons can still make random splitting optimistic; geographic block testing is recommended for stronger evidence.

## Satellite bands and scope

The reference uses B02/B03/B04/B08/B11. This version adds **B8A** and **NDMI_8A** to reflect the lecturer's 8A–11–4 instruction. B08 remains for the reference indices (NDVI, NDWI, NDBI); B8A is a distinct narrow NIR band. All bands are put on a 10 m UTM 49S grid, with nearest-neighbor resampling. Resampling B8A/B11 from 20 m does not create additional spatial detail. SCL excludes nodata, saturation, cloud shadows, clouds, cirrus and snow/ice.

This matches the reference's **sample-polygon classifier**. The evaluation overlay colors testing polygons using their predicted class; it is not a classification of every pixel across East Java. Area statistics describe digitized samples only. Satellite basemap images are separate from the Sentinel-2 extraction dates.

## GitHub and Streamlit

See [the deployment guide](uts/deployment-guide.md). Upload the project **contents** to a GitHub repository. Use branch `main` and main file **`uts/deploy/app.py`** in Streamlit Community Cloud. After extraction/training, upload the new CSVs, evaluation GeoJSON and model metadata too. Do not upload raw GeoTIFF job folders or credentials.

**Your live Streamlit URL:** pending deployment. Replace this line with the actual URL once the app is live.

To publish documentation like the reference, enable GitHub Pages with the `gh-pages` branch after the included workflow runs. The deployment guide will be under `/uts/deployment-guide.html`. The notebooks are rendered without execution in GitHub Actions.

## Attribution and verification

Reference project snapshot: `382e8b35bdc816032cf7916917e769f6195d3281`, from the supplied ZIP. Dashboard CSS and tiled extraction are adapted from the reference; model analysis is rewritten to remove its hard-coded results and to use cross-validation within training. The supplied app PDF was used to check the dashboard sections.

Verified locally: source/geometry audit, offline tile plan, sample maps, dashboard execution, and pipeline tests with separate temporary fixtures. Remote satellite jobs, real training scores and live deployment require your account and have not been verified here.
