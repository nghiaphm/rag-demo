import assert from "node:assert/strict";
import fs from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const cache = new Map();
function load(relative) {
  if (cache.has(relative)) return cache.get(relative);
  const exports = {};
  cache.set(relative, exports);
  const file = fileURLToPath(new URL(`../${relative}.ts`, import.meta.url));
  const output = ts.transpileModule(fs.readFileSync(file, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  new Function("exports", "require", output)(exports, specifier => load(specifier.slice(2)));
  return exports;
}

const { HR_ANALYTICS_FIXTURE } = load("fixtures/hr-analytics");
const { HR_GUIDE_SECTIONS, HR_PROMPT_TEMPLATES } = load("fixtures/hr-guide");
const {
  summarizeDepartmentShares,
  summarizeContractStatuses,
  summarizeKnowledgeBaseDocuments,
} = load("lib/hr/analytics");
const {
  classifyHrDocument,
  countDocumentsByCategory,
  filterHrDocuments,
} = load("lib/hr/document-categories");

test("HR analytics helpers summarize department shares, contracts, and real DocumentInfo stats", () => {
  const deptShares = summarizeDepartmentShares(HR_ANALYTICS_FIXTURE.departments);
  assert.equal(deptShares.length, 6);
  assert.equal(deptShares[0].barWidthPercent, 100);
  const totalDept = deptShares.reduce((sum, item) => sum + item.count, 0);
  assert.equal(totalDept, HR_ANALYTICS_FIXTURE.totalEmployees);

  const contractShares = summarizeContractStatuses(HR_ANALYTICS_FIXTURE.contractStatuses);
  const totalContracts = contractShares.reduce((sum, item) => sum + item.count, 0);
  assert.equal(totalContracts, HR_ANALYTICS_FIXTURE.totalEmployees);

  const kb = summarizeKnowledgeBaseDocuments([
    {
      document_id: "1",
      file_name: "chinh-sach-nghi-phep.pdf",
      status: "INDEXED",
      chunk_count: 14,
      version_count: 1,
      cleanup_pending: false,
      created_at: "2026-11-01T00:00:00Z",
      updated_at: "2026-11-01T00:00:00Z",
    },
    {
      document_id: "2",
      file_name: "quy-trinh-onboarding.md",
      status: "PROCESSING",
      chunk_count: 0,
      version_count: 1,
      cleanup_pending: false,
      created_at: "2026-11-01T00:00:00Z",
      updated_at: "2026-11-01T00:00:00Z",
    },
    {
      document_id: "3",
      file_name: "corrupt.pdf",
      status: "FAILED",
      chunk_count: 0,
      version_count: 1,
      cleanup_pending: false,
      created_at: "2026-11-01T00:00:00Z",
      updated_at: "2026-11-01T00:00:00Z",
    },
  ]);
  assert.deepEqual(kb, {
    totalDocuments: 3,
    indexedDocuments: 1,
    processingDocuments: 1,
    failedDocuments: 1,
    totalChunks: 14,
  });
});

test("HR document category classifier and filters handle Vietnamese and English keywords deterministically", () => {
  assert.equal(classifyHrDocument("Chính sách nghỉ phép 2026.pdf"), "POLICY");
  assert.equal(classifyHrDocument("employee-leave-policy.md"), "POLICY");
  assert.equal(classifyHrDocument("Nội quy lao động & Bảo mật.pdf"), "REGULATION");
  assert.equal(classifyHrDocument("Quy trình Onboarding nhân viên.docx"), "PROCEDURE");
  assert.equal(classifyHrDocument("notes.txt"), "OTHER");

  const docs = [
    { document_id: "1", file_name: "Chính sách phúc lợi.pdf" },
    { document_id: "2", file_name: "Quy định bảo mật.md" },
    { document_id: "3", file_name: "Quy trình onboarding.xlsx" },
    { document_id: "4", file_name: "misc.txt" },
  ];
  assert.deepEqual(countDocumentsByCategory(docs), {
    ALL: 4,
    POLICY: 1,
    REGULATION: 1,
    PROCEDURE: 1,
    OTHER: 1,
  });

  assert.equal(filterHrDocuments(docs, { category: "POLICY" }).length, 1);
  assert.equal(filterHrDocuments(docs, { category: "ALL", query: "bao mat" }).length, 1);
  assert.equal(filterHrDocuments(docs, { category: "PROCEDURE", query: "khong-ton-tai" }).length, 0);
});

test("HR guide fixtures provide 4 structured guide sections and prompt templates", () => {
  assert.equal(HR_GUIDE_SECTIONS.length, 4);
  assert(HR_PROMPT_TEMPLATES.length >= 6);
  for (const item of HR_PROMPT_TEMPLATES) {
    assert.ok(item.prompt.length > 10);
  }
});
