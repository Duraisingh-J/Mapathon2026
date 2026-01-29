import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.features import shapes
from rasterio.mask import mask
from rasterio.io import MemoryFile
import geopandas as gpd
import numpy as np
import pandas as pd
from datetime import datetime
import os
from pyproj import CRS

# Optional cloud masking
try:
    from s2cloudless import S2PixelCloudDetector
    S2CLOUDLESS_AVAILABLE = True
except:
    S2CLOUDLESS_AVAILABLE = False

NDWI_THRESHOLD = 0.0


# ======================================================
# AUTO BAND DETECTION (Green + NIR)
# ======================================================
def detect_green_nir_bands(src):
    descriptions = src.descriptions
    count = src.count

    if descriptions and any(descriptions):
        desc = [d.lower() if d else "" for d in descriptions]

        green_keys = ["b3", "green"]
        nir_keys = ["b8", "nir"]

        g = n = None
        for i, name in enumerate(desc):
            if any(k in name for k in green_keys):
                g = i
            if any(k in name for k in nir_keys):
                n = i

        if g is not None and n is not None:
            print(f"[INFO] Detected bands → Green={g+1}, NIR={n+1}")
            return g, n

    # Fallback heuristics
    print("[WARN] Band metadata missing → Using heuristics")
    if count == 4:
        return 1, 3  # B3, B8 (Indicies 1, 3 for 0-indexed access? No, rasterio bands are 1-indexed usually, but read() returns array)
    if count >= 12:
        return 2, 7  # Sentinel-2 standard (B3=idx2, B8=idx7)

    # Default fallback for subsets
    return 1, 3


# ======================================================
# OPTIONAL CLOUD MASK (safe fallback)
# ======================================================
def apply_s2cloudless_mask(data):
    if not S2CLOUDLESS_AVAILABLE:
        print("[WARN] s2cloudless not installed → skipping cloud masking")
        return np.zeros(data.shape[1:], dtype=bool)

    try:
        # s2cloudless expects (H, W, Bands) and 0-1 range
        img = np.moveaxis(data, 0, -1) / 10000.0
        detector = S2PixelCloudDetector(threshold=0.4, average_over=4, dilation_size=2)
        
        # Note: If bands mismatch, this might throw, but we catch it
        probs = detector.get_cloud_probability_maps(img)
        mask = probs > 0.4
        print(f"[INFO] Cloud pixels masked: {mask.sum()}")
        return mask
    except Exception as e:
        print(f"[WARN] Cloud masking failed: {e}")
        return np.zeros(data.shape[1:], dtype=bool)


# ======================================================
# REPROJECT TO UTM
# ======================================================
def reproject_to_utm(src):
    bounds = src.bounds
    lon = (bounds.left + bounds.right) / 2
    lat = (bounds.top + bounds.bottom) / 2

    # UTM Zone calculation
    zone = int((lon + 180) / 6) + 1
    epsg = 32600 + zone if lat >= 0 else 32700 + zone
    utm = CRS.from_epsg(epsg)
    print(f"Reprojecting to: {utm}")

    transform, width, height = calculate_default_transform(
        src.crs, utm, src.width, src.height, *src.bounds
    )

    profile = src.profile.copy()
    profile.update(crs=utm, transform=transform, width=width, height=height)

    # Create destination array
    data = np.zeros((src.count, height, width), dtype=np.float32)

    for i in range(1, src.count + 1):
        reproject(
            rasterio.band(src, i),
            data[i - 1],
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=transform,
            dst_crs=utm,
            resampling=Resampling.nearest,
        )

    return data, profile


