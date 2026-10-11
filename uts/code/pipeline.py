"""Joni's UTS pipeline, adapted from Muhammad Ainul Fuady/PSD's UTS workflow."""
from pathlib import Path
import argparse, hashlib, json, shutil
import numpy as np
import pandas as pd
import geopandas as gpd
import folium
from shapely.geometry import shape, mapping, MultiPolygon
from shapely import make_valid
from shapely.validation import explain_validity

ROOT = Path(__file__).resolve().parents[2]
UTS = ROOT / 'uts'
GEO = UTS / 'data/geojson'
DEPLOY = UTS / 'deploy'
RAW = GEO / 'EastJawa_Data.geojson'
CLASSES = {'Sawah': 1, 'Pemukiman': 2, 'Hutan Non-Mangrove': 3, 'Air': 4, 'Hutan Mangrove': 5}
ALIASES = {'Air':'Air', 'Water':'Air', 'Building':'Pemukiman', 'Farmland':'Sawah', 'Mangroves':'Hutan Mangrove', 'Forest':'Hutan Non-Mangrove'}
COLORS = {'Air':'#1f77b4','Hutan Mangrove':'#2ca02c','Hutan Non-Mangrove':'#006400','Pemukiman':'#d62728','Sawah':'#bcbd22'}
BANDS = ['B02','B03','B04','B08','B8A','B11']
FEATURES = BANDS + ['NDVI','NDWI','MNDWI','NDBI','NDMI_8A']

def polygon_parts(g):
    if g.geom_type == 'Polygon': return [g]
    if hasattr(g, 'geoms'): return [p for part in g.geoms for p in polygon_parts(part)]
    return []

def prepare():
    data = json.loads(RAW.read_text(encoding='utf-8'))
    features, issues = [], []
    for i, f in enumerate(data['features'], start=1):
        props = f.get('properties') or {}
        label = ALIASES.get(props.get('Class') or props.get('Type'))
        if label is None: raise ValueError(f'Unknown class at feature {i}: {props}')
        try:
            geom = shape(f['geometry'])
            if not geom.is_valid:
                reason = explain_validity(geom)
                parts = polygon_parts(make_valid(geom))
                if not parts: raise ValueError(reason + '; no polygon area after repair')
                geom = parts[0] if len(parts)==1 else MultiPolygon(parts)
                issues.append({'source_feature':i,'class':label,'action':'repaired','reason':reason})
            if geom.is_empty or geom.area <= 0: raise ValueError('Empty or zero-area geometry')
        except Exception as e:
            issues.append({'source_feature':i,'class':label,'action':'excluded','reason':str(e)})
            continue
        features.append({'type':'Feature','geometry':mapping(geom),'properties':{
            'source_feature':i,'poligon_no':i-1,'poligon_id':f'JONI_{i:04d}',
            'label_teks':label,'label':CLASSES[label]}})
    GEO.mkdir(parents=True, exist_ok=True); DEPLOY.mkdir(parents=True, exist_ok=True)
    clean = {'type':'FeatureCollection','features':features}
    (GEO/'jawatimur_5kelas.geojson').write_text(json.dumps(clean), encoding='utf-8')
    pd.DataFrame(issues,columns=['source_feature','class','action','reason']).to_csv(DEPLOY/'geometry_issues.csv',index=False)
    g = gpd.GeoDataFrame.from_features(clean,crs='EPSG:4326')
    metric = g.to_crs(32749)
    g['area_km2'] = metric.area.to_numpy()/1e6
    centers = metric.centroid.to_crs(4326)
    g['lon_centroid'],g['lat_centroid'] = centers.x.to_numpy(),centers.y.to_numpy()
    overlap=[]
    for i,geom in enumerate(g.geometry):
        for j in g.sindex.query(geom,predicate='intersects'):
            if j > i and geom.intersection(g.geometry.iloc[j]).area > 1e-12:
                overlap.append({'polygon_a':g.poligon_id.iloc[i],'polygon_b':g.poligon_id.iloc[j],
                                'same_class':g.label.iloc[i]==g.label.iloc[j]})
    pd.DataFrame(overlap,columns=['polygon_a','polygon_b','same_class']).to_csv(DEPLOY/'overlap_issues.csv',index=False)
    summary = g.groupby('label_teks').agg(polygons=('poligon_id','size'),sample_area_km2=('area_km2','sum')).reset_index()
    summary.to_csv(DEPLOY/'sample_summary.csv',index=False)
    g.drop(columns='geometry').to_csv(DEPLOY/'sample_polygons.csv',index=False)
    shutil.copy(GEO/'jawatimur_5kelas.geojson',DEPLOY/'samples.geojson')
    shutil.copy(GEO/'jawa_timur_provinsi.geojson',DEPLOY/'province.geojson')
    status={'source_sha256':hashlib.sha256(RAW.read_bytes()).hexdigest(),'original_polygons':len(data['features']),
            'usable_polygons':len(g),'excluded':sum(i['action']=='excluded' for i in issues),
            'repaired':sum(i['action']=='repaired' for i in issues),'overlap_pairs':len(overlap),'training_complete':False}
    (DEPLOY/'data_status.json').write_text(json.dumps(status,indent=2))
    for name in ['ringkasan_model_knn.csv','confusion_matrix.csv','metrik_evaluasi_knn.csv','kepentingan_fitur.csv','kurva_validasi_k.csv','prediksi_data_uji.csv','model_metadata.json','evaluation.geojson','map_lulc_predicted.html']:
        (DEPLOY/name).unlink(missing_ok=True)
    make_map(g).save(str(DEPLOY/'map_lulc.html'))
    print(summary.to_string(index=False)); print(json.dumps(status,indent=2))
    return g

