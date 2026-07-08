/**
 * Safety scanner — Tier 1 (regex) built-in, zero deps.
 *
 * Detects and masks PII (CPF, CNPJ, email, phone, credit card),
 * prompt injection, banned words, and custom regex patterns.
 *
 * 1:1 parity with Python dna.safety.scanner.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Violation {
  ruleType: string;
  entity: string;
  text: string;
  start: number;
  end: number;
  replacement: string;
}

export interface ScanResult {
  found: boolean;
  violations: Violation[];
}

export interface Scanner {
  available(): boolean;
  scan(text: string): Violation[];
}

// ---------------------------------------------------------------------------
// Validation helpers
// ---------------------------------------------------------------------------

function validateCPF(cpf: string): boolean {
  const digits = cpf.replace(/\D/g, "");
  if (digits.length !== 11) return false;
  if (/^(\d)\1{10}$/.test(digits)) return false;
  let sum = 0;
  for (let i = 0; i < 9; i++) sum += parseInt(digits[i]) * (10 - i);
  let check = 11 - (sum % 11);
  if (check >= 10) check = 0;
  if (parseInt(digits[9]) !== check) return false;
  sum = 0;
  for (let i = 0; i < 10; i++) sum += parseInt(digits[i]) * (11 - i);
  check = 11 - (sum % 11);
  if (check >= 10) check = 0;
  return parseInt(digits[10]) === check;
}

function validateCNPJ(cnpj: string): boolean {
  const digits = cnpj.replace(/\D/g, "");
  if (digits.length !== 14) return false;
  const weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
  const weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
  let sum = 0;
  for (let i = 0; i < 12; i++) sum += parseInt(digits[i]) * weights1[i];
  let check = sum % 11 < 2 ? 0 : 11 - (sum % 11);
  if (parseInt(digits[12]) !== check) return false;
  sum = 0;
  for (let i = 0; i < 13; i++) sum += parseInt(digits[i]) * weights2[i];
  check = sum % 11 < 2 ? 0 : 11 - (sum % 11);
  return parseInt(digits[13]) === check;
}

function maskKeepFormat(text: string, visibleEnd = 2): string {
  const digits = text.replace(/\D/g, "");
  let idx = 0;
  return text.replace(/\d/g, () => {
    const d = idx++;
    return d >= digits.length - visibleEnd ? digits[d] : "*";
  });
}

// ---------------------------------------------------------------------------
// PII pattern registry
// ---------------------------------------------------------------------------

interface PatternEntry {
  entity: string;
  regex: RegExp;
  maskFn: (match: string) => string;
  validate?: (match: string) => boolean;
}

const PII_PATTERNS: Record<string, PatternEntry> = {
  cpf: {
    entity: "cpf",
    regex: /\d{3}\.?\d{3}\.?\d{3}-?\d{2}/g,
    maskFn: (m) => maskKeepFormat(m, 0),
    validate: validateCPF,
  },
  cnpj: {
    entity: "cnpj",
    regex: /\d{2}\.?\d{3}\.?\d{3}\/?\d{4}-?\d{2}/g,
    maskFn: (m) => maskKeepFormat(m, 0),
    validate: validateCNPJ,
  },
  email: {
    entity: "email",
    regex: /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g,
    maskFn: (m) => {
      const [local, domain] = m.split("@");
      return `${local[0]}***@${domain}`;
    },
  },
  phone: {
    entity: "phone",
    regex: /\+?\d{1,3}[\s.-]?\(?\d{2,3}\)?[\s.-]?\d{4,5}[\s.-]?\d{4}/g,
    maskFn: (m) => maskKeepFormat(m, 4),
  },
  credit_card: {
    entity: "credit_card",
    regex: /\d{4}[\s.-]?\d{4}[\s.-]?\d{4}[\s.-]?\d{4}/g,
    maskFn: (m) => {
      const d = m.replace(/\D/g, "");
      return `****-****-****-${d.slice(-4)}`;
    },
  },
};

// ---------------------------------------------------------------------------
// RegexScanner — Tier 1, built-in, zero deps
// ---------------------------------------------------------------------------

export class RegexScanner implements Scanner {
  private patterns: PatternEntry[];

  constructor(rules: Array<Record<string, unknown>>) {
    this.patterns = [];
    for (const rule of rules) {
      if (
        rule.type !== "pii" &&
        rule.type !== "prompt_injection" &&
        rule.type !== "banned_words" &&
        rule.type !== "custom_regex"
      ) continue;
      const tier = (rule.tier as string) ?? this.inferTier(rule);
      if (tier !== "regex") continue;
      this.patterns.push(...this.buildPatterns(rule));
    }
  }

  available(): boolean {
    return true;
  }

  scan(text: string): Violation[] {
    const violations: Violation[] = [];
    for (const { entity, regex, maskFn, validate } of this.patterns) {
      // Create fresh regex to reset lastIndex
      const re = new RegExp(regex.source, regex.flags);
      let match: RegExpExecArray | null;
      while ((match = re.exec(text)) !== null) {
        if (validate && !validate(match[0])) continue;
        violations.push({
          ruleType: "pii",
          entity,
          text: match[0],
          start: match.index,
          end: match.index + match[0].length,
          replacement: maskFn(match[0]),
        });
      }
    }
    return violations;
  }

  private inferTier(rule: Record<string, unknown>): string {
    if (rule.type === "pii") {
      const entities = (rule.entities as string[]) ?? [];
      if (entities.some((e) => ["person", "location"].includes(e))) return "ml";
      return "regex";
    }
    return "regex";
  }

  private buildPatterns(rule: Record<string, unknown>): PatternEntry[] {
    const patterns: PatternEntry[] = [];

    if (rule.type === "pii") {
      const entities = (rule.entities as string[]) ?? [];
      for (const entity of entities) {
        const p = PII_PATTERNS[entity];
        if (p) patterns.push(p);
      }
    }
    if (rule.type === "prompt_injection") {
      patterns.push({
        entity: "prompt_injection",
        regex: /\b(ignore\s+(previous|above|all)\s+(instructions?|rules?|prompts?)|system\s+prompt|jailbreak|DAN\s+mode)\b/gi,
        maskFn: () => "[BLOCKED]",
      });
    }
    if (rule.type === "banned_words") {
      const words = (rule.words as string[]) ?? [];
      if (words.length > 0) {
        const escaped = words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
        patterns.push({
          entity: "banned_word",
          regex: new RegExp(`\\b(${escaped.join("|")})\\b`, "gi"),
          maskFn: () => "[REDACTED]",
        });
      }
    }
    if (rule.type === "custom_regex") {
      const regexPatterns = (rule.patterns as string[]) ?? [];
      for (const p of regexPatterns) {
        try {
          patterns.push({
            entity: "custom",
            regex: new RegExp(p, "g"),
            maskFn: () => "[REDACTED]",
          });
        } catch {
          /* invalid regex — skip */
        }
      }
    }
    return patterns;
  }
}

// ---------------------------------------------------------------------------
// ScannerPipeline
// ---------------------------------------------------------------------------

export class ScannerPipeline {
  private scanners: Scanner[];

  constructor(rules: Array<Record<string, unknown>>) {
    this.scanners = [new RegexScanner(rules)];
    // Tier 2/3/4 would be added here if available
  }

  scan(text: string): ScanResult {
    const violations: Violation[] = [];
    for (const scanner of this.scanners) {
      if (scanner.available()) violations.push(...scanner.scan(text));
    }
    return { found: violations.length > 0, violations };
  }

  apply(text: string, action: string): string {
    const result = this.scan(text);
    if (!result.found) return text;
    if (action === "block") {
      throw new Error(
        `SafetyPolicy violation: ${result.violations.map((v) => v.entity).join(", ")}`,
      );
    }
    if (action === "mask") {
      // Sort violations by position descending to replace from end to start
      const sorted = [...result.violations].sort((a, b) => b.start - a.start);
      let masked = text;
      for (const v of sorted) {
        masked = masked.slice(0, v.start) + v.replacement + masked.slice(v.end);
      }
      return masked;
    }
    return text; // log: no modification
  }
}
