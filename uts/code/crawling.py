"""
Sentinel-2 L2A (CDSE openEO) per-tile + ekstraksi KELAS PER PIKSEL -> CSV.

Setiap baris CSV = satu piksel, dengan penanda poligon asalnya:
  - poligon_id : ID stabil poligon, mis. "Sawah_0012" (nama kelas + nomor fitur di file sumbernya)
  - poligon_no : nomor fitur (urutan baris) di shapefile sumber, mulai dari 0
  - sampel_id  : indeks poligon pada GeoDataFrame gabungan (internal)

Poligon sampel masuk ke SEMUA tile yang dilewatinya. Piksel di zona overlap antar-tile
hanya diambil sekali (dimiliki sel grid-nya).

Pakai (script):   python sentinel2_piksel.py
Pakai (notebook): from sentinel2_piksel import main; main()
"""

import threading
import time
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import numpy as np
import openeo
import pandas as pd
import rasterio
from openeo.extra.job_management import CsvJobDatabase, MultiBackendJobManager
from rasterio.features import rasterize
from rasterio.mask import mask as rio_mask
from rasterio.warp import transform as warp_transform
from rasterio.windows import Window
from shapely.geometry import box
from shapely.validation import make_valid

# ==============================================================================
# KONFIGURASI
# ==============================================================================
from pipeline import GEO, UTS, BANDS, RAW

SUMBER = {}  # Labels and IDs are read from Joni's normalized GeoJSON.

TILE_DEG = 0.20      # ukuran tile ~22 km (~2200 x 2200 piksel @10 m)
BUFFER_DEG = 0.005   # margin ~500 m di sekeliling sampel

TANGGAL = ["2026-09-01", "2026-09-30"]
BANDS = ["B02", "B03", "B04", "B08", "B8A", "B11"]  # Blue, Green, Red, NIR, SWIR
PAKAI_MASK_SCL = True  # mask awan/bayangan per piksel pakai band SCL
MAX_CLOUD = 30         # filter awan level scene (kalau PAKAI_MASK_SCL=False, pakai ~10)

PARALEL = 2            # job bersamaan (akun gratis CDSE biasanya max 2)

# Ekstraksi piksel
MAKS_PIKSEL_PER_POLIGON = 2000  # None = ambil SEMUA piksel (hati-hati: poligon laut/hutan bisa jutaan -> CSV sangat besar)
SEED = 42
BUAT_RASTER_LABEL = True        # buat label_<tile>.tif di samping citra tiap tile

OUT_DIR = UTS / "data/csv/hasil_s2_piksel"
JOB_DB_PATH = OUT_DIR / "daftar_job.csv"
PETA_CSV = OUT_DIR / "peta_sampel_tile.csv"
PIKSEL_OUT = OUT_DIR / "piksel_s2.csv"


# ==============================================================================
# 1. BACA & GABUNGKAN SAMPEL
# ==============================================================================
def baca_semua() -> gpd.GeoDataFrame:
    g = gpd.read_file(GEO / "jawatimur_5kelas.geojson").to_crs("EPSG:4326")
    if not g.geometry.is_valid.all(): raise ValueError("Run pipeline.py prepare first")
    print(g.groupby("label_teks").size().to_string())
    return g[["poligon_id", "poligon_no", "label", "label_teks", "geometry"]]


