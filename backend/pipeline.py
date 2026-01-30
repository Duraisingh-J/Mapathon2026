import os
import uuid
from datetime import datetime
import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.crs import CRS
from rasterio.features import shapes
from shapely.geometry import Polygon, mapping, shape
from shapely.ops import unary_union
from rasterio.vrt import WarpedVRT
import geopandas as gpd
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from rasterio.plot import show
from skimage import morphology

try:
    from s2cloudless import S2PixelCloudDetector
    S2CLOUDLESS_AVAILABLE = True
except ImportError:
    S2CLOUDLESS_AVAILABLE = False


# ======================================================
# CONSTANTS
# ======================================================
# ======================================================
# CONSTANTS
# ======================================================
# ======================================================
# CONSTANTS
# ======================================================
NDWI_THRESHOLD = 0.0 # Relaxed from 0.15 to 0.05 to recover missing water


# ======================================================
# OPTIONAL CLOUD MASK (safe fallback)
# ======================================================
def apply_s2cloudless_mask(data):
    if not S2CLOUDLESS_AVAILABLE:
        print("[WARN] s2cloudless not installed → skipping cloud masking")
        return np.zeros(data.shape[1:], dtype=bool)

    try:
        # Check data range to normalize correctly
        # s2cloudless model expects values 0.0 - 1.0
        max_val = np.max(data)
        
        if max_val > 5000:
             scale_factor = 10000.0 # Standard Sentinel-2 L1C/L2A (12-16 bit)
             print("[DEBUG] Data max > 5000, assuming 16-bit S2 data (scale 10000)")
        elif max_val > 1.0:
             scale_factor = 255.0   # Likely 8-bit export
             print("[DEBUG] Data max <= 5000, assuming 8-bit data (scale 255)")
        else:
             scale_factor = 1.0     # Already normalized
             print("[DEBUG] Data max <= 1.0, assuming normalized data (scale 1)")

        # Move axis to (H, W, Bands)
        img = np.moveaxis(data, 0, -1) / scale_factor
        
        # Clip to ensure valid range 0-1
        img = np.clip(img, 0, 1)

        # Stricter settings: threshold 0.2 (more sensitive), dilation 4 (removes cloud edges)
        detector = S2PixelCloudDetector(threshold=0.2, average_over=4, dilation_size=4)
        
        # Note: If bands mismatch, this might throw, but we catch it
        # S2Cloudless expects specific bands. If input has fewer, it might fail or give junk.
        # It expects B01, B02, B04, B05, B08, B8A, B09, B10, B11, B12 (10 bands).
        # If user uploads 3-band RGB or 4-band, we can't use S2PixelCloudDetector properly.
        # It usually throws an error if band count mismatches.
        
        if img.shape[-1] < 10:
             print(f"[WARN] Image has {img.shape[-1]} bands. S2Cloudless needs 10+ standard S2 bands. Skipping ML cloud mask.")
             return np.zeros(data.shape[1:], dtype=bool)

        probs = detector.get_cloud_probability_maps(img)
        mask = probs > 0.2
        print(f"[INFO] Cloud pixels masked: {mask.sum()}")
        return mask
    except Exception as e:
        print(f"[WARN] Cloud masking failed: {e}")
        return np.zeros(data.shape[1:], dtype=bool)

# ======================================================
# BAND DETECTION & SCL LOGIC
# ======================================================
def detect_band_indices(src):
    """
    Detect Green, NIR, and SCL bands automatically.
    Returns dict with keys: green, nir, scl (optional)
    """
    band_map = {"green": None, "nir": None, "scl": None}

    # If descriptions exist (best case)
    if src.descriptions:
        for i, desc in enumerate(src.descriptions):
            if not desc:
                continue
            d = desc.lower()
            if d in ["b3", "green"]:
                band_map["green"] = i
            elif d in ["b8", "nir"]:
                band_map["nir"] = i
            elif "scl" in d:
                band_map["scl"] = i

    # Fallback by band count (Sentinel-2 typical)
    if band_map["green"] is None or band_map["nir"] is None:
        if src.count >= 12:
            band_map["green"] = 2   # B3 (0-indexed logic: B1, B2, B3 -> 2)
            band_map["nir"]   = 7   # B8
        elif src.count == 4:
            band_map["green"] = 1
            band_map["nir"]   = 3
        else:
            band_map["green"] = 0
            band_map["nir"]   = 1
            
    # SCL is usually usually the last band in L2A stacks or separate. 
    # If not found by description, we assume it's NOT present in simple stacks.
    
    return band_map

def scl_cloud_mask(scl):
    # Classes: 1(Saturated), 3(Shadow), 7(Unclassified), 8(Cloud med), 9(Cloud high), 10(Cirrus), 11(Snow)
    # Removing these ensures we don't accidentally classify noise as water
    cloud_classes = [1, 3, 7, 8, 9, 10, 11] 
    return np.isin(scl, cloud_classes)

