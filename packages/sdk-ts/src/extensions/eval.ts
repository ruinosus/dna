/**
 * EvalExtension — evaluation authoring as data (TS twin).
 *
 * Registers 4 Kinds, all from descriptors (F3 — record Kinds are data,
 * not classes): EvalCase (eval-eval-case), EvalSuite (eval-eval-suite),
 * EvalRun (eval-eval-run), EvalBaseline (eval-eval-baseline). The
 * kinds/*.kind.yaml files are PARITY-CRITICAL package data —
 * byte-identical mirrors of the Python copies
 * (tests/test_descriptor_hash_parity.py enforces).
 *
 * The local synchronous runner (run_suite / compare / EvalTargetPort) is
 * Py-primary by design (dna/extensions/eval/runner.py): the runner is a
 * host-side execution library — the same declare-here/execute-in-the-host
 * split as Automation, where the DECLARATION (these Kinds) is the
 * cross-language contract and execution lives with the host. A TS host
 * evaluates the same documents against the same schemas; a TS runner twin
 * lands when a TS host needs one.
 */

import type { Extension, ExtensionHost } from "../kernel/protocols.js";
import { loadDescriptors } from "../kernel/descriptor-loader.js";

export class EvalExtension implements Extension {
  readonly name = "eval";
  readonly version = "1.0.0";

  register(kernel: ExtensionHost): void {
    // F3: builtin record Kinds as descriptors — package data through the
    // same funnel as per-scope KindDefinitions (plane lint + digest
    // idempotency + builtin conflict marker).
    for (const raw of loadDescriptors(import.meta.url, "eval/kinds")) {
      kernel.kindFromDescriptor(raw);
    }
  }
}
