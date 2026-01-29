import os
import uuid
from datetime import datetime
import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.crs import CRS
from rasterio.features import shapes
from rasterio.vrt import WarpedVRT
import geopandas as gpd
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from rasterio.plot import show

try:
    from s2cloudless import S2PixelCloudDetector
    S2CLOUDLESS_AVAILABLE = True
except ImportError:
    S2CLOUDLESS_AVAILABLE = False


# ======================================================
# CONSTANTS
# ======================================================
NDWI_THRESHOLD = 0.0 # Adjustable


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

def detect_green_nir_bands(src):
    count = src.count
    # Simple logic based on band count
    if count == 4:
        return 1, 3  # B3, B8 (Indicies 1, 3 for 0-indexed access? No, rasterio bands are 1-indexed usually, but read() returns array)
    if count >= 12:
        return 2, 7  # Sentinel-2 standard (B3=idx2, B8=idx7)

    # Default fallback for subsets
    return 1, 3

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
    # date = datetime.strptime(date_str, "%Y-%m-%d").date() # handle logic outside?
    
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

        ndwi_path = os.path.join(ndwi_dir, f"{lake_id}_{date_str}_ndwi.tif")
        prof = profile.copy()
        prof.update(dtype="float32", count=1, nodata=np.nan)
        with rasterio.open(ndwi_path, "w", **prof) as dst:
            dst.write(ndwi, 1)

        water = (ndwi >= NDWI_THRESHOLD).astype(np.uint8)

        mask_path = os.path.join(mask_dir, f"{lake_id}_{date_str}_mask.tif")
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
            return {"area_ha": 0.0, "polygon_path": None, "mask_path": None}

        gdf = gpd.GeoDataFrame.from_features(geoms, crs=profile["crs"])
        gdf["area_m2"] = gdf.area
        gdf = gdf.sort_values("area_m2", ascending=False).head(1)
        area_ha = float(gdf.area.iloc[0] / 10000)

        poly_path = os.path.join(poly_dir, f"{lake_id}_{date_str}_water.geojson")
        gdf.to_file(poly_path, driver="GeoJSON")

        return {"area_ha": area_ha, "polygon_path": poly_path, "mask_path": mask_path}


# ======================================================
# DEM-BASED VOLUME
# ======================================================
def calculate_lake_volume(dem_path, polygon_path, base_level=None, target_area_ha=None):
    # Note: polygon_path is now used only for CRS reference, not for clipping the DEM.
    # This ensures "Volume @ Base Level" refers to the full DEM capacity.
    print(f"[DEBUG] Calculating Volume (Full Basin): DEM={os.path.basename(dem_path)}")
    gdf = gpd.read_file(polygon_path)
    print(f"[DEBUG] Ref CRS from Poly: {gdf.crs}")
    
    # Ensure Polygon is Projected (Metric) for accurate Volume
    # We FORCE a Metric CRS (UTM 44N) to guarantee pixel_area is in Meters.
    # (Assuming South India/Tamil Nadu region for this project)
    dst_crs = 'EPSG:32644'
    if gdf.crs != dst_crs:
         print(f"[DEBUG] Reprojecting Polygon to {dst_crs} for Metric Volume Calc.")
         gdf = gdf.to_crs(dst_crs)

    with rasterio.open(dem_path) as src:
        print(f"[DEBUG] DEM CRS: {src.crs}, Bounds: {src.bounds}")
        
        # Use WarpedVRT to reproject DEM to Metric CRS on the fly
        with WarpedVRT(src, crs=dst_crs, resampling=Resampling.bilinear) as vrt:
            print(f"[DEBUG] Warping DEM to {dst_crs}")
            
            # Read the full DEM (no masking by water polygon)
            dem = vrt.read(1)
            # Update transform to warped version
            transform = vrt.transform
            print(f"[DEBUG] Full DEM Shape: {dem.shape}")
            print(f"[DEBUG] VRT Transform: {transform}")
            
            # Update pixel area based on the WARPED transform (Meters)
            # transform[0] is pixel width, transform[4] is pixel height (often negative)
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

    df = pd.DataFrame(records)
    
    if df.empty:
         print(f"[WARN] Volume Curve Empty. Min Elev: {min_elev}, Max: {max_elev}")
         return {"min_elevation": min_elev, "max_elevation": max_elev, "max_volume_m3": 0, "curve_df": df}
         
    final_max_vol = df['volume_m3'].max()
    min_curve_area = df['area_ha'].min()
    print(f"[DEBUG] Volume Curve Generated. Points: {len(df)}. Min Area: {min_curve_area:.2f} Ha, Max Vol: {final_max_vol:.2f} m3")

    # Interpolate for Base Level
    volume_at_base = 0
    if base_level is not None:
         # Find closest or interp
         try:
             volume_at_base = np.interp(base_level, df['elevation'], df['volume_m3'])
         except:
             volume_at_base = 0

    # Interpolate Current Volume based on Target Area
    current_vol = 0
    detected_level = min_elev
    
    if target_area_ha is not None:
        try:
             # We want to find Volume where Area = target_area_ha
             # Since Area increases with Elevation, we can interp.
             # x = area, y = volume
             # Check if target area is within range
             min_curve_area = df['area_ha'].min()
             max_curve_area = df['area_ha'].max()
             
             if target_area_ha > max_curve_area:
                 print(f"[WARN] Target Area {target_area_ha} > Max Curve Area {max_curve_area}. Using Max Volume.")
                 current_vol = final_max_vol
                 detected_level = max_elev
             elif target_area_ha <= min_curve_area:
                 # Interpolate between 0 and smallest curve point
                 print(f"[INFO] Target Area {target_area_ha} <= Min Curve Area {min_curve_area}. Interpolating down to 0.")
                 # Add (0,0) point virtually for interpolation
                 xp = [0] + df['area_ha'].tolist()
                 yp = [0] + df['volume_m3'].tolist()
                 yp_elev = [min_elev - 1.0] + df['elevation'].tolist() # Extend elevation down slightly
                 
                 current_vol = np.interp(target_area_ha, xp, yp)
                 detected_level = np.interp(target_area_ha, xp, yp_elev)
             else:
                current_vol = np.interp(target_area_ha, df['area_ha'], df['volume_m3'])
                detected_level = np.interp(target_area_ha, df['area_ha'], df['elevation'])
                print(f"[DEBUG] Interpolated Vol: {current_vol} m3 @ {detected_level} m")
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

