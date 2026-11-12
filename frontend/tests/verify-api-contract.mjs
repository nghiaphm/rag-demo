import assert from "node:assert/strict";
import fs from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";

// Offline schema parity check. No lifespan, cloud clients, provider calls or installs.
const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const root = path.dirname(frontend);
const python = process.env.PYTHON || (fs.existsSync(path.join(root, ".venv", "Scripts", "python.exe"))
  ? path.join(root, ".venv", "Scripts", "python.exe")
  : (fs.existsSync(path.join(root, ".venv", "bin", "python"))
      ? path.join(root, ".venv", "bin", "python")
      : "python"));
const exported = spawnSync(python, ["-c", String.raw`
import json, socket, sys
from types import SimpleNamespace
sys.path.insert(0, 'backend')
def blocked(*args, **kwargs):
    raise RuntimeError('F1-01: network disabled')
socket.socket.connect = blocked
socket.socket.connect_ex = blocked
socket.create_connection = blocked
from app.main import app, health, dependency_health
import app.main as main
from app.infrastructure.status import ConnectionStatus
from app.api.streaming.sse_schema import SSEStartEvent, SSEMetadataEvent, SSECitationEvent, SSEDeltaEvent, SSEDoneEvent, SSEErrorEvent
from pydantic import TypeAdapter
spec = app.openapi()
schemas = spec['components']['schemas'].copy()
for cls in (SSEStartEvent, SSEMetadataEvent, SSECitationEvent, SSEDeltaEvent, SSEDoneEvent, SSEErrorEvent):
    schema = cls.model_json_schema(mode='serialization')
    schemas.update(schema.pop('$defs', {}))
    # The event: wire line and serialized done.status are always present.
    schema['required'] = list(schema.get('properties', {}))
    schemas[cls.__name__] = schema
schemas['SSEDoneData']['required'] = ['sequence', 'status', 'usage']
schemas['ConnectionStatus'] = TypeAdapter(ConnectionStatus).json_schema()
assert set(health()) == {'status', 'llm_model'} and health()['status'] == 'ok'
schemas['HealthResponse'] = {'type': 'object', 'properties': {'status': {'const': 'ok'}, 'llm_model': {'type': 'string'}}, 'required': ['status', 'llm_model']}
# Invoke the real handler with deterministic dependency/threadpool fixtures.
# This also avoids Windows event-loop self-pipe sockets under the network guard.
async def inline_threadpool(function):
    return function()
main.run_in_threadpool = inline_threadpool
for healthy in (True, False):
    statuses = {name: ConnectionStatus(name, healthy, 'fixture', 'fixture') for name in ('mongodb', 'qdrant')}
    app.state.cloud_connections = SimpleNamespace(connect_all=lambda: statuses)
    coroutine = dependency_health()
    try:
        coroutine.send(None)
        raise AssertionError('Unexpected asynchronous I/O in fixture handler')
    except StopIteration as finished:
        response = finished.value
    body = json.loads(response.body)
    assert response.status_code == (200 if healthy else 503)
    assert body['status'] == ('ok' if healthy else 'degraded')
    assert set(body) == {'status', 'dependencies'}
    assert body['dependencies'] == {name: value.to_dict() for name, value in statuses.items()}
schemas['DependencyHealthResponse'] = {'type': 'object', 'required': ['status', 'dependencies'], 'properties': {'status': {'enum': ['ok', 'degraded']}, 'dependencies': {'type': 'object', 'required': ['mongodb', 'qdrant'], 'properties': {name: {'$ref': '#/$defs/ConnectionStatus'} for name in ('mongodb', 'qdrant')}}}}
print(json.dumps({'schemas': schemas, 'paths': spec['paths']}))
`], { cwd: root, encoding: "utf8", maxBuffer: 5 * 1024 * 1024 });
assert.equal(exported.status, 0, "Offline Python schema export failed (no provider requests permitted)");
const { schemas, paths } = JSON.parse(exported.stdout);

