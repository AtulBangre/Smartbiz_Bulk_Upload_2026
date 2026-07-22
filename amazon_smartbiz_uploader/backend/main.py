from fastapi import FastAPI, HTTPException, Request, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import List, Optional
import uvicorn
import os
import io
from datetime import datetime, timezone
from bson import ObjectId

from database import admin_collection, drafts_collection, sheets_collection, get_fs
from auth import verify_password, create_access_token, get_current_admin, get_password_hash
from upload_handler import process_draft_upload
from scraper import scrape_amazon_product
from seo_generator import generate_seo_tags
from excel_handler import generate_smartbiz_excel

app = FastAPI(title="Amazon SmartBiz Uploader API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    try:
        hashed = get_password_hash("adminpassword123")
        await admin_collection.update_one(
            {"username": "admin"},
            {"$set": {"username": "admin", "hashed_password": hashed}},
            upsert=True
        )
        print("Default admin account successfully initialized/reset.")
    except Exception as e:
        print(f"Startup admin init warning: {e}")

# Helper to fix ObjectId serialization
def serialize_doc(doc):
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc

# --- AUTH ROUTES ---
@app.post("/api/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    try:
        admin = await admin_collection.find_one({"username": form_data.username})
        if not admin or not verify_password(form_data.password, admin["hashed_password"]):
            raise HTTPException(status_code=400, detail="Incorrect username or password")
            
        access_token = create_access_token(data={"sub": admin["username"]})
        return {"access_token": access_token, "token_type": "bearer"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Login internal error: {e}")
        raise HTTPException(status_code=500, detail=f"Database or Server Error: {str(e)}")

# --- DRAFT ROUTES ---
class DraftItemCreate(BaseModel):
    url: str
    custom_sku: str = ""
    business_category: str = "GENERAL"
    product_category: str = ""
    variant_relationship: str = ""
    size: str = ""
    color_name: str = ""
    best_seller: str = "No"

@app.get("/api/draft")
async def get_drafts(current_admin = Depends(get_current_admin)):
    cursor = drafts_collection.find({"username": current_admin["username"]})
    items = await cursor.to_list(length=1000)
    return [serialize_doc(i) for i in items]

@app.post("/api/draft/item")
async def add_draft_item(item: DraftItemCreate, current_admin = Depends(get_current_admin)):
    doc = item.model_dump()
    doc["username"] = current_admin["username"]
    result = await drafts_collection.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc

@app.delete("/api/draft/item/{item_id}")
async def delete_draft_item(item_id: str, current_admin = Depends(get_current_admin)):
    result = await drafts_collection.delete_one({"_id": ObjectId(item_id), "username": current_admin["username"]})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"status": "success"}

@app.delete("/api/draft/clear")
async def clear_draft(current_admin = Depends(get_current_admin)):
    await drafts_collection.delete_many({"username": current_admin["username"]})
    return {"status": "success"}

@app.get("/api/draft/template")
async def download_draft_template():
    from openpyxl import Workbook
    from openpyxl.worksheet.datavalidation import DataValidation
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Draft Template"
    
    headers = [
        "Amazon Link / ASIN", "Custom SKU", "Business Category", 
        "Product Category", "Variant Relationship", "Size", 
        "Color Name", "Best Seller"
    ]
    ws.append(headers)
    
    # Setup Dropdowns (Data Validation)
    # Business Category (Column C)
    categories = '"APPLIANCES,BABY,BEAUTY_AND_PERSONAL_CARE,BOOKS_AND_STATIONERY,CLOTHING,ELECTRONICS,FOOD_AND_GROCERY,FOOTWEAR,FURNITURE,GENERAL,HEALTH_SUPPLEMENTS,HOME_CARE,HOME_AND_KITCHEN,JEWELRY,LAWN_AND_GARDEN,LUGGAGE_AND_BAGS,MULTIPURPOSE,PET_PRODUCTS,SPORTS_AND_FITNESS,TOYS_AND_GAMES,WATCHES"'
    dv_cat = DataValidation(type="list", formula1=categories, allow_blank=True)
    dv_cat.error = 'Your entry is not in the list'
    dv_cat.errorTitle = 'Invalid Entry'
    dv_cat.prompt = 'Please select from the list'
    dv_cat.promptTitle = 'Select Category'
    ws.add_data_validation(dv_cat)
    dv_cat.add("C2:C1000")
    
    # Variant Relationship (Column E)
    dv_var = DataValidation(type="list", formula1='"Parent,Child"', allow_blank=True)
    ws.add_data_validation(dv_var)
    dv_var.add("E2:E1000")
    
    # Best Seller (Column H)
    dv_best = DataValidation(type="list", formula1='"Yes,No"', allow_blank=True)
    ws.add_data_validation(dv_best)
    dv_best.add("H2:H1000")
    
    # Adjust column widths slightly for better UX
    for col in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']:
        ws.column_dimensions[col].width = 20
    
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    
    return StreamingResponse(
        buffer, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Draft_Upload_Template.xlsx"}
    )

@app.post("/api/draft/upload-excel")
async def upload_excel_draft(file: UploadFile = File(...), current_admin = Depends(get_current_admin)):
    return await process_draft_upload(file, drafts_collection, current_admin["username"])

# --- GENERATE & HISTORY ROUTES ---
class GenerateRequest(BaseModel):
    sheet_name: str

@app.post("/api/generate")
async def generate_excel(request: GenerateRequest, current_admin = Depends(get_current_admin)):
    try:
        # 1. Fetch draft items
        cursor = drafts_collection.find({"username": current_admin["username"]})
        items = await cursor.to_list(length=1000)
        
        if not items:
            raise HTTPException(status_code=400, detail="Your draft is empty.")

        scraped_data = []
        for item in items:
            url = item.get("url", "")
            if url and not url.startswith("http"):
                url = f"https://www.amazon.in/dp/{url}"
                
            try:
                details = await scrape_amazon_product(url)
            except Exception as e:
                print(f"Scraper error for {url}: {e}")
                details = {"name": "Amazon Product", "mrp": "1000", "selling_price": "800", "description": "", "images": []}
                
            try:
                seo_data = await generate_seo_tags(details.get("name", ""), details.get("description", ""))
            except Exception as e:
                print(f"SEO gen error: {e}")
                seo_data = {"seo_title": "", "seo_description": ""}
            
            product_data = {
                "custom_sku": item.get("custom_sku", ""),
                "business_category": item.get("business_category", ""),
                "product_category": item.get("product_category", ""),
                "variant_relationship": item.get("variant_relationship", ""),
                "size": item.get("size", ""),
                "color_name": item.get("color_name", ""),
                "best_seller": item.get("best_seller", ""),
                "name": details.get("name", ""),
                "mrp": details.get("mrp", ""),
                "selling_price": details.get("selling_price", ""),
                "description": details.get("description", ""),
                "images": details.get("images", []),
                "seo_title": seo_data.get("seo_title", ""),
                "seo_description": seo_data.get("seo_description", "")
            }
            scraped_data.append(product_data)
            
        # 2. Generate Excel in memory
        template_path = os.path.join(os.path.dirname(__file__), "smartbiz_bulk_upload_template_v5 (2).xlsx")
        temp_output_path = os.path.join(os.path.dirname(__file__), f"temp_{ObjectId()}.xlsx")
        
        success = generate_smartbiz_excel(scraped_data, template_path, temp_output_path)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to generate Excel file")
            
        # 3. Save to GridFS
        fs = get_fs()
        with open(temp_output_path, "rb") as f:
            file_id = await fs.upload_from_stream(
                f"{request.sheet_name}.xlsx", 
                f,
                metadata={"contentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
            )
            
        if os.path.exists(temp_output_path):
            os.remove(temp_output_path)
        
        # 4. Save history record
        record = {
            "username": current_admin["username"],
            "sheet_name": request.sheet_name,
            "file_id": file_id,
            "date_generated": datetime.now(timezone.utc).isoformat(),
            "item_count": len(items)
        }
        await sheets_collection.insert_one(record)
        
        # 5. Clear draft
        await drafts_collection.delete_many({"username": current_admin["username"]})
        
        return {"status": "success", "file_id": str(file_id)}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in generate_excel: {e}")
        raise HTTPException(status_code=500, detail=f"Generation error: {str(e)}")

@app.get("/api/sheets/history")
async def get_history(current_admin = Depends(get_current_admin)):
    cursor = sheets_collection.find({"username": current_admin["username"]}).sort("date_generated", -1)
    history = await cursor.to_list(length=100)
    for h in history:
        h["_id"] = str(h["_id"])
        h["file_id"] = str(h["file_id"])
    return history

@app.get("/api/sheets/download/{file_id}")
async def download_sheet(file_id: str):
    fs = get_fs()
    try:
        grid_out = await fs.open_download_stream(ObjectId(file_id))
        content = await grid_out.read()
        
        return StreamingResponse(
            io.BytesIO(content), 
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={grid_out.filename}"}
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail="File not found")

@app.delete("/api/sheets/{sheet_id}")
async def delete_sheet(sheet_id: str, current_admin = Depends(get_current_admin)):
    sheet = await sheets_collection.find_one({"_id": ObjectId(sheet_id), "username": current_admin["username"]})
    if not sheet:
        raise HTTPException(status_code=404, detail="Sheet record not found")
        
    fs = get_fs()
    await fs.delete(sheet["file_id"])
    await sheets_collection.delete_one({"_id": ObjectId(sheet_id)})
    return {"status": "success"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