# ==============================================================================
# 2. BAGI JADI TILE (poligon masuk ke semua sel yang dilewatinya)
# ==============================================================================
def buat_tile(gdf: gpd.GeoDataFrame):
    T, B = TILE_DEG, BUFFER_DEG
    peta, batas, sel_xy = [], {}, {}

    for idx, geom in gdf.geometry.items():
        minx, miny, maxx, maxy = geom.bounds
        for gx in range(int(np.floor(minx / T)), int(np.floor(maxx / T)) + 1):
            for gy in range(int(np.floor(miny / T)), int(np.floor(maxy / T)) + 1):
                sel = box(gx * T, gy * T, (gx + 1) * T, (gy + 1) * T)
                if not geom.intersects(sel):
                    continue
                bagian = geom.intersection(sel)
                if bagian.is_empty:
                    continue
                b = bagian.bounds
                tid = f"x{gx}_y{gy}"
                peta.append({"tile_id": tid, "sampel_id": idx, "poligon_id": gdf.at[idx, "poligon_id"]})
                sel_xy[tid] = (gx, gy)
                if tid in batas:
                    o = batas[tid]
                    batas[tid] = (min(o[0], b[0]), min(o[1], b[1]), max(o[2], b[2]), max(o[3], b[3]))
                else:
                    batas[tid] = b

    tiles = pd.DataFrame(
        [
            {
                "tile_id": tid,
                "gx": sel_xy[tid][0],
                "gy": sel_xy[tid][1],
                "west": b[0] - B,
                "south": b[1] - B,
                "east": b[2] + B,
                "north": b[3] + B,
            }
            for tid, b in batas.items()
        ]
    )
    peta = pd.DataFrame(peta)
    tiles["n_sampel"] = tiles["tile_id"].map(peta.groupby("tile_id")["sampel_id"].nunique())

    lebar_km = (tiles.east - tiles.west) * 111.32 * np.cos(np.radians((tiles.north + tiles.south) / 2))
    tinggi_km = (tiles.north - tiles.south) * 110.57
    print(f"\nJumlah tile (job)       : {len(tiles)}")
    print(f"Ukuran tile terbesar    : {lebar_km.max():.1f} km x {tinggi_km.max():.1f} km")
    print(f"Total area diunduh      : {(lebar_km * tinggi_km).sum():,.0f} km2")
    return tiles, peta


# ==============================================================================
# 3. JALANKAN BATCH JOB PER TILE
# ==============================================================================
def _jam() -> str:
    return datetime.now().strftime("%H:%M:%S")


def start_job(row, connection, **kwargs):
    print(f"[{_jam()}] >> Mengirim job tile {row['tile_id']} ({row.get('n_sampel', '?')} poligon)...", flush=True)
    bbox = {
        "west": float(row["west"]),
        "south": float(row["south"]),
        "east": float(row["east"]),
        "north": float(row["north"]),
    }
    bands = BANDS + ["SCL"] if PAKAI_MASK_SCL else BANDS
    cube = connection.load_collection(
        "SENTINEL2_L2A",
        spatial_extent=bbox,
        temporal_extent=TANGGAL,
        bands=bands,
        max_cloud_cover=MAX_CLOUD,
    )

    if PAKAI_MASK_SCL:
        scl = cube.band("SCL")
        # 1=jenuh, 3=bayangan awan, 8/9=awan sedang/tinggi, 10=cirrus
        mask_awan = (scl == 0) | (scl == 1) | (scl == 3) | (scl == 11) | (scl == 8) | (scl == 9) | (scl == 10)
        cube = cube.filter_bands(BANDS).mask(mask_awan)
    cube = cube.resample_spatial(resolution=10, projection=32749, method="near")

    komposit = cube.median_time()
    return komposit.create_job(title=f"s2_{row['tile_id']}", out_format="GTiff")


INTERVAL_LAPOR = 30  # detik antar laporan progres di terminal


class ManagerBerlapor(MultiBackendJobManager):
    """Manager job yang mencetak pesan saat job selesai / gagal."""

    def on_job_done(self, job, row):
        print(f"[{_jam()}] [OK]    Tile {row['tile_id']} selesai (job {job.job_id}), mengunduh hasil...", flush=True)
        super().on_job_done(job, row)
        print(f"[{_jam()}] [OK]    Tile {row['tile_id']} terunduh.", flush=True)

    def on_job_error(self, job, row):
        print(f"[{_jam()}] [ERROR] Tile {row['tile_id']} gagal (job {job.job_id}). Log disimpan di folder job.", flush=True)
        super().on_job_error(job, row)


def _lapor_berkala(job_db, berhenti: threading.Event):
    mulai = time.time()
    while not berhenti.wait(INTERVAL_LAPOR):
        try:
            df = job_db.read()
        except Exception:  # file sedang ditulis manager; lewati satu siklus
            continue
        n = len(df)
        hitung = df["status"].value_counts().to_dict()
        selesai = hitung.get("finished", 0)
        gagal = sum(hitung.get(s, 0) for s in ("error", "start_failed", "skipped"))
        jalan = hitung.get("running", 0) + hitung.get("queued", 0) + hitung.get("created", 0)
        belum = hitung.get("not_started", 0)
        persen = 100 * selesai / n if n else 0
        menit = (time.time() - mulai) / 60
        print(
            f"[{_jam()}] Progres job: {selesai}/{n} selesai ({persen:.0f}%) | "
            f"berjalan/antre {jalan} | belum mulai {belum} | gagal {gagal} | {menit:.1f} menit",
            flush=True,
        )


