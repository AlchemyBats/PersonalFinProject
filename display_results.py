from flask import Flask, render_template_string, abort
import json

# ---------- Configuration ----------
RESULTS_FILE = "llm_vs_traditional_results.json"

# Load data once at startup
with open(RESULTS_FILE) as f:
    DATA = json.load(f)

TICKERS = sorted(DATA.keys())

app = Flask(__name__)

# ---------- Inline Templates with bar chart and extended summary ----------

INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Financial Analysis Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body { font-family: Arial, sans-serif; margin: 20px; }
    canvas { max-width: 600px; margin: 20px 0; }
    select { font-size: 1em; padding: 5px; }
    pre { white-space: pre-wrap; word-wrap: break-word; }
  </style>
</head>
<body>
  <h1>Overview</h1>
  <p>
    This dashboard presents an interactive visualization of how Generative AI compares to   
    classical trend‐analysis methods over 5 years of historical stock data (sourced from 
    yFinance and WRDS). It computes 20-day and 50-day moving averages plus exponential 
    smoothing for each ticker, then gathers interpretive insights via DeepSeek-R1 and 
    concise investment recommendations via Mistral. The “similarity” metric shows how 
    consistently the AI’s portfolio advice repeats across multiple runs, highlighting 
    its response stability and variability.
  </p>
  <div>
    <label for="tickerSelect">Jump to ticker:</label>
    <select id="tickerSelect" onchange="if(this.value) window.location=this.value;">
      <option value="">-- Select --</option>
      {% for t in tickers %}
      <option value="/ticker/{{ t }}">{{ t }}</option>
      {% endfor %}
    </select>
  </div>

  <h2>Overall Recommendation Counts</h2>
  <canvas id="recBar"></canvas>

  <h2>Average Runtime per Ticker (seconds)</h2>
  <canvas id="runtimeBar"></canvas>

  <h2>Similarity Ranking per Ticker</h2>
  <canvas id="simBar"></canvas>
  <p><strong>Average Similarity:</strong> {{ overall_similarity }}%</p>

<script>
  const recCounts = {{ rec_counts|tojson }};
  const avgRuntimes = {{ avg_runtimes|tojson }};
  const simRanks = {{ sim_ranks|tojson }};

  // Bar chart for overall recommendation counts
  new Chart(document.getElementById('recBar').getContext('2d'), {
    type: 'bar',
    data: {
      labels: Object.keys(recCounts),
      datasets: [{
        label: 'Count',
        data: Object.values(recCounts)
      }]
    },
    options: {
      responsive: true,
      scales: {
        y: { beginAtZero: true, title: { display: true, text: 'Count' } },
        x: { title: { display: true, text: 'Recommendation' } }
      }
    }
  });

  // Bar chart for average runtimes
  new Chart(document.getElementById('runtimeBar').getContext('2d'), {
    type: 'bar',
    data: {
      labels: Object.keys(avgRuntimes),
      datasets: [{
        label: 'Avg Runtime (s)',
        data: Object.values(avgRuntimes)
      }]
    },
    options: { responsive: true }
  });

  // Bar chart for similarity rankings
  new Chart(document.getElementById('simBar').getContext('2d'), {
    type: 'bar',
    data: {
      labels: Object.keys(simRanks),
      datasets: [{
        label: 'Similarity %',
        data: Object.values(simRanks)
      }]
    },
    options: {
      responsive: true,
      scales: {
        y: { beginAtZero: true, title: { display: true, text: 'Similarity (%)' } },
        x: { title: { display: true, text: 'Ticker' } }
      }
    }
  });