function typeOf(schema) {
  if (schema.$ref) return `Expected_${schema.$ref.split("/").at(-1)}`;
  if ("const" in schema) return JSON.stringify(schema.const);
  if (schema.enum) return schema.enum.map(value => JSON.stringify(value)).join(" | ");
  if (schema.anyOf) return schema.anyOf.map(typeOf).join(" | ");
  if (schema.type === "null") return "null";
  if (schema.type === "string") return schema.format === "binary" || schema.contentMediaType === "application/octet-stream" ? "File" : "string";
  if (schema.type === "integer" || schema.type === "number") return "number";
  if (schema.type === "boolean") return "boolean";
  if (schema.type === "array") return `(${typeOf(schema.items)})[]`;
  if (schema.type === "object") {
    if (!schema.properties) return "Record<string, unknown>";
    const required = new Set(schema.required ?? []);
    return `{ ${Object.entries(schema.properties).map(([key, value]) =>
      `${JSON.stringify(key)}${required.has(key) ? "" : "?"}: ${typeOf(value)};`
    ).join(" ")} }`;
  }
  return "unknown";
}

const imports = ["api", "chat", "sessions", "document"];
const sourceFiles = imports.map(name => path.join(frontend, "types", `${name}.ts`));
const exportedNames = new Set();
for (const filename of sourceFiles) {
  const source = ts.createSourceFile(filename, ts.sys.readFile(filename), ts.ScriptTarget.Latest, true);
  for (const statement of source.statements) {
    if ((ts.isInterfaceDeclaration(statement) || ts.isTypeAliasDeclaration(statement)) &&
        statement.modifiers?.some(modifier => modifier.kind === ts.SyntaxKind.ExportKeyword)) {
      exportedNames.add(statement.name.text);
    }
  }
}
const names = Object.keys(schemas).filter(name => !name.startsWith("Body_"));
for (const name of names) assert(exportedNames.has(name), `Missing DTO export: ${name}`);
const checks = [];
for (const name of names) {
  checks.push(`type Expected_${name} = ${typeOf(schemas[name])};`);
  checks.push(`type Check_${name} = Assert<BothWays<${name}, Expected_${name}>>;`);
  if (schemas[name].properties) {
    checks.push(`type Keys_${name} = Assert<BothWays<keyof ${name}, keyof Expected_${name}>>;`);
  }
}

// Query DTOs and multipart/list response shapes are sourced from actual operations.
for (const [dto, route] of [
  ["ListSessionsQuery", "/sessions"],
  ["ListMessagesQuery", "/sessions/{session_id}/messages"],
  ["ListDocumentsQuery", "/documents"],
]) {
  const parameters = paths[route].get.parameters.filter(parameter => parameter.in === "query");
  const schema = { type: "object", properties: Object.fromEntries(parameters.map(parameter => [parameter.name, parameter.schema])), required: parameters.filter(parameter => parameter.required).map(parameter => parameter.name) };
  checks.push(`type Check_${dto} = Assert<BothWays<${dto}, ${typeOf(schema)}>>;`);
  checks.push(`type Keys_${dto} = Assert<BothWays<keyof ${dto}, keyof ${typeOf(schema)}>>;`);
}
const uploadRef = paths["/documents/upload"].post.requestBody.content["multipart/form-data"].schema.$ref;
const updateRef = paths["/documents/{document_id}"].put.requestBody.content["multipart/form-data"].schema.$ref;
assert.deepEqual(schemas[uploadRef.split("/").at(-1)].properties, schemas[updateRef.split("/").at(-1)].properties);
checks.push(`type Check_upload = Assert<BothWays<DocumentUploadRequest, ${typeOf(schemas[uploadRef.split("/").at(-1)])}>>;`);
checks.push(`type Check_document_list = Assert<BothWays<DocumentListResponse, ${typeOf(paths["/documents"].get.responses[200].content["application/json"].schema)}>>;`);
checks.push(`type Check_sse_union = Assert<BothWays<SSEEvent, SSEStartEvent | SSEMetadataEvent | SSECitationEvent | SSEDeltaEvent | SSEDoneEvent | SSEErrorEvent>>;`);
checks.push(`type Check_discriminator = Assert<BothWays<SSEEvent['event'], 'start' | 'metadata' | 'citation' | 'delta' | 'done' | 'error'>>;`);
checks.push(`type Check_required_nullable = Assert<BothWays<MessageResponse['model'], string | null>>;`);
checks.push(`type Check_optional_nullable = Assert<BothWays<Citation['page'], number | null | undefined>>;`);
checks.push(`type Check_no_history_sources = Assert<BothWays<Extract<keyof MessageResponse, 'sources' | 'ordinal'>, never>>;`);

