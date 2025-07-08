# main.py

import os
import asyncio
import json
from dotenv import load_dotenv

# --- FastAPI and Pydantic Imports ---
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# --- MISSING IMPORTS - NOW ADDED ---
import requests
from bs4 import BeautifulSoup

# --- Google API Imports ---
import google.generativeai as genai
from googleapiclient.discovery import build

# --- Load Environment Variables ---
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
SEARCH_ENGINE_ID = os.getenv("SEARCH_ENGINE_ID")

# --- Startup Validation ---
if not all([GEMINI_API_KEY, GOOGLE_API_KEY, SEARCH_ENGINE_ID]):
    raise RuntimeError("CRITICAL ERROR: One or more API keys (GEMINI_API_KEY, GOOGLE_API_KEY, SEARCH_ENGINE_ID) are not set.")

# Configure the Gemini API client
genai.configure(api_key=GEMINI_API_KEY)


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


# ==============================================================================
# SECTION 2: Core Logic Functions
# ==============================================================================

def discover_sources(query: str, country_code: str) -> list[str]:
    """Uses Google's Programmable Search Engine to find potential retailer websites."""
    print(f"Discovering sources for '{query}' in country '{country_code}'...")
    try:
        service = build("customsearch", "v1", developerKey=GOOGLE_API_KEY)
        res = service.cse().list(
            q=f"buy {query}",
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
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        }
        # THIS LINE FAILED BECAUSE `requests` WAS NOT IMPORTED
        response = await asyncio.to_thread(requests.get, url, headers=headers, timeout=12)
        response.raise_for_status()

        # THIS LINE FAILED BECAUSE `BeautifulSoup` WAS NOT IMPORTED
        soup = BeautifulSoup(response.text, 'html.parser')
        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'svg', 'iframe']):
            tag.decompose()
        html_content = str(soup.body)[:50000]

        prompt = f"Analyze the HTML from a product webpage. The user is searching for: '{user_query}'. Identify the main product's name, its price, and currency. Check if the product is relevant to the user's query. HTML: ```html {html_content} ```"
        
        system_instruction = """You are an expert data extraction bot. Your response MUST be a single, clean JSON object. The JSON must have three keys: "productName" (string), "price" (number), and "currency" (string). The 'price' value MUST be a number (integer or float). The 'currency' value MUST be a standard 3-letter ISO 4217 currency code (e.g., "USD", "INR", "EUR"), not a symbol. If you cannot find all required information or if the product is not relevant, your entire response must be the single word: null. Do not include any other text or markdown."""
        
        async def generate_in_thread():
            model = genai.GenerativeModel('gemini-1.5-flash-latest', system_instruction=system_instruction)
            return model.generate_content(prompt, generation_config=genai.types.GenerationConfig(temperature=0.1))

        gemini_response = await generate_in_thread()
        cleaned_response_text = gemini_response.text.strip()
        
        if cleaned_response_text.lower() == "null":
            print(f"Gemini correctly identified no valid product on: {url}")
            return None

        if cleaned_response_text.startswith("```json"):
            cleaned_response_text = cleaned_response_text[7:-3].strip()

        data = json.loads(cleaned_response_text)
        
        if not all(k in data for k in ["productName", "price", "currency"]) or not isinstance(data["price"], (int, float)):
            print(f"Invalid data structure from Gemini for {url}: {data}")
            return None

        print(f"Successfully extracted from {url}: {data}")
        return ProductResult(link=url, **data)
    except Exception as e:
        print(f"Error processing {url}: {e}")
        return None

# ==============================================================================
# SECTION 3: FastAPI Application Setup
# ==============================================================================

app = FastAPI(
    title="Universal Price Fetcher API",
    description="Fetches product prices from various websites using Gemini 1.5 Flash.",
    version="2.1.0", # Version bump for the fix
)

# --- API Route Definition (Define this BEFORE mounting static files) ---
@app.post("/fetch-prices", response_model=list[ProductResult])
async def fetch_prices_endpoint(query: ProductQuery):
    """Main API endpoint to fetch and rank product prices."""
    urls = discover_sources(query.query, query.country)
    if not urls:
        raise HTTPException(status_code=404, detail="Could not find any potential sources for the given query.")
    
    tasks = [extract_product_data_with_gemini(url, query.query) for url in urls]
    results = await asyncio.gather(*tasks)
    successful_results = [res for res in results if res is not None]
    
    if not successful_results:
        raise HTTPException(status_code=404, detail="AI could not extract valid product information from any of the discovered sources. They may be blocked or not be standard e-commerce pages.")
        
    sorted_results = sorted(successful_results, key=lambda x: x.price)
    return sorted_results

# --- Static Frontend Server (Define this LAST) ---
app.mount("/", StaticFiles(directory="static", html=True), name="static")