def jalankan_job(tiles: pd.DataFrame, ulangi_error: bool = True):
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    conn = openeo.connect("https://openeo.dataspace.copernicus.eu")
    conn.authenticate_oidc()

    manager = ManagerBerlapor(root_dir=OUT_DIR, poll_sleep=30)
    manager.add_backend("cdse", connection=conn, parallel_jobs=PARALEL)

    job_db = CsvJobDatabase(JOB_DB_PATH)
    if not job_db.exists():
        job_db.initialize_from_df(tiles)
    elif ulangi_error:
        df = job_db.read()
        gagal = df["status"].isin(["error", "start_failed", "skipped"])
        if gagal.any():
            print(f"Mengulang {int(gagal.sum())} job yang sebelumnya gagal.")
            df.loc[gagal, "status"] = "not_started"
            job_db.persist(df)

    # thread pemantau: cetak ringkasan status job tiap INTERVAL_LAPOR detik
    berhenti = threading.Event()
    pemantau = threading.Thread(target=_lapor_berkala, args=(job_db, berhenti), daemon=True)
    pemantau.start()
    try:
        manager.run_jobs(start_job=start_job, job_db=job_db)
    finally:
        berhenti.set()
        pemantau.join(timeout=5)

    df = job_db.read()
    print("\nRingkasan status job:")
    print(df["status"].value_counts().to_string())
    return df


# ==============================================================================
# 4. EKSTRAK KELAS PER PIKSEL -> CSV
# ==============================================================================
def _nama_band(src) -> list:
    desc = list(src.descriptions or [])
    if len(desc) == src.count and all(desc) and set(BANDS) <= set(desc):
        return desc
    if src.count != len(BANDS):
        raise ValueError(f"Expected {len(BANDS)} bands, got {src.count}: {src.name}")
    raise ValueError(f"Missing band descriptions in {src.name}. Confirm band order before extraction.")


def _valid_mask(data, nodata, masked=None):
    """data: (band, H, W). Piksel valid = semua band terbatas, > 0, bukan nodata."""
    ok = np.isfinite(data).all(axis=0) & (data > 0).all(axis=0)
    if nodata is not None and not np.isnan(nodata):
        ok &= ~(data == nodata).any(axis=0)
    if masked is not None:
        ok &= ~masked
    return ok


def _piksel_geom(src, geom):
    """Semua piksel valid yang pusatnya di dalam geometri.
    Return (nilai[band, n], baris_raster, kolom_raster, x, y) dalam CRS raster, atau None."""
    nodata = src.nodata

    if geom.geom_type == "Point":
        rr, cc = src.index(geom.x, geom.y)
        if not (0 <= rr < src.height and 0 <= cc < src.width):
            return None
        data = src.read(window=Window(cc, rr, 1, 1)).astype("float64")  # (band,1,1)
        ok = _valid_mask(data, nodata)
        row0, col0 = rr, cc
    else:
        ok = None
        for all_touched in (False, True):  # poligon sangat kecil: coba lagi dengan all_touched
            try:
                arr, tr = rio_mask(src, [geom], crop=True, all_touched=all_touched, filled=False)
            except ValueError:  # tidak beririsan dengan raster
                return None
            data = np.ma.getdata(arr).astype("float64")
            ok = _valid_mask(data, nodata, np.ma.getmaskarray(arr).any(axis=0))
            row0 = int(round((tr.f - src.transform.f) / src.transform.e))
            col0 = int(round((tr.c - src.transform.c) / src.transform.a))
            if ok.any():
                break
        if ok is None or not ok.any():
            return None

    r_idx, c_idx = np.nonzero(ok)
    if len(r_idx) == 0:
        return None
    nilai = data[:, r_idx, c_idx]
    px_row, px_col = row0 + r_idx, col0 + c_idx
    xs, ys = rasterio.transform.xy(src.transform, px_row, px_col)
    return nilai, px_row, px_col, np.asarray(xs), np.asarray(ys)


def tambah_indeks(df: pd.DataFrame) -> pd.DataFrame:
    e = 1e-9
    df["NDVI"] = (df["B08"] - df["B04"]) / (df["B08"] + df["B04"] + e)
    df["NDWI"] = (df["B03"] - df["B08"]) / (df["B03"] + df["B08"] + e)
    df["MNDWI"] = (df["B03"] - df["B11"]) / (df["B03"] + df["B11"] + e)
    df["NDBI"] = (df["B11"] - df["B08"]) / (df["B11"] + df["B08"] + e)
    df["NDMI_8A"] = (df["B8A"] - df["B11"]) / (df["B8A"] + df["B11"] + e)
    return df


