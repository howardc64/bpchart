#!/usr/bin/env python3
"""
bp_chart.py — Blood Pressure Chart Generator
============================================
Usage:
  python bp_chart.py input.csv
  python bp_chart.py input.csv output.html
  python bp_chart.py input.csv output.html meds.txt

CSV columns expected (as exported by common BP apps):
  Date, Time, Systolic (mmHg), Diastolic (mmHg), Pulse (bpm), Notes
  Date format: "May 01, 2026" or "Apr 29, 2026" (abbreviated or full month name)

Optional meds.txt format (one period per line):
  8/10/25 to 10/1/25 Lisinopril-HCTZ 10-12.5mg 1/2tab
  10/2/25 to 1/20/26 Lisinopril 5mg
  4/8/26 to current  Losartan 50mg

Outputs a self-contained HTML file — open it in any browser.
No external dependencies required beyond Python 3.6+.
"""

import csv
import sys
import json
import re
import os
from datetime import datetime


# ── CSV parsing ──────────────────────────────────────────────────────────────

DATE_FORMATS = [
    "%b %d, %Y",   # Apr 29, 2026  (abbreviated month, zero-padded day)
    "%B %d, %Y",   # April 29, 2026 (full month, zero-padded day)
    "%Y-%m-%d",    # 2026-04-29
    "%m/%d/%Y",    # 04/29/2026
    "%m/%d/%y",    # 04/29/26
]

def parse_date(s):
    s = s.strip().strip('"').strip("'")
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date format: {s!r}")


def parse_csv(path):
    rows = []
    skipped = 0
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            date_str = row.get("Date", "").strip()
            sys_str  = row.get("Systolic (mmHg)", "").strip()
            dia_str  = row.get("Diastolic (mmHg)", "").strip()
            if not date_str or not sys_str or not dia_str:
                skipped += 1
                continue
            try:
                dt  = parse_date(date_str)
                rows.append({
                    "ts":  int(dt.timestamp() * 1000),
                    "sys": int(sys_str),
                    "dia": int(dia_str),
                })
            except (ValueError, TypeError) as e:
                skipped += 1
                print(f"  Skipping row ({e}): {date_str!r}")
    rows.sort(key=lambda r: r["ts"])
    if skipped:
        print(f"  ({skipped} rows skipped)")
    return rows


# ── Medication file parsing ──────────────────────────────────────────────────

MED_DATE_FORMATS = ["%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d"]

def parse_med_date(s):
    s = s.strip()
    for fmt in MED_DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse medication date: {s!r}")


def split_label(label):
    words = label.split()
    if len(words) <= 2:
        return [label]
    mid = (len(words) + 1) // 2
    return [" ".join(words[:mid]), " ".join(words[mid:])]


def parse_meds(path):
    meds = []
    today_ms  = int(datetime.now().timestamp() * 1000)
    future_ms = today_ms + 14 * 24 * 3600 * 1000

    pattern = re.compile(
        r"(\d{1,2}/\d{1,2}/\d{2,4})\s+to\s+(\d{1,2}/\d{1,2}/\d{2,4}|current)\s+(.+)",
        re.IGNORECASE,
    )
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = pattern.match(line)
            if not m:
                continue
            start_str, end_str, label = m.group(1), m.group(2), m.group(3).strip()
            try:
                start_ms = int(parse_med_date(start_str).timestamp() * 1000)
                end_ms   = future_ms if end_str.lower() == "current" else int(parse_med_date(end_str).timestamp() * 1000)
                meds.append({"start": start_ms, "end": end_ms, "lines": split_label(label)})
            except ValueError as e:
                print(f"  Skipping med line ({e}): {line!r}")
    return meds


def default_meds():
    today_ms  = int(datetime.now().timestamp() * 1000)
    future_ms = today_ms + 14 * 24 * 3600 * 1000
    return [
        {"start": int(datetime(2025,  8, 10).timestamp() * 1000),
         "end":   int(datetime(2025, 10,  1).timestamp() * 1000),
         "lines": ["Lisinopril-HCTZ", "10-12.5mg \u00bdtab"]},
        {"start": int(datetime(2025, 10,  2).timestamp() * 1000),
         "end":   int(datetime(2026,  1, 19).timestamp() * 1000),
         "lines": ["Lisinopril 5mg"]},
        {"start": int(datetime(2026,  1, 20).timestamp() * 1000),
         "end":   int(datetime(2026,  4,  7).timestamp() * 1000),
         "lines": ["Losartan 25mg"]},
        {"start": int(datetime(2026,  4,  8).timestamp() * 1000),
         "end":   future_ms,
         "lines": ["Losartan 50mg"]},
    ]


