"""East Java land-cover dashboard: a scrolling, English, native-theme interface."""
from pathlib import Path
import json
import sys

import altair as alt
import geopandas as gpd
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="East Java Land Cover", page_icon="🌍", layout="wide", initial_sidebar_state="expanded")

# Styling is scoped to layout and components. Text and surfaces inherit the
# selected Streamlit theme; no light/dark theme is forced here.
st.markdown("""
<style>
    .block-container { max-width: 1480px; padding: 2.6rem 2.5rem 4rem; }
    [data-testid="stSidebar"] { border-right: 1px solid color-mix(in srgb, currentColor 10%, transparent); }
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: .85rem; }
    [data-testid="stHeading"] h2 { font-size: 1.65rem; letter-spacing: -.045em; font-weight: 650; padding-top: .65rem; }
    [data-testid="stHeading"] h3 { font-size: 1.13rem; letter-spacing: -.025em; font-weight: 600; }
    [data-testid="stVerticalBlockBorderWrapper"] > div {
        border-radius: 18px !important;
        border-color: color-mix(in srgb, currentColor 11%, transparent) !important;
        padding: 1.25rem !important;
        box-shadow: 0 3px 18px rgba(0,0,0,.025);
    }
    [data-testid="stMetricLabel"] { opacity: .7; font-size: .8rem; }
    [data-testid="stMetricValue"] { font-size: 2.2rem; font-weight: 650; letter-spacing: -.06em; }
    [data-testid="stDownloadButton"] button { border-radius: 10px; }
    [data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; }
    [data-testid="stExpander"] { border-radius: 12px; }
    .st-key-evaluation-map-frame iframe, .st-key-sample-map-frame iframe { border-radius: 13px; overflow: hidden; }
    .dash-brand { display:flex; align-items:center; gap:12px; margin-bottom:6px; }
    .dash-logo { display:grid; place-items:center; width:42px; height:42px; border-radius:13px; background:linear-gradient(135deg,#0891b2,#14b8a6); color:white; flex-shrink:0; }
    .dash-brand-title { font-size:1.16rem; letter-spacing:-.04em; font-weight:700; line-height:1.2; }
    .dash-brand-sub { font-size:.65rem; opacity:.52; letter-spacing:.15em; margin-top:4px; text-transform:uppercase; }
    .dash-hero { position:relative; overflow:hidden; border-radius:24px; padding:34px 38px;
        border:1px solid color-mix(in srgb,currentColor 12%,transparent);
        background:radial-gradient(ellipse at 100% 0%,rgba(20,184,166,.18),transparent 58%),color-mix(in srgb,currentColor 2%,transparent); }
    .dash-hero:after { content:""; position:absolute; right:-85px; top:-110px; width:310px; height:310px; border:1px solid rgba(20,184,166,.2); border-radius:50%; box-shadow:0 0 0 35px rgba(20,184,166,.035),0 0 0 70px rgba(20,184,166,.025),0 0 0 105px rgba(20,184,166,.02); pointer-events:none; }
    .dash-eyebrow { font-size:.68rem; font-weight:700; text-transform:uppercase; letter-spacing:.17em; opacity:.58; margin-bottom:15px; }
    .dash-hero-title { font-size:clamp(2rem,3.8vw,3.45rem); font-weight:750; letter-spacing:-.065em; line-height:1.1; margin:0 0 14px; position:relative; z-index:1; }
    .dash-hero-description { font-size:.97rem; line-height:1.7; max-width:650px; opacity:.7; margin:0 0 24px; position:relative; z-index:1; }
    .dash-chips { display:flex; gap:8px; flex-wrap:wrap; position:relative; z-index:1; }
    .dash-chip { font-size:.72rem; font-weight:500; border:1px solid color-mix(in srgb,currentColor 13%,transparent); padding:6px 11px; border-radius:30px; background:color-mix(in srgb,currentColor 3%,transparent); }
    .dash-chip-live { background:rgba(20,184,166,.1); border-color:rgba(20,184,166,.2); }
    .dash-dot { display:inline-block; width:6px; height:6px; background:#14b8a6; border-radius:50%; margin-right:6px; vertical-align:middle; }
    .dash-byline { font-size:.72rem; opacity:.55; margin-top:24px; }
    .dash-nav a { display:block; text-decoration:none; color:inherit; font-size:.82rem; opacity:.7; padding:7px 10px; border-radius:8px; margin-bottom:2px; }
    .dash-nav a:hover { background:color-mix(in srgb,currentColor 6%,transparent); opacity:1; }
    .dash-nav span { font-size:.62rem; opacity:.45; margin-right:12px; }
    .dash-section { margin:1.7rem 0 .5rem; display:flex; align-items:center; gap:10px; }
    .dash-section-number { font-size:.67rem; padding:4px 7px; border:1px solid color-mix(in srgb,currentColor 13%,transparent); border-radius:6px; opacity:.55; }
    .dash-section-name { font-size:.66rem; font-weight:600; letter-spacing:.15em; text-transform:uppercase; opacity:.55; }
    .dash-stat-note { display:flex; flex-wrap:wrap; gap:10px 22px; margin:0 0 8px; font-size:.76rem; opacity:.65; }
    .dash-legend { display:flex; flex-wrap:wrap; gap:8px; margin:6px 0 8px; }
    .dash-legend-item { font-size:.7rem; border:1px solid color-mix(in srgb,currentColor 10%,transparent); padding:5px 9px; border-radius:8px; }
    .dash-legend-item i { display:inline-block; width:7px; height:7px; border-radius:50%; margin-right:6px; }
    @media(max-width:760px) { .block-container{padding:1.2rem 1rem 3rem;} .dash-hero{padding:25px 23px;} }
</style>
""", unsafe_allow_html=True)

