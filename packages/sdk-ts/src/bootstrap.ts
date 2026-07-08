/**
 * Opinionated SDK bootstrap.
 *
 * The kernel itself (src/kernel/*) is extension-agnostic by design — it
 * knows about the 5-port architecture and nothing else. This module is
 * where the SDK ships its default wiring: the six built-in extensions,
 * the default resolvers, and the quick-start helpers used by examples
 * and tests.
 *
 * Callers that want a minimal kernel can `import { Kernel }` directly
 * and register exactly the extensions they need. Callers that want the
 * batteries-included experience use `createKernelWithBuiltins()` or
 * `quickInstance()`.
 */
import { Kernel } from "./kernel/index.js";
import { Runtime } from "./kernel/runtime.js";
import { FilesystemSource } from "./adapters/filesystem/source.js";
import { FilesystemCache } from "./adapters/filesystem/cache.js";
import { LocalResolver } from "./adapters/resolvers/local.js";
import { HttpResolver } from "./adapters/resolvers/http.js";
import { GitHubResolver } from "./adapters/resolvers/github.js";
import { HelixExtension } from "./extensions/helix.js";
import { AgentSkillsExtension } from "./extensions/agentskills.js";
import { SoulSpecExtension } from "./extensions/soulspec.js";
import { AgentsMdExtension } from "./extensions/agentsmd.js";
import { GuardrailExtension } from "./extensions/guardrails.js";
import { HookExtension } from "./extensions/hooks.js";
import { KindDefinitionExtension } from "./extensions/kinddef.js";
import { SafetyPolicyExtension } from "./extensions/safety.js";
import { RecognizerExtension } from "./extensions/recognizer.js";
import { FederationExtension } from "./extensions/federation.js";
import { AuditExtension } from "./extensions/audit.js";
import { TenantExtension } from "./extensions/tenant.js";
import { EvidenceExtension } from "./extensions/evidence.js";
import type { Extension } from "./kernel/protocols.js";
import type { ManifestInstance } from "./kernel/instance.js";

/**
 * The canonical built-in extension set. Loaded into BOTH a Kernel and a
 * Runtime through this SINGLE list so the two bootstraps can never drift
 * (s-export-unwired-ts-extensions — they had, and Community/Research/Sdlc were
 * loaded by neither). Add a built-in here once and both paths get it.
 */
function loadBuiltins<T extends { load(ext: Extension): void }>(target: T): T {
  for (const ext of [
    new HelixExtension(),
    new AgentSkillsExtension(),
    new SoulSpecExtension(),
    new AgentsMdExtension(),
    new GuardrailExtension(),
    new HookExtension(),
    new KindDefinitionExtension(),
    new SafetyPolicyExtension(),
    new RecognizerExtension(),
    new FederationExtension(),
    new AuditExtension(),
    new TenantExtension(),
    new EvidenceExtension(),
  ] as Extension[]) {
    target.load(ext);
  }
  // s-alias-generated-not-typed — com TODAS as extensions carregadas, todo
  // dep_filter builtin deve resolver pra um alias registrado. Antes: alias
  // com typo degradava o prompt silenciosamente (warning enterrado); agora
  // o boot falha apontando o Kind + campo + alias. Runtime herda de Kernel,
  // então AMBOS os caminhos (createKernelWithBuiltins/createRuntimeWithBuiltins)
  // passam por aqui — o twin TS do gate no fim de Kernel.auto() (Python).
  (target as unknown as { validateDepFilters?: () => void })
    .validateDepFilters?.();
  return target;
}

/**
 * Return a fresh Kernel with all six built-in extensions registered.
 * No source, cache, or resolvers wired — callers are responsible for
 * that. Use `quickInstance()` if you want the full batteries-included
 * shortcut.
 */
export function createKernelWithBuiltins(): Kernel {
  return loadBuiltins(new Kernel());
}

/**
 * Batteries-included shortcut: kernel + all built-in extensions +
 * default filesystem source / cache / resolvers, then returns a
 * `ManifestInstance` for the given scope. Equivalent to the old
 * `Kernel.quick(scope, baseDir)` static method that used to live on
 * the kernel class itself.
 */
export async function quickInstance(
  scope: string,
  baseDir: string = ".dna",
): Promise<ManifestInstance> {
  const k = createKernelWithBuiltins();
  k.source(new FilesystemSource(baseDir));
  k.cache(new FilesystemCache(baseDir));
  k.resolver("local", new LocalResolver(baseDir));
  k.resolver("http", new HttpResolver());
  k.resolver("https", new HttpResolver());
  k.resolver("github", new GitHubResolver());
  return k.instance(scope);
}

/**
 * Return a fresh Runtime with all six built-in extensions registered.
 * No source, cache, or resolvers wired — callers are responsible for
 * that. Use `quickManifest()` if you want the full batteries-included
 * shortcut.
 */
export function createRuntimeWithBuiltins(): Runtime {
  return loadBuiltins(new Runtime());
}

/**
 * Batteries-included shortcut using Runtime: all built-in extensions +
 * default filesystem source / cache / resolvers, then returns a
 * `ManifestInstance` for the given scope.
 */
export async function quickManifest(
  scope: string,
  baseDir: string = ".dna",
): Promise<ManifestInstance> {
  const rt = createRuntimeWithBuiltins();
  rt.storage(new FilesystemSource(baseDir));
  rt.cache(new FilesystemCache(baseDir));
  rt.resolver("local", new LocalResolver(baseDir));
  rt.resolver("http", new HttpResolver());
  rt.resolver("https", new HttpResolver());
  rt.resolver("github", new GitHubResolver());
  return rt.manifest(scope);
}
