import shutil
import os
import uuid
from datetime import date
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from . import pipeline

app = FastAPI()

@app.get("/")
def home():
    return {"message": "Lake Analysis API is running"}

# Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directory Setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

from fastapi import FastAPI, UploadFile, File, Form

# ... (imports)

from typing import List

@app.post("/analyze")
async def analyze(
    satellite: List[UploadFile] = File(...), 
    dem: UploadFile = File(None),
    base_level: float = Form(None),
    dates: str = Form(None)
):
    # Generate unique run ID
    run_id = str(uuid.uuid4())[:8]
    
    # Parse dates if provided
    date_list = []
    if dates:
        # Expect comma or newline separated dates
        date_list = [d.strip() for d in dates.replace("\n", ",").split(",") if d.strip()]
    
    # Save DEM if provided (optional) - ONE DEM for ALL images
    dem_abs_path = None
    if dem:
        dem_ext = os.path.splitext(dem.filename)[1]
        dem_filename = f"{run_id}_dem{dem_ext}"
        dem_path = os.path.join(UPLOAD_DIR, dem_filename)
        with open(dem_path, "wb") as f:
            shutil.copyfileobj(dem.file, f)
        dem_abs_path = dem_path
        print(f"[DEBUG] DEM saved to {dem_path}")

    results = []

    for idx, sat_file in enumerate(satellite):
        # Determine date for this image
        if idx < len(date_list):
            current_date_str = date_list[idx]
        else:
            # Fallback: Use today's date
            # If multiple images have same date, pipeline might overwrite specific day files, 
            # but usually fine for unique run_ids or different output filenames.
            # To be safe, we might want to append index or something if needed, 
            # but pipeline uses lake_id (run_id) + date. 
            # Let's simple use today
            current_date_str = str(date.today())

        # Save Uploaded File
        sat_ext = os.path.splitext(sat_file.filename)[1]
        # Unique filename per image
        sat_filename = f"{run_id}_sat_{idx}{sat_ext}"
        sat_path = os.path.join(UPLOAD_DIR, sat_filename)
        
        with open(sat_path, "wb") as f:
            shutil.copyfileobj(sat_file.file, f)
            
        print(f"[DEBUG] Processing Image {idx+1}/{len(satellite)}: {sat_filename} for date {current_date_str}")

        try:
            # Call Analysis Orchestrator
            # Call Analysis Orchestrator
            result = pipeline.analyze_lake(
                sat_path=sat_path,
                dem_path=dem_abs_path,
                lake_id=f"{run_id}_{idx}", # Unique ID per image to prevent overwrite
                date_str=current_date_str,
                output_dir=OUTPUT_DIR,
                base_level=base_level
            )
            
            # Add date to result for frontend display
            result["date"] = current_date_str
            results.append(result)
            
        except Exception as e:
            print(f"[ERROR] Processing {sat_filename} failed: {e}")
            results.append({
                "error": str(e), 
                "filename": sat_filename,
                "date": current_date_str
            })

    print(f"[DEBUG] All processing done. Returning {len(results)} results.")
    return results