def section_label(number, name):
    st.markdown(f'<div class="dash-section"><span class="dash-section-number">{number:02d}</span><span class="dash-section-name">{name}</span></div>',unsafe_allow_html=True)

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parent / "code"))
from pipeline import make_map, CLASSES

CLASS_NAMES = {
    "Sawah": "Farmland",
    "Pemukiman": "Built-up areas",
    "Hutan Non-Mangrove": "Forest",
    "Air": "Water bodies",
    "Hutan Mangrove": "Mangrove forest",
}
CLASS_ICONS = {"Sawah":"🟨", "Pemukiman":"🟥", "Hutan Non-Mangrove":"🟩", "Air":"🟦", "Hutan Mangrove":"🌿"}
DISPLAY_COLUMNS = {
    "label_teks":"Land-cover class", "polygons":"Polygons", "sample_area_km2":"Sample area (km²)",
    "poligon_id":"Polygon ID", "poligon_no":"Source index", "source_feature":"Source feature",
    "label":"Class code", "n_piksel":"Valid pixels", "lon_centroid":"Longitude", "lat_centroid":"Latitude",
    "kelas_asli":"Actual class", "prediksi_knn":"Predicted class", "benar":"Correct prediction",
    "Kategori":"Category", "Precision":"Precision", "Recall":"Recall", "F1_Score":"F1 score", "Support":"Support",
    "Fitur":"Feature", "Importance":"Importance", "Std":"Standard deviation", "k":"Neighbors (k)",
    "Akurasi_CV":"CV accuracy (%)", "Std_CV":"CV standard deviation (%)", "area_km2":"Sample area (km²)",
    "class":"Class", "action":"Action", "reason":"Reason", "polygon_a":"Polygon A", "polygon_b":"Polygon B", "same_class":"Same class",
}

@st.cache_data
def read_table(path, modified):
    return pd.read_csv(path)

@st.cache_data
def read_geojson(path, modified):
    return gpd.read_file(path)

def table(name):
    path=BASE/name
    return read_table(str(path),path.stat().st_mtime_ns)

def spatial(name):
    path=BASE/name
    return read_geojson(str(path),path.stat().st_mtime_ns)

def english_table(data):
    out=data.copy()
    for column in out.select_dtypes(include=["object","string"]).columns:
        out[column]=out[column].replace(CLASS_NAMES | {"macro avg":"Macro average", "weighted avg":"Weighted average", "accuracy":"Accuracy", "repaired":"Repaired", "excluded":"Excluded"})
    return out.rename(columns=DISPLAY_COLUMNS)

