#!/usr/bin/env python3
"""
bp_chart.py — Blood Pressure Chart Generator
============================================
Usage:
  python bp_chart.py input.csv meds.txt
  python bp_chart.py input.csv meds.txt output.html

Arguments:
  input.csv    BP readings CSV with columns:
               Date, Time, Systolic (mmHg), Diastolic (mmHg), Pulse (bpm), Notes
               Date format: "May 01, 2026" or "Apr 29, 2026"

  meds.txt     Medication list — plain text or RTF — one period per line:
               8/10/25 to 10/1/25 Lisinopril-HCTZ 10-12.5mg 1/2tab
               10/2/25 to 1/20/26 Lisinopril 5mg
               4/8/26 to current  Losartan 50mg

  output.html  Optional. Defaults to input filename with _chart.html suffix.

Outputs a self-contained HTML file — open in any browser, no server needed.
No external Python dependencies required beyond the standard library.
"""

import csv
import sys
import json
import re
import os
from datetime import datetime


# ── CSV parsing ───────────────────────────────────────────────────────────────

DATE_FORMATS = [
    "%b %d, %Y",   # Apr 29, 2026
    "%B %d, %Y",   # April 29, 2026
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
                dt = parse_date(date_str)
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


# ── Medication file parsing ───────────────────────────────────────────────────

MED_DATE_FORMATS = ["%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d"]

def parse_med_date(s):
    s = s.strip()
    for fmt in MED_DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse medication date: {s!r}")


def extract_plain_text(raw):
    """Convert RTF to plain text if needed, otherwise return as-is."""
    if not raw.lstrip().startswith('{\\rtf'):
        return raw
    # Remove RTF control words (e.g. \pard, \f0, \fs24)
    text = re.sub(r'\\[a-zA-Z]+\d*\s?', '', raw)
    # Backslashes in RTF source represent line breaks / escaped chars
    text = text.replace('\\', '\n')
    # Remove braces
    text = re.sub(r'[{}]', '', text)
    # Collapse excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


def clean_label(s):
    """Normalise label text: replace 1/2 with ½, strip stray punctuation."""
    s = re.sub(r'\b1/2\b', '\u00bd', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def parse_meds(path):
    meds = []
    today_ms  = int(datetime.now().timestamp() * 1000)
    future_ms = today_ms + 14 * 24 * 3600 * 1000  # 2 weeks ahead for "current"

    with open(path, encoding="utf-8", errors="replace") as f:
        raw = f.read()

    text = extract_plain_text(raw)

    pattern = re.compile(
        r'(\d{1,2}/\d{1,2}/\d{2,4})\s+to\s+(\d{1,2}/\d{1,2}/\d{2,4}|current)\s+([^\n\r]+)',
        re.IGNORECASE,
    )

    for m in pattern.finditer(text):
        start_str = m.group(1).strip()
        end_str   = m.group(2).strip()
        label     = clean_label(m.group(3))
        if not label:
            continue
        try:
            start_ms = int(parse_med_date(start_str).timestamp() * 1000)
            end_ms   = future_ms if end_str.lower() == "current" \
                       else int(parse_med_date(end_str).timestamp() * 1000)
            meds.append({"start": start_ms, "end": end_ms, "label": label})
        except ValueError as e:
            print(f"  Skipping med line ({e}): {m.group(0)!r}")

    if not meds:
        print("  WARNING: No medication periods parsed from file.")
    else:
        for med in meds:
            print(f"    {med['label']}")
    return meds


# ── HTML template ─────────────────────────────────────────────────────────────

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
  .chart-box { position: relative; width: 100%; height: 500px; }
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

// ── LOESS smoother ────────────────────────────────────────────────────────
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

// ── Word-wrap: splits label string into lines fitting maxWidth px ─────────
function wrapText(ctx, text, maxWidth) {
  const words = text.split(' ');
  const lines = [];
  let cur = '';
  for (const w of words) {
    const test = cur ? cur + ' ' + w : w;
    if (cur && ctx.measureText(test).width > maxWidth) {
      lines.push(cur);
      cur = w;
    } else {
      cur = test;
    }
  }
  if (cur) lines.push(cur);
  return lines;
}

// ── Plugin: dashed lines + above-x-axis medication labels ─────────────────
const medPlugin = {
  id: 'medPlugin',
  afterDraw(chart) {
    const {ctx, chartArea, scales: {x}} = chart;
    ctx.save();

    // Dashed vertical lines at each medication boundary
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

    // Medication labels: top-anchored just inside top of chart, word-wrapped
    const fontSize = 10.5;
    const lineH    = fontSize + 3;
    const pad      = 4;
    const maxRows  = 2;
    const labelTop = chartArea.top + pad;

    ctx.font = `${fontSize}px Arial, sans-serif`;
    ctx.fillStyle = '#333';
    ctx.textBaseline = 'top';

    MEDS.forEach(m => {
      const x1      = Math.max(x.getPixelForValue(m.start), chartArea.left);
      const x2      = Math.min(x.getPixelForValue(m.end),   chartArea.right);
      const regionW = x2 - x1 - pad * 2;
      if (regionW < 10) return;

      // Wrap label into lines that fit the region; clamp to maxRows
      let lines = wrapText(ctx, m.label, regionW);
      if (lines.length > maxRows) lines = lines.slice(0, maxRows);

      // Clip to region and draw top-down from top of chart
      ctx.save();
      ctx.beginPath();
      ctx.rect(x1, chartArea.top, x2 - x1, chartArea.bottom - chartArea.top);
      ctx.clip();
      lines.forEach((line, i) => {
        ctx.fillText(line, x1 + pad, labelTop + i * lineH);
      });
      ctx.restore();
    });

    ctx.restore();
  }
};
Chart.register(medPlugin);

// ── Chart ─────────────────────────────────────────────────────────────────
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
        grid: {color: 'rgba(0,0,0,0.15)', lineWidth: 1},
        border: {display: false}
      },
      y: {
        min: 55, max: 170,
        ticks: {color: '#666', font: {size: 11}, stepSize: 10},
        grid: {color: 'rgba(0,0,0,0.15)', lineWidth: 1},
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

    if len(args) < 2:
        print("Usage: python bp_chart.py input.csv meds.txt [output.html]")
        print()
        print(__doc__)
        sys.exit(1)

    csv_path = args[0]
    med_path = args[1]
    out_path = args[2] if len(args) > 2 else os.path.splitext(csv_path)[0] + "_chart.html"

    print(f"Reading CSV : {csv_path}")
    data = parse_csv(csv_path)
    if not data:
        print("ERROR: No valid rows parsed. Check date/column format.")
        sys.exit(1)
    print(f"  {len(data)} readings loaded.")

    print(f"Reading meds: {med_path}")
    meds = parse_meds(med_path)
    if not meds:
        print("ERROR: No medication periods found. Check meds file format.")
        sys.exit(1)
    print(f"  {len(meds)} medication periods loaded.")

    data_span = data[-1]["ts"] - data[0]["ts"]
    min_x = data[0]["ts"]  - int(data_span * 0.01)
    max_x = data[-1]["ts"] + int(data_span * 0.05)
    if meds[-1]["end"] > max_x:
        max_x = meds[-1]["end"] + int(data_span * 0.02)

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
