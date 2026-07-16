"use client";

// DNA-emitted approval card (HITL) — the human write-gate for a servable copilot.
//
// Runtime-agnostic: rendered by `useHumanInTheLoop` when a gated write tool
// pauses the run. Approve resumes the run so the tool proceeds; Reject resumes
// with a declined decision. Title/details/reason are supplied by the console
// from the Copilot's `hitl.approval_card` config. Neutral extraction of the two
// reference consoles' approval cards — no domain or brand coupling.
import { useState } from "react";

export interface ApprovalDecision {
  approved: boolean;
  edits?: string;
}

export interface ApprovalCardProps {
  title: string;
  details: string;
  reason?: string;
  status?: "inProgress" | "executing" | "complete";
  respond?: (decision: ApprovalDecision) => void;
}

export function ApprovalCard({ title, details, reason, status, respond }: ApprovalCardProps) {
  const [decided, setDecided] = useState(false);
  // In `inProgress` the tool args are still partial — hide the controls so the
  // user can't approve against undefined args (mirrors the reference cards).
  const awaitingArgs = status === "inProgress";
  const done = decided || (status === "complete" && !respond);

  const decide = (approved: boolean, edits?: string) => {
    if (decided || !respond) return;
    setDecided(true);
    respond({ approved, edits });
  };

  return (
    <div className="dna-approval-card" data-testid="dna-approval-card">
      <p className="dna-approval-title">{title}</p>
      {details && <p className="dna-approval-details">{details}</p>}
      {reason && (
        <p className="dna-approval-reason">
          <span className="dna-approval-reason-label">Why</span> {reason}
        </p>
      )}
      {!done && !awaitingArgs && (
        <div className="dna-approval-actions">
          <button type="button" className="dna-approve" onClick={() => decide(true)}>
            Approve
          </button>
          <button type="button" className="dna-reject" onClick={() => decide(false)}>
            Reject
          </button>
        </div>
      )}
    </div>
  );
}
