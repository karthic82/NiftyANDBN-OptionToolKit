# Libraries
import streamlit as st
import pandas as pd
import requests
import math
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# Page wide mode
st.set_page_config(page_title="Options Toolkit", layout="wide")
st.header('NIFTY and BANKNIFTY Options Toolkit', divider='rainbow')

# Method to get nearest strikes
def round_nearest(x, num=50): return int(math.ceil(float(x)/num)*num)
def nearest_strike_bnf(x): return round_nearest(x, 100)
def nearest_strike_nf(x): return round_nearest(x, 50)

# Browser Headers to mimic a real user and bypass blocks
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json,text/plain,*/*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.nseindia.com/option-chain',
    'Connection': 'keep-alive'
}

# Fetch Data with Streamlit Caching
@st.cache_data(ttl=60)
def fetch_nse_data(symbol="NIFTY"):
    session = requests.Session()
    try:
        session.get("https://www.nseindia.com", headers=headers, timeout=8)
        session.get("https://www.nseindia.com/option-chain", headers=headers, timeout=8)
        
        c_res = session.get(f"https://www.nseindia.com/api/option-chain-contract-info?symbol={symbol}", headers=headers, timeout=8)
        c_res.raise_for_status()
        expiries = c_res.json().get("expiryDates", [])
        
        if not expiries: 
            return None
            
        chain_res = session.get(f"https://www.nseindia.com/api/option-chain-v3?type=Indices&symbol={symbol}&expiry={expiries[0]}", headers=headers, timeout=8)
        chain_res.raise_for_status()
        return chain_res.json()
    except Exception as e:
        print(f"Fetch Error ({symbol}): {e}")
        return None

# Extract underlying spot price
def get_spot_price(data):
    if not data: return 0.0
    spot = float(data.get('records', {}).get('underlyingValue', 0.0))
    if spot == 0.0:
        for row in data.get('records', {}).get('data', []):
            for leg in ("CE", "PE"):
                if row.get(leg, {}).get("underlyingValue", 0):
                    return float(row.get(leg).get("underlyingValue"))
    return spot

# 1. FIXED: Explicit target targeting instead of sequential counting
def get_io(num, step, nearest, data):
    try:
        if not data: return []
        currExpiryDate = data["records"]["expiryDates"][0]
        
        # We explicitly define the 3 strikes we want for the UI (ITM, ATM, OTM)
        target_strikes = [nearest - step, nearest, nearest + step]
        data_list = []
        
        for item in data['records']['data']:
            if item.get("expiryDate") == currExpiryDate and item["strikePrice"] in target_strikes:
                data_list.append({
                    'expiry': str(currExpiryDate),
                    'strike': item["strikePrice"],
                    'ce_ltp': item.get("CE", {}).get("lastPrice", 0),
                    'ce_change': round(item.get("CE", {}).get("change", 0), 2),
                    'pe_ltp': item.get("PE", {}).get("lastPrice", 0),
                    'pe_change': round(item.get("PE", {}).get("change", 0), 2)
                })
        
        # Sort ascending by strike so index 0, 1, 2 map correctly to the UI columns
        return sorted(data_list, key=lambda x: x['strike'])
    except Exception as e:
        print(f"Error in get_io: {e}")
        return []

# 2. FIXED: Range-based filtering for the chart
def oi_plot(num, step, nearest, data):
    try:
        if not data: return pd.DataFrame()
        currExpiryDate = data["records"]["expiryDates"][0]
        
        # Define the boundary of the chart
        min_strike = nearest - (step * num)
        max_strike = nearest + (step * num)
        
        ce_oi_list, pe_oi_list, oi_strike_list = [], [], []
        
        for item in data['records']['data']:
            if item.get("expiryDate") == currExpiryDate:
                if min_strike <= item["strikePrice"] <= max_strike:
                    pe_oi_list.append(item.get("PE", {}).get("openInterest", 0))
                    ce_oi_list.append(item.get("CE", {}).get("openInterest", 0))
                    oi_strike_list.append(item["strikePrice"])

        df = pd.DataFrame({
            "CE_OI": ce_oi_list,
            "PE_OI": pe_oi_list,
            "Strike": oi_strike_list,
        })
        
        if not df.empty:
            df = df.sort_values('Strike').reset_index(drop=True)
        return df
    except Exception as e:
        print(f"Error in oi_plot: {e}")
        return pd.DataFrame()

# 3. FIXED: Range-based filtering for Support/Resistance levels
def highest_oi(num, step, nearest, data, option_type="CE"):
    try:
        if not data: return nearest
        currExpiryDate = data["records"]["expiryDates"][0]
        
        min_strike = nearest - (step * num)
        max_strike = nearest + (step * num)
        max_oi, max_oi_strike = 0, nearest
        
        for item in data['records']['data']:
            if item.get("expiryDate") == currExpiryDate:
                if min_strike <= item["strikePrice"] <= max_strike:
                    current_oi = item.get(option_type, {}).get("openInterest", 0)
                    if current_oi > max_oi:
                        max_oi = current_oi
                        max_oi_strike = item["strikePrice"]
        return max_oi_strike
    except Exception as e:
        print(f"Error in highest_oi_{option_type}: {e}")
        return nearest

if __name__ == "__main__":
    
    count = st_autorefresh(interval=30000, limit=10000, key="mycounter")
    
    nifty_data = fetch_nse_data("NIFTY")
    bank_nifty_data = fetch_nse_data("BANKNIFTY")

    if not nifty_data or not bank_nifty_data:
        st.warning("⚠️ NSE Data is currently unavailable or rate-limited. Retrying on next refresh...")
        st.stop()

    # Process NIFTY
    nf_ul = get_spot_price(nifty_data)
    nf_nearest = nearest_strike_nf(nf_ul)
    nifty_oi_data = get_io(2, 50, nf_nearest, nifty_data)
    nf_highestoi_CE = highest_oi(15, 50, nf_nearest, nifty_data, "CE") 
    nf_highestoi_PE = highest_oi(15, 50, nf_nearest, nifty_data, "PE")
    # Increased 'num' from 5 to 20 here so your bar chart shows a wider range of strikes
    nifty_chart_data = oi_plot(20, 50, nf_nearest, nifty_data) 

    # Process BANKNIFTY
    bnf_ul = get_spot_price(bank_nifty_data)
    bnf_nearest = nearest_strike_bnf(bnf_ul)
    bank_nifty_oi_data = get_io(2, 100, bnf_nearest, bank_nifty_data)
    bnf_highestoi_CE = highest_oi(20, 100, bnf_nearest, bank_nifty_data, "CE")
    bnf_highestoi_PE = highest_oi(20, 100, bnf_nearest, bank_nifty_data, "PE")
    # Increased 'num' from 10 to 20 for a wider chart view
    bank_nifty_chart_data = oi_plot(20, 100, bnf_nearest, bank_nifty_data)

    # --- NIFTY UI RENDERING ---
    st.metric("NIFTY 50 Index", f"{nf_ul:,.2f}")
    
    if len(nifty_oi_data) >= 3:
        st.write(f"NIFTY Exp-{nifty_oi_data[0]['expiry']} :blue[LTP {str(nf_ul)}], :gray[CE[ ATM:{str(nf_nearest)},ITM:{str(nf_nearest-50)},OTM:{str(nf_nearest+50)}]], :gray[PE[ ATM:{str(nf_nearest)}, ITM:{str(nf_nearest+50)}, OTM:{str(nf_nearest-50)}]], :green[OI_SUP {str(nf_highestoi_PE)}] :red[OI_RES {str(nf_highestoi_CE)}]")
        
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        with st.container():
            col1.metric(label="NIFTY "+str(nifty_oi_data[0]['strike'])+" CE", value=str(nifty_oi_data[0]['ce_ltp']), delta=str(nifty_oi_data[0]['ce_change']))
            col2.metric(label="NIFTY "+str(nifty_oi_data[0]['strike'])+" PE", value=str(nifty_oi_data[0]['pe_ltp']), delta=str(nifty_oi_data[0]['pe_change']))
            col3.metric(label="NIFTY "+str(nifty_oi_data[1]['strike'])+" CE", value=str(nifty_oi_data[1]['ce_ltp']), delta=str(nifty_oi_data[1]['ce_change']))
            col4.metric(label="NIFTY "+str(nifty_oi_data[1]['strike'])+" PE", value=str(nifty_oi_data[1]['pe_ltp']), delta=str(nifty_oi_data[1]['pe_change']))
            col5.metric(label="NIFTY "+str(nifty_oi_data[2]['strike'])+" CE", value=str(nifty_oi_data[2]['ce_ltp']), delta=str(nifty_oi_data[2]['ce_change']))
            col6.metric(label="NIFTY "+str(nifty_oi_data[2]['strike'])+" PE", value=str(nifty_oi_data[2]['pe_ltp']), delta=str(nifty_oi_data[2]['pe_change']))
            st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            st.divider()

    with st.expander("Click to see Nifty OI"):
        if not nifty_chart_data.empty:
            st.bar_chart(nifty_chart_data, x="Strike", y=["CE_OI", "PE_OI"], color=["#0000FF", "#FF0000"])

    # --- BANKNIFTY UI RENDERING ---
    st.metric("NIFTY BANK Index", f"{bnf_ul:,.2f}")
    
    if len(bank_nifty_oi_data) >= 3:
        st.write(f"BANKNIFTY Exp-{bank_nifty_oi_data[0]['expiry']} :blue[LTP {str(bnf_ul)}] , :gray[ CE[ATM: {str(bnf_nearest)},ITM:{str(bnf_nearest-100)},OTM:{str(bnf_nearest+100)}]], :gray[PE[ ATM:{str(bnf_nearest)}, ITM:{str(bnf_nearest+100)}, OTM:{str(bnf_nearest-100)}]], :green[OI_SUP {str(bnf_highestoi_PE)}],  :red[OI_RES {str(bnf_highestoi_CE)}]")
        
        bnf_col1, bnf_col2, bnf_col3, bnf_col4, bnf_col5, bnf_col6 = st.columns(6)
        with st.container():
            bnf_col1.metric(label="BANKNIFTY "+str(bank_nifty_oi_data[0]['strike'])+" CE", value=str(bank_nifty_oi_data[0]['ce_ltp']), delta=str(bank_nifty_oi_data[0]['ce_change']))
            bnf_col2.metric(label="BANKNIFTY "+str(bank_nifty_oi_data[0]['strike'])+" PE", value=str(bank_nifty_oi_data[0]['pe_ltp']), delta=str(bank_nifty_oi_data[0]['pe_change']))
            bnf_col3.metric(label="BANKNIFTY "+str(bank_nifty_oi_data[1]['strike'])+" CE", value=str(bank_nifty_oi_data[1]['ce_ltp']), delta=str(bank_nifty_oi_data[1]['ce_change']))
            bnf_col4.metric(label="BANKNIFTY "+str(bank_nifty_oi_data[1]['strike'])+" PE", value=str(bank_nifty_oi_data[1]['pe_ltp']), delta=str(bank_nifty_oi_data[1]['pe_change']))
            bnf_col5.metric(label="BANKNIFTY "+str(bank_nifty_oi_data[2]['strike'])+" CE", value=str(bank_nifty_oi_data[2]['ce_ltp']), delta=str(bank_nifty_oi_data[2]['ce_change']))
            bnf_col6.metric(label="BANKNIFTY "+str(bank_nifty_oi_data[2]['strike'])+" PE", value=str(bank_nifty_oi_data[2]['pe_ltp']), delta=str(bank_nifty_oi_data[2]['pe_change']))
            st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            st.divider()

    with st.expander("Click to see BankNifty OI"):
        if not bank_nifty_chart_data.empty:
            st.bar_chart(bank_nifty_chart_data, x="Strike", y=["CE_OI", "PE_OI"], color=["#0000FF", "#FF0000"])