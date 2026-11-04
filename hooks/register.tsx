// house-lights mod: every feature in one hooks module, since a plugin has one.
//   recipes  checks each recipe Claude writes (.way.yaml, .blueprint.yaml, .drill.yaml, .chalk, a chalk-talk .json)
//            with its skill's own check, and refuses it with the messages
//   names    in a repository that runs the names audit, refuses a write with a name of the person's private list;
//            /names says what it watches
//   guard    checks each .sim file Claude writes and refuses it with the validator's messages
//   /sim     runs a recipe with no model turn and prints median and p10 to p90 per metric
//   preview  a pane with the recipe's flow, opened by /sim-preview or the first valid write
import type { Register } from 'claude-code'

import { simCommand } from './box-office/command'
import { namesCommand, namesGuard } from './names/guard'
import { recipesGuard } from './recipes/guard'
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
  namesGuard(on)
  namesCommand(on)
  guard(on)
  simCommand(on)
  preview(on)
}
