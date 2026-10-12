MATCHED PROVINCE MAP VIEWER -- BUILD 2026.10.12.2

The app(1).py you uploaded is the older polygon dashboard. It does not import classified_map.py and cannot render the province classification map. This package supplies a matched province app, helper and local map library.

1. Stop the old Streamlit process with Ctrl+C.
2. Extract this ZIP into the MAIN PROJECT folder that contains .venv and uts.
3. Replace uts/deploy/app.py and uts/deploy/classified_map.py. Keep uts/deploy/map_assets beside them.
4. Double-click START_VIEWER.bat, or run this command from the main folder:

.\.venv\Scripts\python.exe -m streamlit run uts/deploy/app.py --server.port 8502

5. Open http://localhost:8502 -- not the previous 8501 page.
6. Scroll to the page bottom and confirm: Map viewer build 2026.10.12.2.

The app loads the helper from its own deploy folder and refreshes cached map HTML when the helper/assets change. The complete map library is bundled locally. Generated model files, statistics, classification PNGs and satellite data are not altered.

No retraining, downloading or reclassification is needed.

If the map still fails on your machine, click "Open map separately: download HTML" directly below the map, open the downloaded HTML in your browser and share any "Map initialization error" message or browser Console error. This checks the map independently of Streamlit embedding.

Verification: matched renderer tested inside a real Streamlit iframe using temporary local class-image fixtures, with all non-local HTTP requests blocked. Five image layers, layer controls and zoom controls rendered without JavaScript errors. Actual user province exports were not available for this test.
