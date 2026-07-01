from fastapi import FastAPI, Response, Request
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel 
from datetime import datetime
import pyoxigraph

import crawler  # Extends your existing crawler functionalities

#####################################################################################################
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting up LDES API...")
    yield
    print("Shutting down LDES API...")

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

#####################################################################################################
class fetch_ldes_params(BaseModel):
    base_uri: str
    before_date: str
    after_date: str

#####################################################################################################
@app.get("/")
async def root():
    return {"message": "Welcome to the LDES Crawler API!"}

@app.post("/fetch_ldes")
async def fetch_ldes(params: fetch_ldes_params):
    # 1. Parse date formats
    try:
        parsed_before_date = datetime.strptime(params.before_date, '%d-%m-%Y')
        parsed_after_date = datetime.strptime(params.after_date, '%d-%m-%Y')
    except ValueError:
        return {"status": "error", "message": "Invalid date format. Please use 'DD-MM-YYYY'."}
        
    base_uri = params.base_uri

    if parsed_after_date > parsed_before_date:
        return {"status": "error", "message": "'after_date' must be earlier than or equal to 'before_date'."}
    
    # 2. CRITICAL: Reset the crawler's global state so multi-user/multi-requests don't mix up data
    crawler.years_set.clear()
    crawler.months_set.clear()
    crawler.day_set.clear()
    crawler.members_set.clear()
    crawler.objects_store = pyoxigraph.Store()  # Re-instantiate a fresh in-memory graph store

    # 3. Execute the full sequential workflow from crawler.py
    try:
        print("Starting full LDES Crawling pipeline...")
        
        crawler.fetch_ldes_year(base_uri, before_date=parsed_before_date, after_date=parsed_after_date)
        print("Completed: Year parsing.")
        
        crawler.fetch_ldes_month(before_date=parsed_before_date, after_date=parsed_after_date)
        print("Completed: Month parsing.")
        
        crawler.fetch_ldes_day(before_date=parsed_before_date, after_date=parsed_after_date)
        print("Completed: Day parsing.")
        
        crawler.fetch_ldes_members()
        print("Completed: Member extraction & store population.")
        
        # Optional: Interact with your Virtuoso Triplestore
        crawler.clear_triplestore()
        
        # Write to your output graph file defined in constants
        crawler.dump_graph_file()
        
        # Verify changes
        crawler.verify_triplestore()
        
        # 4. Return an informative execution summary back to the API client
        return {
            "status": "success",
            "message": "Full LDES crawling, processing, and storage pipeline completed successfully.",
            "summary": {
                "base_uri_processed": base_uri,
                "years_found": len(crawler.years_set),
                "months_found": len(crawler.months_set),
                "days_found": len(crawler.day_set),
                "total_members_extracted": len(crawler.members_set)
            }
        }
        
    except Exception as e:
        print(f"Pipeline failed: {e}")
        return {
            "status": "error",
            "message": f"An unhandled error occurred during crawling execution: {str(e)}"
        }