def scl_water_mask(scl):
    return scl == 6

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
    ndwi_dir = os.path.join(output_dir, "ndwi")
    mask_dir = os.path.join(output_dir, "masks")
    poly_dir = os.path.join(output_dir, "polygons")
    os.makedirs(ndwi_dir, exist_ok=True)
    os.makedirs(mask_dir, exist_ok=True)
    os.makedirs(poly_dir, exist_ok=True)

    with rasterio.open(image_path) as src:
        # Reproject if needed
        if not src.crs or not src.crs.is_projected:
            data, profile = reproject_to_utm(src)
        else:
            data = src.read().astype("float32")
            profile = src.profile

        bands = detect_band_indices(src)
        
        # Safe fallback for Green/NIR indices
        g_idx = bands["green"] if bands["green"] is not None and bands["green"] < data.shape[0] else 0
        n_idx = bands["nir"] if bands["nir"] is not None and bands["nir"] < data.shape[0] else 1
        
        green = data[g_idx]
        nir   = data[n_idx]

        water_mask = None
        scl_found = False

        # ==================================================
        # 1. SCL PATH (Priority)
        # ==================================================
        if bands.get("scl") is not None and bands["scl"] < data.shape[0]:
            print(f"[INFO] SCL Band found at index {bands['scl']}. Using SCL for Cloud Masking ONLY.")
            scl = data[bands["scl"]].astype(np.uint8)
            
            # 1. Use SCL to identify Clouds and Shadows (Strict Masking)
            cloud_mask_layer = scl_cloud_mask(scl)
            
            # 2. Revert to Simple Water Detection (Old Code Style)
            # Just mask out the bad pixels (clouds) and use standard NDWI threshold
            green_masked = np.where(cloud_mask_layer, np.nan, green)
            nir_masked   = np.where(cloud_mask_layer, np.nan, nir)
            
            ndwi = (green_masked - nir_masked) / (green_masked + nir_masked + 1e-6)
            
            # Simple Thresholding (No SCL Water requirement)
            # This recovers the "drastically reduced" area by being inclusive again
            ndwi_filled = np.nan_to_num(ndwi, nan=-1.0)
            water_mask = ndwi_filled > NDWI_THRESHOLD
            
            scl_found = True
            
        # ==================================================
        # 2. FALLBACK PATH (NDWI + s2cloudless)
        # ==================================================
        if not scl_found:
            print("[INFO] No SCL band found. Falling back to s2cloudless + NDWI.")
            cloud_mask_layer = apply_s2cloudless_mask(data)
            
            green_masked = np.where(cloud_mask_layer, np.nan, green)
            nir_masked   = np.where(cloud_mask_layer, np.nan, nir)
            
            ndwi = (green_masked - nir_masked) / (green_masked + nir_masked + 1e-6)
            water_mask = ndwi >= NDWI_THRESHOLD

            # Clean noise (Aggressive)
            kernel = morphology.square(3) 
            water_mask = morphology.opening(water_mask, kernel)
            water_mask = morphology.remove_small_objects(water_mask.astype(bool), min_size=64).astype(np.uint8)
            
            water_mask = (water_mask > 0)
            
        # Save NDWI (Optional, but good for reference)
        # If we used SCL, ndwi variable is still calculated above for consistency or strictly for export
        ndwi_path = os.path.join(ndwi_dir, f"{lake_id}_{date_str}_ndwi.tif")
        prof = profile.copy()
        prof.update(dtype="float32", count=1, nodata=np.nan)
        if 'ndwi' in locals():
             with rasterio.open(ndwi_path, "w", **prof) as dst:
                 dst.write(ndwi, 1)

        # Save Mask
        mask_path = os.path.join(mask_dir, f"{lake_id}_{date_str}_mask.tif")
        mask_profile = profile.copy()
        mask_profile.update(dtype="uint8", count=1, nodata=0)
        with rasterio.open(mask_path, "w", **mask_profile) as dst:
             dst.write(water_mask.astype(np.uint8), 1)

        # Save Mask as PNG for Frontend (RED MARGIN VIEW)
        mask_png_filename = f"{lake_id}_{date_str}_mask_view.png"
        mask_png_path = os.path.join(output_dir, mask_png_filename)
        
        plt.figure(figsize=(10, 10))
        # Background: NDWI
        plt.imshow(ndwi, cmap='gray', vmin=-0.5, vmax=0.5)
        
        # Overlay: Water Contours (Red Margin)
        # We use contour to show the edge
        plt.contour(water_mask, levels=[0.5], colors='red', linewidths=2)
        
        # Make water slightly blue shaded?
        # Create clear overlay
        overlay = np.zeros((water_mask.shape[0], water_mask.shape[1], 4))
        overlay[water_mask == 1] = [0, 0, 1, 0.3] # Blue transparent
        plt.imshow(overlay)
        
        plt.axis('off')
        plt.savefig(mask_png_path, bbox_inches='tight', pad_inches=0, dpi=150)
        plt.close()

        # Convert to Polygon
        # Shapes returns generator of (geojson_geometry, value)
        # We want value=1 (Water)
        mask_uint8 = water_mask.astype(np.uint8)
        shapes_gen = shapes(mask_uint8, mask=mask_uint8==1, transform=profile['transform'])
        
        polys = [shape(geom) for geom, val in shapes_gen if val == 1]
        
        if not polys: 
             return {
                 "area_ha": 0, 
                 "polygon_path": None, 
                 "mask_path": mask_path,
                 "image_png": mask_png_filename
             }
        
        # Merge multi-polygons
        final_poly = unary_union(polys)
        
        gdf = gpd.GeoDataFrame({"geometry": [final_poly]}, crs=profile['crs'])
        poly_out = os.path.join(poly_dir, f"{lake_id}_{date_str}.geojson")
        gdf.to_file(poly_out, driver="GeoJSON")
        
        area_sqm = gdf.area.sum()
        area_ha = area_sqm / 10000.0
        
        return {
            "area_ha":  area_ha, 
            "polygon_path": poly_out, 
            "mask_path": mask_path,
            "image_png": mask_png_filename
        }


