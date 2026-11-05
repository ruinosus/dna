// The Porter stemmer (M.F. Porter, 1980), as SQLite FTS5's «porter» tokenizer applies it after unicode61: words of
// fewer than 3 letters, longer than 64, or with anything but a–z are left as they are.
const isCons = (w, i) => {
  const c = w[i]
  if ('aeiou'.includes(c)) return false
  if (c === 'y') return i === 0 ? true : !isCons(w, i - 1)
  return true
}

/** m(): the number of VC sequences in w[0..j]. */
function measure(w, j) {
  let n = 0
  let i = 0
  while (i <= j && isCons(w, i)) i++
  while (i <= j) {
    while (i <= j && !isCons(w, i)) i++
    if (i > j) break
    n++
    while (i <= j && isCons(w, i)) i++
  }
  return n
}

const hasVowel = (w, j) => {
  for (let i = 0; i <= j; i++) if (!isCons(w, i)) return true
  return false
}
const doubleCons = (w, j) => j >= 1 && w[j] === w[j - 1] && isCons(w, j)
const cvc = (w, j) => j >= 2 && isCons(w, j) && !isCons(w, j - 1) && isCons(w, j - 2) && !'wxy'.includes(w[j])

/** If w ends with `s` and the stem before it has m() > `m`, replace it with `r`. */
function swap(w, s, r, m) {
  if (!w.endsWith(s)) return null
  const stem = w.slice(0, w.length - s.length)
  return measure(stem, stem.length - 1) > m ? stem + r : w
}

const STEP2 = [
  ['ational', 'ate'], ['tional', 'tion'], ['enci', 'ence'], ['anci', 'ance'], ['izer', 'ize'], ['bli', 'ble'],
  ['alli', 'al'], ['entli', 'ent'], ['eli', 'e'], ['ousli', 'ous'], ['ization', 'ize'], ['ation', 'ate'],
  ['ator', 'ate'], ['alism', 'al'], ['iveness', 'ive'], ['fulness', 'ful'], ['ousness', 'ous'], ['aliti', 'al'],
  ['iviti', 'ive'], ['biliti', 'ble'], ['logi', 'log'],
]
const STEP3 = [['icate', 'ic'], ['ative', ''], ['alize', 'al'], ['iciti', 'ic'], ['ical', 'ic'], ['ful', ''], ['ness', '']]
const STEP4 = ['al', 'ance', 'ence', 'er', 'ic', 'able', 'ible', 'ant', 'ement', 'ment', 'ent', 'ion', 'ou', 'ism', 'ate', 'iti', 'ous', 'ive', 'ize']

export function stem(word) {
  if (word.length < 3 || word.length > 64 || !/^[a-z]+$/.test(word)) return word
  let w = word
  // step 1a
  if (w.endsWith('sses')) w = w.slice(0, -2)
  else if (w.endsWith('ies')) w = w.slice(0, -2)
  else if (w.endsWith('ss')) {
    // stays
  } else if (w.endsWith('s')) w = w.slice(0, -1)
  // step 1b
  let again = false
  if (w.endsWith('eed')) {
    if (measure(w, w.length - 4) > 0) w = w.slice(0, -1)
  } else if (w.endsWith('ed') && hasVowel(w, w.length - 3)) {
    w = w.slice(0, -2)
    again = true
  } else if (w.endsWith('ing') && hasVowel(w, w.length - 4)) {
    w = w.slice(0, -3)
    again = true
  }
  if (again) {
    if (w.endsWith('at') || w.endsWith('bl') || w.endsWith('iz')) w += 'e'
    else if (doubleCons(w, w.length - 1) && !'lsz'.includes(w[w.length - 1])) w = w.slice(0, -1)
    else if (measure(w, w.length - 1) === 1 && cvc(w, w.length - 1)) w += 'e'
  }
  // step 1c
  if (w.endsWith('y') && hasVowel(w, w.length - 2)) w = w.slice(0, -1) + 'i'
  // step 2
  for (const [s, r] of STEP2) {
    if (w.endsWith(s)) {
      w = swap(w, s, r, 0)
      break
    }
  }
  // step 3
  for (const [s, r] of STEP3) {
    if (w.endsWith(s)) {
      w = swap(w, s, r, 0)
      break
    }
  }
  // step 4
  for (const s of STEP4) {
    if (!w.endsWith(s)) continue
    const st = w.slice(0, w.length - s.length)
    if (measure(st, st.length - 1) > 1 && (s !== 'ion' || /[st]$/.test(st))) w = st
    break
  }
  // step 5a
  if (w.endsWith('e')) {
    const st = w.slice(0, -1)
    const m = measure(st, st.length - 1)
    if (m > 1 || (m === 1 && !cvc(st, st.length - 1))) w = st
  }
  // step 5b
  if (measure(w, w.length - 1) > 1 && doubleCons(w, w.length - 1) && w.endsWith('l')) w = w.slice(0, -1)
  return w
}