</script>
</body>
</html>
"""

TICKER_HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>{{ symbol }} Details</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body { font-family: Arial, sans-serif; margin: 20px; }
    canvas { max-width: 600px; margin: 20px 0; }
    table { border-collapse: collapse; width: 100%; margin: 20px 0; }
    th, td { border: 1px solid #ccc; padding: 8px; text-align: left; vertical-align: top; }
    details { cursor: pointer; }
    pre { white-space: pre-wrap; word-wrap: break-word; }
  </style>
</head>
<body>
  <h1>Ticker: {{ symbol }}</h1>
  <p><a href="/">« Back to Overview</a></p>

  <h2>Trend Analysis (last 100 days)</h2>
  <canvas id="trendLine"></canvas>

  <h2>DeepSeek Insights</h2>
  <pre>{{ deepseek.trimmed_response }}</pre>

  <h2>Mistral Recommendation Frequencies</h2>
  <canvas id="freqBar"></canvas>
  <h3>Similarity Ranking: {{ similarity_percent }}%</h3>

  <h2>Mistral Runtimes</h2>
  <canvas id="runtimeBarTicker"></canvas>

  <table>
    <thead>
      <tr>
        <th>Run</th>
        <th>Recommendation</th>
        <th>Runtime (s)</th>
        <th>Word Count</th>
        <th>Raw Response</th>
      </tr>
    </thead>
    <tbody>
      {% for rec in mistral %}
      <tr>
        <td>{{ loop.index }}</td>
        <td>{{ rec.recommendation }}</td>
        <td>{{ rec.runtime_seconds }}</td>
        <td>{{ rec.word_count }}</td>
        <td>
          <details>
            <summary>View</summary>
            <pre>{{ rec.raw_response }}</pre>
          </details>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

<script>
  const trad = {{ traditional|tojson }};
  const xLabels = trad.moving_average_20.map((_, i) => i + 1);

  new Chart(document.getElementById('trendLine').getContext('2d'), {
    type: 'line',
    data: {
      labels: xLabels,
      datasets: [
        { label: 'MA20', data: trad.moving_average_20, fill: false },
        {% if traditional.moving_average_50 %}
        { label: 'MA50', data: trad.moving_average_50, fill: false },
        {% endif %}
        { label: 'EMA20', data: trad.ema_20, fill: false }
      ]
    },
    options: {
      responsive: true,
      scales: {
        x: { title: { display: true, text: 'Day Index' } },
        y: { title: { display: true, text: 'Price' } }
      }
    }
  });

  const freq = {};
  {{ mistral|tojson }}.forEach(r => {
    freq[r.recommendation] = (freq[r.recommendation]||0) + 1;
  });
  new Chart(document.getElementById('freqBar').getContext('2d'), {
    type: 'bar',
    data: {
      labels: Object.keys(freq),
      datasets: [{ label: 'Count', data: Object.values(freq) }]
    },
    options: { responsive: true }
  });

  const misRec = {{ mistral|tojson }};
  new Chart(document.getElementById('runtimeBarTicker').getContext('2d'), {
    type: 'bar',
    data: {
      labels: misRec.map((_, i) => i + 1),
      datasets: [{
        label: 'Runtime (s)',
        data: misRec.map(r => r.runtime_seconds)
      }]
    },
    options: { responsive: true }
  });
</script>
</body>
</html>
"""

# ---------- Helper to aggregate overview data ----------

def aggregate_overview(data):
    rec_counts = {}
    avg_runtimes = {}
    sim_ranks = {}
    for ticker, info in data.items():
        recs = info.get("mistral_recommendations", [])
        if recs:
            for r in recs:
                rec_counts[r["recommendation"]] = rec_counts.get(r["recommendation"], 0) + 1
            avg_runtimes[ticker] = round(sum(r["runtime_seconds"] for r in recs) / len(recs), 4)
            counts = {}
            for r in recs:
                counts[r["recommendation"]] = counts.get(r["recommendation"], 0) + 1
            max_count = max(counts.values())
            sim_ranks[ticker] = round((max_count / len(recs)) * 100, 2)
        else:
            sim_ranks[ticker] = 0.0
    return rec_counts, avg_runtimes, sim_ranks

# ---------- Routes ----------

@app.route("/")
def index():
    rec_counts, avg_runtimes, sim_ranks = aggregate_overview(DATA)
    overall_similarity = round(sum(sim_ranks.values()) / len(sim_ranks), 2) if sim_ranks else 0.0
    return render_template_string(
        INDEX_HTML,
        tickers=TICKERS,
        rec_counts=rec_counts,
        avg_runtimes=avg_runtimes,
        sim_ranks=sim_ranks,
        overall_similarity=overall_similarity
    )

@app.route("/ticker/<symbol>")
def ticker_detail(symbol):
    if symbol not in DATA:
        abort(404, description="Ticker not found")
    info = DATA[symbol]
    recs = info.get("mistral_recommendations", [])
    if recs:
        counts = {}
        for r in recs:
            counts[r["recommendation"]] = counts.get(r["recommendation"], 0) + 1
        max_count = max(counts.values())
        similarity = round((max_count / len(recs)) * 100, 2)
    else:
        similarity = 0.0

    return render_template_string(
        TICKER_HTML,
        symbol=symbol,
        traditional=info["traditional_analysis"],
        deepseek=info["deepseek"],
        mistral=recs,
        similarity_percent=similarity
    )

if __name__ == "__main__":
    app.run(debug=True)
