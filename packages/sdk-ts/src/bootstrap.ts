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
import { SdlcExtension } from "./extensions/sdlc.js";
import { AuditExtension } from "./extensions/audit.js";
import { LessonExtension } from "./extensions/lesson.js";
import { TenantExtension } from "./extensions/tenant.js";
import { EvidenceExtension } from "./extensions/evidence.js";
import { DocExtension } from "./extensions/doc.js";
import { ResearchExtension } from "./extensions/research.js";
import { TestkitExtension } from "./extensions/testkit.js";
import { ModelRegExtension } from "./extensions/modelreg.js";
import { CloudExtension } from "./extensions/cloud.js";
import { AutomationExtension } from "./extensions/automation.js";
import { EvalExtension } from "./extensions/eval.js";
import { IntelExtension } from "./extensions/intel.js";
import type { CacheItem } from "./kernel/protocols.js";
import type { Extension } from "./kernel/protocols.js";
import type { ManifestInstance } from "./kernel/instance.js";
import { loadConfig, type DnaConfig } from "./config.js";
import { resolveDefaultFsUrl, sourceFromUrl } from "./adapters/source-url.js";

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
    new SdlcExtension(),
    new AuditExtension(),
    new LessonExtension(),
    new TenantExtension(),
    new EvidenceExtension(),
    new DocExtension(),
    new ResearchExtension(),
    new TestkitExtension(),
    new ModelRegExtension(),
    new CloudExtension(),
    new AutomationExtension(),
    new EvalExtension(),
    new IntelExtension(),
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

/** Minimal CachePort for non-filesystem sources (all docs self-contained).
 *  TS twin of python `kernel_bootstrap._NoopCache`. */
class NoopCache {
  async loadAll(): Promise<Record<string, unknown>[]> {
    return [];
  }
  async loadKey(): Promise<Record<string, unknown>[]> {
    return [];
  }
  async store(_scope: string, _key: string, _items: CacheItem[]): Promise<void> {
    // no-op
  }
  async has(): Promise<boolean> {
    return true; // pretend always hit → skip resolver calls
  }
}

/**
 * Boot a fully-wired Kernel from a `dna.config.yaml` (declarative port wiring —
 * s-dx-kernel-from-config). TS twin of python `Kernel.from_config`.
 *
 * The config selects the `source` (`file://` / `postgresql://`) and,
 * optionally, the `search` + `embedding` providers; every port is resolved to
 * its adapter and wired. With NO config present (and no `path`) the behavior is
 * unchanged — a filesystem `.dna` source, exactly like the bare default.
 *
 * Returns a wired Kernel; call `.instance(scope)` for the ManifestInstance.
 * (Python exposes this as the `Kernel.from_config` static; the TS bootstrap
 * keeps it a free function, mirroring `quickInstance` — same documented
 * asymmetry the SDK already lives with.)
 */
export async function fromConfig(path?: string): Promise<Kernel> {
  const cfg = loadConfig(path);
  const sourceUrl = cfg ? cfg.source : resolveDefaultFsUrl();
  const source = await sourceFromUrl(sourceUrl);

  const k = createKernelWithBuiltins();
  k.source(source);

  if ((source as { supportsReaders?: boolean }).supportsReaders) {
    const baseDir = (source as unknown as { baseDir: string }).baseDir;
    k.cache(new FilesystemCache(baseDir));
    k.resolver("local", new LocalResolver(baseDir));
    k.resolver("http", new HttpResolver());
    k.resolver("https", new HttpResolver());
    k.resolver("github", new GitHubResolver());
  } else {
    k.cache(new NoopCache());
  }

  // Uniform writer/reader wiring for any KernelAttachable source.
  const attach = (source as { attachKernel?: (k: Kernel) => void }).attachKernel;
  if (typeof attach === "function") attach.call(source, k);

  if (cfg) {
    await wireSearch(k, cfg);
    await wireEmbedding(k, cfg);
  }
  return k;
}

async function wireEmbedding(kernel: Kernel, cfg: DnaConfig): Promise<void> {
  if (cfg.embedding === "off" || cfg.embedding === "fake") return;
  if (cfg.embedding === "onnx") {
    // Dynamic import: the ONNX adapter (transformers.js) must never enter the
    // default bundle (guard: tests/embedding-import-isolation.test.ts).
    const { OnnxEmbeddingProvider } = await import("./adapters/embedding/onnx.js");
    kernel.embeddingProvider(new OnnxEmbeddingProvider());
  }
}

async function wireSearch(kernel: Kernel, cfg: DnaConfig): Promise<void> {
  if (cfg.search === "off") return;
  if (cfg.search === "sqlite-vec") {
    // Dynamic import: sqlite-vec must never enter the default bundle
    // (guard: tests/search-import-isolation.test.ts).
    const { SqliteVecRecordSearchProvider } = await import(
      "./adapters/search/sqlite-vec.js"
    );
    kernel.recordSearchProvider(new SqliteVecRecordSearchProvider(kernel, {}));
  } else if (cfg.search === "pgvector") {
    throw new Error(
      "search: pgvector is Python-only in this build — the TS runtime ships " +
        "the sqlite-vec record-search provider. Use `search: sqlite-vec` here.",
    );
  }
}
