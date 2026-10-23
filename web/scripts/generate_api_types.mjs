import { execFileSync } from 'node:child_process'
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import openapiTS, { astToString } from 'openapi-typescript'
import ts from 'typescript'

const root = resolve(fileURLToPath(new URL('../..', import.meta.url)))
const output = resolve(root, 'web/infra/openapi.d.ts')
const schemaPath = process.argv.indexOf('--schema')
const raw = schemaPath < 0
  ? execFileSync(process.env.LIGHTNING_PYTHON ?? resolve(root, '.venv/bin/python'), ['-m', 'scripts.export_openapi'], { cwd: root, encoding: 'utf8' })
  : readFileSync(process.argv[schemaPath + 1], 'utf8')
const ast = await openapiTS(JSON.parse(raw), {
  transform(schema) {
    if (schema.format === 'binary') return ts.factory.createTypeReferenceNode('Blob')
  },
})
const generated = astToString(ast)
if (process.argv.includes('--check')) {
  if (readFileSync(output, 'utf8') !== generated) {
    console.error('OpenAPI 已变化，请运行 npm run generate:api --prefix web 更新 TypeScript 类型')
    process.exit(1)
  }
} else {
  writeFileSync(output, generated)
}