# ======================================================
# DEM-BASED VOLUME
# ======================================================
    # ... imports 

def log_to_file(msg):
    try:
        with open("debug_volume.log", "a") as f:
            f.write(f"{datetime.now()}: {msg}\n")
    except:
        pass

def calculate_lake_volume(dem_path, polygon_path, base_level=None, target_area_ha=None):
    # Note: polygon_path is now used only for CRS reference, not for clipping the DEM.
    # This ensures "Volume @ Base Level" refers to the full DEM capacity.
    log_to_file(f"START Volume Calc: DEM={dem_path}, Target={target_area_ha}")
    
    gdf = gpd.read_file(polygon_path)
    # ... rest of code
    
    # ...
    # Inside the function, replace prints with log_to_file or add both

    
    # Ensure Polygon is Projected (Metric) for accurate Volume
    # We FORCE a Metric CRS (UTM 44N) to guarantee pixel_area is in Meters.
    # (Assuming South India/Tamil Nadu region for this project)
    dst_crs = 'EPSG:32644'
    if gdf.crs != dst_crs:
         print(f"[DEBUG] Reprojecting Polygon to {dst_crs} for Metric Volume Calc.")
         gdf = gdf.to_crs(dst_crs)

    # Get bounds of the polygon to clip the DEM
    minx, miny, maxx, maxy = gdf.total_bounds
    # Add a margin (e.g. 500m or 50% width) to catch the surrounding basin for Base Level calc
    margin = max(maxx - minx, maxy - miny) * 0.5 
    window_bounds = (minx - margin, miny - margin, maxx + margin, maxy + margin)
    print(f"[DEBUG] Clipping DEM to bounds with margin: {window_bounds}")

    with rasterio.open(dem_path) as src:
        print(f"[DEBUG] DEM CRS: {src.crs}")
        
        with WarpedVRT(src, crs=dst_crs, resampling=Resampling.bilinear) as vrt:
             # Calculate window in the VRT's (and Polygon's) CRS
             window = vrt.window(*window_bounds)
             # Read only the window
             dem = vrt.read(1, window=window)
             transform = vrt.window_transform(window)
             
             print(f"[DEBUG] Clipped DEM Shape: {dem.shape}")
             pixel_area = abs(transform[0] * transform[4])
             print(f"[DEBUG] Pixel Area: {pixel_area:.4f} m^2")

    # Filter invalid data (Assume Elevation > 0 and filter Nodata)
    # If using SRTM/Metric DEMs, 0 is often background or sea level (invalid for inland lakes).
    valid = dem[dem > 0.0]
    print(f"[DEBUG] Valid DEM Pixels (>0): {valid.size}, Min: {valid.min() if valid.size else 'N/A'}, Max: {valid.max() if valid.size else 'N/A'}")
    
    if valid.size == 0:
         print("[WARN] No valid DEM pixels found (All <= 0)!")
         return {"min_elevation": 0, "max_elevation": 0, "max_volume_m3": 0, "curve_df": pd.DataFrame()}
         
    min_elev, max_elev = valid.min(), valid.max()

    step = 0.1
    levels = np.arange(min_elev, max_elev + step, step)

    records = []
    # Vectorized Curve Calculation (Faster)
    # Flatten DEM for processing
    dem_flat = dem.ravel()
    dem_valid = dem_flat[dem_flat > 0.0]
    
    # If DEM is huge, this loop can be slow. But for typical lakes it's fine.
    # Optimization: Sort DEM once
    dem_sorted = np.sort(dem_valid)
    n_pixels = len(dem_sorted)
    
    if n_pixels == 0:
         return {"min_elevation": 0, "max_elevation": 0, "max_volume_m3": 0, "curve_df": pd.DataFrame()}

    for lvl in levels:
        # Count pixels <= current level
        # Since sorted, we can use searchsorted
        idx = np.searchsorted(dem_sorted, lvl, side='right')
        # Wait, volume is area * height? 
        # No, Volume varies by level. 
        # Standard method: 
        # Area(h) = count(pixels < h) * pixel_area
        # Volume(h) = sum((h - pixel_h) * pixel_area) for pixel_h < h
        
        # Let's do the volume sum correctly:
        # pixels below lvl
        pixels_below = dem_sorted[:idx]
        if pixels_below.size > 0:
             vol = np.sum((lvl - pixels_below) * pixel_area)
             area = pixels_below.size * (pixel_area / 10000.0) # Ha
        else:
             vol = 0
             area = 0
             
        records.append({"elevation": lvl, "volume_m3": vol, "area_ha": area})

    # Sort and create DataFrame
    if not records:
         return {"min_elevation": 0, "max_elevation": 0, "max_volume_m3": 0, "curve_df": pd.DataFrame()}

    first_area_ha = records[0]["area_ha"]
    min_elev = records[0]["elevation"]
    
    # Check if a custom "Floor" (Base Level) is provided by the user
    # If base_level < min_elev, we use it as the zero-volume anchor.
    # This respects the user's input to define the depth.
    
    custom_floor_applied = False
    
    if base_level is not None:
        try:
            floor_elev = float(base_level)
            if floor_elev < min_elev - 0.1: # Significant difference
                print(f"[INFO] Using User Base Level {floor_elev}m as Lake Floor (DEM Min: {min_elev}m)")
                log_to_file(f"Using User Base Level {floor_elev} as Floor")
                
                # Extrapolate Volume from Floor to Min Elev
                # Assume Conical/Pyramidal growth from Floor(0 area) to MinElev(first_area)
                depth = min_elev - floor_elev
                
                # Volume of frustum/cone segment
                # V = 1/3 * Area * Height
                vol_offset = (1.0/3.0) * (first_area_ha * 10000.0) * depth
                
                msg = f"Extrapolating from {floor_elev}m to {min_elev}m. Added Volume: {vol_offset:.2f} m3"
                print(msg)
                log_to_file(msg)
                
                records.insert(0, {"elevation": floor_elev, "volume_m3": 0.0, "area_ha": 0.0})
                
                # Shift existing volumes
                for rec in records[1:]:
                    rec["volume_m3"] += vol_offset
                    
                custom_floor_applied = True
        except:
            pass

    if not custom_floor_applied:
        # Check for Flat Bottom / "Effective Floor" / Zero Volume Issue
        # Scan for the first significant area (e.g., > 10 Ha)
        # If the area jumps significantly (e.g. from <1 to >100), we infer a flat bottom.
        
        effective_floor_idx = -1
        for i, rec in enumerate(records):
            if rec["area_ha"] > 10.0: # Threshold for "significant lake start"
                effective_floor_idx = i
                break
        
        should_rectify = False
        eff_floor_elev = min_elev
        eff_floor_area = 0.0
        
        if effective_floor_idx != -1:
            # We found a start. Check if it's a jump or valid start.
            curr_area = records[effective_floor_idx]["area_ha"]
            prev_area = records[effective_floor_idx-1]["area_ha"] if effective_floor_idx > 0 else 0.0
            
            if curr_area > 50.0 and prev_area < 5.0:
                # Clear jump (e.g. 0.1 -> 590)
                should_rectify = True
                eff_floor_elev = records[effective_floor_idx]["elevation"]
                eff_floor_area = curr_area
                log_to_file(f"Detected Effective Lake Floor at {eff_floor_elev}m (Area Jump: {prev_area:.2f} -> {curr_area:.2f} Ha)")
            elif effective_floor_idx == 0 and curr_area > 10.0:
                # Starts big immediately
                should_rectify = True
                eff_floor_elev = min_elev
                eff_floor_area = curr_area
                
        if should_rectify:
             # Apply "Auto-Detected Base"
             default_depth = 5.0
             auto_floor = eff_floor_elev - default_depth
             
             log_to_file(f"Auto-Rectifying Zero Volume: Applying Default Floor at {auto_floor:.2f}m (5m below effective floor)")
             
             vol_offset = (1.0/3.0) * (eff_floor_area * 10000.0) * default_depth
             
             # Insert floor point
             records.insert(0, {"elevation": auto_floor, "volume_m3": 0.0, "area_ha": 0.0})
             
             # Apply offset to all records at or above the effective floor
             # Note: indices shifted by 1 after insert.
             # We simply add volume to any record where elev >= eff_floor_elev? 
             # Actually, simpler: just add to everything that was originally 'above' the floor.
             # But the interpolation handles between auto_floor and eff_floor_elev.
             # The existing records at eff_floor_elev needs the offset.
             
             for rec in records:
                 if rec["elevation"] >= eff_floor_elev:
                     rec["volume_m3"] += vol_offset
        else:
            log_to_file("No Lower Base Level provided and no flat bottom detected. Using DEM Min as Floor.")
            records.insert(0, {"elevation": min_elev - 0.1, "volume_m3": 0.0, "area_ha": 0.0})

    df = pd.DataFrame(records)
    log_to_file(f"Curve Data Head:\n{df.head().to_string()}")
    
    # Interp check
    if target_area_ha is not None:
         try:
             current_vol = np.interp(target_area_ha, df['area_ha'], df['volume_m3'])
             log_to_file(f"Interpolation: Target {target_area_ha} -> Vol {current_vol}")
         except Exception as e:
             log_to_file(f"Interp Error: {e}")
    
    if df.empty:
         print(f"[WARN] Volume Curve Empty. Min Elev: {min_elev}, Max: {max_elev}")
         return {"min_elevation": min_elev, "max_elevation": max_elev, "max_volume_m3": 0, "curve_df": df}
         
    final_max_vol = df['volume_m3'].max()
    min_curve_area = df['area_ha'].min() # Should be 0 now
    
    # Interpolate for Base Level
    volume_at_base = 0
    if base_level is not None:
         try:
             volume_at_base = np.interp(base_level, df['elevation'], df['volume_m3'])
         except:
             volume_at_base = 0

    # Interpolate Current Volume based on Target Area
    current_vol = 0
    detected_level = min_elev
    
    if target_area_ha is not None:
        try:
             # Regular interpolation since we now have 0,0
             # Note: df['area_ha'] is sorted? No, elevation is sorted. 
             # Area generally increases with elevation, so it should be sorted.
             # Let's clean up duplicates in area to be safe for interp (xp must be increasing)
             
             # Group by area to handle flats? 
             # Simpler: just use interp, it handles it reasonable well if sorted.
             # If multiple elevations have same area (vertical wall), interp is unpredictable.
             # But here Area increases with Elev.
             
             current_vol = np.interp(target_area_ha, df['area_ha'], df['volume_m3'])
             detected_level = np.interp(target_area_ha, df['area_ha'], df['elevation'])
             
             print(f"[DEBUG] Target: {target_area_ha} Ha -> Vol: {current_vol} m3 @ {detected_level} m")

        except Exception as e:
             # Fallback block removed as we simplified logic
             print(f"[ERROR] Interpolation failed: {e}")
             current_vol = 0.0
                 

        except Exception as e:
            print(f"[ERROR] Interpolation failed: {e}")
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
# WATER FREQUENCY HEATMAP
# ======================================================
def generate_frequency_map(mask_paths, output_dir):
    if not mask_paths:
        return None
    
    print(f"[INFO] Generating Water Frequency Heatmap from {len(mask_paths)} images...")
    
    try:
        # Load first mask to get profile
        with rasterio.open(mask_paths[0]) as src:
            profile = src.profile.copy()
            acc = np.zeros((src.height, src.width), dtype=np.float32)
            
        count = 0
        for p in mask_paths:
            if not p: continue
            try:
                with rasterio.open(p) as src:
                    if src.profile['transform'] != profile['transform']:
                        with WarpedVRT(src, crs=profile['crs'], transform=profile['transform'], width=profile['width'], height=profile['height']) as vrt:
                             data = vrt.read(1)
                    else:
                        data = src.read(1)
                        
                    acc += (data > 0)
                    count += 1
            except Exception as ex:
                print(f"[WARN] Failed to add mask {p} to heatmap: {ex}")

        if count == 0: return None
        
        freq = acc / count
        freq_pct = (freq * 100).astype(np.uint8)
        
        heatmap_filename = f"water_frequency_{uuid.uuid4().hex[:8]}.tif"
        heatmap_path = os.path.join(output_dir, heatmap_filename)
        
        profile.update(dtype=rasterio.uint8, count=1, nodata=0)
        
        with rasterio.open(heatmap_path, "w", **profile) as dst:
            dst.write(freq_pct, 1)
            
        print(f"[SUCCESS] Heatmap saved: {heatmap_path}")
        return heatmap_filename
        
    except Exception as e:
        print(f"[ERROR] Heatmap generation failed: {e}")
        return None

