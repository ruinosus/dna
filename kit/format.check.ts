// The kit's format reader: the line of a path, the nearest part of it in the file, a syntax error and a file of
// another format. Run by tools/check.mjs.
import assert from 'node:assert/strict'
import { readFormat, upgradeHeader } from './format'

const text = 'format: shop/v1\nname: Corner shop\nitems:\n  - id: tea\n    price: 3\n  - id: cake\n'
const r = readFormat(text, 'shop/v1')
assert.ok(r.ok)
if (r.ok) {
  assert.equal(r.format.raw.name, 'Corner shop')
  assert.equal(r.format.at(['name']), 2)
  assert.equal(r.format.at(['items', 1]), 6)
  assert.equal(r.format.at(['items', 1, 'price']), 6, 'a path not in the file says where its nearest part is')
  assert.equal(r.format.at(['nowhere']), 1)
  assert.equal(r.format.lineOf(text.indexOf('cake')), 6)
}
const syntax = readFormat('format: shop/v1\nname: x\n  bad: indent\n', 'shop/v1')
assert.ok(!syntax.ok && syntax.problem.key === 'syntax' && syntax.problem.line === 2)
const other = readFormat('format: other/v1\nname: x\n', 'shop/v1')
assert.ok(!other.ok && other.problem.key === 'format' && other.problem.line === 1)
const list = readFormat('- a\n- b\n', 'shop/v1')
assert.ok(!list.ok && list.problem.key === 'format')
console.log('kit format checks ok')

// DNA's header: the same raw as the format line of before, the name found in metadata, another kind or owner refused at
// the apiVersion line; and the old header rewritten as DNA's, keeping the comments and the rest
{
  const dna = '# a shop\napiVersion: github.com/ruinosus/dna/v1\nkind: Shop\nmetadata:\n  name: Corner shop\nitems:\n  - id: tea\n'
  const d = readFormat(dna, 'shop/v1', 'Shop')
  assert.ok(d.ok)
  if (d.ok) {
    assert.deepEqual(d.format.raw, { format: 'shop/v1', name: 'Corner shop', items: [{ id: 'tea' }] })
    assert.equal(d.format.header, 'dna')
    assert.equal(d.format.at(['name']), 5)
    assert.equal(d.format.at(['format']), 2)
  }
  const wrongKind = readFormat(dna.replace('kind: Shop', 'kind: Market'), 'shop/v1', 'Shop')
  assert.ok(!wrongKind.ok && wrongKind.problem.key === 'format' && wrongKind.problem.line === 2)
  assert.ok(!readFormat(dna.replace('ruinosus/dna', 'example/x'), 'shop/v1', 'Shop').ok)
  assert.ok(!readFormat(dna, 'shop/v1').ok, 'a reader that names no kind reads no DNA file')
  const old = '# a shop\nformat: shop/v1   # the old line\nname: Corner shop\nitems:\n  - id: tea\n'
  const up = upgradeHeader(old, 'shop/v1', 'Shop')!
  assert.equal(up, '# a shop\napiVersion: github.com/ruinosus/dna/v1\nkind: Shop\nmetadata:\n  name: Corner shop\nitems:\n  - id: tea\n')
  const again = readFormat(up, 'shop/v1', 'Shop')
  const before = readFormat(old, 'shop/v1')
  assert.ok(again.ok && before.ok && JSON.stringify(again.format.raw) === JSON.stringify(before.format.raw), 'the upgraded file reads the same')
  assert.equal(upgradeHeader(up, 'shop/v1', 'Shop'), undefined, 'already DNA: nothing to do')
  assert.equal(upgradeHeader('format: other/v1\n', 'shop/v1', 'Shop'), undefined)
}
console.log('kit DNA header checks ok')
