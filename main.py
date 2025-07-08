# main.py

import os
import asyncio
import json
import uuid
from dotenv import load_dotenv

# --- Third-Party Imports ---
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from googleapiclient.discovery import build
import redis

# --- FastAPI and Pydantic Imports ---
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# --- Load Environment Variables ---
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
SEARCH_ENGINE_ID = os.getenv("SEARCH_ENGINE_ID")
KV_URL = os.getenv("KV_URL")

# --- Startup Validation ---
if not all([GEMINI_API_KEY, GOOGLE_API_KEY, SEARCH_ENGINE_ID, KV_URL]):
    raise RuntimeError("CRITICAL ERROR: One or more environment variables are not set.")

# --- Configure API Clients ---
genai.configure(api_key=GEMINI_API_KEY)
kv = redis.from_url(KV_URL)


# ==============================================================================
# SECTION 1: Pydantic Models for Data Validation
# ==============================================================================

class ProductQuery(BaseModel):
    country: str
    query: str

class ProductResult(BaseModel):
    link: str
    price: float
    currency: str
    productName: str

class TaskResponse(BaseModel):
    task_id: str

class TaskStatus(BaseModel):
    status: str
    data: list[ProductResult] | str | None = None


# ==============================================================================
# SECTION 2: Core Logic Functions (The Worker)
# ==============================================================================

def discover_sources(query: str, country_code: str) -> list[str]:
    """Uses Google's Programmable Search Engine to find potential retailer websites."""
    # FIX: Make the search query more specific to e-commerce
    search_query = f"buy {query} online price"
    print(f"Discovering sources for '{search_query}' in country '{country_code}'...")
    try:
        service = build("customsearch", "v1", developerKey=GOOGLE_API_KEY)
        res = service.cse().list(
            q=search_query, # Use the refined search query
            cx=SEARCH_ENGINE_ID,
            gl=country_code.lower(),
            num=5
        ).execute()
        urls = [item['link'] for item in res.get('items', []) if 'link' in item]
        print(f"Found {len(urls)} potential sources via Google CSE.")
        return urls
    except Exception as e:
        print(f"Error during source discovery: {e}")
        return []

async def extract_product_data_with_gemini(url: str, user_query: str) -> ProductResult | None:
    """Fetches HTML from a URL and uses Gemini to extract structured product data."""
    try:
        print(f"Processing URL: {url}")
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        # FIX: Increase timeout to 20 seconds to handle slow sites
        response = await asyncio.to_thread(requests.get, url, headers=headers, timeout=20)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # FIX: Add a guard clause to prevent crash if page has no <body> tag
        if not soup.body:
            print(f"No <body> tag found on {url}. Skipping.")
            return None

        for tag in soup.body.find_all(['script', 'style', 'nav', 'footer', 'header', 'svg', 'iframe']):
            tag.decompose()
        html_content = str(soup.body)[:50000]

        prompt = f"Analyze the HTML from a product webpage. The user is searching for: '{user_query}'. Identify the main product's name, its price, and currency. Check if the product is relevant to the user's query. HTML: ```html {html_content} ```"
        system_instruction = """You are an expert data extraction bot. Your response MUST be a single, clean JSON object. The JSON must have three keys: "productName" (string), "price" (number), and "currency" (string). The 'price' value MUST be a number (integer or float). The 'currency' value MUST be a standard 3-letter ISO 4217 currency code (e.g., "USD", "INR", "EUR"), not a symbol. If you cannot find all required information or if the product is not relevant, your entire response must be the single word: null. Do not include any other text or markdown."""
        
        model = genai.GenerativeModel('gemini-2.5-flash-latest', system_instruction=system_instruction)
        gemini_response = await asyncio.to_thread(
            model.generate_content, 
            prompt, 
            generation_config=genai.types.GenerationConfig(temperature=0.1)
        )
        
        cleaned_response_text = gemini_response.text.strip()
        
        if cleaned_response_text.lower() == "null": return None
        if cleaned_response_text.startswith("```json"): cleaned_response_text = cleaned_response_text[7:-3].strip()

        data = json.loads(cleaned_response_text)
        if not all(k in data for k in ["productName", "price", "currency"]) or not isinstance(data["price"], (int, float)): return None

        print(f"Successfully extracted from {url}: {data}")
        return ProductResult(link=url, **data)
    except Exception as e:
        print(f"Error processing {url}: {e}")
        return None

async def perform_search_and_store_results(task_id: str, query: str, country: str):
    """The main worker function that runs in the background."""
    print(f"[{task_id}] Starting background search...")
    try:
        urls = discover_sources(query, country)
        if not urls:
            raise ValueError("Could not find any potential sources for the given query.")
        
        tasks = [extract_product_data_with_gemini(url, query) for url in urls]
        results = await asyncio.gather(*tasks)
        successful_results = [res for res in results if res is not None]
        
        if not successful_results:
            raise ValueError("AI could not extract valid product information from any of the discovered sources. The sites may be blocking automated access or the search query was too generic.")
        
        sorted_results = sorted(successful_results, key=lambda x: x.price)
        final_data = TaskStatus(status="completed", data=[res.model_dump() for res in sorted_results])
        kv.set(task_id, final_data.model_dump_json(), ex=3600)
        print(f"[{task_id}] Task completed and results stored.")

    except Exception as e:
        print(f"[{task_id}] Task failed: {e}")
        error_data = TaskStatus(status="failed", data=str(e))
        kv.set(task_id, error_data.model_dump_json(), ex=3600)


# ==============================================================================
# SECTION 3: FastAPI Application Setup
# ==============================================================================

app = FastAPI(title="Universal Price Fetcher API")

# API Route Definitions
@app.post("/start-search", response_model=TaskResponse, status_code=202)
async def start_search_endpoint(query: ProductQuery, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    print(f"Received request. Assigning task_id: {task_id}")
    initial_data = TaskStatus(status="pending", data=None)
    kv.set(task_id, initial_data.model_dump_json(), ex=3600)
    background_tasks.add_task(perform_search_and_store_results, task_id, query.query, query.country)
    return {"task_id": task_id}

@app.get("/search-status/{task_id}", response_model=TaskStatus)
async def get_search_status_endpoint(task_id: str):
    result = kv.get(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Search task not found or expired.")
    return json.loads(result)

# Static Frontend Server (Mount this LAST)
app.mount("/", StaticFiles(directory="static", html=True), name="static")
