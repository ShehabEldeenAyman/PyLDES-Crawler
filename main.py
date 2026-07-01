from fastapi import FastAPI, Response, Request
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel 
from datetime import datetime
import pyoxigraph

import crawler

#####################################################################################################
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Simplified lifespan without file system restoration checks
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
    try:
        parsed_before_date = datetime.strptime(params.before_date, '%d-%m-%Y')
        parsed_after_date = datetime.strptime(params.after_date, '%d-%m-%Y')
    except ValueError:
        return {"status": "error", "message": "Invalid date format. Please use 'DD-MM-YYYY'."}
        
    base_uri = params.base_uri

    if parsed_after_date > parsed_before_date:
        return {"status": "error", "message": "'after_date' must be earlier than or equal to 'before_date'."}
    
    # 1. Clear ONLY the discovery path sets so this crawl targets ONLY the new URI structure
    crawler.years_set.clear()
    crawler.months_set.clear()
    crawler.day_set.clear()
    crawler.members_set.clear()

    # NOTE: We intentionally do NOT clear crawler.objects_store here. 
    # It will continue to store and aggregate triples from all processed URIs over its uptime.

    try:
        print(f"Pipeline started for URI: {base_uri}")
        
        # 2. Run sequential crawling steps
        crawler.fetch_ldes_year(base_uri, before_date=parsed_before_date, after_date=parsed_after_date)
        crawler.fetch_ldes_month(before_date=parsed_before_date, after_date=parsed_after_date)
        crawler.fetch_ldes_day(before_date=parsed_before_date, after_date=parsed_after_date)
        crawler.fetch_ldes_members()
        
        # 3. Handle external storage updates
        crawler.clear_triplestore()
        crawler.dump_graph_file()
        crawler.upload_graph_triplestore()
        crawler.verify_triplestore()
        
        return {
            "status": "success",
            "message": f"Data from {base_uri} has been merged into the in-memory store.",
            "store_metrics": {
                "total_accumulated_triples": len(crawler.objects_store),
                "new_uris_discovered_this_run": {
                    "years": len(crawler.years_set),
                    "months": len(crawler.months_set),
                    "days": len(crawler.day_set)
                }
            }
        }
        
    except Exception as e:
        print(f"Pipeline failed: {e}")
        return {
            "status": "error",
            "message": f"An error occurred during crawling execution: {str(e)}"
        }