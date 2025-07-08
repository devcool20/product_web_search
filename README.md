# Universal Price Fetcher

This is a full-stack application that can fetch the price of a given product from multiple websites based on the country, using Google's Gemini 1.5 Flash AI model for data extraction.

### Hosted URL

**You can test the live application here: [Your Vercel URL]**

---

### How to Run Locally

1.  **Clone the repository and install dependencies:**
    ```bash
    git clone <your-repo-url>
    cd <your-repo-name>
    pip install -r requirements.txt
    ```

2.  **Set up environment variables:**
    Create a `.env` file using `.env.example` as a template and add your API keys.

3.  **Run the application:**
    ```bash
    uvicorn main:app --reload
    ```

4.  **Test in your browser:**
    Open your web browser and navigate to `http://127.0.0.1:8000`. You will see the interactive frontend.

---

### Working `curl` Request Example

The API can also be tested directly via `curl`:

```bash
curl -X 'POST' \
  'http://127.0.0.1:8000/fetch-prices' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "country": "IN",
    "query": "boAt Airdopes 311 Pro"
  }'