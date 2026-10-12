"""Real Sentinel-2 pixel classification for East Java. No credentials or invented results."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import time

import geopandas as gpd
import joblib
import numpy as np
import pandas as pd
import rasterio
from PIL import Image
from rasterio.features import geometry_mask
from rasterio.transform import from_origin
from rasterio.warp import reproject, Resampling, calculate_default_transform, transform_bounds
from shapely.geometry import box, mapping
from sklearn.metrics import accuracy_score, cohen_kappa_score, classification_report
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from pipeline import UTS, DEPLOY, BANDS, FEATURES, CLASSES, add_indices

WORK=UTS/'data/province_processing'
EXPORT=DEPLOY/'province_classification'
MODEL=UTS/'models/model_lulc_pixel.pkl'
CRS='EPSG:32749'
COLORS={1:'#bcbd22',2:'#d62728',3:'#006400',4:'#1f77b4',5:'#2ca02c'}
ENGLISH={1:'Farmland',2:'Built-up areas',3:'Forest',4:'Water bodies',5:'Mangrove forest'}


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,indent=2),encoding='utf-8');temp.replace(path)


def clean_pixels(path):
    df=pd.read_csv(path)
    required={'poligon_id','label_teks',*BANDS}
    if missing:=required-set(df):raise ValueError(f'{path}: missing columns {missing}')
    df[BANDS]=df[BANDS].apply(pd.to_numeric,errors='coerce')
    df=add_indices(df)
    return df.replace([np.inf,-np.inf],np.nan).dropna(subset=FEATURES).loc[lambda d:(d[BANDS]>0).all(axis=1)]


def train_pixel_model(cap=2000):
    tr_path=UTS/'data/csv/training/piksel_train.csv'
    te_path=UTS/'data/csv/testing/piksel_test.csv'
    if not tr_path.exists() or not te_path.exists():
        raise FileNotFoundError('Your original satellite extraction and pipeline.py train must finish first. Pixel training/testing CSVs are required.')
    settings={'train_sha256':sha(tr_path),'test_sha256':sha(te_path),'max_per_class':cap,'features':FEATURES,'k':5}
    meta_path=MODEL.with_suffix('.json')
    if MODEL.exists() and meta_path.exists():
        old=json.loads(meta_path.read_text())
        if old.get('training_settings')==settings:
            print('Reusing the existing pixel model.');return old
    train=clean_pixels(tr_path);test=clean_pixels(te_path)
    if set(train.poligon_id)&set(test.poligon_id):raise ValueError('Polygon IDs overlap between training and test sets.')
    samples=gpd.read_file(DEPLOY/'samples.geojson').set_index('poligon_id')
    for frame in (train,test):
        if not frame.poligon_id.isin(samples.index).all():raise ValueError('Unknown polygon IDs in pixel CSV.')
        if not frame.label_teks.eq(frame.poligon_id.map(samples.label_teks)).all():raise ValueError('Pixel labels differ from source polygons.')
    if set(train.label_teks)!=set(CLASSES) or set(test.label_teks)!=set(CLASSES):raise ValueError('Every class must occur in both pixel datasets.')
    n=min(cap,int(train.label_teks.value_counts().min()))
    if n<5:raise ValueError('Too few valid training pixels in at least one class.')
    balanced=pd.concat([train[train.label_teks==cls].sample(n=n,random_state=42) for cls in CLASSES],ignore_index=True)
    model=make_pipeline(StandardScaler(),KNeighborsClassifier(n_neighbors=5,weights='distance',metric='euclidean',algorithm='kd_tree',n_jobs=-1))
    model.fit(balanced[FEATURES],balanced.label_teks)
    predictions=[]
    for start in range(0,len(test),10000):predictions.extend(model.predict(test.iloc[start:start+10000][FEATURES]))
    accuracy=float(accuracy_score(test.label_teks,predictions));kappa=float(cohen_kappa_score(test.label_teks,predictions))
    report=classification_report(test.label_teks,predictions,output_dict=True,zero_division=0)
    MODEL.parent.mkdir(parents=True,exist_ok=True);joblib.dump(model,MODEL)
    meta={'training_settings':settings,'model_sha256':sha(MODEL),'features':FEATURES,'bands':BANDS,'k':5,
          'balanced_pixels_per_class':n,'training_pixels':len(balanced),'testing_pixels':len(test),
          'test_accuracy_pct':accuracy*100,'test_kappa':kappa,'macro_f1':report['macro avg']['f1-score'],
          'test_scope':'Pixels from held-out polygons. Spatially nearby polygons may still be correlated.',
          'classification_report':report}
    write_json(meta_path,meta)
    print(f'Pixel model: {len(balanced):,} balanced training pixels; test accuracy {accuracy*100:.2f}%; Kappa {kappa:.4f}.')
    return meta


def plan(args):
    province_path=DEPLOY/'province.geojson'
    province=gpd.read_file(province_path).to_crs(CRS)
    region=province.geometry.union_all().buffer(args.coastal_buffer_km*1000)
    settings={'province_sha256':sha(province_path),'bands':BANDS,'dates':[args.start,args.end],
              'resolution_m':args.resolution,'tile_size_m':args.tile_km*1000,
              'coastal_buffer_km':args.coastal_buffer_km,'max_cloud':args.max_cloud,'crs':CRS}
    WORK.mkdir(parents=True,exist_ok=True)
    manifest=WORK/'settings.json'
    if manifest.exists() and json.loads(manifest.read_text())!=settings:
        raise ValueError('Province-processing settings changed. Rename uts/data/province_processing before a fresh run. Existing sample extraction is unaffected.')
    write_json(manifest,settings)
    size=args.tile_km*1000
    if size%args.resolution:raise ValueError('Tile size must be divisible by the classification resolution.')
    west,south,east,north=region.bounds
    tiles=[]
    for ix in range(math.floor(west/size),math.ceil(east/size)):
        for iy in range(math.floor(south/size),math.ceil(north/size)):
            bounds=(ix*size,iy*size,(ix+1)*size,(iy+1)*size)
            tile=box(*bounds)
            if tile.intersection(region).area<=0:continue
            geo=transform_bounds(CRS,'EPSG:4326',*bounds,densify_pts=21)
            tiles.append({'tile_id':f'x{ix}_y{iy}','utm_bounds':list(bounds),'geo_bounds':list(geo)})
    write_json(WORK/'plan.json',{'settings':settings,'tiles':tiles})
    print(f'Plan: {len(tiles)} tiles; {args.resolution} m classification grid; East Java + {args.coastal_buffer_km:g} km coastal buffer.')
    print(f'Approximate study area: {region.area/1e6:,.0f} km²; approximate target pixels: {region.area/args.resolution**2:,.0f}.')
    print('No jobs are submitted by the plan command.')
    return settings,tiles,region


def find_raster(directory):
    files=sorted([*directory.glob('*.tif'),*directory.glob('*.tiff')])
    return files[0] if len(files)==1 else None


def download_tiles(args,settings,tiles):
    import openeo
    print('Authenticating with Copernicus. Existing refresh tokens may skip the login link.',flush=True)
    conn=openeo.connect('https://openeo.dataspace.copernicus.eu').authenticate_oidc()
    for number,tile in enumerate(tiles,1):
        directory=WORK/tile['tile_id'];directory.mkdir(exist_ok=True)
        state_path=directory/'job.json'
        state=json.loads(state_path.read_text()) if state_path.exists() else {}
        if state.get('downloaded') and find_raster(directory):
            print(f'[{number}/{len(tiles)}] {tile["tile_id"]}: cached download.',flush=True);continue
        job=None
        if state.get('job_id'):
            job=conn.job(state['job_id'])
            remote=job.status()
            if remote in {'error','canceled'}:job=None
        if job is None:
            w,s,e,n=tile['geo_bounds']
            cube=conn.load_collection('SENTINEL2_L2A',spatial_extent={'west':w,'south':s,'east':e,'north':n},
                temporal_extent=settings['dates'],bands=BANDS+['SCL'],max_cloud_cover=args.max_cloud)
            scl=cube.band('SCL')
            bad=(scl==0)|(scl==1)|(scl==3)|(scl==8)|(scl==9)|(scl==10)|(scl==11)
            cube=cube.filter_bands(BANDS).mask(bad).resample_spatial(resolution=args.resolution,projection=32749,method='near').median_time()
            job=cube.create_job(title=f'Joni_EastJava_{tile["tile_id"]}_{args.resolution}m',out_format='GTiff')
            state={'job_id':job.job_id,'downloaded':False};write_json(state_path,state)
        remote=job.status()
        if remote=='created':
            for attempt in range(3):
                try:job.start_job();break
                except Exception:
                    if attempt==2:raise
                    print('Temporary start error; retrying the same job in 15 seconds.',flush=True);time.sleep(15)
        while True:
            remote=job.status()
            print(f'[{number}/{len(tiles)}] {tile["tile_id"]}: {remote}',flush=True)
            if remote=='finished':break
            if remote in {'error','canceled'}:
                raise RuntimeError(f'{tile["tile_id"]}: remote job {remote}. Rerun the same command to retry; completed downloads are retained.')
            time.sleep(30)
        job.get_results().download_files(directory)
        tif=find_raster(directory)
        if tif is None:raise RuntimeError(f'{directory}: expected one multi-band GeoTIFF. Multiple assets require explicit inspection before band extraction.')
        state['downloaded']=True;write_json(state_path,state)
    print('All province tiles downloaded.',flush=True)


def feature_array(values):
    frame=pd.DataFrame(values.T,columns=BANDS)
    return add_indices(frame)[FEATURES]


def classify_tile(tile,region,resolution,model,model_hash):
    directory=WORK/tile['tile_id'];tif=find_raster(directory)
    if tif is None:raise FileNotFoundError(f'No downloaded raster in {directory}. Run download first.')
    output_dir=WORK/'classified';output_dir.mkdir(exist_ok=True)
    result_path=output_dir/f'{tile["tile_id"]}.json'
    fingerprint={'source_sha256':sha(tif),'model_sha256':model_hash,'resolution_m':resolution,'bounds':tile['utm_bounds']}
    if result_path.exists():
        cached=json.loads(result_path.read_text())
        if cached.get('fingerprint')==fingerprint and all((EXPORT/image['path']).exists() for image in cached['images']):return cached
    x0,y0,x1,y1=tile['utm_bounds'];width=int(round((x1-x0)/resolution));height=int(round((y1-y0)/resolution))
    transform=from_origin(x0,y1,resolution,resolution)
    inside=geometry_mask([mapping(region)],out_shape=(height,width),transform=transform,invert=True)
    # Warp to a shared UTM grid: adjacent tiles cannot double-count pixels.
    values=np.full((len(BANDS),height,width),np.nan,dtype='float32')
    with rasterio.open(tif) as src:
        descriptions=list(src.descriptions)
        if not set(BANDS)<=set(descriptions):
            raise ValueError(f'{tif}: band descriptions missing or incorrect. Never assume band order.')
        for i,band in enumerate(BANDS):
            reproject(rasterio.band(src,descriptions.index(band)+1),values[i],src_transform=src.transform,src_crs=src.crs,
                src_nodata=src.nodata,dst_transform=transform,dst_crs=CRS,dst_nodata=np.nan,resampling=Resampling.nearest)
    valid=inside&np.isfinite(values).all(axis=0)&(values>0).all(axis=0)
    labels=np.zeros((height,width),dtype='uint8')
    locations=np.flatnonzero(valid)
    flat=values.reshape(len(BANDS),-1)
    for start in range(0,len(locations),10000):
        chosen=locations[start:start+10000]
        features=feature_array(flat[:,chosen])
        usable=np.isfinite(features.to_numpy()).all(axis=1)
        if usable.any():labels.flat[chosen[usable]]=np.array([CLASSES[name] for name in model.predict(features.loc[usable])],dtype='uint8')
    raster_path=output_dir/f'{tile["tile_id"]}.tif'
    with rasterio.open(raster_path,'w',driver='GTiff',height=height,width=width,count=1,dtype='uint8',crs=CRS,transform=transform,nodata=0,compress='deflate') as dst:dst.write(labels,1)
    # Display in Web Mercator so an image overlay aligns with the satellite tiles.
    warp_transform,warp_w,warp_h=calculate_default_transform(CRS,'EPSG:3857',width,height,x0,y0,x1,y1)
    rendered=np.zeros((warp_h,warp_w),dtype='uint8')
    reproject(labels,rendered,src_transform=transform,src_crs=CRS,src_nodata=0,dst_transform=warp_transform,dst_crs='EPSG:3857',dst_nodata=0,resampling=Resampling.nearest)
    projected=rasterio.transform.array_bounds(warp_h,warp_w,warp_transform)
    w,s,e,n=transform_bounds('EPSG:3857','EPSG:4326',*projected)
    images=[]
    image_dir=EXPORT/'layers'/f'{model_hash[:12]}_{fingerprint["source_sha256"][:12]}_{resolution}m'/tile['tile_id'];image_dir.mkdir(parents=True,exist_ok=True)
    counts={str(code):int(np.sum(labels==code)) for code in ENGLISH}
    for code,color in COLORS.items():
        if counts[str(code)]==0:continue
        rgb=tuple(int(color[i:i+2],16) for i in (1,3,5))
        rgba=np.zeros((*rendered.shape,4),dtype='uint8');mask=rendered==code
        rgba[mask,:3]=rgb;rgba[mask,3]=205
        image_path=image_dir/f'class_{code}.png';Image.fromarray(rgba).save(image_path,optimize=True)
        images.append({'class_code':code,'path':image_path.relative_to(EXPORT).as_posix(),'bounds':[[s,w],[n,e]]})
    result={'tile_id':tile['tile_id'],'fingerprint':fingerprint,'target_pixels':int(inside.sum()),
            'valid_pixels':int(np.count_nonzero(labels)),'counts':counts,'images':images}
    write_json(result_path,result)
    return result


def classify_all(args,settings,tiles,region):
    if not MODEL.exists():raise FileNotFoundError('Run the train command first to create the separate pixel model.')
    meta=json.loads(MODEL.with_suffix('.json').read_text());model_hash=sha(MODEL)
    if model_hash!=meta['model_sha256']:raise ValueError('Pixel model and metadata do not match. Train again.')
    model=joblib.load(MODEL)
    EXPORT.mkdir(parents=True,exist_ok=True)
    # Publish only after all planned tiles finish, so partial runs are never called full coverage.
    results=[]
    for number,tile in enumerate(tiles,1):
        print(f'Classifying {number}/{len(tiles)}: {tile["tile_id"]}',flush=True)
        results.append(classify_tile(tile,region,args.resolution,model,model_hash))
    counts={str(code):sum(t['counts'][str(code)] for t in results) for code in ENGLISH}
    valid=sum(counts.values());target=sum(t['target_pixels'] for t in results)
    if valid==0:raise ValueError('No valid classified pixels. Change acquisition dates or inspect the raster/mask before publishing.')
    summary=pd.DataFrame([{'Class':ENGLISH[code],'class_code':code,'Pixels':counts[str(code)],
        'Percentage':counts[str(code)]/valid*100,'Area_km2':counts[str(code)]*args.resolution**2/1e6,'Color':COLORS[code]} for code in ENGLISH])
    summary.to_csv(EXPORT/'class_summary.csv',index=False)
    study=gpd.GeoDataFrame({'name':['East Java study area']},geometry=[region],crs=CRS).to_crs(4326)
    study.to_file(EXPORT/'study_area.geojson',driver='GeoJSON')
    manifest={'version':1,'complete':True,'settings':settings,'model':meta,'model_sha256':model_hash,
        'valid_pixels':valid,'target_pixels':target,'valid_coverage_pct':valid/target*100 if target else 0,
        'missing_pixels':target-valid,'tile_count':len(tiles),'bounds':study.total_bounds.tolist(),
        'tiles':results,'statistics_scope':'Valid classified grid pixels inside East Java plus the configured coastal buffer. NoData is excluded from class percentages.',
        'resolution_note':'100 m is a coarse classification/sampling grid, not native Sentinel-2 spatial resolution.'}
    write_json(EXPORT/'manifest.json',manifest)
    print(summary.to_string(index=False));print(f'Classified {valid:,} valid pixels; valid-data coverage {manifest["valid_coverage_pct"]:.2f}%.')
    print('Finished. Restart Streamlit; the province classification map will appear automatically.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('step',choices=['train','plan','download','classify','run'])
    parser.add_argument('--resolution',type=int,default=100,choices=[20,50,100,200])
    parser.add_argument('--tile-km',type=int,default=100)
    parser.add_argument('--coastal-buffer-km',type=float,default=5)
    parser.add_argument('--max-cloud',type=int,default=30)
    parser.add_argument('--start',default='2026-09-01');parser.add_argument('--end',default='2026-10-01')
    parser.add_argument('--max-per-class',type=int,default=2000)
    args=parser.parse_args()
    if args.tile_km<=0 or args.coastal_buffer_km<0 or args.max_per_class<5:parser.error('Use positive tile sizes and sample caps; coastal buffer must be nonnegative.')
    if args.step in {'train','run'}:train_pixel_model(args.max_per_class)
    if args.step=='train':return
    settings,tiles,region=plan(args)
    if args.step=='plan':return
    if args.step in {'download','run'}:download_tiles(args,settings,tiles)
    if args.step in {'classify','run'}:classify_all(args,settings,tiles,region)

if __name__=='__main__':main()