# ── HTML template ────────────────────────────────────────────────────────────

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Blood Pressure Chart</title>
<style>
  body { margin: 0; font-family: Arial, sans-serif; background: #faf8f4; }
  .wrapper { max-width: 980px; margin: 0 auto; padding: 28px 24px 24px; }
  .chart-box { position: relative; width: 100%; height: 480px; }
  .legend {
    display: flex; flex-wrap: wrap; gap: 20px;
    margin-top: 14px; font-size: 12px; color: #555;
    justify-content: center; align-items: center;
  }
  .leg-item { display: flex; align-items: center; gap: 5px; }
  .sw-line { display:inline-block; width:28px; height:3px; border-radius:2px; }
  .sw-dot  { display:inline-block; width:10px; height:10px; border-radius:50%; }
  .sw-dash { display:inline-block; width:0; height:14px; border-left:2px dashed #888; }
</style>
</head>
<body>
<div class="wrapper">
  <div class="chart-box">
    <canvas id="bpChart"
      role="img"
      aria-label="Blood pressure scatter chart with systolic and diastolic trends and medication annotations">
      Systolic and diastolic blood pressure readings over time with medication period labels.
    </canvas>
  </div>
  <div class="legend">
    <span class="leg-item"><span class="sw-line" style="background:#b53030;"></span> Systolic trend</span>
    <span class="leg-item"><span class="sw-dot"  style="background:rgba(200,80,80,0.5);"></span> Systolic reading</span>
    <span class="leg-item"><span class="sw-line" style="background:#2a6fa8;"></span> Diastolic trend</span>
    <span class="leg-item"><span class="sw-dot"  style="background:rgba(60,130,200,0.45);"></span> Diastolic reading</span>
    <span class="leg-item"><span class="sw-dash"></span> Medication change</span>
  </div>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const RAW   = RAW_DATA_PLACEHOLDER;
const MEDS  = MED_DEFS_PLACEHOLDER;
const MIN_X = MIN_X_PLACEHOLDER;
const MAX_X = MAX_X_PLACEHOLDER;

function loess(xs, ys, bw) {
  return xs.map(x0 => {
    let sw=0, swx=0, swy=0, swxx=0, swxy=0;
    xs.forEach((x, j) => {
      const w = Math.exp(-0.5 * ((x - x0) / bw) ** 2);
      sw+=w; swx+=w*x; swy+=w*ys[j]; swxx+=w*x*x; swxy+=w*x*ys[j];
    });
    const det = sw*swxx - swx*swx;
    if (Math.abs(det) < 1e-10) return swy / sw;
    return ((swxx*swy - swx*swxy) + (sw*swxy - swx*swy)*x0) / det;
  });
}

const xs = RAW.map(r => r[0]);
const bw = (xs[xs.length-1] - xs[0]) * 0.09;
const sysTrend = loess(xs, RAW.map(r=>r[1]), bw);
const diaTrend = loess(xs, RAW.map(r=>r[2]), bw);
const medBounds = MEDS.slice(1).map(m => m.start);

const medPlugin = {
  id: 'medPlugin',
  afterDraw(chart) {
    const {ctx, chartArea, scales: {x}} = chart;
    ctx.save();
    medBounds.forEach(t => {
      const px = x.getPixelForValue(t);
      if (px < chartArea.left || px > chartArea.right) return;
      ctx.beginPath();
      ctx.setLineDash([6, 4]);
      ctx.strokeStyle = 'rgba(100,100,100,0.65)';
      ctx.lineWidth = 1.5;
      ctx.moveTo(px, chartArea.top);
      ctx.lineTo(px, chartArea.bottom);
      ctx.stroke();
      ctx.setLineDash([]);
    });
    ctx.font = '10.5px Arial, sans-serif';
    ctx.fillStyle = '#333';
    ctx.textBaseline = 'top';
    const labelY = chartArea.top + 6;
    MEDS.forEach(m => {
      const x1 = Math.max(x.getPixelForValue(m.start), chartArea.left);
      const x2 = Math.min(x.getPixelForValue(m.end),   chartArea.right);
      if (x2 - x1 < 5) return;
      ctx.save();
      ctx.beginPath();
      ctx.rect(x1, labelY, x2 - x1, 32);
      ctx.clip();
      m.lines.forEach((line, i) => ctx.fillText(line, x1 + 4, labelY + i * 13));
      ctx.restore();
    });
    ctx.restore();
  }
};
Chart.register(medPlugin);

new Chart(document.getElementById('bpChart'), {
  type: 'scatter',
  data: {
    datasets: [
      {
        label: 'Systolic reading',
        data: RAW.map(r => ({x: r[0], y: r[1]})),
        backgroundColor: 'rgba(200,80,80,0.4)',
        pointRadius: 4.5, showLine: false, order: 2
      },
      {
        label: 'Systolic trend',
        data: RAW.map((r,i) => ({x: r[0], y: sysTrend[i]})),
        borderColor: '#b53030', borderWidth: 2.5,
        backgroundColor: 'transparent', pointRadius: 0,
        showLine: true, tension: 0.4, order: 1
      },
      {
        label: 'Diastolic reading',
        data: RAW.map(r => ({x: r[0], y: r[2]})),
        backgroundColor: 'rgba(60,130,200,0.38)',
        pointRadius: 4.5, showLine: false, order: 2
      },
      {
        label: 'Diastolic trend',
        data: RAW.map((r,i) => ({x: r[0], y: diaTrend[i]})),
        borderColor: '#2a6fa8', borderWidth: 2.5,
        backgroundColor: 'transparent', pointRadius: 0,
        showLine: true, tension: 0.4, order: 1
      }
    ]
  },
  options: {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    plugins: {
      legend: {display: false},
      tooltip: {
        filter: item => !item.dataset.label.includes('trend'),
        callbacks: {
          title: items => new Date(items[0].parsed.x).toLocaleDateString('en-US',
            {month:'short', day:'numeric', year:'2-digit'}),
          label: ctx => ctx.dataset.label + ': ' + Math.round(ctx.parsed.y)
        }
      }
    },
    scales: {
      x: {
        type: 'linear', min: MIN_X, max: MAX_X,
        ticks: {
          color: '#666', font: {size: 11},
          maxRotation: 0, maxTicksLimit: 9,
          callback: val => new Date(val).toLocaleDateString('en-US',
            {month:'short', day:'numeric', year:'2-digit'})
        },
        grid: {color: 'rgba(0,0,0,0.1)', lineWidth: 1},
        border: {display: false}
      },
      y: {
        min: 55, max: 170,
        ticks: {color: '#666', font: {size: 11}, stepSize: 10},
        grid: {color: 'rgba(0,0,0,0.1)', lineWidth: 1},
        border: {display: false},
        title: {display: true, text: 'mmHg', color: '#666', font: {size: 12}}
      }
    },
    layout: {padding: {top: 10, bottom: 10, left: 0, right: 10}}
  }
});
</script>
</body>
</html>
"""

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    csv_path = args[0]
    out_path = args[1] if len(args) > 1 else os.path.splitext(csv_path)[0] + "_chart.html"
    med_path = args[2] if len(args) > 2 else None

    print(f"Reading CSV : {csv_path}")
    data = parse_csv(csv_path)
    if not data:
        print("ERROR: No valid rows parsed. Check date/column format.")
        sys.exit(1)
    print(f"  {len(data)} readings loaded.")

    if med_path:
        print(f"Reading meds: {med_path}")
        meds = parse_meds(med_path)
        print(f"  {len(meds)} medication periods loaded.")
    else:
        print("No meds file supplied — using built-in defaults.")
        meds = default_meds()

    min_x = data[0]["ts"]  - 2 * 86_400_000
    max_x = data[-1]["ts"] + 5 * 86_400_000

    html = HTML_TEMPLATE \
        .replace("RAW_DATA_PLACEHOLDER", json.dumps([[r["ts"], r["sys"], r["dia"]] for r in data])) \
        .replace("MED_DEFS_PLACEHOLDER",  json.dumps(meds)) \
        .replace("MIN_X_PLACEHOLDER",     str(min_x)) \
        .replace("MAX_X_PLACEHOLDER",     str(max_x))

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Chart saved : {out_path}")


if __name__ == "__main__":
    main()