def map_html(data, selected, prediction=False):
    # Build from the original labels, so the trained model/data are untouched.
    # Translate only the presentation copy embedded in the Leaflet map.
    html=make_map(data,selected=selected,prediction=prediction).get_root().render()
    translations={
        **CLASS_NAMES,
        "Batas Jawa Timur":"East Java boundary", "Satelit Esri":"Esri satellite",
        "Tanpa piksel valid":"No valid pixels", "Belum diuji":"Not tested",
        "Tidak diuji":"Not evaluated", "Testing":"Test set", "Training":"Training set",
        "Benar":"Correct", "Salah":"Incorrect", "SALAH":"INCORRECT", "TRAIN":"TRAIN", "TEST":"TEST",
        "poligon_id":"Polygon ID", "label_teks":"Actual class", "status_split":"Dataset split",
        "prediksi_ml":"Predicted class", "evaluasi":"Evaluation",
    }
    import re
    # Match original terms once; translated words must not be translated again.
    pattern=re.compile("|".join(re.escape(term) for term in sorted(translations,key=len,reverse=True)))
    html=pattern.sub(lambda m:translations[m.group(0)],html)
    map_style="""<style>
    .leaflet-container{font-family:Inter,system-ui,sans-serif!important;}
    .leaflet-control-layers,.leaflet-bar{border:0!important;border-radius:10px!important;box-shadow:0 5px 22px rgba(0,0,0,.22)!important;overflow:hidden;}
    .leaflet-control-layers{padding:10px 12px!important;line-height:1.8!important;}
    .leaflet-control-layers label{font-size:11px!important;}
    .leaflet-tooltip{border-radius:9px!important;padding:8px 11px!important;}
    </style>"""
    return html.replace("</head>",map_style+"</head>")

def heatmap(frame, title, correlation=False):
    data=frame.copy()
    data.index=data.index.map(lambda x:CLASS_NAMES.get(x,x))
    data.columns=[CLASS_NAMES.get(x,x) for x in data.columns]
    data.index.name="Actual" if not correlation else "Feature"
    long=data.reset_index().melt(id_vars=[data.index.name],var_name="Predicted" if not correlation else "Other feature",value_name="Value")
    y=data.index.name; x="Predicted" if not correlation else "Other feature"
    scale=alt.Scale(scheme="redblue",domain=[-1,1]) if correlation else alt.Scale(scheme="tealblues")
    base=alt.Chart(long).encode(x=alt.X(f"{x}:N",sort=list(data.columns),title=x,axis=alt.Axis(labelAngle=-35)),y=alt.Y(f"{y}:N",sort=list(data.index),title=y))
    blocks=base.mark_rect(cornerRadius=4,strokeWidth=2,strokeOpacity=0).encode(color=alt.Color("Value:Q",scale=scale,title="Correlation" if correlation else "Polygons"),tooltip=[y,x,alt.Tooltip("Value:Q",format=".2f" if correlation else ".0f")])
    cutoff=float(long.Value.max())*.55
    labels=base.mark_text(fontSize=12).encode(text=alt.Text("Value:Q",format=".2f" if correlation else ".0f"),color=alt.condition("abs(datum.Value) > 0.55" if correlation else alt.datum.Value>cutoff,alt.value("white"),alt.value("#18232F")))
    return (blocks+labels).properties(height=330 if not correlation else 480,title=title)

status=json.loads((BASE/"data_status.json").read_text())
trained=bool(status.get("training_complete")) and (BASE/"model_metadata.json").exists()
samples=spatial("samples.geojson")
summary=table("sample_summary.csv")
metrics=table("ringkasan_model_knn.csv").set_index("Metrik").Nilai if trained else None

with st.sidebar:
    st.markdown('<div class="dash-brand"><div class="dash-logo"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M3 7l9-5 9 5-9 5-9-5zm0 5l9 5 9-5M3 17l9 5 9-5"/></svg></div><div><div class="dash-brand-title">East Java Atlas</div><div class="dash-brand-sub">Land-cover intelligence</div></div></div>',unsafe_allow_html=True)
    st.divider()
    st.markdown("**Joni Kumar Meghwar**")
    st.caption("Student ID · 240411100234")
    st.subheader("Map layers")
    st.caption("Choose which land-cover classes to display.")
    selected=[cls for cls in CLASSES if st.checkbox(CLASS_NAMES[cls],value=True,key=f"map_{cls}")]
    st.divider()
    st.caption("EXPLORE THE DASHBOARD")
    st.markdown('<nav class="dash-nav"><a href="#evaluation-map"><span>01</span>Spatial overview</a><a href="#model-performance"><span>02</span>Model performance</a><a href="#prediction-details"><span>03</span>Prediction explorer</a><a href="#sample-map"><span>04</span>Sample atlas</a><a href="#data-exploration"><span>05</span>Data insights</a><a href="#project-purpose"><span>06</span>About the study</a></nav>',unsafe_allow_html=True)
    st.divider()
    st.caption("Sentinel-2 · Level-2A\n\nScaled k-NN · k = 5\n\nBands: B02, B03, B04, B08, B8A, B11")
    if trained:st.success("Model results available")
    else:st.info("Digitized samples available")