def _tif_tile(r):
    tifs = sorted(p for p in OUT_DIR.glob(f"job_{r['id']}/*.tif") if not p.name.startswith("label_"))
    return tifs[0] if tifs else None


def ekstrak_piksel(gdf, db, peta) -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    T = TILE_DEG
    potongan = []
    selesai = db[db["status"] == "finished"]
    print(f"\nEkstraksi piksel dari {len(selesai)} tile yang selesai...")

    total_tile = len(selesai)
    total_piksel = 0
    t0 = time.time()

    for no_tile, (_, r) in enumerate(selesai.iterrows(), start=1):
        tif = _tif_tile(r)
        if tif is None:
            print(f"  [!] File .tif tidak ditemukan untuk tile {r['tile_id']} (job {r['id']})")
            continue

        cx0, cy0 = int(r["gx"]) * T, int(r["gy"]) * T
        ids = peta.loc[peta["tile_id"] == r["tile_id"], "sampel_id"].unique()
        n_poli = len(ids)
        piksel_tile = 0
        print(f"[{_jam()}] Tile {no_tile}/{total_tile} ({r['tile_id']}): {n_poli} poligon", flush=True)

        with rasterio.open(tif) as src:
            nama_band = _nama_band(src)
            sub_r = gdf.loc[ids].to_crs(src.crs)

            for no_poli, (idx, row) in enumerate(sub_r.iterrows(), start=1):
                if no_poli % 25 == 0 or no_poli == n_poli:
                    print(
                        f"    poligon {no_poli}/{n_poli} | piksel tile ini: {piksel_tile:,} | "
                        f"total: {total_piksel:,} | {(time.time() - t0) / 60:.1f} menit",
                        end="\r", flush=True,
                    )
                hasil = _piksel_geom(src, row.geometry)
                if hasil is None:
                    continue
                nilai, px_row, px_col, xs, ys = hasil

                lon, lat = warp_transform(src.crs, "EPSG:4326", xs.tolist(), ys.tolist())
                lon, lat = np.asarray(lon), np.asarray(lat)

                # hanya piksel yang pusatnya di dalam sel grid tile ini -> tidak ada duplikat antar-tile
                pilih = np.flatnonzero((lon >= cx0) & (lon < cx0 + T) & (lat >= cy0) & (lat < cy0 + T))
                if len(pilih) == 0:
                    continue
                if MAKS_PIKSEL_PER_POLIGON and len(pilih) > MAKS_PIKSEL_PER_POLIGON:
                    pilih = rng.choice(pilih, MAKS_PIKSEL_PER_POLIGON, replace=False)

                d = {
                    "poligon_id": row["poligon_id"],   # penanda poligon asal
                    "poligon_no": row["poligon_no"],
                    "sampel_id": idx,
                    "tile_id": r["tile_id"],
                    "label": row["label"],
                    "label_teks": row["label_teks"],
                    "px_row": px_row[pilih],
                    "px_col": px_col[pilih],
                    "lon": lon[pilih],
                    "lat": lat[pilih],
                }
                for i, nb in enumerate(nama_band):
                    d[nb] = nilai[i, pilih]
                potongan.append(pd.DataFrame(d))
                piksel_tile += len(pilih)
                total_piksel += len(pilih)

        print(f"\n    -> tile {r['tile_id']} selesai: {piksel_tile:,} piksel", flush=True)

    if not potongan:
        print("Tidak ada piksel yang berhasil diekstrak.")
        return pd.DataFrame()

    df = pd.concat(potongan, ignore_index=True)

    # piksel yang sama dimiliki poligon kelas berbeda = label ambigu -> dibuang
    kunci = ["tile_id", "px_row", "px_col"]
    ganda = df.duplicated(kunci, keep=False)
    konflik = ganda & (df.groupby(kunci)["label"].transform("nunique") > 1)
    if konflik.any():
        print(f"Membuang {int(konflik.sum())} piksel dengan label bertabrakan antar-kelas.")
    df = df[~konflik]

    # Drop pixels shared by different polygons, including same-class overlaps.
    n_sebelum = len(df)
    pixel_key = ["tile_id", "px_row", "px_col"]
    conflict = df.groupby(pixel_key)["poligon_id"].transform("nunique") > 1
    print(f"Dropping {int(conflict.sum())} rows in overlapping polygons (avoid leakage).")
    df = df.loc[~conflict].drop_duplicates(kunci).reset_index(drop=True)
    if n_sebelum != len(df):
        print(f"Menghapus {n_sebelum - len(df)} piksel ganda (poligon sekelas yang saling tumpang tindih).")

    df = tambah_indeks(df)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(PIKSEL_OUT, index=False)
    print(f"\nTersimpan: {PIKSEL_OUT}")
    print(f"Total piksel berlabel: {len(df):,}")
    print(df.groupby("label_teks").size().to_string())
    print(f"Jumlah poligon yang menghasilkan piksel: {df['poligon_id'].nunique()}")
    return df


