import fs from "node:fs";
import path from "node:path";
import { Workbook } from "@oai/artifact-tool";

const root = process.argv[2] ?? "interface_thickness_prototype";
const outputPath =
  process.argv[3] ??
  path.join(root, "results", "csv_artifact_validation.json");
const targets = [
  "final_model_status.csv",
  "coverage_model_summary.csv",
  "kpoint_reference_check.csv",
  "relative_coverage_formation_energy.csv",
  "dft_proxy_summary.csv",
];

const reports = [];
for (const fileName of targets) {
  const filePath = path.join(root, "results", fileName);
  const csv = fs.readFileSync(filePath, "utf8");
  const sheetName = path.basename(fileName, ".csv").slice(0, 31);
  const workbook = await Workbook.fromCSV(csv, { sheetName });
  const inspection = await workbook.inspect({
    kind: "table",
    range: `${sheetName}!A1:Z12`,
    include: "values",
    tableMaxRows: 12,
    tableMaxCols: 26,
  });
  const errors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
    options: { useRegex: true, maxResults: 20 },
    summary: `${fileName} formula/error scan`,
  });
  reports.push({
    file: fileName,
    loaded: true,
    inspection,
    formula_or_cell_errors: errors,
  });
}

const report = {
  validator: "@oai/artifact-tool Workbook.fromCSV + inspect",
  all_loaded: reports.every((item) => item.loaded),
  files: reports,
};
fs.writeFileSync(outputPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
process.stdout.write(
  `${JSON.stringify({
    output: outputPath,
    all_loaded: report.all_loaded,
    files: reports.map((item) => item.file),
  }, null, 2)}\n`,
);
