// The kit's format reader: the line of a path, the nearest part of it in the file, a syntax error and a file of
// another format. Run by tools/check.mjs.
import assert from 'node:assert/strict'
import { readFormat } from './format'

const text = 'format: shop/v1\nname: Corner shop\nitems:\n  - id: tea\n    price: 3\n  - id: cake\n'
const r = readFormat(text, 'shop/v1')
assert.ok(r.ok)
if (r.ok) {
  assert.equal(r.format.raw.name, 'Corner shop')
  assert.equal(r.format.at(['name']), 2)
  assert.equal(r.format.at(['items', 1]), 6)
  assert.equal(r.format.at(['items', 1, 'price']), 6, 'a path not in the file says where its nearest part is')
  assert.equal(r.format.at(['nowhere']), 1)
}
const syntax = readFormat('format: shop/v1\nname: x\n  bad: indent\n', 'shop/v1')
assert.ok(!syntax.ok && syntax.problem.key === 'syntax' && syntax.problem.line === 2)
const other = readFormat('format: other/v1\nname: x\n', 'shop/v1')
assert.ok(!other.ok && other.problem.key === 'format' && other.problem.line === 1)
const list = readFormat('- a\n- b\n', 'shop/v1')
assert.ok(!list.ok && list.problem.key === 'format')
console.log('kit format checks ok')
