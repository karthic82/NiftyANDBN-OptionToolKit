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

# FIXED: Standard mathematical rounding to find the true nearest ATM strike
def round_nearest(x, num=50): return int(round(float(x)/num)*num)
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

# Fetch Data: Reverted to the reliable 'option-chain-indices' endpoint
@st.cache_data(ttl=60)
def fetch_nse_data(symbol="NIFTY"):
    session = requests.Session()
    try:
        # Establish session cookies
        session.get("https://www.nseindia.com", headers=headers, timeout=8)
        
        url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
        chain_res = session.get(url, headers=headers, timeout=8)
        
        # Retry once if NSE throws an unauthorized session error
        if chain_res.status_code == 401:
            session.get("https://www.nseindia.com", headers=headers, timeout=8)
            chain_res = session.get(url, headers=headers, timeout=8)
            
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

def get_io(step, nearest, data):
    try:
        if not data: return []
        currExpiryDate = data["records"]["expiryDates"][0]
        
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
        
        return sorted(data_list, key=lambda x: x['strike'])
    except Exception as e:
        print(f"Error in get_io: {e}")
        return []

def oi_plot(num, step, nearest, data):
    try:
        if not data: return pd.DataFrame()
        currExpiryDate = data["records"]["expiryDates"][0]
        
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
    nifty_oi_data = get_io(50, nf_nearest, nifty_data)
    nf_highestoi_CE = highest_oi(15, 50, nf_nearest, nifty_data, "CE") 
    nf_highestoi_PE = highest_oi(15, 50, nf_nearest, nifty_data, "PE")
    nifty_chart_data = oi_plot(20, 50, nf_nearest, nifty_data) 

    # Process BANKNIFTY
    bnf_ul = get_spot_price(bank_nifty_data)
    bnf_nearest = nearest_strike_bnf(bnf_ul)
    bank_nifty_oi_data = get_io(100, bnf_nearest, bank_nifty_data)
    bnf_highestoi_CE = highest_oi(20, 100, bnf_nearest, bank_nifty_data, "CE")
    bnf_highestoi_PE = highest_oi(20, 100, bnf_nearest, bank_nifty_data, "PE")
    bank_nifty_chart_data = oi_plot(20, 100, bnf_nearest, bank_nifty_data)

    # ==========================================
    # NIFTY UI RENDERING
    # ==========================================
    st.metric("NIFTY 50 Index", f"{nf_ul:,.2f}")
    
    if nifty_oi_data:
        st.write(f"NIFTY Exp-{nifty_oi_data[0]['expiry']} :blue[LTP {str(nf_ul)}], :gray[CE[ ATM:{str(nf_nearest)},ITM:{str(nf_nearest-50)},OTM:{str(nf_nearest+50)}]], :gray[PE[ ATM:{str(nf_nearest)}, ITM:{str(nf_nearest+50)}, OTM:{str(nf_nearest-50)}]], :green[OI_SUP {str(nf_highestoi_PE)}] :red[OI_RES {str(nf_highestoi_CE)}]")
        
        # FIXED: Dynamic column rendering so it never crashes if strikes are missing
        cols = st.columns(6)
        col_idx = 0
        with st.container():
            for row in nifty_oi_data[:3]:
                cols[col_idx].metric(label=f"NIFTY {row['strike']} CE", value=str(row['ce_ltp']), delta=str(row['ce_change']))
                cols[col_idx+1].metric(label=f"NIFTY {row['strike']} PE", value=str(row['pe_ltp']), delta=str(row['pe_change']))
                col_idx += 2
            st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            st.divider()

    with st.expander("Click to see Nifty OI"):
        if not nifty_chart_data.empty:
            st.bar_chart(nifty_chart_data, x="Strike", y=["CE_OI", "PE_OI"], color=["#0000FF", "#FF0000"])

    # ==========================================
    # BANKNIFTY UI RENDERING
    # ==========================================
    st.metric("NIFTY BANK Index", f"{bnf_ul:,.2f}")
    
    if bank_nifty_oi_data:
        st.write(f"BANKNIFTY Exp-{bank_nifty_oi_data[0]['expiry']} :blue[LTP {str(bnf_ul)}] , :gray[ CE[ATM: {str(bnf_nearest)},ITM:{str(bnf_nearest-100)},OTM:{str(bnf_nearest+100)}]], :gray[PE[ ATM:{str(bnf_nearest)}, ITM:{str(bnf_nearest+100)}, OTM:{str(bnf_nearest-100)}]], :green[OI_SUP {str(bnf_highestoi_PE)}],  :red[OI_RES {str(bnf_highestoi_CE)}]")
        
        # FIXED: Dynamic column rendering
        bnf_cols = st.columns(6)
        bnf_col_idx = 0
        with st.container():
            for row in bank_nifty_oi_data[:3]:
                bnf_cols[bnf_col_idx].metric(label=f"BANKNIFTY {row['strike']} CE", value=str(row['ce_ltp']), delta=str(row['ce_change']))
                bnf_cols[bnf_col_idx+1].metric(label=f"BANKNIFTY {row['strike']} PE", value=str(row['pe_ltp']), delta=str(row['pe_change']))
                bnf_col_idx += 2
            st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            st.divider()

    with st.expander("Click to see BankNifty OI"):
        if not bank_nifty_chart_data.empty:
            st.bar_chart(bank_nifty_chart_data, x="Strike", y=["CE_OI", "PE_OI"], color=["#0000FF", "#FF0000"])