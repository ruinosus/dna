// Finds the agents in a folder as the VS Code extension clones them: a folder with agent.mcs.yml (or .yaml) at its top
// is an agent, and everything under it is its files (a child agent in agents/<Name>/ stays inside its parent). Hidden
// files and folders (.mcs/ holds the environment's ids) are never read.
import { readdirSync, readFileSync } from 'node:fs'
import { basename, join } from 'node:path'

export interface AgentFolder { id: string; dir: string; files: { path: string; text: string }[] }

const AGENT = /^agent\.mcs\.ya?ml$/
const YAML = /\.ya?ml$/
// a flow's definition, in the folder the extension clones it to
const FLOW = /(^|\/)workflows\/.+\.json$/

const visible = (dir: string) => readdirSync(dir, { withFileTypes: true }).filter((e) => !e.name.startsWith('.') && e.name !== 'node_modules')

function filesOf(dir: string, at = ''): AgentFolder['files'] {
  return visible(dir).flatMap((e) => {
    const path = at ? `${at}/${e.name}` : e.name
    if (e.isDirectory()) return filesOf(join(dir, e.name), path)
    // only YAML and a flow's JSON are read; any other file is kept by name, for «what the analysis did not understand»
    return e.isFile() ? [{ path, text: YAML.test(e.name) || FLOW.test(path) ? readFileSync(join(dir, e.name), 'utf8') : '' }] : []
  })
}

export function agentsIn(root: string): AgentFolder[] {
  const entries = visible(root)
  if (entries.some((e) => e.isFile() && AGENT.test(e.name))) return [{ id: basename(root), dir: root, files: filesOf(root) }]
  return entries.filter((e) => e.isDirectory()).flatMap((e) => agentsIn(join(root, e.name)))
}