# ==============================================================================
# 5. (OPSIONAL) RASTER LABEL GeoTIFF SEJAJAR DENGAN CITRA TILE
# ==============================================================================
def buat_raster_label(gdf, db, peta):
    """Tulis label_<tile>.tif (uint8, 0 = tanpa label) pada grid yang sama dengan citra tile."""
    selesai = db[db["status"] == "finished"]
    total = len(selesai)
    for no, (_, r) in enumerate(selesai.iterrows(), start=1):
        tif = _tif_tile(r)
        if tif is None:
            continue
        print(f"[{_jam()}] Raster label {no}/{total}: tile {r['tile_id']}", flush=True)
        ids = peta.loc[peta["tile_id"] == r["tile_id"], "sampel_id"].unique()
        with rasterio.open(tif) as src:
            sub_r = gdf.loc[ids].to_crs(src.crs)
            shapes = [(g, int(l)) for g, l in zip(sub_r.geometry, sub_r["label"])]
            lab = rasterize(
                shapes, out_shape=(src.height, src.width), transform=src.transform,
                fill=0, dtype="uint8",
            )
            profil = dict(
                driver="GTiff", height=src.height, width=src.width, count=1, dtype="uint8",
                crs=src.crs, transform=src.transform, nodata=0, compress="deflate",
            )
            keluar = tif.with_name(f"label_{r['tile_id']}.tif")
            with rasterio.open(keluar, "w", **profil) as dst:
                dst.write(lab, 1)
    print("Raster label selesai (label_<tile>.tif di folder tiap job).")


# ==============================================================================
# MAIN
# ==============================================================================
def main(jalankan: bool = True, ekstrak: bool = True, ulangi_error: bool = True):
    gdf = baca_semua()
    tiles, peta = buat_tile(gdf)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tiles.to_csv(OUT_DIR / "rencana_tile.csv", index=False)
    peta.to_csv(PETA_CSV, index=False)
    # tabel referensi poligon (tanpa geometri) untuk join dengan CSV piksel
    gdf.drop(columns="geometry").assign(
        luas_m2=gdf.to_crs(32749).geometry.area.to_numpy()
    ).to_csv(OUT_DIR / "daftar_poligon.csv", index_label="sampel_id")

    if jalankan:
        db = jalankan_job(tiles, ulangi_error=ulangi_error)
    else:
        db = CsvJobDatabase(JOB_DB_PATH).read()

    hasil = None
    if ekstrak:
        hasil = ekstrak_piksel(gdf, db, peta)
    if BUAT_RASTER_LABEL:
        buat_raster_label(gdf, db, peta)
    return hasil if hasil is not None else db


if __name__ == "__main__":
    import argparse, hashlib, json
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", action="store_true", help="Plan tiles without logging in")
    parser.add_argument("--start", default="2026-09-01")
    parser.add_argument("--end", default="2026-10-01", help="Exclusive end date")
    args = parser.parse_args()
    TANGGAL = [args.start, args.end]
    settings = {"source_sha256": hashlib.sha256(RAW.read_bytes()).hexdigest(), "dates": TANGGAL,
                "bands": BANDS, "grid": TILE_DEG, "resolution":10, "cloud":MAX_CLOUD}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = OUT_DIR / "extraction_settings.json"
    if manifest.exists() and json.loads(manifest.read_text()) != settings:
        raise ValueError("Extraction settings changed. Rename hasil_s2_piksel before a new run to avoid mixing cached jobs.")
    manifest.write_text(json.dumps(settings, indent=2))
    if args.plan:
        g = baca_semua(); tiles, peta = buat_tile(g)
        tiles.to_csv(OUT_DIR / "rencana_tile.csv", index=False)
        peta.to_csv(PETA_CSV,index=False)
        print("Plan only; no jobs submitted. Run without --plan to authenticate.")
    else:
        main()
