// What can be wrong in a profile or a cast file, each with its line, and the sentence that says it.

export type Problem =
  | { line: number; key: 'syntax'; detail: string }
  | { line: number; key: 'format'; format: string }
  | { line: number; key: 'missing'; what: string }
  | { line: number; key: 'duplicate'; what: string; id: string }
  | { line: number; key: 'unknownKey'; what: string }
  | { line: number; key: 'threshold'; value: string }
  | { line: number; key: 'minAgents'; value: string }
  | { line: number; key: 'role'; what: string; value: string }
  | { line: number; key: 'status'; value: string }
  | { line: number; key: 'scope'; value: string }
  | { line: number; key: 'regex'; what: string; detail: string }
  | { line: number; key: 'in'; what: string; value: string }
  | { line: number; key: 'when'; what: string }
  | { line: number; key: 'prefix'; what: string; value: string }
  | { line: number; key: 'rule'; what: string }

export function problemText(p: Problem, lang: 'en' | 'pt' = 'en'): string {
  const pt = lang === 'pt'
  switch (p.key) {
    case 'syntax': return pt ? `não se lê como YAML (${p.detail})` : `does not read as YAML (${p.detail})`
    case 'format': return pt ? `«format» precisa ser ${p.format}` : `«format» must be ${p.format}`
    case 'missing': return pt ? `falta «${p.what}»` : `«${p.what}» is missing`
    case 'duplicate': return pt ? `${p.what}: o id «${p.id}» se repete` : `${p.what}: the id «${p.id}» is repeated`
    case 'unknownKey': return pt ? `«${p.what}» não é um campo deste arquivo` : `«${p.what}» is not a field of this file`
    case 'threshold': return pt ? `«threshold» vai de 0 a 1, como 0.7 (está «${p.value}»)` : `«threshold» goes from 0 to 1, like 0.7 (it is «${p.value}»)`
    case 'minAgents': return pt ? `«min_agents» é um número inteiro a partir de 1 (está «${p.value}»)` : `«min_agents» is a whole number from 1 (it is «${p.value}»)`
    case 'role': return pt ? `«${p.what}» é orchestrator ou specialist (está «${p.value}»)` : `«${p.what}» is orchestrator or specialist (it is «${p.value}»)`
    case 'status': return pt ? `«status» é accepted ou rejected (está «${p.value}»)` : `«status» is accepted or rejected (it is «${p.value}»)`
    case 'scope': return pt ? `«scope» é platform, specialist, orchestrator ou type:<tipo> (está «${p.value}»)` : `«scope» is platform, specialist, orchestrator or type:<type> (it is «${p.value}»)`
    case 'regex': return pt ? `«${p.what}» não é uma expressão regular válida (${p.detail})` : `«${p.what}» is not a valid regular expression (${p.detail})`
    case 'in': return pt ? `«${p.what}» é instructions, descriptions ou all (está «${p.value}»)` : `«${p.what}» is instructions, descriptions or all (it is «${p.value}»)`
    case 'when': return pt ? `«${p.what}» precisa de «when» com all, any ou none` : `«${p.what}» needs a «when» with all, any or none`
    case 'prefix': return pt ? `«${p.what}»: nenhuma chave começa como «${p.value}» (veja references/keys.md)` : `«${p.what}»: no key starts like «${p.value}» (see references/keys.md)`
    case 'rule': return pt ? `«${p.what}» precisa de «has» ou «not»: o que conferir` : `«${p.what}» needs «has» or «not»: what to check`
  }
}