def generate_comparison_plot(output_dir, lake_id, date_str, current_poly_path, ref_poly_path, dem_path=None, suffix=""):
    """
    Generates a plot showing the Reference Boundary vs Current Water Spread.
    """
    try:
        filename = f"{lake_id}_{date_str}_comparison{suffix}.png"
        out_path = os.path.join(output_dir, filename)
        
        fig, ax = plt.subplots(figsize=(6, 6)) # Square aspect
        
        # 1. Background (Clean White)
        ax.set_facecolor('white')
            
        # 2. Plot Reference Boundary (Base - Blue Outline)
        if ref_poly_path and os.path.exists(ref_poly_path):
            ref_gdf = gpd.read_file(ref_poly_path)
            ref_gdf.plot(ax=ax, facecolor='none', edgecolor='blue', linewidth=2, linestyle='--', label='Base')
            
            # Zoom to reference bounds
            minx, miny, maxx, maxy = ref_gdf.total_bounds
            ax.set_xlim(minx - 500, maxx + 500)
            ax.set_ylim(miny - 500, maxy + 500)

        # 3. Plot Current Water (Current - Red Contour)
        if current_poly_path and os.path.exists(current_poly_path):
             cur_gdf = gpd.read_file(current_poly_path)
             # Red Outline, Light Red Fill
             cur_gdf.plot(ax=ax, facecolor='red', alpha=0.1) # Light fill
             cur_gdf.plot(ax=ax, facecolor='none', edgecolor='red', linewidth=2, label='Current')
             
        ax.set_title(f"Spread Comparison: {date_str}")
        ax.axis('off') # Hide coords
        
        plt.tight_layout()
        plt.savefig(out_path, dpi=100, bbox_inches='tight')
        plt.close(fig)
        
        return filename
    except Exception as e:
        print(f"[WARN] Comparison plot generation failed: {e}")
        return None