# ======================================================
# AREA + POLYGON EXTRACTION
# ======================================================
def process_water_from_image(image_path, lake_id, date_str, output_dir):
    date = datetime.strptime(date_str, "%Y-%m-%d").date()

    ndwi_dir = os.path.join(output_dir, "ndwi")
    mask_dir = os.path.join(output_dir, "masks")
    poly_dir = os.path.join(output_dir, "polygons")
    os.makedirs(ndwi_dir, exist_ok=True)
    os.makedirs(mask_dir, exist_ok=True)
    os.makedirs(poly_dir, exist_ok=True)

    with rasterio.open(image_path) as src:
        if not src.crs:
            raise ValueError("Raster CRS missing")

        if not src.crs.is_projected:
            data, profile = reproject_to_utm(src)
        else:
            data = src.read().astype("float32")
            profile = src.profile

        green_idx, nir_idx = detect_green_nir_bands(src)

        cloud_mask = apply_s2cloudless_mask(data)

        # Handle band access safetly
        if green_idx >= data.shape[0] or nir_idx >= data.shape[0]:
             print(f"[WARN] Band indices {green_idx}/{nir_idx} out of range for shape {data.shape}. Using 0,1.")
             green_idx, nir_idx = 0, 1

        green = np.where(cloud_mask, np.nan, data[green_idx])
        nir = np.where(cloud_mask, np.nan, data[nir_idx])

        ndwi = (green - nir) / (green + nir + 1e-6)

        ndwi_path = os.path.join(ndwi_dir, f"{lake_id}_{date}_ndwi.tif")
        prof = profile.copy()
        prof.update(dtype="float32", count=1, nodata=np.nan)
        with rasterio.open(ndwi_path, "w", **prof) as dst:
            dst.write(ndwi, 1)

        water = (ndwi >= NDWI_THRESHOLD).astype(np.uint8)

        mask_path = os.path.join(mask_dir, f"{lake_id}_{date}_mask.tif")
        prof.update(dtype="uint8", count=1, nodata=0)
        with rasterio.open(mask_path, "w", **prof) as dst:
            dst.write(water, 1)

        results = (
            {"geometry": geom, "properties": {}}
            for geom, val in shapes(water, transform=profile["transform"])
            if val == 1
        )

        geoms = list(results)
        if not geoms:
            return {"area_ha": 0.0, "polygon_path": None}

        gdf = gpd.GeoDataFrame.from_features(geoms, crs=profile["crs"])
        gdf["area_m2"] = gdf.area
        gdf = gdf.sort_values("area_m2", ascending=False).head(1)
        area_ha = float(gdf.area.iloc[0] / 10000)

        poly_path = os.path.join(poly_dir, f"{lake_id}_{date}_water.geojson")
        gdf.to_file(poly_path, driver="GeoJSON")

        return {"area_ha": area_ha, "polygon_path": poly_path}


