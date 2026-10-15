import { createRequire } from "node:module";
import { readFileSync } from "node:fs";

const require = createRequire(import.meta.url);
const ELK = require("elkjs");

const raw = readFileSync(0, "utf8");
const graph = JSON.parse(raw);
const elk = new ELK();
const laid = await elk.layout(graph);
process.stdout.write(JSON.stringify(laid));