def generate_comparison_plot(output_dir, lake_id, date_str, current_poly_path, ref_poly_path, dem_path=None):
    """
    Generates a plot showing the Reference Boundary (Red Outline) vs Current Water Spread (Blue Fill).
    Background: DEM (if available) or Blank.
    """
    try:
        filename = f"{lake_id}_{date_str}_comparison.png"
        out_path = os.path.join(output_dir, filename)
        
        fig, ax = plt.subplots(figsize=(6, 6)) # Square aspect
        
        # 1. Plot Background (DEM or White)
        if dem_path and os.path.exists(dem_path):
            with rasterio.open(dem_path) as src:
                # We should really clip this to the polygon bounds, but plotting the whole thing is safer for context.
                # If DEM is huge, this might be slow/ugly.
                # For now, let's just assume we want context.
                # Better: Plot the DEM but strictly zoomed to the Ref Polygon Bounds.
                show(src, ax=ax, cmap='terrain', alpha=0.5)
        else:
            ax.set_facecolor('white')
            
        # 2. Plot Reference Boundary (Red Outline)
        if ref_poly_path and os.path.exists(ref_poly_path):
            ref_gdf = gpd.read_file(ref_poly_path)
            # Ensure CRS matches if we plotted DEM? 
            # Assuming all are in same CRS or we accept mismatch for now (usually we handle reprojection).
            # For purely visual, let's just plot.
            ref_gdf.plot(ax=ax, facecolor='none', edgecolor='red', linewidth=2, label='Reference')
            
            # Zoom to reference bounds
            minx, miny, maxx, maxy = ref_gdf.total_bounds
            ax.set_xlim(minx - 500, maxx + 500)
            ax.set_ylim(miny - 500, maxy + 500)

        # 3. Plot Current Water (Blue Fill)
        if current_poly_path and os.path.exists(current_poly_path):
             cur_gdf = gpd.read_file(current_poly_path)
             cur_gdf.plot(ax=ax, color='blue', alpha=0.5, label='Current Water')
             
        ax.set_title(f"Spread Comparison: {date_str}")
        ax.axis('off') # Hide coords
        
        plt.tight_layout()
        plt.savefig(out_path, dpi=100, bbox_inches='tight')
        plt.close(fig)
        
        return filename
    except Exception as e:
        print(f"[WARN] Comparison plot generation failed: {e}")
        return None

