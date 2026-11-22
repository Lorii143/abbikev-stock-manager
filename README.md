# Abbikev Stock Manager

A Streamlit app for Abbikev Beauty Parlour, Ukunda, Kwale. It turns two handwritten records (a purchase list and a sales list) into a stock dashboard, a restock planner and a simple AI assistant.

Built as the decision aid for the DSA 8402 Data Science Consultancy Capstone, Strathmore University.

## What it does
- **Dashboard**: restock spend by item and category, sales mix, items at or below reorder level.
- **Stock counts**: type in what is on the shelf and a reorder level for each item.
- **Restock plan**: allocates a budget to items that need buying, with a safety buffer and a demand setting (80%, 100%, 120%) so the owner can see how the need changes. Compared with the last restock.
- **Sales / Purchases**: the two records as transcribed, with unit costs and a check on lines whose total does not equal quantity × price. A form logs new dated sales.
- **Assistant**: answers questions about the data. Works offline with simple answers; adds full AI answers when an Anthropic API key is set.
- **Data quality**: scope, findings, mismatches and data layers.

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Put it on GitHub
1. Create a new repository on GitHub. **Make it private**: the data is client data (supplier prices, sales).
2. Upload every file in this folder (keep the folder structure), or use git:
   ```bash
   git init && git add . && git commit -m "Abbikev stock manager"
   git branch -M main
   git remote add origin https://github.com/<you>/abbikev-stock-manager.git
   git push -u origin main
   ```

## Deploy on Streamlit Community Cloud
1. Go to https://share.streamlit.io and sign in with GitHub.
2. Choose **Create app**, pick the repository, branch `main`, and main file `app.py`.
3. (Optional, for AI answers) Open **Advanced settings > Secrets** and paste:
   ```toml
   ANTHROPIC_API_KEY = "your-key-here"
   ```
4. Deploy. Private repositories work; set the app’s sharing to specific viewers.

## Things to know
- **Saved counts and sales are not permanent on Streamlit Cloud.** The app writes to `data/*.csv`, but the cloud disk resets when the app restarts. Use the download buttons to keep copies, and commit the CSVs back to the repository. A shared database (for example Google Sheets or Supabase) is the next step if the owner needs this to persist.
- **Neither record has dates.** The app does not forecast demand. Logging dated sales is how a forecast becomes possible.
- **Record A is read as purchases and Record B as sales.** The owner should confirm. Categories and the service/product split are first groupings to confirm.
- **Confidentiality.** Use a pseudonym instead of the business name if the owner has not agreed to it being named. Never commit `.streamlit/secrets.toml`.
- **AI use.** Record any AI assistance in your AI use log: tool, purpose, information shared, and how you verified the output.

## Files
```
app.py                     the app
requirements.txt           Python packages
.streamlit/config.toml     purple, white and black theme
assets/logo.png            logo
data/purchases.csv         Record A as transcribed (original values)
data/sales.csv             Record B as transcribed (original values)
data/stock_counts.csv      counts entered in the app
data/sales_log.csv         new dated sales entered in the app
```
