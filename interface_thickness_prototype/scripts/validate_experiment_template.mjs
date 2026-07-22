import fs from "node:fs";
import { Workbook } from "@oai/artifact-tool";

const path = process.argv[2] ?? "interface_thickness_prototype/results/experiment_data_template.csv";
const csv = fs.readFileSync(path, "utf8");
const workbook = await Workbook.fromCSV(csv, { sheetName: "experiment_data" });
const inspection = await workbook.inspect({
  kind: "table",
  range: "experiment_data!A1:K3",
  include: "values",
  tableMaxRows: 3,
  tableMaxCols: 11,
});
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 20 },
  summary: "final formula error scan",
});
process.stdout.write(`${JSON.stringify({ inspection, errors }, null, 2)}\n`);
