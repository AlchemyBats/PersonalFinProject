import os
import json
import time
import re
import logging

import pandas as pd
import numpy as np
import ollama

# ---------- Configuration ----------
DATA_DIR = "use_stocks"   # make sure this matches your folder name
OUTPUT_FILE = "llm_vs_traditional_results.json"
NUM_TICKERS = 12
NUM_MISTRAL_RUNS = 10

DEEPSEEK_MODEL = "deepseek-r1"
MISTRAL_MODEL = "mistral"

# Extended set of normalized labels
LABEL_KEYWORDS = {
    "strong buy":  ["strong buy", "definitely buy", "highly recommend buying"],
    "buy":         ["buy", "recommend buying", "a good investment"],
    "hold":        ["hold", "consider holding", "no immediate action"],
    "sell":        ["sell", "recommend selling", "consider exiting"],
    "strong sell": ["strong sell", "definitely sell", "highly recommend selling"],
    "short":       ["short", "bet against", "expect decline"],
    "long":        ["long", "expect increase", "bullish"],
    "avoid":       ["avoid", "stay away", "not advisable"],
    "do not buy":  ["do not buy", "don't buy"],
    "speculative": ["risky", "volatile", "uncertain"],
    "cautious":    ["cautious", "wary", "careful"]
}

# set up logging
logging.basicConfig(
    format="%(asctime)s %(levelname)s:%(message)s",
    level=logging.INFO
)

def normalize_label(text: str) -> str:
    for label, keywords in LABEL_KEYWORDS.items():
        for kw in keywords:
            if re.search(rf"\b{re.escape(kw)}\b", text, flags=re.IGNORECASE):
                return label
    return "other"

def load_ticker_files(data_dir, limit):
    files = sorted(f for f in os.listdir(data_dir) if f.endswith("_data.csv"))
    return files[:limit]

def compute_traditional(df):
    """Compute traditional trend metrics on the given DataFrame."""
    result = {}
    # moving averages and EMA on truncated data
    ma20 = df['close'].rolling(20).mean().dropna().tolist()
    ma50 = df['close'].rolling(50).mean().dropna().tolist()
    ema20 = df['close'].ewm(span=20, adjust=False).mean().dropna().tolist()

    if ma20:
        result['moving_average_20'] = ma20
    if ma50:
        result['moving_average_50'] = ma50
    if ema20:
        result['ema_20'] = ema20

    # regression slope
    try:
        x = np.arange(len(df))
        slope, _ = np.polyfit(x, df['close'], 1)
        if not np.isnan(slope):
            result['regression_slope'] = float(slope)
    except Exception:
        pass

    # summary statistics
    mean_close = df['close'].mean()
    std_close = df['close'].std()
    stats = {}
    if not np.isnan(mean_close):
        stats['mean_close'] = float(mean_close)
    if not np.isnan(std_close):
        stats['std_close'] = float(std_close)
    if stats:
        result['summary_stats'] = stats

    return result

def trim_deepseek(raw: str) -> str:
    """Strip off <think>...</think> sections and return only the final analysis."""
    parts = re.split(r"</think\s*>", raw, flags=re.IGNORECASE)
    return parts[-1].strip()

def run_deepseek(data_string: str):
    prompt = (
        "Analyze the following stock data and describe trends. Be clear with your final response:\n"
        f"{data_string}"
    )
    resp = ollama.chat(model=DEEPSEEK_MODEL, messages=[{"role": "user", "content": prompt}])
    raw = resp["message"]["content"]
    trimmed = trim_deepseek(raw)
    return raw, trimmed

def run_mistral(input_text: str):
    prompt = (
        "For research purposes only—not financial advice.\n"
        "Based on the analysis below, what is your investment recommendation "
        "for a standard portfolio? Use one of: buy, strong buy, hold, sell, strong sell, "
        "short, long, avoid, do not buy, speculative, or cautious. Be decisive with your answer. You must pick something. Respond succinctly:\n\n"
        f"{input_text}"
    )
    start = time.time()
    resp = ollama.chat(model=MISTRAL_MODEL, messages=[{"role": "user", "content": prompt}])
    runtime = time.time() - start
    raw = resp["message"]["content"].strip()
    label = normalize_label(raw)
    # Include word count of the raw response
    word_count = len(raw.split())
    return {
        "raw_response": raw,
        "recommendation": label,
        "runtime_seconds": round(runtime, 4),
        "word_count": word_count
    }

def main():
    logging.info(f"Looking in data directory: {DATA_DIR}")
    if not os.path.isdir(DATA_DIR):
        logging.error(f"Directory not found: {DATA_DIR}")
        return

    tickers = load_ticker_files(DATA_DIR, NUM_TICKERS)
    logging.info(f"Found ticker files: {tickers}")
    if not tickers:
        logging.error("No CSV ticker files found; check your DATA_DIR and file naming.")
        return

    results = {}
    for fname in tickers:
        ticker = fname.split("_")[0]
        df_full = pd.read_csv(os.path.join(DATA_DIR, fname), parse_dates=["date"])
        df_full.sort_values("date", inplace=True)
        df = df_full.tail(100)

        trad = compute_traditional(df)
        data_string = df.to_string(index=False)

        deep_raw, deep_trimmed = run_deepseek(data_string)

        mistral_results = []
        for _ in range(NUM_MISTRAL_RUNS):
            rec = run_mistral(deep_trimmed)
            if all(v is not None for v in rec.values()):
                mistral_results.append(rec)

        results[ticker] = {
            "traditional_analysis": trad,
            "deepseek": {
                "raw_response": deep_raw.strip(),
                "trimmed_response": deep_trimmed
            },
            "mistral_recommendations": mistral_results
        }

    # write out and confirm
    with open(OUTPUT_FILE, "w") as fp:
        json.dump(results, fp, indent=2, sort_keys=True)
    logging.info(f"Wrote results for {len(results)} tickers to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()