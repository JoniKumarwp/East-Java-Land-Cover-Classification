# Verification

Local checks completed on 11 October 2026:

- Original file has 250 labeled features; normalized data has 247 valid area geometries across all five classes.
- Nine geometry repairs and exclusions of original features 70, 71 and 148 are recorded. Original uploaded bytes remain unchanged.
- Fifteen overlapping polygon pairs are recorded.
- Offline tile plan creates 18 tiles without authentication or submission.
- Sample Leaflet map and empty/single-class filtering are checked.
- Streamlit dashboard starts without an exception and responds to class toggles before training.
- In a separate temporary copy, synthetic fixtures exercised polygon-level splitting, the six evaluation CSV exports, model export, trained dashboard, class/status filters, and raster pixel extraction with B8A.
- An overlapping-polygon raster fixture verifies that shared pixels are excluded.
- Temporary fixture results were deleted and are not included in this project.
- Python files compile and all three notebooks validate.
- Jupyter Book builds successfully, including `uts/deployment-guide.html`, without executing satellite jobs.

Not completed here: authenticated Copernicus processing, actual Sentinel-2 results/accuracy, public GitHub push, GitHub Pages publication or Streamlit deployment. Those need the user's accounts. All model results shown after running the project must come from the real extracted satellite data.