def make_map(g, selected=None, prediction=False):
    m=folium.Map(location=[-7.6,112.6],zoom_start=8,tiles=None)
    folium.TileLayer(tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics and the GIS User Community',name='Satelit Esri').add_to(m)
    folium.TileLayer('OpenStreetMap',name='OpenStreetMap').add_to(m)
    if (DEPLOY/'province.geojson').exists():
        folium.GeoJson(json.loads((DEPLOY/'province.geojson').read_text()),name='Batas Jawa Timur',
            style_function=lambda f:{'color':'#EA580C','weight':1,'fillOpacity':0}).add_to(m)
    shown_class=g.label_teks.copy()
    if prediction and 'status_split' in g:
        testing=g.status_split.eq('Testing')
        shown_class.loc[testing]=g.loc[testing,'prediksi_ml']
    for cls in selected if selected is not None else CLASSES:
        sub=g[shown_class==cls]
        if len(sub)==0: continue
        fields=['poligon_id','label_teks']
        if 'status_split' in g: fields+=['status_split','prediksi_ml','evaluasi']
        layer=folium.FeatureGroup(name=cls,show=True)
        def style(f):
            p=f['properties']; color=COLORS.get(p.get('prediksi_ml') if prediction and p.get('status_split')=='Testing' else p['label_teks'],COLORS[p['label_teks']])
            boundary='#0284c7' if p.get('status_split')=='Training' else '#c026d3' if p.get('status_split')=='Testing' else color
            return {'color':boundary,'fillColor':color,'weight':2,'fillOpacity':0.45,'dashArray':'5,5' if p.get('status_split')=='Testing' else None}
        folium.GeoJson(json.loads(sub.to_json()),style_function=style,tooltip=folium.GeoJsonTooltip(fields=fields)).add_to(layer)
        if 'status_split' in sub:
            for row in sub.itertuples():
                if row.status_split not in {'Training','Testing'}: continue
                text,bg=('TRAIN','#0284c7') if row.status_split=='Training' else ('TEST ✓','#16a34a') if row.evaluasi=='Benar' else ('SALAH','#EA580C')
                point=row.geometry.representative_point()
                folium.Marker([point.y,point.x],tooltip=f'{row.poligon_id} | {row.label_teks} | {row.prediksi_ml}',
                    icon=folium.DivIcon(html=f'<div style="color:white;background:{bg};border:1px solid white;border-radius:10px;font:bold 9px Arial;text-align:center;padding:3px;width:46px">{text}</div>',icon_size=(48,18))).add_to(layer)
        layer.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    b=g.total_bounds
    m.fit_bounds([[b[1],b[0]],[b[3],b[2]]])
    return m

def add_indices(df):
    def nd(a,b):
        den=df[a]+df[b]
        return (df[a]-df[b])/den.replace(0,np.nan)
    df=df.copy()
    for name,a,b in [('NDVI','B08','B04'),('NDWI','B03','B08'),('MNDWI','B03','B11'),('NDBI','B11','B08'),('NDMI_8A','B8A','B11')]: df[name]=nd(a,b)
    return df

def train(csv_path=None):
    from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.neighbors import KNeighborsClassifier
    from sklearn.metrics import accuracy_score,cohen_kappa_score,classification_report,confusion_matrix
    from sklearn.inspection import permutation_importance
    import joblib
    csv_path=Path(csv_path) if csv_path else UTS/'data/csv/hasil_s2_piksel/piksel_s2.csv'
    if not csv_path.exists(): raise FileNotFoundError('Run crawling first: python uts/code/crawling.py')
    df=add_indices(pd.read_csv(csv_path))
    needed=BANDS+['poligon_id','label','label_teks','lon','lat']
    if missing:=set(needed)-set(df): raise ValueError(f'Missing CSV columns: {missing}')
    df=df.replace([np.inf,-np.inf],np.nan).dropna(subset=FEATURES)
    samples=gpd.read_file(DEPLOY/'samples.geojson')
    if not set(df.poligon_id)<=set(samples.poligon_id): raise ValueError('Pixel CSV contains unknown polygon IDs. Re-extract your own data.')
    labels=samples.set_index('poligon_id').label_teks
    if not df.label_teks.eq(df.poligon_id.map(labels)).all(): raise ValueError('CSV labels differ from your GeoJSON.')
    # Polygon-level split prevents pixels from the same polygon entering both sets.
    cen=df.groupby('poligon_id')[FEATURES].mean().join(df.groupby('poligon_id').agg(
        label=('label','first'),label_teks=('label_teks','first'),n_piksel=('label','size'))).reset_index()
    cen=cen.merge(pd.read_csv(DEPLOY/'sample_polygons.csv')[['poligon_id','lon_centroid','lat_centroid']],on='poligon_id',validate='one_to_one')
    pd.DataFrame({'poligon_id':sorted(set(samples.poligon_id)-set(cen.poligon_id))}).to_csv(DEPLOY/'missing_satellite_polygons.csv',index=False)
    if set(cen.label_teks)!=set(CLASSES) or cen.label_teks.value_counts().min()<5:
        raise ValueError('Need at least 5 polygons with valid satellite pixels for EVERY class. Widen dates or redraw small polygons.')
    tr,te=train_test_split(cen,test_size=.3,random_state=42,stratify=cen.label_teks)
    for folder,polys in [('training',tr),('testing',te)]:
        out=UTS/'data/csv'/folder;out.mkdir(parents=True,exist_ok=True)
        polys.to_csv(out/f'poligon_{"train" if folder=="training" else "test"}.csv',index=False)
        df[df.poligon_id.isin(polys.poligon_id)].to_csv(out/f'piksel_{"train" if folder=="training" else "test"}.csv',index=False)
    out=UTS/'data/csv/poligon';out.mkdir(parents=True,exist_ok=True);cen.to_csv(out/'centroid_poligon.csv',index=False)
    def model(k): return make_pipeline(StandardScaler(),KNeighborsClassifier(n_neighbors=k,weights='distance',metric='euclidean'))
    cv=StratifiedKFold(n_splits=min(5,int(tr.label_teks.value_counts().min())),shuffle=True,random_state=42)
    curve=[]
    for k in range(1,min(15,int(len(tr)*.7))+1):
        scores=cross_val_score(model(k),tr[FEATURES],tr.label_teks,cv=cv)
        curve.append({'k':k,'Akurasi_CV':scores.mean()*100,'Std_CV':scores.std()*100})
    # Keep k=5 as in the reference; CV is reported without consulting the test set.
    fitted=model(5).fit(tr[FEATURES],tr.label_teks)
    pred=fitted.predict(te[FEATURES]); acc=accuracy_score(te.label_teks,pred)
    train_acc=accuracy_score(tr.label_teks,fitted.predict(tr[FEATURES]));kappa=cohen_kappa_score(te.label_teks,pred)
    order=list(fitted.classes_)
    pd.DataFrame(confusion_matrix(te.label_teks,pred,labels=order),index=pd.Index(order,name='Aktual'),columns=order).to_csv(DEPLOY/'confusion_matrix.csv')
    report=classification_report(te.label_teks,pred,output_dict=True,zero_division=0)
    pd.DataFrame(report).T.rename_axis('Kategori').reset_index().rename(columns={'precision':'Precision','recall':'Recall','f1-score':'F1_Score','support':'Support'}).to_csv(DEPLOY/'metrik_evaluasi_knn.csv',index=False)
    metrics={'Overall Accuracy Testing':acc*100,'Accuracy Training':train_acc*100,'Cohen Kappa Index':kappa,
             'Total Sampel Poligon':len(cen),'Jumlah Data Latih (70%)':len(tr),'Jumlah Data Uji (30%)':len(te),
             'Jumlah Prediksi Benar':int(np.sum(te.label_teks.to_numpy()==pred)),'Jumlah Prediksi Salah':int(np.sum(te.label_teks.to_numpy()!=pred)),'Nilai k':5}
    pd.DataFrame([{'Metrik':k,'Nilai':v} for k,v in metrics.items()]).to_csv(DEPLOY/'ringkasan_model_knn.csv',index=False)
    imp=permutation_importance(fitted,te[FEATURES],te.label_teks,n_repeats=30,random_state=42)
    pd.DataFrame({'Fitur':FEATURES,'Importance':imp.importances_mean,'Std':imp.importances_std}).sort_values('Importance',ascending=False).to_csv(DEPLOY/'kepentingan_fitur.csv',index=False)
    pd.DataFrame(curve).to_csv(DEPLOY/'kurva_validasi_k.csv',index=False)
    test=te.copy();test['kelas_asli']=test.label_teks;test['prediksi_knn']=pred;test['benar']=test.kelas_asli==test.prediksi_knn
    test.to_csv(DEPLOY/'prediksi_data_uji.csv',index=False)
    samples['status_split']=np.where(samples.poligon_id.isin(tr.poligon_id),'Training',np.where(samples.poligon_id.isin(te.poligon_id),'Testing','Tanpa piksel valid'))
    samples['prediksi_ml']=samples.poligon_id.map(test.set_index('poligon_id').prediksi_knn).fillna('Belum diuji')
    samples['evaluasi']=samples.poligon_id.map(test.set_index('poligon_id').benar).map({True:'Benar',False:'Salah'}).fillna('Tidak diuji')
    samples.to_file(DEPLOY/'evaluation.geojson',driver='GeoJSON')
    make_map(samples,prediction=True).save(str(DEPLOY/'map_lulc_predicted.html'))
    (UTS/'models').mkdir(exist_ok=True);joblib.dump(fitted,UTS/'models/model_lulc_knn.pkl')
    metadata={'features':FEATURES,'bands':BANDS,'k':5,'split':'polygon-stratified 70/30, random_state=42',
              'pixel_csv_sha256':hashlib.sha256(csv_path.read_bytes()).hexdigest(),
              'source_sha256':hashlib.sha256(RAW.read_bytes()).hexdigest(),'scope':'Mean spectral features of sample polygons; not a province-wide raster map'}
    (DEPLOY/'model_metadata.json').write_text(json.dumps(metadata,indent=2))
    status=json.loads((DEPLOY/'data_status.json').read_text());status['training_complete']=True
    (DEPLOY/'data_status.json').write_text(json.dumps(status,indent=2))
    print(json.dumps(metrics,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('step',choices=['prepare','train']);parser.add_argument('--csv')
    args=parser.parse_args()
    prepare() if args.step=='prepare' else train(args.csv)