import textwrap

# ... [Keep previous imports]

import time
import matplotlib
matplotlib.use('Agg') # Force non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# ...

# ======================================================
# COMPOSITE MAP V2 (Updated Legend)
# ======================================================
def generate_composite_map_v2(output_dir, lake_id, all_polys, dem_path=None):
    """
    Generates a single map overlaying ALL boundaries.
    all_polys: List of {"date": str, "path": str, "area": float, "filename": str}
    """
    try:
        if not all_polys: return None
        
        # Timestamp to avoid browser caching
        timestamp = int(time.time())
        filename = f"{lake_id}_composite_map_{timestamp}.png"
        out_path = os.path.join(output_dir, filename)
        
        # Increase figure size for legend
        fig, ax = plt.subplots(figsize=(12, 10))
        
        # 1. Background (DEM)
        if dem_path and os.path.exists(dem_path):
            with rasterio.open(dem_path) as src:
                show(src, ax=ax, cmap='terrain', alpha=0.4)
        else:
            ax.set_facecolor('white')
            
        # 2. Plot Polygons
        colors = plt.cm.jet(np.linspace(0, 1, len(all_polys)))
        
        base_area = None
        if len(all_polys) > 0:
            base_area = all_polys[0]["area"]

        legend_handles = []

        for idx, item in enumerate(all_polys):
            p_path = item["path"]
            p_date = item["date"]
            p_fname = item.get("filename", "Unknown")
            
            if os.path.exists(p_path):
                gdf = gpd.read_file(p_path)
                color = colors[idx]
                
                # Wrap long filename for legend
                clean_name = os.path.splitext(p_fname)[0] # Remove extension
                if len(clean_name) > 20:
                     clean_name = "\n".join(textwrap.wrap(clean_name, 20))
                
                # Relative Change Text
                curr_area = item["area"]
                rel_text = " (Base)"
                if idx > 0 and base_area > 0:
                     diff = ((curr_area - base_area) / base_area) * 100
                     sign = "+" if diff > 0 else ""
                     rel_text = f" ({sign}{diff:.1f}%)"
                
                label_text = f"{clean_name}\n{p_date}\n{curr_area} Ha{rel_text}"
                
                # Plot Outline
                gdf.plot(ax=ax, facecolor='none', edgecolor=color, linewidth=2)
                # Fill with very low alpha
                gdf.plot(ax=ax, color=color, alpha=0.1)
                
                # Create Custom Handle for Legend
                patch = mpatches.Patch(facecolor=color, edgecolor=color, alpha=0.3, label=label_text)
                legend_handles.append(patch)

        # Zoom to union bounds
        minx, miny, maxx, maxy = float('inf'), float('inf'), float('-inf'), float('-inf')
        found_poly = False
        for item in all_polys:
             if os.path.exists(item["path"]):
                 gdf = gpd.read_file(item["path"])
                 mnx, mny, mxx, mxy = gdf.total_bounds
                 minx = min(minx, mnx)
                 miny = min(miny, mny)
                 maxx = max(maxx, mxx)
                 maxy = max(maxy, mxy)
                 found_poly = True
             
        if found_poly:
            margin = 500
            ax.set_xlim(minx - margin, maxx + margin)
            ax.set_ylim(miny - margin, maxy + margin)
            
        ax.set_title("Multi-Temporal Composite Analysis")
        
        # Legend outside the plot
        lgd = ax.legend(handles=legend_handles, bbox_to_anchor=(1.05, 1), loc='upper left', borderaxespad=0., fontsize='small')
        
        ax.axis('off')
        
        # Save with extra artists (legend)
        plt.savefig(out_path, dpi=150, bbox_extra_artists=(lgd,), bbox_inches='tight')
        plt.close(fig)
        return filename
        
    except Exception as e:
        print(f"[WARN] Composite Map failed: {e}")
        return None