# ======================================================
# DEM-BASED VOLUME
# ======================================================
def calculate_lake_volume(dem_path, polygon_path, base_level=None, target_area_ha=None):
    gdf = gpd.read_file(polygon_path)

    with rasterio.open(dem_path) as src:
        if src.crs != gdf.crs:
            gdf = gdf.to_crs(src.crs)

        geoms = [g for g in gdf.geometry]
        
        # Mask and Crop
        try:
            clipped, transform = mask(src, geoms, crop=True)
            dem = clipped[0]
        except ValueError:
            # Overlap issue
            return {"min_elevation": 0, "max_elevation": 0, "max_volume_m3": 0, "curve_df": pd.DataFrame()}

    # Filter invalid data
    valid = dem[dem > -10000]
    if valid.size == 0:
         return {"min_elevation": 0, "max_elevation": 0, "max_volume_m3": 0, "curve_df": pd.DataFrame()}
         
    min_elev, max_elev = valid.min(), valid.max()

    pixel_area = abs(transform[0] * transform[4])
    step = 0.1
    levels = np.arange(min_elev, max_elev + step, step)

    records = []
    for level in levels:
        # Only look at pixels BELOW this level
        mask_arr = (dem > -10000) & (dem < level)
        
        if np.any(mask_arr):
            depth = level - dem[mask_arr]
            volume = np.sum(depth) * pixel_area
            area = np.sum(mask_arr) * pixel_area / 10000.0 # Ha
        else:
            volume = 0.0
            area = 0.0
            
        records.append((level, volume, area))

    df = pd.DataFrame(records, columns=["water_level", "volume_m3", "area_ha"])
    
    final_max_vol = df["volume_m3"].max() if not df.empty else 0

    # 1. Base Level Interpolation (Volume Capacity)
    volume_at_base = None
    if base_level is not None:
        try:
             # Interpolate volume for the base level
             if base_level < min_elev:
                 volume_at_base = 0.0
             elif base_level > max_elev:
                 volume_at_base = final_max_vol
             else:
                 volume_at_base = np.interp(base_level, df["water_level"], df["volume_m3"])
        except:
             volume_at_base = 0.0

    # 2. Current Volume Interpolation (Area Lookup)
    current_vol = 0.0
    detected_level = min_elev
    
    if target_area_ha is not None and not df.empty:
        try:
            # Sort by area
            df_sorted = df.sort_values("area_ha")
            if target_area_ha <= df_sorted["area_ha"].min():
                detected_level = min_elev
                current_vol = 0.0
            elif target_area_ha >= df_sorted["area_ha"].max():
                detected_level = max_elev
                current_vol = final_max_vol
            else:
                detected_level = np.interp(target_area_ha, df_sorted["area_ha"], df_sorted["water_level"])
                current_vol = np.interp(target_area_ha, df_sorted["area_ha"], df_sorted["volume_m3"])
        except:
            current_vol = 0.0

    return {
        "min_elevation": float(min_elev),
        "max_elevation": float(max_elev),
        "max_volume_m3": float(final_max_vol),
        "volume_at_base_level": volume_at_base,
        "volume_at_current_level": float(current_vol),
        "water_level_recalculated": float(detected_level),
        "curve_df": df
    }


# ======================================================
# ORCHESTRATOR
# ======================================================
def analyze_lake(sat_path, dem_path, lake_id, date_str, output_dir, base_level=None):

    area_res = process_water_from_image(
        sat_path, lake_id, date_str, output_dir
    )

    area_ha = area_res["area_ha"]
    poly = area_res["polygon_path"]

    volume_m3 = 0
    vol_tmc = 0
    elev_min = elev_max = 0
    detected_level = 0
    volume_at_base = None

    if dem_path and poly:
        vol_res = calculate_lake_volume(dem_path, poly, base_level=base_level, target_area_ha=area_ha)
        
        volume_m3 = vol_res.get("volume_at_current_level", 0)
        vol_tmc = volume_m3 / 28316846.592
        
        elev_min = vol_res["min_elevation"]
        elev_max = vol_res["max_elevation"]
        detected_level = vol_res.get("water_level_recalculated", 0)
        
        volume_at_base = vol_res.get("volume_at_base_level")
        
        # Save Curve
        if "curve_df" in vol_res and not vol_res["curve_df"].empty:
             curve_path = os.path.join(output_dir, f"{lake_id}_{date_str}_volume_curve.csv")
             # Add volume_tmc column for CSV
             vol_res["curve_df"]["volume_tmc"] = vol_res["curve_df"]["volume_m3"] / 28316846.592
             vol_res["curve_df"].to_csv(curve_path, index=False)

    final_res = {
        "area_ha": round(area_ha, 2),
        "water_level": round(detected_level, 2),
        "volume_m3": round(volume_m3, 2),
        "volume_tmc": round(vol_tmc, 4),
        "min_elevation": round(elev_min, 2),
        "max_elevation": round(elev_max, 2),
        "message": "Analysis successful"
    }
    
    # Add Base Level results if available
    if volume_at_base is not None:
         final_res["base_level"] = round(float(base_level), 2)
         final_res["volume_at_level_m3"] = round(float(volume_at_base), 2)
         final_res["volume_at_level_tmc"] = round(float(volume_at_base) / 28316846.592, 4)

    return final_res