def generate_composite_map_v2(output_dir, lake_id, all_polys, dem_path=None):
    """
    Generates a single map overlaying ALL boundaries.
    all_polys: List of {"date": str, "path": str, "area": float}
    """
    try:
        if not all_polys: return None
        
        filename = f"{lake_id}_composite_map.png"
        out_path = os.path.join(output_dir, filename)
        
        fig, ax = plt.subplots(figsize=(10, 10))
        
        # 1. Background (DEM)
        if dem_path and os.path.exists(dem_path):
            with rasterio.open(dem_path) as src:
                show(src, ax=ax, cmap='terrain', alpha=0.4)
        else:
            ax.set_facecolor('white')
            
        # 2. Plot Polygons
        # Sort by Area (Largest first) so smaller ones appear on top? 
        # Or Sort by Date? Let's sort by Date for chronology or Area for visibility.
        # "Show how relatively area changes" -> Chronology is sometimes better.
        # But if a later one is huge, it covers earlier ones.
        # Let's use transparency + colored lines.
        
        # Define colors (Red, Orange, Yellow, Green, Blue, Purple)
        colors = plt.cm.jet(np.linspace(0, 1, len(all_polys)))
        
        for idx, item in enumerate(all_polys):
            p_path = item["path"]
            p_date = item["date"]
            if os.path.exists(p_path):
                gdf = gpd.read_file(p_path)
                color = colors[idx]
                
                # Plot Outline with Label
                gdf.plot(ax=ax, facecolor='none', edgecolor=color, linewidth=2, label=f"{p_date} ({item['area']} Ha)")
                # Fill with very low alpha
                gdf.plot(ax=ax, color=color, alpha=0.1)

        # Zoom to union bounds
        # (Simplified: Zoom to last polygon assuming they overlap, or first)
        # Better: iterate all to find min/max
        minx, miny, maxx, maxy = float('inf'), float('inf'), float('-inf'), float('-inf')
        for item in all_polys:
             gdf = gpd.read_file(item["path"])
             mnx, mny, mxx, mxy = gdf.total_bounds
             minx = min(minx, mnx)
             miny = min(miny, mny)
             maxx = max(maxx, mxx)
             maxy = max(maxy, mxy)
             
        if minx != float('inf'):
            margin = 500
            ax.set_xlim(minx - margin, maxx + margin)
            ax.set_ylim(miny - margin, maxy + margin)
            
        ax.set_title("Composite Spread Analysis (All Dates)")
        ax.legend(loc='upper right', fontsize='small')
        ax.axis('off')
        
        plt.tight_layout()
        plt.savefig(out_path, dpi=150, bbox_inches='tight')
        plt.close(fig)
        return filename
        
    except Exception as e:
        print(f"[WARN] Composite Map failed: {e}")
        return None


# ======================================================
# ORCHESTRATOR
# ======================================================
def analyze_lake(image_paths, dem_path, lake_id, date_string, output_dir, base_level=None):
    print(f"[DEBUG] Analysis Orchestrator: {len(image_paths)} images. DEM={dem_path}")
    
    dates = date_string.split(",") if date_string else []
    results = []
    masks_for_heatmap = []
    reference_poly_path = None # The polygon of the FIRST valid image
    all_polygons = [] # To store (date, path) for composite map

    for i, sat_path in enumerate(image_paths):
        print(f"[DEBUG] Processing Image {i+1}/{len(image_paths)}: {os.path.basename(sat_path)}")
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
    
        final_res = {
            "id": f"{lake_id}_{i}",
            "date": date_str,
            "area_ha": round(area_ha, 2),
            "water_level": round(detected_level, 2),
            "volume_m3": round(volume_m3, 2),
            "volume_tmc": round(vol_tmc, 4),
            "min_elevation": round(elev_min, 2),
            "max_elevation": round(elev_max, 2),
            "message": "Analysis successful"
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
             if comp_map:
                 final_res["comparison_map"] = comp_map
        
        if poly:
            all_polygons.append({"date": date_str, "path": poly, "area": area_ha})
            # Also store poly path in result for composite map function if needed later?
            # actually I can just pass all_polygons list.
            final_res["polygon_path"] = poly # Store for reference

        results.append(final_res)
        
    # Generate Heatmap
    heatmap_file = generate_frequency_map(masks_for_heatmap, output_dir)
    if heatmap_file:
        for r in results:
            r["frequency_map"] = heatmap_file
            
    # Generate Composite Map (All in One)
    composite_file = generate_composite_map_v2(output_dir, lake_id, all_polygons, dem_path)
    if composite_file:
        for r in results:
            r["composite_map"] = composite_file
            
    return results