from mpl_toolkits.mplot3d import Axes3D
from matplotlib import cm

# ======================================================
# 3D VOLUME VISUALIZATION
# ======================================================
def generate_3d_volume_map(output_dir, lake_id, level_data, dem_path, suffix=""):
    """
    Generates a 3D perspective view of the lake bed and water levels.
    level_data: List of {"date": str, "level": float, "volume": float}
    dem_path: Path to the DEM file
    suffix: Optional suffix for filename
    """
    try:
        if not dem_path or not os.path.exists(dem_path) or not level_data:
            return None
            
        timestamp = int(time.time())
        filename = f"{lake_id}_3d_volume_{timestamp}{suffix}.png"
        out_path = os.path.join(output_dir, filename)

        with rasterio.open(dem_path) as src:
            # Read data
            # We must downsample heavily for 3D plotting performance
            # Target approx 100x100 grid or similar aspect ratio
            
            # Read low res
            overview_factor = max(1, int(max(src.width, src.height) / 100))
            data = src.read(1, out_shape=(1, int(src.height // overview_factor), int(src.width // overview_factor)))
            
            # Filter nodata
            data = data.astype('float32')
            data[data == src.nodata] = np.nan
            data[data < -100] = np.nan # Basic filter
            
            # Create meshgrid for X, Y
            rows, cols = data.shape
            x = np.linspace(src.bounds.left, src.bounds.right, cols)
            y = np.linspace(src.bounds.bottom, src.bounds.top, rows)
            X, Y = np.meshgrid(x, y)
            Z = data
            
        # Create Plot
        fig = plt.figure(figsize=(12, 10))
        ax = fig.add_subplot(111, projection='3d')
        
        # 1. Plot Terrain (Lake Bed)
        # Use a bathymetric colormap or terrain reversed
        surf = ax.plot_surface(X, Y, Z, cmap=cm.terrain, linewidth=0, antialiased=False, alpha=0.6)
        
        # 2. Plot Water Planes
        # Sort levels to handle transparency correctly (painters algo?)
        # Matplotlib 3D transparency is tricky.
        
        # We pick distinct colors for dates
        colors = ['blue', 'cyan', 'teal', 'navy']
        if len(level_data) > len(colors):
            colors = plt.cm.Blues(np.linspace(0.5, 1, len(level_data)))

        # Find bounds for Z axis
        z_min = np.nanmin(Z)
        z_max = np.nanmax(Z)
        
        # To avoid clutter, maybe only plot the FIRST (Base) and LAST (Current)?
        # Or all if few.
        items_to_plot = level_data
        
        legend_proxies = []
        
        for idx, item in enumerate(items_to_plot):
            lvl = item["level"]
            date = item["date"]
            vol = item.get("volume", 0)
            
            # Color
            c = colors[idx % len(colors)]
            
            # Create a plane at Z = lvl
            # We restrict the plane to where Z_terrain < lvl (i.e., inside the lake)
            # or just plot a flat square for context? 
            # Better: Plot flat square trimmed to axis bounds
            
            # Create a water surface array
            # We can use the same X, Y
            water_Z = np.full_like(Z, lvl)
            
            # Mask water where it's below terrain? (Technically water is ON TOP, but for vis we want to see the "fill")
            # Usually we want to show the water surface. 
            # Mask out where water_Z < Z (terrain sticks out)
            water_Z[water_Z < Z] = np.nan
            
            ax.plot_surface(X, Y, water_Z, color=c, alpha=0.4, shade=False)
            
            # Cleanup Date for Legend (remove extension if passed as date/name)
            # Actually level_data has 'date' which is date string.
            # But just in case we add name data?
            # For now, just use date.
            
            # If we want filename in 3D map legend? 
            # The user asked: "legend sould be the lake file name wihtout he extension"
            # Current 3D map uses 'date' for label. 
            # I should update level_data to include filename.
            
            f_name_raw = item.get("filename", "")
            clean_fname = os.path.splitext(f_name_raw)[0] if f_name_raw else date
            
            # Legend Entry
            label = f"{clean_fname}: {lvl}m ({vol:.2f} TMC)"
            legend_proxies.append(mpatches.Patch(color=c, alpha=0.4, label=label))
            
            z_max = max(z_max, lvl)

        # Labels
        ax.set_title("3D Volumetric Change Visualization")
        ax.set_zlabel("Elevation (m)")
        
        # Adjust View
        ax.view_init(elev=30, azim=-60)
        
        # Z Limits
        # Default fallback (Reverted Zoom as per user request to show context)
        min_z = np.nanmin(Z)
        max_z = np.nanmax(Z)
        ax.set_zlim(min_z, max(max_z, min_z + 20))
        
        # Legend with unique entries
        ax.legend(handles=legend_proxies, loc='upper left', bbox_to_anchor=(0.0, 1.0), fontsize='small')

        plt.tight_layout()
        plt.savefig(out_path, dpi=120)
        plt.close(fig)
        
        return filename

    except Exception as e:
        print(f"[WARN] 3D Map failed: {e}")
        return None

# ======================================================
# ORCHESTRATOR
# ======================================================
def analyze_lake(image_paths, dem_path, lake_id, date_string, output_dir, base_level=None, original_names=None):
    print(f"[DEBUG] Analysis Orchestrator: {len(image_paths)} images. DEM={dem_path}")
    
    dates = date_string.split(",") if date_string else []
    results = []
    masks_for_heatmap = []
    reference_poly_path = None # The polygon of the FIRST valid image
    all_polygons = [] # To store (date, path) for composite map
    
    base_area = None # For relative percentage change

    for i, sat_path in enumerate(image_paths):
        # Use original filename if provided, else basename
        filename = os.path.basename(sat_path)
        if original_names and i < len(original_names):
             filename = original_names[i]
             
        print(f"[DEBUG] Processing Image {i+1}/{len(image_paths)}: {filename}")
        date_str = dates[i].strip() if i < len(dates) else datetime.now().strftime("%Y-%m-%d")
        
        # 1. Processing
        area_res = process_water_from_image(
            sat_path, f"{lake_id}_{i}", date_str, output_dir
        )

        area_ha = area_res["area_ha"]
        poly = area_res["polygon_path"]
        mask_p = area_res.get("mask_path")
        
        if mask_p:
            masks_for_heatmap.append(mask_p)
            
        # Relative Change Calculation
        pct_change = 0.0
        if i == 0:
            base_area = area_ha
        elif base_area and base_area > 0:
            pct_change = ((area_ha - base_area) / base_area) * 100

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
                 vol_res["curve_df"]["volume_tmc"] = vol_res["curve_df"]["volume_m3"] / 28316846.592
                 vol_res["curve_df"].to_csv(curve_path, index=False)

            # Generate Individual 3D Map
            vol_3d_map = None
            if detected_level > 0:
                single_level_data = [{
                    "level": detected_level, 
                    "volume": vol_tmc, 
                    "date": date_str, 
                    "filename": filename
                }]
                vol_3d_map = generate_3d_volume_map(output_dir, lake_id, single_level_data, dem_path, suffix=f"_img_{i}")
    
        final_res = {
            "id": f"{lake_id}_{i}",
            "date": date_str,
            "filename": filename,
            "area_ha": round(area_ha, 2),
            "pct_change": round(pct_change, 2),
            "water_level": round(detected_level, 2),
            "volume_m3": round(volume_m3, 2),
            "volume_tmc": round(vol_tmc, 4),
            "min_elevation": round(elev_min, 2),
            "max_elevation": round(elev_max, 2),
            "message": "Analysis successful",
            "volume_map_3d": vol_3d_map,
            "result_image": area_res.get("image_png"),
            "polygon_path": poly
        }
        
        if volume_at_base is not None:
             final_res["base_level"] = round(float(base_level), 2)
             final_res["volume_at_level_m3"] = round(float(volume_at_base), 2)
             final_res["volume_at_level_tmc"] = round(float(volume_at_base) / 28316846.592, 4)
             
        # Generate Comparison Map
        # If this is the first image, set it as reference
        if i == 0 and poly:
             reference_poly_path = poly
             
        # Plot (Current vs Reference)
        if poly and reference_poly_path:
             print(f"[DEBUG] Generating Comparison Plot for {date_str}...")
             comp_map = generate_comparison_plot(output_dir, lake_id, date_str, poly, reference_poly_path, dem_path, suffix=f"_img_{i}")
             if comp_map:
                 final_res["comparison_map"] = comp_map
        
        if poly:
            all_polygons.append({
                "date": date_str, 
                "path": poly, 
                "area": area_ha,
                "filename": filename # Pass filename for legend
            })
            final_res["polygon_path"] = poly
            
        # Add the viewable mask image
        if "image_png" in area_res:
             final_res["result_image"] = area_res["image_png"] 

        results.append(final_res)
        
    # Generate Heatmap
    heatmap_file = generate_frequency_map(masks_for_heatmap, output_dir)
    if heatmap_file:
        for r in results:
            r["frequency_map"] = heatmap_file
            
    # Generate Composite Map (All in One)
    composite_file = generate_composite_map_v2(output_dir, lake_id, all_polygons, dem_path)
    
    # Generate 3D Volume Map
    level_list = []
    for r in results:
        if "water_level" in r and r["water_level"] > 0:
            level_list.append({
                "date": r["date"],
                "level": r["water_level"],
                "volume": r.get("volume_tmc", 0),
                "filename": r.get("filename", "")
            })
            
    volume_3d_file = generate_3d_volume_map(output_dir, lake_id, level_list, dem_path)
    
    if composite_file or volume_3d_file:
        for r in results:
            if composite_file: r["composite_map"] = composite_file
            if volume_3d_file: r["combined_volume_map"] = volume_3d_file
            
    return results
