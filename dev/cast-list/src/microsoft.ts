// The 15 reference patterns of microsoft/skills-for-copilot-studio (patterns/*.md, commit 9c42d3a), and how cast-list
// knows an agent follows one. Eight leave a clear mark in the YAML (`sign`: the extractor sets `ms:<id>` when it sees
// it); the other seven live in instructions' wording or in intent, so they come only as declared (`declared:ms:<id>`).

export const PATTERNS_URL = 'https://github.com/microsoft/skills-for-copilot-studio/blob/main/patterns'

export interface MsPattern {
  id: string
  name: string
  /** What in the YAML says the agent follows it; absent when only a person can say. */
  sign?: string
}

export const MS_PATTERNS: MsPattern[] = [
  { id: 'orchestrator-variables', name: 'Orchestrator-Generated Variables', sign: 'an OnRecognizedIntent topic with an AutomaticTaskInput that has shouldPromptUser: false' },
  { id: 'rai-error-handling', name: 'RAI Error Handling', sign: 'the OnError topic reads System.Error.SubCode' },
  { id: 'knowledge-hold-message', name: 'Knowledge Hold Message', sign: 'an OnKnowledgeRequested topic that sends a message' },
  { id: 'prevent-tool-call-leaks', name: 'Prevent Tool Call Leaks', sign: 'an OnGeneratedResponse topic that sets System.ContinueResponse' },
  { id: 'dynamic-topic-redirect', name: 'Dynamic Topic Redirect', sign: 'a BeginDialog whose dialog is a =Switch( expression' },
  { id: 'channel-aware-behavior', name: 'Channel-Aware Behavior', sign: 'a condition or SetVariable that reads System.Activity.ChannelId (not a tool input)' },
  { id: 'date-context', name: 'Date Context', sign: 'the instructions use Today() or Now()' },
  { id: 'line-breaks-in-messages', name: 'Line Breaks in Messages', sign: '<br /> inside a SendActivity or Question' },
  // the same YAML shape as orchestrator-variables: what tells them apart is what the variable is for
  { id: 'conversation-history-variable', name: 'Conversation History Variable' },
  { id: 'chain-of-thought-logging', name: 'Chain of Thought Logging' },
  // instructions' wording, or a child agent whose purpose only its author knows
  { id: 'deterministic-mcp-calls', name: 'Deterministic MCP Calls' },
  { id: 'prevent-child-agent-responses', name: 'Prevent Child Agent Responses' },
  // both load something on the first message (OnActivity): which one depends on what is loaded
  { id: 'jit-glossary', name: 'JIT Glossary' },
  { id: 'jit-user-context', name: 'JIT User Context' },
  // eight practices together; a few triggers alone do not make it
  { id: 'teams-production-hardening', name: 'Teams Production Hardening' },
]
