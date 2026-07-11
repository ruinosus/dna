// acme-support-bot (TS/JS twin) — ships the `support` scope as package data.
//
// The scope lives at `.dna/support` next to this file and is published via the
// package.json `files` array, so an `npm install` carries it into node_modules
// and into a Docker image. The app resolves it WITHOUT path navigation:
//
//   import { loadPrompts } from "dna-sdk";
//   const prompts = await loadPrompts("support", { anchor: "acme-support-bot" });
//   export const TRIAGE = await prompts.get("triage");
//
// `anchor: "acme-support-bot"` resolves the scope from inside THIS installed
// package (via its package.json) — identical from a source checkout, an
// installed dependency, or a container whose CWD is not the repo. No
// `path.resolve(__dirname, "../..")`, no manual `COPY .dna`.
import { loadPrompts } from "dna-sdk";

export async function triagePrompt() {
  const prompts = await loadPrompts("support", { anchor: "acme-support-bot" });
  return prompts.get("triage");
}
