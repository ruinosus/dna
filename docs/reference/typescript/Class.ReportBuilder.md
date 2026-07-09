# Class: ReportBuilder

## Constructors

### Constructor

```ts
new ReportBuilder(mi): ReportBuilder;
```

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `mi` | [`ManifestInstance`](Class.ManifestInstance.md) |

#### Returns

`ReportBuilder`

## Methods

### complianceMatrix()

```ts
complianceMatrix(framework): string;
```

Generate a compliance matrix mapping findings to regulatory articles.
 Supported frameworks: lgpd, gdpr, nist_ai_rmf.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `framework` | `string` |

#### Returns

`string`

***

### evalSummary()

```ts
evalSummary(suite?): string;
```

Generate an eval summary report grouped by suite.
 If `suite` is given, only that suite is included.

#### Parameters

| Parameter | Type |
| ------ | ------ |
| `suite?` | `string` |

#### Returns

`string`

***

### evidenceManifest()

```ts
evidenceManifest(): string;
```

Generate a manifest of all evidence documents.

#### Returns

`string`

***

### findingsSummary()

```ts
findingsSummary(minSeverity?): string;
```

Generate a findings summary grouped by severity.
 Filters out findings with severity below `minSeverity`.

#### Parameters

| Parameter | Type | Default value |
| ------ | ------ | ------ |
| `minSeverity` | `string` | `"low"` |

#### Returns

`string`
