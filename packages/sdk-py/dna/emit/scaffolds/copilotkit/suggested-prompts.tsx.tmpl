"use client";

// DNA-emitted suggested prompts — the antidote to the blank-box / prompt-
// paralysis anti-pattern. Starter chips that send on click via the AG-UI agent
// (addMessage + runAgent), shown only until the conversation starts. Generic:
// the prompts come from the console (the Copilot's `frontend.suggested_prompts`).
import { useAgent } from "@copilotkit/react-core/v2";
import { useEffect, useState } from "react";

export interface SuggestedPromptsProps {
  agentId: string;
  prompts: string[];
}

export function SuggestedPrompts({ agentId, prompts }: SuggestedPromptsProps) {
  const { agent } = useAgent({ agentId });
  const [hasMessages, setHasMessages] = useState(false);

  useEffect(() => {
    if (!agent) return;
    const sync = () => setHasMessages((agent.messages?.length ?? 0) > 0);
    sync();
    const sub = agent.subscribe({
      onRunInitialized: () => setHasMessages(true),
      onMessagesChanged: sync,
    });
    return () => sub.unsubscribe();
  }, [agent]);

  if (hasMessages || prompts.length === 0) return null;

  const send = (text: string) => {
    if (!agent) return;
    const id =
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.round(Math.random() * 1e6)}`;
    agent.addMessage({ id, role: "user", content: text });
    setHasMessages(true);
    void agent.runAgent();
  };

  return (
    <div className="dna-suggest">
      <span className="dna-suggest-label">Try:</span>
      <div className="dna-suggest-chips">
        {prompts.map((q) => (
          <button key={q} type="button" className="dna-suggest-chip" onClick={() => send(q)}>
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
