# Universal Price Fetcher

This is a full-stack application that can fetch the price of a given product from multiple websites based on the country, using Google's Gemini 1.5 Flash AI model for data extraction.

![image](https://github.com/user-attachments/assets/b64f1f4c-4eb8-407d-8e8f-4d0166724991)

### Hosted URL

**You can test the live application here: https://product-web-search.vercel.app/**

---

### Tech Stack & Architecture

This project uses a modern, asynchronous architecture to handle long-running web scraping tasks without timing out.

*   **Backend**: FastAPI (Python)
*   **AI Model**: Google Gemini 1.5 Flash for intelligent data extraction from raw HTML.
*   **Task Queue & State Management**: Redis is used to manage the status of search tasks. This is handled by **Vercel KV** in production and a **Docker** container for local development.
*   **Source Discovery**: Google Programmable Search Engine API to find relevant e-commerce websites dynamically.
*   **Frontend**: Vanilla HTML/JS with Pico.css for clean, lightweight styling.

The workflow is as follows:
1.  The user initiates a search, which calls the `/start-search` endpoint.
2.  The server immediately creates a background job, assigns it a unique `task_id`, and returns this ID to the user with a `202 Accepted` response.
3.  The frontend polls the `/search-status/{task_id}` endpoint every few seconds.
4.  Meanwhile, the background job scrapes websites, runs AI extraction, and stores the final result in Redis against the `task_id`.
5.  Once the job is complete, the polling endpoint retrieves the result from Redis and sends it back to the frontend to be displayed.

---

### How to Run Locally

1.  **Clone the repository and move into the directory:**
    ```bash
    git clone https://github.com/devcool20/product-web-search.git
    cd product-web-search
    ```

2.  **Start a local Redis database using Docker:**
    This application requires a running Redis instance for task management. The easiest way to get one is with Docker.
    ```bash
    docker run --name local-redis -p 6379:6379 -d redis
    ```

3.  **Install Python dependencies:**
    It is highly recommended to use a virtual environment.
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    pip install -r requirements.txt
    ```

4.  **Set up environment variables:**
    Create a `.env` file in the project root. You can copy the structure from `.env.example`. Add your API keys and ensure the `KV_URL` points to your local Docker instance.
    ```env
    # .env file content
    GEMINI_API_KEY="AIzaSy..."
    GOOGLE_API_KEY="AIzaSy..."
    SEARCH_ENGINE_ID="..."
    KV_URL="redis://localhost:6379"
    ```

5.  **Run the application:**
    ```bash
    uvicorn main:app --reload
    ```

6.  **Test in your browser:**
    Open your web browser and navigate to `http://127.0.0.1:8000`. You will see the interactive frontend.

---

### Working `curl` Request Example

Due to the asynchronous architecture, interacting with the API directly requires a two-step process.

#### Step 1: Start the Search

First, send a `POST` request to `/start-search` with your query. This will immediately return a `task_id`.

```bash
curl -X 'POST' \
  'https://product-web-search.vercel.app/start-search' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "country": "IN",
    "query": "boAt Airdopes 311 Pro"
  }'
```

**Sample Response:**
```json
{
  "task_id": "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
}
```

#### Step 2: Poll for Results

Next, use the `task_id` from Step 1 to poll the `/search-status/{task_id}` endpoint until the `status` is "completed" or "failed".

```bash
# Replace {task_id} with the ID you received
TASK_ID="a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"

curl -X 'GET' \
  "https://product-web-search.vercel.app/search-status/$TASK_ID" \
  -H 'accept: application/json'
```

**Pending Response:**
```json
{
  "status": "pending",
  "data": null
}
```

**Completed Response:**
```json
{
  "status": "completed",
  "data": [
    {
      "link": "https://www.boat-lifestyle.com/...",
      "price": 1299.0,
      "currency": "INR",
      "productName": "boAt Airdopes 311 Pro"
    },
    {
      "link": "https://www.amazon.in/...",
      "price": 1349.0,
      "currency": "INR",
      "productName": "boAt Airdopes 311 Pro TWS Earbuds"
    }
  ]
}
```
