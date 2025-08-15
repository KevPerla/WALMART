import os
import json
import gspread
import pandas as pd
from flask import Flask, request, jsonify
from oauth2client.service_account import ServiceAccountCredentials
from apify_client import ApifyClient

app = Flask(__name__)

@app.route("/health", methods=["GET"])
def health_check():
    return {"status": "ok"}, 200

def get_google_client():
    """
    Autenticación con Google Sheets usando la variable de entorno
    GOOGLE_SHEETS_CRED, evitando exponer el JSON en GitHub.
    """
    cred_json = os.environ.get("GOOGLE_SHEETS_CRED")
    if not cred_json:
        raise ValueError("No se encontró la variable de entorno GOOGLE_SHEETS_CRED")
    
    # Crear archivo temporal
    with open("temp_credentials.json", "w") as f:
        f.write(cred_json)
    
    scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("temp_credentials.json", scope)
    client = gspread.authorize(creds)
    return client

def scrap_walmart(urls):
    """
    Hace scraping de las URLs usando Apify.
    """
    apify_token = os.environ.get("APIFY_TOKEN")
    if not apify_token:
        raise ValueError("No se encontró la variable de entorno APIFY_TOKEN")
    
    client = ApifyClient(apify_token)
    results = []

    for url in urls:
        try:
            run = client.actor("apify/walmart-scraper").call(run_input={"startUrls":[{"url":url}]})
            items = run.get("defaultDataset", {}).get("items", [])
            for product in items:
                results.append({
                    "title": product.get("title"),
                    "price": product.get("price"),
                    "url": url
                })
        except Exception as e:
            print(f"Error scraping {url}: {e}")
    
    return results

@app.route("/walmart/load", methods=["POST"])
def load_sheet():
    sheet_id = request.args.get("sheet_id")
    if not sheet_id:
        return jsonify({"error": "No sheet_id provided"}), 400
    
    try:
        client = get_google_client()
        sheet = client.open_by_key(sheet_id).sheet1
        
        # Leer URLs desde la columna A (omitimos cabecera)
        urls = sheet.col_values(1)[1:]
        if not urls:
            return jsonify({"error": "No URLs found in the sheet"}), 400
        
        # Hacer scraping
        data = scrap_walmart(urls)
        if not data:
            return jsonify({"error": "No data scraped"}), 500
        
        # Limpiar sheet y cargar datos nuevos
        sheet.clear()
        df = pd.DataFrame(data)
        sheet.update([df.columns.values.tolist()] + df.values.tolist())
        
        return jsonify({"status": "success", "rows_loaded": len(data)})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
