"""Insider trading & analyst revision signals.

Two of the strongest alpha signals in equity research:
1. Insider buying/selling — people with actual knowledge of the company
2. Analyst estimate revisions — consensus shifts predict price moves

Data source: yfinance (free, no API key needed).
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


# --- Analyst Revisions ---

def analyze_analyst_signals(ticker_obj) -> dict:
    """Extract analyst revision signals from yfinance Ticker object.
    
    Signals:
    - Recent upgrades/downgrades (last 30/90 days)
    - Price target direction (raises vs lowers)
    - Consensus shift (current vs prior month)
    - Consensus skew (bull vs bear ratio)
    
    Args:
        ticker_obj: yfinance Ticker object
    
    Returns:
        dict with score (0-100) and signal details
    """
    result = {
        "score": 50,  # neutral default
        "upgrades_30d": 0,
        "downgrades_30d": 0,
        "pt_raises_30d": 0,
        "pt_lowers_30d": 0,
        "net_revisions_30d": 0,
        "consensus_shift": None,
        "consensus": None,
        "analyst_count": 0,
        "signals": [],
    }
    
    # --- Upgrades/Downgrades ---
    try:
        ud = ticker_obj.upgrades_downgrades
        if ud is not None and len(ud) > 0:
            now = datetime.now()
            cutoff_30d = now - timedelta(days=30)
            cutoff_90d = now - timedelta(days=90)
            
            # Filter recent
            ud.index = pd.to_datetime(ud.index, utc=True)
            recent_30d = ud[ud.index >= cutoff_30d]
            recent_90d = ud[ud.index >= cutoff_90d]
            
            # Grade changes (up/down/reit/main)
            upgrades_30 = len(recent_30d[recent_30d["Action"] == "up"])
            downgrades_30 = len(recent_30d[recent_30d["Action"] == "down"])
            upgrades_90 = len(recent_90d[recent_90d["Action"] == "up"])
            downgrades_90 = len(recent_90d[recent_90d["Action"] == "down"])
            
            result["upgrades_30d"] = upgrades_30
            result["downgrades_30d"] = downgrades_30
            result["upgrades_90d"] = upgrades_90
            result["downgrades_90d"] = downgrades_90
            
            # Price target direction
            pt_raises = 0
            pt_lowers = 0
            for _, row in recent_30d.iterrows():
                curr_pt = row.get("currentPriceTarget")
                prior_pt = row.get("priorPriceTarget")
                if pd.notna(curr_pt) and pd.notna(prior_pt) and prior_pt > 0:
                    if curr_pt > prior_pt:
                        pt_raises += 1
                    elif curr_pt < prior_pt:
                        pt_lowers += 1
            
            result["pt_raises_30d"] = pt_raises
            result["pt_lowers_30d"] = pt_lowers
            result["net_revisions_30d"] = (upgrades_30 + pt_raises) - (downgrades_30 + pt_lowers)
    except Exception as e:
        logger.debug("upgrades_downgrades failed for ticker: %s", e)
    
    # --- Consensus Summary ---
    try:
        rec = ticker_obj.recommendations_summary
        if rec is not None and len(rec) >= 2:
            current = rec.iloc[0]
            prior = rec.iloc[1]
            
            total_now = current.get("strongBuy", 0) + current.get("buy", 0) + current.get("hold", 0) + current.get("sell", 0) + current.get("strongSell", 0)
            total_prior = prior.get("strongBuy", 0) + prior.get("buy", 0) + prior.get("hold", 0) + prior.get("sell", 0) + prior.get("strongSell", 0)
            
            result["analyst_count"] = int(total_now) if total_now else 0
            
            if total_now > 0 and total_prior > 0:
                # Bull ratio: (strongBuy + buy) / total
                bull_now = (current.get("strongBuy", 0) + current.get("buy", 0)) / total_now
                bull_prior = (prior.get("strongBuy", 0) + prior.get("buy", 0)) / total_prior
                
                result["consensus"] = {
                    "strong_buy": int(current.get("strongBuy", 0)),
                    "buy": int(current.get("buy", 0)),
                    "hold": int(current.get("hold", 0)),
                    "sell": int(current.get("sell", 0)),
                    "strong_sell": int(current.get("strongSell", 0)),
                    "bull_ratio": round(bull_now, 3),
                }
                
                shift = bull_now - bull_prior
                result["consensus_shift"] = round(shift, 3)
                
                if shift > 0.05:
                    result["signals"].append("Consensus turning bullish")
                elif shift < -0.05:
                    result["signals"].append("Consensus turning bearish")
    except Exception as e:
        logger.debug("recommendations_summary failed: %s", e)
    
    # --- Score Calculation ---
    score = 50
    
    # Net revisions impact (strongest signal)
    net_rev = result["net_revisions_30d"]
    if net_rev >= 3:
        score += 25
        result["signals"].append(f"Strong positive revisions (+{net_rev} net)")
    elif net_rev >= 1:
        score += 12
        result["signals"].append(f"Positive revisions (+{net_rev} net)")
    elif net_rev <= -3:
        score -= 25
        result["signals"].append(f"Strong negative revisions ({net_rev} net)")
    elif net_rev <= -1:
        score -= 12
        result["signals"].append(f"Negative revisions ({net_rev} net)")
    
    # Consensus shift
    shift = result.get("consensus_shift")
    if shift is not None:
        if shift > 0.10:
            score += 15
        elif shift > 0.05:
            score += 8
        elif shift < -0.10:
            score -= 15
        elif shift < -0.05:
            score -= 8
    
    # Bull ratio absolute level
    consensus = result.get("consensus")
    if consensus and consensus.get("bull_ratio") is not None:
        br = consensus["bull_ratio"]
        if br > 0.80:
            score += 10
        elif br > 0.60:
            score += 5
        elif br < 0.30:
            score -= 10
        elif br < 0.40:
            score -= 5
    
    result["score"] = max(0, min(100, score))
    return result


# --- Insider Trading ---

def analyze_insider_signals(ticker_obj) -> dict:
    """Extract insider trading signals from yfinance Ticker object.
    
    Key insight: insider BUYING is a much stronger signal than selling.
    Insiders sell for many reasons (diversification, taxes, liquidity),
    but they only buy for one: they think the stock is going up.
    
    Args:
        ticker_obj: yfinance Ticker object
    
    Returns:
        dict with score (0-100) and signal details
    """
    result = {
        "score": 50,
        "net_purchases_6m": None,
        "buy_count": 0,
        "sell_count": 0,
        "net_shares": 0,
        "pct_net_purchased": None,
        "signals": [],
    }
    
    # --- Insider Purchases Summary ---
    try:
        ip = ticker_obj.insider_purchases
        if ip is not None and len(ip) > 0:
            # Parse the summary table
            for _, row in ip.iterrows():
                label = str(row.iloc[0]).strip()
                value = row.iloc[1]
                
                if "Purchases" == label:
                    result["buy_count"] = int(value) if pd.notna(value) else 0
                elif "Sales" == label:
                    result["sell_count"] = int(value) if pd.notna(value) else 0
                elif "Net Shares" in label:
                    result["net_shares"] = int(value) if pd.notna(value) else 0
                elif "% Net Shares" in label and "Buy" not in label and "Sell" not in label:
                    result["pct_net_purchased"] = float(value) if pd.notna(value) else None
    except Exception as e:
        logger.debug("insider_purchases failed: %s", e)
    
    # --- Recent Transactions (more granular) ---
    recent_buys = 0
    recent_sells = 0
    try:
        txns = ticker_obj.insider_transactions
        if txns is not None and len(txns) > 0:
            cutoff = datetime.now() - timedelta(days=90)
            for _, row in txns.iterrows():
                date_str = row.get("Start Date")
                if date_str:
                    try:
                        txn_date = pd.to_datetime(date_str, utc=True)
                        if txn_date < cutoff:
                            continue
                    except Exception:
                        pass
                
                text = str(row.get("Text", "")).lower()
                txn_type = str(row.get("Transaction", "")).lower()
                
                if "purchase" in text or "buy" in txn_type:
                    recent_buys += 1
                elif "sale" in text or "sell" in txn_type:
                    recent_sells += 1
    except Exception as e:
        logger.debug("insider_transactions failed: %s", e)
    
    # --- Score ---
    score = 50
    
    net = result["net_shares"]
    buy_count = result["buy_count"]
    sell_count = result["sell_count"]
    
    # Net buying is bullish (strong signal)
    if net > 0 and buy_count > sell_count:
        if buy_count >= 5:
            score += 25
            result["signals"].append(f"Heavy insider buying ({buy_count} buys vs {sell_count} sells)")
        else:
            score += 15
            result["signals"].append(f"Net insider buying ({buy_count} buys vs {sell_count} sells)")
    elif net < 0 and sell_count > buy_count * 3:
        # Heavy selling (only penalize if lopsided — some selling is normal)
        score -= 15
        result["signals"].append(f"Heavy insider selling ({sell_count} sells vs {buy_count} buys)")
    elif net < 0:
        score -= 5
        result["signals"].append("Mild net insider selling (may be routine)")
    
    # % net purchased
    pct = result.get("pct_net_purchased")
    if pct is not None:
        if pct > 0.01:  # > 1% net bought
            score += 10
            result["signals"].append(f"Insiders increased holdings by {pct*100:.1f}%")
        elif pct < -0.02:  # > 2% net sold
            score -= 10
    
    result["score"] = max(0, min(100, score))
    return result


def get_combined_smart_money_score(ticker_obj) -> dict:
    """Combined analyst + insider score for a ticker.
    
    Weight: 60% analyst revisions, 40% insider trading.
    (Analyst revisions are more timely and frequent; insider data is lagged.)
    """
    analyst = analyze_analyst_signals(ticker_obj)
    insider = analyze_insider_signals(ticker_obj)
    
    combined_score = analyst["score"] * 0.6 + insider["score"] * 0.4
    
    all_signals = analyst.get("signals", []) + insider.get("signals", [])
    
    return {
        "score": round(combined_score, 1),
        "analyst_score": analyst["score"],
        "insider_score": insider["score"],
        "analyst": analyst,
        "insider": insider,
        "signals": all_signals,
    }
