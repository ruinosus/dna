// house-lights mod: every feature in one hooks module, since a plugin has one.
//   recipes  checks each recipe Claude writes (.way.yaml, .blueprint.yaml, .drill.yaml, .chalk, a chalk-talk .json)
//            with its skill's own check, and refuses it with the messages
//   previews a pane with the last way of working or service blueprint written; /way-preview, /blueprint-preview
//   names    in a repository that runs the names audit, refuses a write with a name of the person's private list;
//            /names says what it watches
//   /cast    cast-list's comparison of a folder of agents in a pane, and a toast when an agent edited there changes it
//   guard    checks each .sim file Claude writes and refuses it with the validator's messages
//   /sim     runs a recipe with no model turn and prints median and p10 to p90 per metric
//   preview  a pane with the recipe's flow, opened by /sim-preview or the first valid write
import type { Register } from 'claude-code'

import { simCommand } from './box-office/command'
import { namesCommand, namesGuard } from './names/guard'
import { recipesGuard } from './recipes/guard'
import { recipePreview } from './previews/preview'
import { castCommand } from './cast/cast'
import { guard } from './box-office/guard'
import { preview } from './box-office/preview'

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'sim',
      description: 'Run a .sim recipe: median and p10 to p90 of each metric',
      argumentHint: '[file.sim] [--seeds N] [--set knob=value]',
    })
    await $.command.register({
      name: 'way-preview',
      description: 'Show a way of working (.way.yaml) in a pane: stages in lanes, gates and who approves',
      argumentHint: '[file.way.yaml]',
    })
    await $.command.register({
      name: 'blueprint-preview',
      description: 'Show a service blueprint (.blueprint.yaml) in a pane: moments, on stage and behind',
      argumentHint: '[file.blueprint.yaml]',
    })
    await $.command.register({
      name: 'cast',
      description: "Compare a folder of cloned Copilot Studio agents with cast-list: what to look at, in a pane",
      argumentHint: '[agents-folder] [--lang pt]',
    })
    await $.command.register({
      name: 'names',
      description: 'Say what the names guard watches: your private list and this repository',
    })
    await $.command.register({
      name: 'sim-preview',
      description: 'Show the flow of the current .sim recipe in a pane',
      argumentHint: '[file.sim]',
    })
    return next(e)
  })

  recipesGuard(on)
  recipePreview(on)
  castCommand(on)
  namesGuard(on)
  namesCommand(on)
  guard(on)
  simCommand(on)
  preview(on)
}