model_badge="Model evaluated" if trained else "Sample data available"
st.markdown(f"""<section class="dash-hero">
<div class="dash-eyebrow">EARTH OBSERVATION / EAST JAVA, INDONESIA</div>
<h1 class="dash-hero-title">Land cover, in focus.</h1>
<p class="dash-hero-description">A satellite view of East Java’s landscapes. Explore the places we’ve sampled, the classes we predict, and the evidence behind every result.</p>
<div class="dash-chips"><span class="dash-chip dash-chip-live"><span class="dash-dot"></span>{model_badge}</span><span class="dash-chip">Sentinel-2 · Level-2A</span><span class="dash-chip">5 land-cover classes</span><span class="dash-chip">Scaled k-NN</span></div>
<div class="dash-byline">Joni Kumar Meghwar &nbsp; / &nbsp; Student ID 240411100234 &nbsp; / &nbsp; Data Science Midterm</div>
</section>""",unsafe_allow_html=True)

st.write("")
cols=st.columns(4)
if trained:
    cards=[("Test accuracy",f"{metrics['Overall Accuracy Testing']:.2f}%","Performance on held-out polygons"),
           ("Training accuracy",f"{metrics['Accuracy Training']:.2f}%","Fit to the training samples"),
           ("Sample polygons",f"{int(metrics['Total Sampel Poligon']):,}","Polygons with valid spectral features"),
           ("Incorrect predictions",f"{int(metrics['Jumlah Prediksi Salah']):,}","Misclassified test polygons")]
else:
    cards=[("Original polygons",status['original_polygons'],"Uploaded digitization"),("Usable polygons",status['usable_polygons'],"Valid area geometries"),("Land-cover classes",5,"Water, built-up, farmland, forest, mangrove"),("Model status","Pending","Evaluation results not available yet")]
for col,(label,value,note) in zip(cols,cards):
    with col:
        with st.container(border=True, key=f"overview-card-{label.lower().replace(' ' ,'-')}"):
            st.metric(label,value)
            st.caption(note)
if trained:
    st.markdown(f'<div class="dash-stat-note"><span><b>Kappa</b> {metrics["Cohen Kappa Index"]:.4f}</span><span><b>Training</b> {int(metrics["Jumlah Data Latih (70%)"])} polygons</span><span><b>Test set</b> {int(metrics["Jumlah Data Uji (30%)"])} polygons</span><span><b>Correct</b> {int(metrics["Jumlah Prediksi Benar"])} predictions</span></div>',unsafe_allow_html=True)
else:
    st.info("This dashboard currently shows digitized samples. Model evaluation will appear when trained results are available.")

section_label(1,"Spatial overview")
st.header("Explore the landscape",anchor="evaluation-map")
with st.container(border=True,key="evaluation-map-frame"):
    st.subheader("Classification on satellite imagery")
    st.caption("Switch between ground truth and predictions. Filter land-cover classes in the sidebar.")
    if trained:
        show_predictions=st.toggle("Color test polygons by their predicted class",value=True)
        components.html(map_html(spatial("evaluation.geojson"),selected,prediction=show_predictions),height=620,scrolling=False)
        st.markdown('<div class="dash-legend"><span class="dash-legend-item"><i style="background:#0284c7"></i>Training samples</span><span class="dash-legend-item"><i style="background:#16a34a"></i>Correct predictions</span><span class="dash-legend-item"><i style="background:#f97316"></i>Incorrect predictions</span></div>',unsafe_allow_html=True)
        st.caption("Cyan boundaries identify training polygons; dashed magenta boundaries identify test polygons. Hover over polygons to compare actual and predicted classes. Class filters follow predicted colors when prediction mode is enabled.")
    else:
        st.info("The evaluation map is not available yet. Explore the sample map below.")