const virtualPath = path.join(frontend, "tests", "__contract_check__.ts");
const virtualSource = imports.map(name => `import type * as ${name} from '../types/${name}';`).join("\n") +
  [...exportedNames].filter(name => !["PaginatedResponse"].includes(name)).map(name => {
    const dtoModule = imports.find(moduleName => new RegExp(`export (?:interface|type) ${name}\\b`).test(ts.sys.readFile(path.join(frontend, "types", `${moduleName}.ts`))));
    return `type ${name} = ${dtoModule}.${name};`;
  }).join("\n") + `
type Assert<T extends true> = T;
type BothWays<A, B> = [A] extends [B] ? ([B] extends [A] ? true : false) : false;
${checks.join("\n")}
function narrow(event: SSEEvent): string | null {
  switch (event.event) {
    case 'start': return event.data.request_id;
    case 'metadata': return event.data.model;
    case 'citation': return event.data.citation.chunk_id;
    case 'delta': return event.data.content;
    case 'done': return event.data.status;
    case 'error': return event.data.error.code;
    default: { const exhaustive: never = event; return exhaustive; }
  }
}
// @ts-expect-error question is required
const missingQuestion: ChatRequest = {session_id: null};
// @ts-expect-error done cannot carry a failure status
const invalidDone: SSEDoneData = {sequence: 3, status: 'FAILED', usage: null};
// @ts-expect-error nullable model is required, not optional
const missingModel: ChatResponseMetadata = {mode: 'STATELESS'};
// @ts-expect-error SSE event discriminator and payload must agree
const mismatchedDelta: SSEEvent = {event: 'delta', data: {sequence: 3, status: 'COMPLETED', usage: null}};
`;
const options = { strict: true, noEmit: true, skipLibCheck: true, target: ts.ScriptTarget.ES2017, module: ts.ModuleKind.ESNext, moduleResolution: ts.ModuleResolutionKind.Bundler, lib: ["lib.esnext.d.ts", "lib.dom.d.ts"] };
const host = ts.createCompilerHost(options);
const originalGetSourceFile = host.getSourceFile.bind(host);
host.getSourceFile = (filename, languageVersion, ...rest) => path.resolve(filename) === virtualPath
  ? ts.createSourceFile(filename, virtualSource, languageVersion, true)
  : originalGetSourceFile(filename, languageVersion, ...rest);
const program = ts.createProgram([virtualPath, ...sourceFiles], options, host);
const diagnostics = ts.getPreEmitDiagnostics(program);
if (diagnostics.length) {
  console.error(ts.formatDiagnosticsWithColorAndContext(diagnostics, {
    getCanonicalFileName: filename => filename,
    getCurrentDirectory: () => frontend,
    getNewLine: () => "\n",
  }));
  process.exitCode = 1;
} else {
  console.log(`PASS: ${names.length} REST/SSE/health schemas; queries, multipart, document list, SSE narrowing, nullable/optional/history checks; network disabled.`);
}
