// dna mod: every feature in one hooks module, since a plugin has one.
//   recipes  checks each recipe Claude writes (.way.yaml, .blueprint.yaml, .drill.yaml, .chalk, a visual-explainer .json)
//            with its skill's own check, and refuses it with the messages
//   previews a pane with the last way of working or service blueprint written; /way-preview, /blueprint-preview
//   names    in a repository that runs the names audit, refuses a write with a name of the person's private list;
//            /names says what it watches
//   /agents    agent-review's comparison of a folder of agents in a pane, and a toast when an agent edited there changes it
//   /lenses  a way of working as the other skills' recipes (a .sim, a blueprint, a drill), written beside it on a
//            press, and a toast when the way changes under a lens
//   /solution an solution solution in a pane: each piece and where it stands, a lens made again from the way
//   /drill   an incident drill played in a pane: the clock, the scene, the choices and calls as buttons, the debrief
//   guard    checks each .sim file Claude writes and refuses it with the validator's messages
//   /simulate     runs a recipe with no model turn and prints median and p10 to p90 per metric
//   preview  a pane with the recipe's flow, opened by /simulation-preview or the first valid write
import type { Register } from 'claude-code'

import { simCommand } from './process-simulation/command'
import { namesCommand, namesGuard } from './names/guard'
import { recipesGuard } from './recipes/guard'
import { recipePreview } from './previews/preview'
import { castCommand } from './agents/cast'
import { drillGame } from './drill/drill'
import { lensesCommand } from './lenses/lenses'
import { solutionCommand } from './solution/solution'
import { guard } from './process-simulation/guard'
import { preview } from './process-simulation/preview'

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'simulate',
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
      name: 'agents',
      description: "Compare a folder of cloned Copilot Studio agents with agent-review: what to look at, in a pane",
      argumentHint: '[agents-folder] [--lang pt]',
    })
    await $.command.register({
      name: 'drill',
      description: 'Play an incident drill (.drill.yaml) in a pane: the clock, the choices, who to call, the debrief',
      argumentHint: '[file.drill.yaml] [--lang pt]',
    })
    await $.command.register({
      name: 'lenses',
      description: 'See a way of working (.way.yaml) as a simulation, a service blueprint and a drill, and write them beside it',
      argumentHint: '[file.way.yaml] [--gate id] [--lang pt]',
    })
    await $.command.register({
      name: 'solution',
      description: 'Show an solution solution (.solution.yaml) in a pane: each piece, where it stands, and the lenses behind the way',
      argumentHint: '[file.solution.yaml] [--lang pt]',
    })
    await $.command.register({
      name: 'names',
      description: 'Say what the names guard watches: your private list and this repository',
    })
    await $.command.register({
      name: 'simulation-preview',
      description: 'Show the flow of the current .sim recipe in a pane',
      argumentHint: '[file.sim]',
    })
    return next(e)
  })

  recipesGuard(on)
  recipePreview(on)
  castCommand(on)
  drillGame(on)
  lensesCommand(on)
  solutionCommand(on)
  namesGuard(on)
  namesCommand(on)
  guard(on)
  simCommand(on)
  preview(on)
}
