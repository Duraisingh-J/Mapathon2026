import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.features import shapes
from rasterio.mask import mask
from rasterio.io import MemoryFile
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import shape
from datetime import datetime
import os
from pyproj import CRS

# -----------------------
# CONFIG
# -----------------------
GREEN_BAND = 2   # Sentinel-2 B3
NIR_BAND   = 4   # Sentinel-2 B8
NDWI_THRESHOLD = 0.0


# -----------------------
# Reproject raster to UTM if needed
# -----------------------



def reproject_to_utm(src):
    bounds = src.bounds
    lon = (bounds.left + bounds.right) / 2
    lat = (bounds.top + bounds.bottom) / 2

    zone = int((lon + 180) / 6) + 1
    epsg = 32600 + zone if lat >= 0 else 32700 + zone
    utm_crs = CRS.from_epsg(epsg)

    print("Reprojecting to:", utm_crs)

    transform, width, height = calculate_default_transform(
        src.crs, utm_crs, src.width, src.height, *src.bounds
    )

    profile = src.profile.copy()
    profile.update({
        "crs": utm_crs,
        "transform": transform,
        "width": width,
        "height": height
    })

    data = np.zeros((src.count, height, width), dtype=np.float32)

    for i in range(1, src.count + 1):
        reproject(
            source=rasterio.band(src, i),
            destination=data[i - 1],
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=transform,
            dst_crs=utm_crs,
            resampling=Resampling.nearest
        )

    return data, profile


def calculate_lake_volume(dem_path, polygon_path):
    # -----------------------------
    # 1. Load polygon
    # -----------------------------
    gdf = gpd.read_file(polygon_path)

    if gdf.crs is None:
        raise ValueError("Polygon has no CRS")

    # Reproject polygon to UTM if needed
    if not gdf.crs.is_projected:
        gdf = gdf.to_crs(epsg=32644)

    # -----------------------------
    # 2. Load DEM
    # -----------------------------
    with rasterio.open(dem_path) as src:
        src_array = src.read(1)
        src_transform = src.transform
        src_crs = src.crs
        src_meta = src.meta.copy()

    # Reproject DEM to match polygon CRS
    dst_crs = gdf.crs

    transform, width, height = calculate_default_transform(
        src_crs, dst_crs, src.width, src.height, *src.bounds
    )

    with MemoryFile() as memfile:
        meta = src_meta.copy()
        meta.update({
            "crs": dst_crs,
            "transform": transform,
            "width": width,
            "height": height,
            "nodata": -32767
        })

        with memfile.open(**meta) as dst:
            reproject(
                source=src_array,
                destination=rasterio.band(dst, 1),
                src_transform=src_transform,
                src_crs=src_crs,
                dst_transform=transform,
                dst_crs=dst_crs,
                resampling=Resampling.bilinear
            )

            # -----------------------------
            # 3. Clip DEM to polygon
            # -----------------------------
            geoms = [geom for geom in gdf.geometry]
            try:
                clipped_img, clipped_transform = mask(dst, geoms, crop=True)
                dem_clipped = clipped_img[0]
            except ValueError:
                 print("⚠️ Polygon does not overlap with DEM")
                 return {"min_elevation": 0, "max_elevation": 0, "max_volume_m3": 0}

    # -----------------------------
    # 4. Zonal stats
    # -----------------------------
    valid = dem_clipped != -32767
    vals = dem_clipped[valid]
    
    if vals.size == 0:
        return {"min_elevation": 0, "max_elevation": 0, "max_volume_m3": 0}

    min_elev = float(vals.min())
    max_elev = float(vals.max())

    # -----------------------------
    # 5. Volume curve
    # -----------------------------
    step = 0.1
    levels = np.arange(min_elev, max_elev + step, step)

    pixel_area = abs(clipped_transform[0] * clipped_transform[4])

    records = []
    for level in levels:
        depth = level - dem_clipped
        mask_arr = (dem_clipped != -32767) & (dem_clipped < level)

        volume_m3 = np.sum(depth[mask_arr]) * pixel_area if np.any(mask_arr) else 0
        records.append([level, volume_m3])

    df = pd.DataFrame(records, columns=["water_level", "volume_m3"])

    # Example: return final max volume
    final_volume = float(df["volume_m3"].max())

    return {
        "min_elevation": min_elev,
        "max_elevation": max_elev,
        "max_volume_m3": final_volume
    }


