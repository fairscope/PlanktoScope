#!/usr/bin/env node
/**
 * PlanktoScope Visualizer Benchmark Tool
 *
 * Measures memory usage and speed of TSV loading/processing for the
 * visualization pipeline. Can test both the OLD approach (full file load,
 * 12x redundant parsing) and the NEW streaming columnar approach.
 *
 * Usage:
 *   node visualizer_benchmark.js <tsv_file>              # benchmark both old and new
 *   node visualizer_benchmark.js <tsv_file> --old-only    # benchmark old approach only
 *   node visualizer_benchmark.js <tsv_file> --new-only    # benchmark new approach only
 *   node visualizer_benchmark.js --generate <rows> <out>  # generate synthetic TSV for testing
 *
 * Examples:
 *   node visualizer_benchmark.js /home/pi/data/objects/2026-03-04/S_1/A_4/ecotaxa_A_4.tsv
 *   node visualizer_benchmark.js --generate 50000 /tmp/test_50k.tsv
 *   node visualizer_benchmark.js /tmp/test_50k.tsv
 */

const fs = require("fs");
const path = require("path");

// ─── Utility ────────────────────────────────────────────────────────────────

function formatBytes(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

function getMemory() {
  if (global.gc) global.gc();
  const mem = process.memoryUsage();
  return {
    rss: mem.rss,
    heapUsed: mem.heapUsed,
    heapTotal: mem.heapTotal,
    external: mem.external,
  };
}

function memDelta(before, after) {
  return {
    rss: after.rss - before.rss,
    heapUsed: after.heapUsed - before.heapUsed,
    heapTotal: after.heapTotal - before.heapTotal,
    external: after.external - before.external,
  };
}

function printMemory(label, mem) {
  console.log(
    `  ${label.padEnd(20)} RSS: ${formatBytes(mem.rss).padStart(10)}  Heap: ${formatBytes(mem.heapUsed).padStart(10)}  External: ${formatBytes(mem.external).padStart(10)}`
  );
}

function hrMs(hrtime) {
  return (hrtime[0] * 1000 + hrtime[1] / 1e6).toFixed(1);
}

// ─── Chart column specs (same as Node-RED flow) ────────────────────────────

const NEEDED_COLUMNS = [
  "object_x", "object_y", "object_equivalent_diameter", "object_area",
  "object_MeanSaturation", "object_MeanValue", "object_width", "object_height",
  "object_MeanHue", "object_circ.", "object_perim.", "object_StdValue",
  "object_solidity", "object_elongation", "object_major", "object_minor",
  "object_eccentricity", "object_id", "object_date", "sample_id",
  "sample_project", "acq_id", "img_file_name", "process_pixel",
];

// Charts and which columns they use (simulates the 12 downstream nodes)
const CHARTS = [
  { name: "HEATMAP",    cols: ["object_x", "object_y"],                          type: "scatter" },
  { name: "ESD",        cols: ["object_equivalent_diameter"],                     type: "histogram" },
  { name: "TIMELINE",   cols: ["object_area"],                                    type: "histogram" },
  { name: "COLORSPACE", cols: ["object_MeanSaturation", "object_MeanValue"],      type: "scatter" },
  { name: "ASPECT",     cols: ["object_width", "object_height"],                  type: "scatter" },
  { name: "GREENNESS",  cols: ["object_MeanHue", "object_circ."],                 type: "scatter" },
  { name: "COMPLEXITY", cols: ["object_area", "object_perim."],                   type: "scatter" },
  { name: "TEXTURE",    cols: ["object_area", "object_StdValue"],                 type: "scatter" },
  { name: "SOLIDITY",   cols: ["object_solidity"],                                type: "histogram" },
  { name: "EXPLORER",   cols: ["object_id", "object_area", "object_width", "object_height", "object_equivalent_diameter"], type: "table" },
  { name: "GALLERY",    cols: ["object_id", "object_area", "object_width", "object_height"], type: "table" },
  { name: "METADATA",   cols: ["sample_id", "sample_project", "acq_id"],         type: "meta" },
];

// ─── OLD approach: load full file, parse per chart ──────────────────────────

function oldParseTSV(rawText) {
  const lines = rawText.trim().split(/\r?\n/);
  const headers = lines[0].split("\t");
  const val = (row, col) => {
    const idx = headers.indexOf(col);
    return idx >= 0 ? row[idx] : null;
  };

  const dataLines = lines.slice(1).filter((l) => !l.trim().startsWith("["));
  const rows = dataLines.map((l) => l.split("\t"));
  return { headers, val, rows };
}

function oldProcessChart(chart, rawText) {
  const { headers, val, rows } = oldParseTSV(rawText);
  // Simulate building chart payload (same as original Node-RED code)
  const data = rows.map((r) => {
    const obj = {};
    for (const col of chart.cols) {
      const v = val(r, col);
      obj[col] = v !== null ? parseFloat(v) || v : null;
    }
    return obj;
  });
  return data;
}

async function benchmarkOld(filePath) {
  console.log("\n══════════════════════════════════════════════════════════════");
  console.log("  OLD APPROACH: Full file load + 12x redundant parsing");
  console.log("══════════════════════════════════════════════════════════════\n");

  const memBaseline = getMemory();
  printMemory("Baseline", memBaseline);

  // Step 1: Load entire file
  const t1 = process.hrtime();
  const rawText = fs.readFileSync(filePath, "utf8");
  const t1end = process.hrtime(t1);
  const memAfterLoad = getMemory();

  console.log(`\n  Step 1: Load full file`);
  console.log(`    Time: ${hrMs(t1end)} ms`);
  console.log(`    File size: ${formatBytes(Buffer.byteLength(rawText, "utf8"))}`);
  printMemory("After load", memDelta(memBaseline, memAfterLoad));

  // Step 2: Parse 12 times (one per chart)
  const chartResults = [];
  const t2 = process.hrtime();
  for (const chart of CHARTS) {
    const tc = process.hrtime();
    const data = oldProcessChart(chart, rawText);
    const tcEnd = process.hrtime(tc);
    const payloadSize = JSON.stringify(data).length;
    chartResults.push({
      name: chart.name,
      rows: data.length,
      timeMs: hrMs(tcEnd),
      payloadSize,
    });
  }
  const t2end = process.hrtime(t2);
  const memAfterCharts = getMemory();

  console.log(`\n  Step 2: Parse & build chart payloads (12 charts)`);
  console.log(`    Total time: ${hrMs(t2end)} ms`);
  printMemory("After charts", memDelta(memBaseline, memAfterCharts));

  console.log(`\n  Per-chart breakdown:`);
  console.log(
    `    ${"Chart".padEnd(15)} ${"Rows".padStart(8)} ${"Time".padStart(10)} ${"Payload".padStart(12)}`
  );
  console.log(`    ${"─".repeat(48)}`);
  for (const r of chartResults) {
    console.log(
      `    ${r.name.padEnd(15)} ${String(r.rows).padStart(8)} ${(r.timeMs + " ms").padStart(10)} ${formatBytes(r.payloadSize).padStart(12)}`
    );
  }

  const totalPayload = chartResults.reduce((s, r) => s + r.payloadSize, 0);
  console.log(`    ${"─".repeat(48)}`);
  console.log(
    `    ${"TOTAL".padEnd(15)} ${"".padStart(8)} ${(hrMs(t2end) + " ms").padStart(10)} ${formatBytes(totalPayload).padStart(12)}`
  );

  const memPeak = getMemory();
  console.log(`\n  Peak memory:`);
  printMemory("Peak RSS", memPeak);
  printMemory("Delta from baseline", memDelta(memBaseline, memPeak));

  return {
    approach: "OLD",
    loadTimeMs: parseFloat(hrMs(t1end)),
    parseTimeMs: parseFloat(hrMs(t2end)),
    totalTimeMs: parseFloat(hrMs(t1end)) + parseFloat(hrMs(t2end)),
    peakRss: memPeak.rss,
    totalPayloadBytes: totalPayload,
    rows: chartResults[0]?.rows || 0,
  };
}

// ─── NEW approach: streaming columnar + aggregation ─────────────────────────

function newStreamParse(filePath) {
  return new Promise((resolve) => {
    const columns = {};
    NEEDED_COLUMNS.forEach((k) => (columns[k] = []));
    const colIdx = {};
    const meta = {};
    let totalRows = 0;
    let lineNum = 0;
    let remainder = "";

    const stream = fs.createReadStream(filePath, { encoding: "utf8" });

    stream.on("data", (chunk) => {
      remainder += chunk;
      const lines = remainder.split("\n");
      remainder = lines.pop();

      for (const line of lines) {
        if (!line.trim()) continue;
        lineNum++;

        if (lineNum === 1) {
          const headers = line.split("\t");
          headers.forEach((h, i) => {
            if (NEEDED_COLUMNS.includes(h)) colIdx[h] = i;
          });
          continue;
        }
        if (line.trim().startsWith("[")) continue;

        const fields = line.split("\t");
        totalRows++;

        if (totalRows === 1) {
          meta.sample_id = fields[colIdx["sample_id"]] || "";
          meta.sample_project = fields[colIdx["sample_project"]] || "";
          meta.acq_id = fields[colIdx["acq_id"]] || "";
          meta.process_pixel = fields[colIdx["process_pixel"]] || "";
        }

        for (const key of NEEDED_COLUMNS) {
          if (colIdx[key] !== undefined) {
            columns[key].push(fields[colIdx[key]]);
          }
        }
      }
    });

    stream.on("end", () => {
      if (remainder.trim() && !remainder.trim().startsWith("[") && lineNum > 0) {
        const fields = remainder.split("\t");
        totalRows++;
        for (const key of NEEDED_COLUMNS) {
          if (colIdx[key] !== undefined) {
            columns[key].push(fields[colIdx[key]]);
          }
        }
      }
      resolve({ columns, meta, totalRows });
    });

    stream.on("error", (err) => {
      console.error("Stream error:", err.message);
      resolve({ columns, meta, totalRows: 0 });
    });
  });
}

function newProcessChart(chart, columns, totalRows) {
  const MAX_POINTS = 10000;
  const MAX_TABLE_ROWS = 5000;

  if (chart.type === "meta") {
    return [{ sample_id: columns["sample_id"]?.[0] }];
  }

  if (chart.type === "table") {
    const idCol = columns["object_id"] || [];
    const n = Math.min(idCol.length, MAX_TABLE_ROWS);
    const data = [];
    for (let i = 0; i < n; i++) {
      const item = {};
      for (const col of chart.cols) {
        item[col] = (columns[col] || [])[i];
      }
      data.push(item);
    }
    // Sort by area descending
    data.sort((a, b) => parseFloat(b.object_area || 0) - parseFloat(a.object_area || 0));
    return data;
  }

  if (chart.type === "histogram") {
    const raw = columns[chart.cols[0]] || [];
    return raw.map((v) => ({ v: parseFloat(v) }));
  }

  // Scatter with reservoir sampling
  const xCol = columns[chart.cols[0]] || [];
  const yCol = columns[chart.cols[1]] || [];
  const n = xCol.length;

  if (n <= MAX_POINTS) {
    return xCol.map((x, i) => ({ x: parseFloat(x), y: parseFloat(yCol[i]) }));
  }

  const data = new Array(MAX_POINTS);
  for (let i = 0; i < MAX_POINTS; i++) {
    data[i] = { x: parseFloat(xCol[i]), y: parseFloat(yCol[i]) };
  }
  for (let i = MAX_POINTS; i < n; i++) {
    const j = Math.floor(Math.random() * (i + 1));
    if (j < MAX_POINTS) {
      data[j] = { x: parseFloat(xCol[i]), y: parseFloat(yCol[i]) };
    }
  }
  return data;
}

async function benchmarkNew(filePath) {
  console.log("\n══════════════════════════════════════════════════════════════");
  console.log("  NEW APPROACH: Streaming columnar + server-side aggregation");
  console.log("══════════════════════════════════════════════════════════════\n");

  const memBaseline = getMemory();
  printMemory("Baseline", memBaseline);

  // Step 1: Stream-parse file
  const t1 = process.hrtime();
  const { columns, meta, totalRows } = await newStreamParse(filePath);
  const t1end = process.hrtime(t1);
  const memAfterStream = getMemory();

  console.log(`\n  Step 1: Stream-parse file (${NEEDED_COLUMNS.length} columns extracted)`);
  console.log(`    Time: ${hrMs(t1end)} ms`);
  console.log(`    Rows parsed: ${totalRows}`);
  printMemory("After stream", memDelta(memBaseline, memAfterStream));

  // Step 2: Process each chart
  const chartResults = [];
  const t2 = process.hrtime();
  for (const chart of CHARTS) {
    const tc = process.hrtime();
    const data = newProcessChart(chart, columns, totalRows);
    const tcEnd = process.hrtime(tc);
    const payloadSize = JSON.stringify(data).length;
    chartResults.push({
      name: chart.name,
      rows: data.length,
      timeMs: hrMs(tcEnd),
      payloadSize,
    });
  }
  const t2end = process.hrtime(t2);
  const memAfterCharts = getMemory();

  console.log(`\n  Step 2: Build chart payloads (12 charts, with aggregation)`);
  console.log(`    Total time: ${hrMs(t2end)} ms`);
  printMemory("After charts", memDelta(memBaseline, memAfterCharts));

  console.log(`\n  Per-chart breakdown:`);
  console.log(
    `    ${"Chart".padEnd(15)} ${"Rows".padStart(8)} ${"Time".padStart(10)} ${"Payload".padStart(12)}`
  );
  console.log(`    ${"─".repeat(48)}`);
  for (const r of chartResults) {
    console.log(
      `    ${r.name.padEnd(15)} ${String(r.rows).padStart(8)} ${(r.timeMs + " ms").padStart(10)} ${formatBytes(r.payloadSize).padStart(12)}`
    );
  }

  const totalPayload = chartResults.reduce((s, r) => s + r.payloadSize, 0);
  console.log(`    ${"─".repeat(48)}`);
  console.log(
    `    ${"TOTAL".padEnd(15)} ${"".padStart(8)} ${(hrMs(t2end) + " ms").padStart(10)} ${formatBytes(totalPayload).padStart(12)}`
  );

  const memPeak = getMemory();
  console.log(`\n  Peak memory:`);
  printMemory("Peak RSS", memPeak);
  printMemory("Delta from baseline", memDelta(memBaseline, memPeak));

  return {
    approach: "NEW",
    loadTimeMs: parseFloat(hrMs(t1end)),
    parseTimeMs: parseFloat(hrMs(t2end)),
    totalTimeMs: parseFloat(hrMs(t1end)) + parseFloat(hrMs(t2end)),
    peakRss: memPeak.rss,
    totalPayloadBytes: totalPayload,
    rows: totalRows,
  };
}

// ─── Comparison summary ─────────────────────────────────────────────────────

function printComparison(oldResult, newResult) {
  console.log("\n══════════════════════════════════════════════════════════════");
  console.log("  COMPARISON SUMMARY");
  console.log("══════════════════════════════════════════════════════════════\n");

  const row = (label, oldVal, newVal, unit, lowerIsBetter = true) => {
    const ratio = oldVal / newVal;
    const better = lowerIsBetter ? (ratio > 1 ? "NEW" : "OLD") : ratio < 1 ? "NEW" : "OLD";
    const improvement =
      ratio > 1 ? `${ratio.toFixed(1)}x smaller` : `${(1 / ratio).toFixed(1)}x smaller`;
    console.log(
      `  ${label.padEnd(22)} OLD: ${(oldVal.toFixed(1) + " " + unit).padStart(14)}   NEW: ${(newVal.toFixed(1) + " " + unit).padStart(14)}   ${better === "NEW" ? "▼" : "▲"} ${improvement}`
    );
  };

  row("Total time", oldResult.totalTimeMs, newResult.totalTimeMs, "ms");
  row("  File load/parse", oldResult.loadTimeMs, newResult.loadTimeMs, "ms");
  row("  Chart processing", oldResult.parseTimeMs, newResult.parseTimeMs, "ms");
  row("Peak RSS", oldResult.peakRss / 1024 / 1024, newResult.peakRss / 1024 / 1024, "MB");
  row(
    "WebSocket payload",
    oldResult.totalPayloadBytes / 1024,
    newResult.totalPayloadBytes / 1024,
    "KB"
  );

  console.log(`\n  Dataset: ${oldResult.rows} rows`);
  console.log("");
}

// ─── Synthetic TSV generator ────────────────────────────────────────────────

function generateSyntheticTSV(numRows, outputPath) {
  console.log(`Generating synthetic TSV with ${numRows} rows...`);

  // Real ecotaxa header (all 80+ columns)
  const allColumns = [
    "object_segmented", "sample_project", "sample_operator", "sample_id",
    "sample_gear", "object_date", "object_time", "object_lat", "object_lon",
    "sample_net_mouth_diameter", "sample_net_length", "sample_net_mesh_size",
    "sample_filtered_volume", "sample_concentration_factor", "sample_sieve_mesh_size",
    "sample_depth", "sample_collected_volume", "acq_id", "acq_nb_frame",
    "acq_interframe_volume", "acq_imaged_volume", "acq_pumped_volume",
    "acq_comment", "acq_progression", "acq_duration_left",
    "acq_tube_lens_reference", "acq_objective_lens_reference",
    "process_pixel_size", "acq_flowcell_thickness", "acq_interframe_flowrate",
    "acq_local_datetime", "acq_camera_resolution", "acq_camera_iso",
    "acq_camera_shutter_speed", "acq_uuid", "sample_uuid",
    "process_datetime", "process_uuid", "process_id",
    "process_1st_operation", "process_2nd_operation", "process_3rd_operation",
    "process_4th_operation", "process_5th_operation", "process_6th_operation",
    "process_7th_operation", "object_label", "object_width", "object_height",
    "object_bx", "object_by", "object_circ.", "object_area_exc",
    "object_area", "object_%area", "object_major", "object_minor",
    "object_y", "object_x", "object_convex_area", "object_perim.",
    "object_elongation", "object_perimareaexc", "object_perimmajor",
    "object_circex", "object_angle", "object_bounding_box_area",
    "object_eccentricity", "object_equivalent_diameter", "object_euler_number",
    "object_extent", "object_local_centroid_col", "object_local_centroid_row",
    "object_solidity", "object_blur_laplacian", "object_MeanHue",
    "object_MeanSaturation", "object_MeanValue", "object_StdHue",
    "object_StdSaturation", "object_StdValue", "object_id",
    "img_file_name", "img_rank", "process_pixel",
  ];

  const header = allColumns.join("\t");
  // Type row (ecotaxa format)
  const typeRow = allColumns.map(() => "[f]").join("\t");

  const fd = fs.openSync(outputPath, "w");
  fs.writeSync(fd, header + "\n");
  fs.writeSync(fd, typeRow + "\n");

  const rand = (min, max) => (Math.random() * (max - min) + min).toFixed(4);
  const randInt = (min, max) => Math.floor(Math.random() * (max - min) + min);

  for (let i = 0; i < numRows; i++) {
    const values = allColumns.map((col) => {
      if (col === "sample_project") return "benchmark_project";
      if (col === "sample_id") return "benchmark_project_S_1";
      if (col === "acq_id") return "benchmark_project_S_1_A_1";
      if (col === "sample_operator") return "benchmark";
      if (col === "object_date") return "2026-03-05";
      if (col === "object_time") return "12:00:00";
      if (col === "object_id") return `obj_${String(i).padStart(6, "0")}`;
      if (col === "img_file_name") return `2026-03-05_12-00-00-000000_${i}.jpg`;
      if (col === "process_pixel") return "1.12";
      if (col === "object_x") return rand(0, 4056);
      if (col === "object_y") return rand(0, 3040);
      if (col === "object_width") return randInt(5, 500);
      if (col === "object_height") return randInt(5, 500);
      if (col === "object_area") return rand(10, 50000);
      if (col === "object_equivalent_diameter") return rand(1, 500);
      if (col === "object_perim.") return rand(5, 2000);
      if (col === "object_major") return rand(5, 500);
      if (col === "object_minor") return rand(2, 300);
      if (col === "object_circ.") return rand(0, 1);
      if (col === "object_elongation") return rand(1, 10);
      if (col === "object_solidity") return rand(0, 1);
      if (col === "object_eccentricity") return rand(0, 1);
      if (col === "object_MeanHue") return rand(0, 180);
      if (col === "object_MeanSaturation") return rand(0, 255);
      if (col === "object_MeanValue") return rand(0, 255);
      if (col === "object_StdValue") return rand(0, 100);
      if (col === "object_StdHue") return rand(0, 50);
      if (col === "object_StdSaturation") return rand(0, 50);
      if (col.startsWith("object_")) return rand(0, 100);
      return "";
    });
    fs.writeSync(fd, values.join("\t") + "\n");

    if ((i + 1) % 10000 === 0) {
      process.stdout.write(`  ${i + 1}/${numRows} rows...\r`);
    }
  }

  fs.closeSync(fd);
  const stats = fs.statSync(outputPath);
  console.log(`  Generated: ${outputPath} (${formatBytes(stats.size)}, ${numRows} rows)`);
  return outputPath;
}

// ─── Main ───────────────────────────────────────────────────────────────────

async function main() {
  const args = process.argv.slice(2);

  if (args.length === 0) {
    console.log("Usage:");
    console.log("  node visualizer_benchmark.js <tsv_file>              # benchmark both");
    console.log("  node visualizer_benchmark.js <tsv_file> --old-only   # old approach only");
    console.log("  node visualizer_benchmark.js <tsv_file> --new-only   # new approach only");
    console.log("  node visualizer_benchmark.js --generate <rows> <out> # generate test TSV");
    console.log("");
    console.log("Tip: run with --expose-gc for accurate memory measurement:");
    console.log("  node --expose-gc visualizer_benchmark.js <tsv_file>");
    process.exit(1);
  }

  // Handle --generate
  if (args[0] === "--generate") {
    const rows = parseInt(args[1]) || 50000;
    const out = args[2] || `/tmp/synthetic_${rows}.tsv`;
    generateSyntheticTSV(rows, out);
    return;
  }

  const filePath = args[0];
  const oldOnly = args.includes("--old-only");
  const newOnly = args.includes("--new-only");

  if (!fs.existsSync(filePath)) {
    console.error(`File not found: ${filePath}`);
    process.exit(1);
  }

  const stats = fs.statSync(filePath);
  console.log("╔══════════════════════════════════════════════════════════════╗");
  console.log("║       PlanktoScope Visualizer Benchmark                     ║");
  console.log("╚══════════════════════════════════════════════════════════════╝");
  console.log(`\n  File: ${filePath}`);
  console.log(`  Size: ${formatBytes(stats.size)}`);
  if (!global.gc) {
    console.log(`  Note: Run with 'node --expose-gc' for more accurate memory stats`);
  }

  let oldResult, newResult;

  if (!newOnly) {
    oldResult = await benchmarkOld(filePath);
  }

  // Force GC between runs to get clean baseline
  if (global.gc) global.gc();

  if (!oldOnly) {
    newResult = await benchmarkNew(filePath);
  }

  if (oldResult && newResult) {
    printComparison(oldResult, newResult);
  }
}

main().catch(console.error);