section_label(2,"Model performance")
st.header("How well does the model perform?",anchor="model-performance")
if trained:
    pred=table("prediksi_data_uji.csv")
    left,right=st.columns(2)
    with left:
        with st.container(border=True):
            cm=table("confusion_matrix.csv").set_index("Aktual")
            st.subheader("Confusion matrix")
            st.caption("Actual classes versus model predictions on the held-out test set.")
            st.altair_chart(heatmap(cm,""),width="stretch")
            with st.expander("View classification report"):
                st.dataframe(english_table(table("metrik_evaluasi_knn.csv")),hide_index=True,width="stretch")
    with right:
        with st.container(border=True):
            st.subheader("Actual vs. predicted classes")
            st.caption("Compare the number of test polygons assigned to each class.")
            comparison=pd.DataFrame({"Actual":pred.kelas_asli.value_counts(),"Predicted":pred.prediksi_knn.value_counts()}).fillna(0).astype(int)
            comparison.index=comparison.index.map(CLASS_NAMES)
            st.bar_chart(comparison,height=330,x_label="Land-cover class",y_label="Polygons",stack=False)
            with st.expander("View counts"):
                st.dataframe(comparison,width="stretch")
    left,right=st.columns(2)
    with left:
        with st.container(border=True):
            st.subheader("Feature importance")
            st.caption("Change in test accuracy when each feature is shuffled; error bars show variation.")
            fi=english_table(table("kepentingan_fitur.csv"))
            fi["Lower"]=fi.Importance-fi['Standard deviation'];fi["Upper"]=fi.Importance+fi['Standard deviation']
            base=alt.Chart(fi).encode(y=alt.Y("Feature:N",sort="-x",title=None))
            bars=base.mark_bar(color="#14b8a6",cornerRadiusEnd=4).encode(x=alt.X("Importance:Q",title="Mean decrease in accuracy"),tooltip=["Feature",alt.Tooltip("Importance:Q",format=".4f"),alt.Tooltip("Standard deviation:Q",format=".4f")])
            errors=base.mark_rule().encode(x="Lower:Q",x2="Upper:Q")
            st.altair_chart((bars+errors).properties(height=330),width="stretch")
            with st.expander("View feature scores"):
                st.dataframe(fi.drop(columns=["Lower","Upper"]),hide_index=True,width="stretch")
    with right:
        with st.container(border=True):
            st.subheader("Neighbor validation")
            st.caption("Cross-validation accuracy for different k values, using training data only.")
            cv=table("kurva_validasi_k.csv")
            chart=alt.Chart(cv).mark_line(point=alt.OverlayMarkDef(filled=True,size=55),color="#14b8a6",strokeWidth=2.5).encode(x=alt.X("k:O",title="Number of neighbors (k)"),y=alt.Y("Akurasi_CV:Q",title="CV accuracy (%)",scale=alt.Scale(zero=False)),tooltip=[alt.Tooltip("k:O",title="Neighbors"),alt.Tooltip("Akurasi_CV:Q",title="CV accuracy (%)",format=".2f")]).properties(height=330)
            st.altair_chart(chart,width="stretch")
            st.caption("The model keeps k = 5 to follow the reference workflow. The test set is not used to select k.")
    st.caption("Training accuracy describes fit to known samples. Use held-out test metrics to assess generalization.")
else:
    st.info("Performance charts will appear when model results are available.")

section_label(3,"Prediction explorer")
st.header("Inspect every prediction",anchor="prediction-details")
with st.container(border=True):
    if trained:
        left,right=st.columns([3,1])
        with left:
            actual_classes=st.multiselect("Actual land-cover class",options=list(CLASSES),default=list(CLASSES),format_func=lambda c:CLASS_NAMES[c])
        with right:
            condition=st.selectbox("Prediction status",["All predictions","Correct","Incorrect"])
        view=pred[pred.kelas_asli.isin(actual_classes)].copy()
        if condition!="All predictions":view=view[view.benar.eq(condition=="Correct")]
        display=english_table(view).drop(columns=["Land-cover class","Class code"],errors="ignore")
        first=[c for c in ["Polygon ID","Actual class","Predicted class","Correct prediction","Valid pixels","Longitude","Latitude"] if c in display]
        st.caption(f"Showing {len(view)} of {len(pred)} test polygons.")
        st.dataframe(display[first],hide_index=True,width="stretch",height=360)
        st.download_button("Download filtered predictions",display.to_csv(index=False).encode("utf-8"),"east_java_predictions.csv","text/csv")
        missing=table("missing_satellite_polygons.csv")
        if len(missing):st.caption(f"{len(missing)} digitized polygons had no valid satellite pixels and were excluded from modeling.")
    else:st.info("No test predictions are available yet.")