# -----------------------
# MAIN PIPELINE
# -----------------------
def process_water_from_image(image_path, lake_id, date_str, output_dir):

    date = datetime.strptime(date_str, "%Y-%m-%d").date()

    os.makedirs(output_dir, exist_ok=True)
    ndwi_dir = os.path.join(output_dir, "ndwi")
    mask_dir = os.path.join(output_dir, "masks")
    poly_dir = os.path.join(output_dir, "polygons")
    os.makedirs(ndwi_dir, exist_ok=True)
    os.makedirs(mask_dir, exist_ok=True)
    os.makedirs(poly_dir, exist_ok=True)

    with rasterio.open(image_path) as src:
        print("Original CRS:", src.crs)

        if src.crs is None:
            raise ValueError("Raster has no CRS")

        # Reproject if geographic (EPSG:4326 etc.)
        if not src.crs.is_projected:
            data, profile = reproject_to_utm(src)
        else:
            data = src.read().astype("float32")
            profile = src.profile

        green = data[GREEN_BAND - 1]
        nir   = data[NIR_BAND - 1]
        transform = profile["transform"]

        # NDWI
        ndwi = (green - nir) / (green + nir + 1e-6)
        print("NDWI stats:", np.nanmin(ndwi), np.nanmax(ndwi))

        # Save NDWI
        ndwi_path = os.path.join(ndwi_dir, f"{lake_id}_{date}_ndwi.tif")
        ndwi_profile = profile.copy()
        ndwi_profile.update(dtype="float32", count=1, nodata=np.nan)

        with rasterio.open(ndwi_path, "w", **ndwi_profile) as dst:
            dst.write(ndwi, 1)

        # Threshold → water mask
        water_mask = (ndwi >= NDWI_THRESHOLD).astype(np.uint8)
        print("Water pixels:", np.sum(water_mask))

        mask_path = os.path.join(mask_dir, f"{lake_id}_{date}_mask.tif")
        mask_profile = profile.copy()
        mask_profile.update(dtype="uint8", count=1, nodata=0)

        with rasterio.open(mask_path, "w", **mask_profile) as dst:
            dst.write(water_mask, 1)

        # Polygonize
        results = (
            {"properties": {"value": v}, "geometry": s}
            for s, v in shapes(water_mask, transform=transform)
            if v == 1
        )

        geoms = list(results)

        if not geoms:
            print("⚠ No water detected")
            return {"area_ha": 0.0, "polygon_path": None}

        gdf = gpd.GeoDataFrame.from_features(geoms, crs=profile["crs"])

        # Keep only largest water body
        gdf["area_m2"] = gdf.geometry.area
        gdf = gdf.sort_values("area_m2", ascending=False).head(1)

        # Area in hectares
        gdf["area_ha"] = gdf.geometry.area / 10000
        total_area = float(gdf["area_ha"].iloc[0])

        # Save polygon
        poly_path = os.path.join(poly_dir, f"{lake_id}_{date}_water.geojson")
        gdf.to_file(poly_path, driver="GeoJSON")

        # Save CSV
        csv_path = os.path.join(output_dir, "results.csv")
        df = pd.DataFrame([{
            "lake_id": lake_id,
            "date": date,
            "area_ha": round(total_area, 2)
        }])
        df.to_csv(csv_path, index=False)

        print(f"\n✅ Done → Area = {total_area:.2f} ha")
        return {
            "area_ha": total_area, 
            "polygon_path": poly_path
        }


def analyze_lake(sat_path, dem_path, lake_id, date_str, output_dir):
    # 1. Run water detection
    result = process_water_from_image(
        image_path=sat_path,
        lake_id=lake_id,
        date_str=date_str,
        output_dir=output_dir
    )
    
    area_ha = result["area_ha"]
    polygon_path = result["polygon_path"]
    
    volume_data = {
        "min_elevation": 0,
        "max_elevation": 0,
        "max_volume_m3": 0
    }

    # 2. Run volume if DEM is provided and we have a water polygon
    if dem_path and polygon_path:
        print(f"[DEBUG] Calculating volume using DEM: {dem_path}")
        try:
            volume_data = calculate_lake_volume(dem_path, polygon_path)
            print("[DEBUG] Volume calculation successful")
        except Exception as e:
            print(f"[ERROR] Volume calculation failed: {e}")

    volume_m3 = volume_data["max_volume_m3"]
    # TMC = Thousand Million Cubic feet. 1 TMC = 28,316,846.592 m3
    volume_tmc = volume_m3 / 28316846.592

    return {
        "area_ha": round(area_ha, 2),
        "volume_m3": round(volume_m3, 2),
        "volume_tmc": round(volume_tmc, 4),
        "min_elevation": round(volume_data["min_elevation"], 2),
        "max_elevation": round(volume_data["max_elevation"], 2),
        "message": "Analysis successful"
    }



