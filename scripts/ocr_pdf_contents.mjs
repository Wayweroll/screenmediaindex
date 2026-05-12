#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..");
const outDir = path.join(root, "outputs", "ocr_text");
const nodeModulesDir =
  process.env.NODE_MODULES_DIR || "/Users/nickocher/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules";
const require = createRequire(path.join(nodeModulesDir, "package.json"));
const { createCanvas } = require("@napi-rs/canvas");
const { createWorker } = require("tesseract.js");
const pdfjsPath = path.join(
  nodeModulesDir,
  "pdfjs-dist",
  "legacy",
  "build",
  "pdf.mjs",
);
const pdfjsLib = await import(pathToFileURL(pdfjsPath));

class NodeCanvasFactory {
  create(width, height) {
    const canvas = createCanvas(width, height);
    const context = canvas.getContext("2d");
    return { canvas, context };
  }

  reset(canvasAndContext, width, height) {
    canvasAndContext.canvas.width = width;
    canvasAndContext.canvas.height = height;
  }

  destroy(canvasAndContext) {
    canvasAndContext.canvas.width = 0;
    canvasAndContext.canvas.height = 0;
    canvasAndContext.canvas = null;
    canvasAndContext.context = null;
  }
}

async function renderPageToPng(pdf, pageNumber, scale = 2.5) {
  const page = await pdf.getPage(pageNumber);
  const viewport = page.getViewport({ scale });
  const canvasFactory = new NodeCanvasFactory();
  const canvasAndContext = canvasFactory.create(viewport.width, viewport.height);
  await page.render({
    canvasContext: canvasAndContext.context,
    viewport,
    canvasFactory,
  }).promise;
  const png = canvasAndContext.canvas.toBuffer("image/png");
  canvasFactory.destroy(canvasAndContext);
  return png;
}

async function main() {
  const pdfs = process.argv.slice(2);
  if (!pdfs.length) {
    console.error("Usage: ocr_pdf_contents.mjs <pdf> [pdf...]");
    process.exit(2);
  }

  await fs.mkdir(outDir, { recursive: true });
  const worker = await createWorker("eng");

  for (const pdfPath of pdfs) {
    const absolute = path.resolve(root, pdfPath);
    const data = new Uint8Array(await fs.readFile(absolute));
    const pdf = await pdfjsLib.getDocument({
      data,
      canvasFactory: new NodeCanvasFactory(),
      disableFontFace: true,
      useSystemFonts: true,
    }).promise;
    const pageLimit = Math.min(pdf.numPages, 6);
    const chunks = [];
    console.log(`OCR ${pdfPath} (${pageLimit} pages)`);
    for (let pageNumber = 1; pageNumber <= pageLimit; pageNumber += 1) {
      const png = await renderPageToPng(pdf, pageNumber);
      const result = await worker.recognize(png);
      chunks.push(`[[PDF_PAGE ${pageNumber}]]\n${result.data.text}`);
    }
    const safeName = pdfPath.replaceAll("/", "__").replace(/\.pdf$/i, ".txt");
    await fs.writeFile(path.join(outDir, safeName), chunks.join("\n\n"), "utf8");
  }

  await worker.terminate();
}

await main();
