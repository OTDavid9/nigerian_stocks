#!/usr/bin/env python3
"""
data_ingest.py
Router for data ingestion – full analysis pipeline and report retrieval.
POST /run  → triggers analysis for ALL 146 NGX stocks, writes structured reports to MongoDB.
GET /report/{symbol} → returns the latest predictive report document.
"""

import traceback
from datetime import datetime, timedelta
import numpy as np
from fastapi import APIRouter, HTTPException

# Import your MongoDB collection (adjust path as needed)
from core.database import stocks_reports

# Import your analysis modules (adjust import paths to your project)
from services.ngx_analysis import (
    fetch_stock_data,
    clean_prices,
    NGXStockAnalyzer,
    NGXStockPredictor,
)
from models.stocks import Symbol, SymbolList

router = APIRouter(prefix="/data-ingest", tags=["Data Ingest"])

# ---------------------------------------------------------------------
# ALL 146 NGX TICKERS WITH FULL COMPANY NAMES
# ---------------------------------------------------------------------
TICKER_TO_COMPANY = {
    "REGALINS": "Regency Alliance Insurance Plc",
    "JOHNHOLT": "John Holt Plc",
    "VFDGROUP": "VFD Group Plc",
    "PHARMDEKO": "Pharma-Deko Plc",
    "ZICHIS": "Zichis International Plc",
    "CONHALLPLC": "Conhall Plc",
    "NGXGROUP": "Nigerian Exchange Group Plc",
    "SEPLAT": "Seplat Energy Plc",
    "UPL": "University Press Plc",
    "MULTIVERSE": "Multiverse Mining & Exploration Plc",
    "LASACO": "Lasaco Assurance Plc",
    "SOVRENINS": "Sovereign Trust Insurance Plc",
    "UNITYBNK": "Unity Bank Plc",
    "BAPLC": "B.A. Plc (formerly B.A.T. Nigeria)",
    "FIDSON": "Fidson Healthcare Plc",
    "LINKASSURE": "Linkage Assurance Plc",
    "CHAMS": "Chams Plc",
    "NSLTECH": "NSL Technology Plc",
    "CILEASING": "C&I Leasing Plc",
    "IMG": "Industrial & Medical Gases Nigeria Plc",
    "UNILEVER": "Unilever Nigeria Plc",
    "PZ": "PZ Cussons Nigeria Plc",
    "ALEX": "Aluminium Extrusion Industries Plc",
    "OANDO": "Oando Plc",
    "WAPCO": "Lafarge Africa Plc (WAPCO)",
    "WAPIC": "Wapic Insurance Plc",
    "CWG": "CWG Plc",
    "CHELLARAM": "Chellarams Plc",
    "IKEJAHOTEL": "Ikeja Hotel Plc",
    "BUAFOODS": "BUA Foods Plc",
    "INFINITY": "Infinity Trust Mortgage Bank Plc",
    "LIVESTOCK": "Livestock Feeds Plc",
    "CORNERST": "Cornerstone Insurance Plc",
    "EKOCORP": "Ekocorp Plc",
    "TOTAL": "TotalEnergies Marketing Nigeria Plc",
    "TRANSEXPR": "Trans-Nationwide Express Plc",
    "MCNICHOLS": "McNichols Consolidated Plc",
    "ABBEYBDS": "Abbey Mortgage Bank Plc",
    "FIRSTHOLDCO": "First Holdco Plc",
    "ELLAHLAKES": "Ellah Lakes Plc",
    "AFROMEDIA": "Afromedia Plc",
    "HONYFLOUR": "Honeywell Flour Mills Plc",
    "NIDF": "Nigerian Infrastructure Development Fund",
    "ETERNA": "Eterna Plc",
    "PRESTIGE": "Prestige Assurance Plc",
    "CONOIL": "Conoil Plc",
    "RONCHESS": "Ronchess Global Resources Plc",
    "CAP": "Chemical and Allied Products Plc",
    "FTNCOCOA": "FTN Cocoa Processors Plc",
    "MTNN": "MTN Nigeria Communications Plc",
    "MANSARD": "AXA Mansard Insurance Plc",
    "UBA": "United Bank for Africa Plc",
    "SUNUASSUR": "Sunu Assurances Nigeria Plc",
    "MORISON": "Morison Industries Plc",
    "OKOMUOIL": "Okomu Oil Palm Company Plc",
    "MECURE": "Mecure Industries Plc",
    "TIP": "The Initiate Plc (formerly TIP)",
    "GEREGU": "Geregu Power Plc",
    "CUTIX": "Cutix Plc",
    "CHAMPION": "Champion Breweries Plc",
    "AFRIPRUD": "Africa Prudential Plc",
    "FIDELITYBK": "Fidelity Bank Plc",
    "LEARNAFRCA": "Learn Africa Plc",
    "NPFMCRFBK": "NPF Microfinance Bank Plc",
    "LEGENDINT": "Legend International Plc",
    "NB": "Nigerian Breweries Plc",
    "ETRANZACT": "eTranzact International Plc",
    "ETI": "Ecobank Transnational Incorporated",
    "CADBURY": "Cadbury Nigeria Plc",
    "UCAP": "United Capital Plc",
    "AUSTINLAZ": "Austin Laz & Company Plc",
    "MAYBAKER": "May & Baker Nigeria Plc",
    "NNFM": "Northern Nigeria Flour Mills Plc",
    "PREMPAINTS": "Premier Paints Plc",
    "ROYALEX": "Royal Exchange Plc",
    "JULI": "Juli Plc",
    "CAVERTON": "Caverton Offshore Support Group Plc",
    "INTBREW": "International Breweries Plc",
    "REDSTAREX": "Red Star Express Plc",
    "SCOA": "SCOA Nigeria Plc",
    "NESTLE": "Nestlé Nigeria Plc",
    "GUINNESS": "Guinness Nigeria Plc",
    "JAPAULGOLD": "Japaul Gold & Ventures Plc",
    "STACO": "STACO Insurance Plc",
    "OMATEK": "Omaték Plc",
    "NAHCO": "Nigerian Aviation Handling Company Plc",
    "GUINEAINS": "Guinea Insurance Plc",
    "FCMB": "FCMB Group Plc",
    "STERLINGNG": "Sterling Financial Holdings Company Plc",
    "MULTITREX": "Multitrex Integrated Foods Plc",
    "GTCO": "Guaranty Trust Holding Company Plc",
    "TANTALIZER": "Tantalizers Plc",
    "AVAIF": "AV Asset Management Plc",
    "TRANSPOWER": "Transcorp Power Plc",
    "STANBIC": "Stanbic IBTC Holdings Plc",
    "AFRINSURE": "African Alliance Insurance Plc",
    "ZENITHBANK": "Zenith Bank Plc",
    "NREIT": "Nigerian Real Estate Investment Trust",
    "AIRTELAFRI": "Airtel Africa Plc",
    "JAIZBANK": "Jaiz Bank Plc",
    "CNIF": "C & I Leasing Mortgage Fund",
    "CUSTODIAN": "Custodian Investment Plc",
    "BERGER": "Berger Paints Nigeria Plc",
    "NEIMETH": "Neimeth International Pharmaceuticals Plc",
    "UNIONDICON": "Union Dicon Salt Plc",
    "ABCTRANS": "ABC Transport Plc",
    "BETAGLAS": "Beta Glass Plc",
    "TRANSCOHOT": "Transcorp Hotels Plc",
    "NEM": "NEM Insurance Plc",
    "LIVINGTRUST": "LivingTrust Mortgage Bank Plc",
    "NASCON": "Nascon Allied Industries Plc",
    "INTENEGINS": "Intenegy Insurance Company Plc",
    "ENAMELWA": "Enamelware Plc",
    "TRIPPLEG": "Tripple Gee & Company Plc",
    "ACCESSCORP": "Access Holdings Plc",
    "EUNISELL": "Eunisell Interlinked Plc",
    "RTBRISCOE": "RT Briscoe Plc",
    "PRESCO": "Presco Plc",
    "GOLDBREW": "GoldBrew Industries Plc",
    "ACADEMY": "Academy Press Plc",
    "UNIVINSURE": "Universal Insurance Plc",
    "MBENEFIT": "Mutual Benefits Assurance Plc",
    "HMCALL": "HMCall Plc",
    "MEYER": "Meyer Plc",
    "FTGINSURE": "FTG Insurance Brokers Plc",
    "DANGCEM": "Dangote Cement Plc",
    "AIICO": "AIICO Insurance Plc",
    "ARADEL": "Aradel Holdings Plc",
    "UACN": "UAC of Nigeria Plc",
    "UHOMREIT": "UPDC Real Estate Investment Trust (UPDC REIT)",
    "DAARCOMM": "Daar Communications Plc",
    "NCR": "NCR (Nigeria) Plc",
    "TRANSCORP": "Transnational Corporation Plc",
    "SKYAVN": "Skyway Aviation Handling Company Plc",
    "DANGSUGAR": "Dangote Sugar Refinery Plc",
    "UPDCREIT": "UPDC Real Estate Investment Trust",
    "UPDC": "UPDC Plc",
    "DEAPCAP": "Deap Capital Management & Trust Plc",
    "JBERGER": "Julius Berger Nigeria Plc",
    "WEMABANK": "Wema Bank Plc",
    "MOFIREIF": "Mofire Emerging Market Fund",
    "VERITASKAP": "Veritas Kapital Assurance Plc",
    "VITAFOAM": "Vitafoam Nigeria Plc",
    "BUACEMENT": "BUA Cement Plc",
    "THOMASWY": "Thomas Wyatt Nigeria Plc",
    "SFSREIT": "SFS Real Estate Investment Trust",
    "CMFC": "CMFC Plc",
    "HBMNG": "Honeywell Building Materials Nigeria Plc",
    "ABBEYBANK": "Abbey Mortgage Bank Plc"
}