section_label(4,"Sample atlas")
st.header("Your sample atlas",anchor="sample-map")
with st.container(border=True,key="sample-map-frame"):
    st.write("Review your original class labels over satellite imagery.")
    components.html(map_html(samples,selected),height=600,scrolling=False)
    st.caption("Use the sidebar checkboxes or the map’s layer control to isolate a class. The satellite basemap may show a different acquisition date from the Sentinel-2 imagery used for modeling.")
    st.download_button("Download cleaned sample GeoJSON",(BASE/"samples.geojson").read_bytes(),"east_java_samples.geojson","application/geo+json")

section_label(5,"Data insights")
st.header("Understand the data",anchor="data-exploration")
left,right=st.columns([1,1])
with left:
    with st.container(border=True):
        st.subheader("Sample distribution")
        counts=english_table(summary).set_index("Land-cover class")
        st.bar_chart(counts[["Polygons"]],height=300,x_label="Land-cover class",y_label="Polygons")
with right:
    with st.container(border=True):
        st.subheader("Digitized sample area")
        st.dataframe(english_table(summary),hide_index=True,width="stretch")
        st.caption("Areas describe digitized sample polygons, not the total land-cover area of East Java. Overlapping sample areas may be counted more than once.")
with st.expander("Data quality and geometry checks"):
    issues=table("geometry_issues.csv")
    st.caption("Original features 70 and 71 (built-up) and 148 (farmland) have no recoverable polygon area. Nine crossing geometries were repaired.")
    st.dataframe(english_table(issues),hide_index=True,width="stretch")
    overlaps=table("overlap_issues.csv")
    if len(overlaps):
        st.caption(f"{len(overlaps)} overlapping polygon pairs were identified. Shared pixels are removed during extraction to prevent the same observation appearing in multiple polygons.")
        st.dataframe(english_table(overlaps),hide_index=True,width="stretch")
if trained:
    source=BASE.parent/"data/csv/poligon/centroid_poligon.csv"
    cen=read_table(str(source),source.stat().st_mtime_ns)
    with st.container(border=True):
        st.subheader("Spectral feature relationships")
        features=cen.select_dtypes("number").drop(columns=["label","n_piksel","lon_centroid","lat_centroid"],errors="ignore")
        st.altair_chart(heatmap(features.corr(),"",correlation=True),width="stretch")
        with st.expander("Explore mean spectral features by polygon"):
            st.dataframe(english_table(cen),hide_index=True,width="stretch")

section_label(6,"About the study")
st.header("A clearer view of coastal landscapes",anchor="project-purpose")
with st.container(border=True):
    st.subheader("Understand land cover. Review coastal ecosystems.")
    st.write("Support preliminary land-use and coastal review in East Java by distinguishing built-up areas, farmland, water bodies, inland forest, and mangrove forest. The main focus is separating mangroves from inland forest and reviewing classification errors in their geographic context.")
    a,b,c=st.columns(3)
    a.markdown("**01 · Observe**\n\nUse digitized polygons and real Sentinel-2 spectral bands to describe land-cover samples.")
    b.markdown("**02 · Classify**\n\nTrain a scaled, distance-weighted k-NN model and evaluate independent test polygons.")
    c.markdown("**03 · Explore**\n\nInspect class layers, model errors, and spectral relationships on an interactive map.")
    with st.expander("Method and interpretation"):
        st.write("The workflow follows CRISP-DM: business understanding, data understanding, preparation, modeling, evaluation, and deployment. Features are averaged within sample polygons; the 70/30 split is stratified at polygon level, and the scaler is fitted only on training data.")
        st.write("B8A, B11, and B04 support vegetation and moisture analysis. B08 is retained for the reference indices. Resampling bands from 20 m to a 10 m grid aligns observations without creating new spatial detail.")
        st.write("The model classifies sampled polygons. It does not map every pixel across East Java. Nearby samples can share spectral and geographic characteristics; spatially independent block testing would provide stronger evidence of regional generalization.")
st.divider()
st.caption("East Java Land Cover · Joni Kumar Meghwar · 240411100234")
st.caption("Workflow adapted from Muhammad Ainul Fuady/PSD. Digitized samples supplied by Joni Kumar Meghwar.")
