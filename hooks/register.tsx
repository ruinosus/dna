// house-lights mod — box-office: three features in one hooks module, since a plugin has one.
//   guard    checks each .sim file Claude writes and refuses it with the validator's messages
//   /sim     runs a recipe with no model turn and prints median and p10 to p90 per metric
//   preview  a pane with the recipe's flow, opened by /sim-preview or the first valid write
import type { Register } from 'claude-code'

import { simCommand } from './box-office/command'
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
      name: 'sim-preview',
      description: 'Show the flow of the current .sim recipe in a pane',
      argumentHint: '[file.sim]',
    })
    return next(e)
  })

  guard(on)
  simCommand(on)
  preview(on)
}