# ---------------------------------------------------------------------
# Helper: convert numpy types to native Python for BSON compatibility
# ---------------------------------------------------------------------
def make_json_safe(obj):
    """
    Recursively convert numpy arrays and scalars to native Python lists/types.
    """
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: make_json_safe(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [make_json_safe(i) for i in obj]
    else:
        return obj


# ---------------------------------------------------------------------
# Core analysis function
# ---------------------------------------------------------------------
def run_analysis_for_stock(symbol: str, company_name: str) -> dict:
    """
    Run the full technical + predictive pipeline for a single stock.
    Returns a BSON-safe dictionary ready for MongoDB storage.
    """
    print(f"Processing {symbol} ({company_name}) ...")
    # 1. Fetch and clean price data
    raw = fetch_stock_data(symbol)
    dates, closes = clean_prices(raw)
    if len(closes) < 60:
        raise ValueError(f"Not enough data ({len(closes)} days)")

    # 2. Technical analysis
    ta = NGXStockAnalyzer(raw)
    tech_report = ta.generate_report()

    tech_indicators = {
        "sma_50": ta.moving_average_analysis().get("sma_50"),
        "sma_200": ta.moving_average_analysis().get("sma_200"),
        "rsi": ta.rsi(14),
        "macd_signal": ta.macd().get("macd_signal"),
        "max_drawdown": ta.max_drawdown(),
    }

    # 3. Predictive models
    predictor = NGXStockPredictor(dates, closes, forecast_days=5)
    predictor.evaluate_with_walk_forward(n_splits=5)
    predictor.train_final_models()
    predictor.forecast_future()
    pred_report = predictor.generate_prediction_report()

    full_report = f"Investment Analysis for {symbol} ({company_name}) (NGX)\n{'='*60}\n\n"
    full_report += tech_report + "\n" + pred_report

    last_date = dates[-1]
    forecast_dates = [
        (last_date + timedelta(days=i + 1)).strftime("%Y-%m-%d")
        for i in range(5)
    ]
    forecast_prices = [float(p) for p in predictor.future_prices]

    # 4. Build document – sanitise model result dicts before storing
    doc = {
        "symbol": symbol.upper(),
        "company_name": company_name,
        "report_text": full_report,
        "created_at": datetime.utcnow(),
        "best_reg_model": predictor.best_reg_name,
        "mape": float(predictor.reg_results[predictor.best_reg_name]["MAPE"]),
        "best_cls_model": predictor.best_cls_name,
        "accuracy": float(predictor.cls_results[predictor.best_cls_name]["Acc"]),
        "forecast_trend": "upward" if np.mean(predictor.future_prices) > closes[-1] else "downward",
        "forecast_prices": forecast_prices,
        "forecast_dates": forecast_dates,
        "technical_indicators": tech_indicators,
        # Clean model comparison tables – convert any numpy arrays inside
        "regression_results": make_json_safe(predictor.reg_results),
        "classification_results": make_json_safe(predictor.cls_results),
    }

    return doc


# ---------------------------------------------------------------------
# ENDPOINTS
# ---------------------------------------------------------------------
@router.post("/run-single-analysis")
async def run_single_full_analysis(symbol: Symbol):
    """
    Trigger the full analysis for a single NGX stock.
    Writes the structured report to MongoDB.
    """
    symbol_str = symbol.symbol.upper()  # Normalize
    company_name = TICKER_TO_COMPANY.get(symbol_str)
    if not company_name:
        raise HTTPException(status_code=404, detail=f"Symbol '{symbol_str}' not found in company mapping")

    try:
        doc = run_analysis_for_stock(symbol_str, company_name)
        # Ensure document is BSON‑safe
        stocks_reports.replace_one(
            {"symbol": symbol_str},
            doc,
            upsert=True
        )
        return {
            "message": "Analysis completed",
            "symbol": symbol_str,
            "company_name": company_name,
            "mape": round(doc["mape"], 2),
            "accuracy": round(doc["accuracy"], 4),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")



@router.post("/run-bulk-analysis")
async def run_bulk_full_analysis(payload: SymbolList):
    """
    Trigger the full analysis for multiple NGX stocks.
    Writes the structured reports to MongoDB.
    """
    processed = []
    errors = []

    for symbol in payload.symbols:
        symbol = symbol.upper().strip()
        company_name = TICKER_TO_COMPANY.get(symbol)
        if not company_name:
            errors.append({"symbol": symbol, "error": "Symbol not found in company mapping"})
            continue

        try:
            doc = run_analysis_for_stock(symbol, company_name)
            stocks_reports.replace_one(
                {"symbol": symbol},
                doc,
                upsert=True
            )
            processed.append({
                "symbol": symbol,
                "company_name": company_name,
                "mape": round(doc["mape"], 2),
                "accuracy": round(doc["accuracy"], 4),
            })
            print(f"  ✓ {symbol} done. MAPE={doc['mape']:.2f}%, Acc={doc['accuracy']:.2%}")
        except Exception as e:
            traceback.print_exc()
            errors.append({"symbol": symbol, "error": str(e)})

    return {
        "message": "Bulk analysis completed",
        "processed_count": len(processed),
        "error_count": len(errors),
        "processed": processed,
        "errors": errors,
        "timestamp": datetime.utcnow().isoformat()
    }

# @router.post("/run")
# async def run_all_full_analysis():
#     """
#     Trigger the full analysis for all 146 NGX stocks.
#     Writes the structured reports to MongoDB.
#     No request body required.
#     """
#     processed = []
#     errors = []

#     for symbol, company_name in TICKER_TO_COMPANY.items():
#         try:
#             doc = run_analysis_for_stock(symbol, company_name)
#             # The document is already BSON-safe, but ensure all keys are strings
#             stocks_reports.replace_one(
#                 {"symbol": symbol.upper()},
#                 doc,
#                 upsert=True
#             )
#             processed.append({
#                 "symbol": symbol,
#                 "company_name": company_name,
#                 "mape": round(doc["mape"], 2),
#                 "accuracy": round(doc["accuracy"], 4),
#             })
#             print(f"  ✓ {symbol} done. MAPE={doc['mape']:.2f}%, Acc={doc['accuracy']:.2%}")
#         except Exception as e:
#             print(f"  ✗ {symbol} FAILED: {e}")
#             traceback.print_exc()
#             errors.append({"symbol": symbol, "error": str(e)})

#     return {
#         "message": "Full analysis completed",
#         "processed_count": len(processed),
#         "error_count": len(errors),
#         "errors": errors,
#         "timestamp": datetime.utcnow().isoformat()
#     }


# @router.get("/report/{symbol}")
# async def get_latest_report(symbol: str):
#     """
#     Retrieve the latest predictive report for a given NGX symbol.
#     Returns the full structured document (text, metrics, forecast, etc.).
#     """
#     symbol = symbol.upper()
#     doc = stocks_reports.find_one(
#         {"symbol": symbol},
#         sort=[("created_at", -1)]
#     )
#     if not doc:
#         raise HTTPException(
#             status_code=404,
#             detail=f"No report found for symbol '{symbol}'. Run the analysis first."
#         )
#     doc["_id"] = str(doc["_id"])
#     return doc