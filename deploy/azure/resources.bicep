// DNA hosted MCP — resource-group-scoped resources (Phase A of DNA-hosted).
//
// Provisions the minimal, keyless stack to run `dna mcp serve --transport http`
// on Azure Container Apps, authenticated with Microsoft Entra:
//
//   Log Analytics  -> the Container Apps log stream sink
//   ACA managed env -> the Container Apps environment
//   ACR (Basic)     -> holds the image azd builds + pushes
//   User-assigned Managed Identity -> pulls the image from ACR (AcrPull). NO
//                      secrets anywhere: Entra tokens are validated against the
//                      PUBLIC JWKS, and the image pull uses the identity.
//   Storage + Azure Files share -> the DNA source, mounted read-only at /mnt/dna
//                      (seed it with scripts/push-scope.sh; empty share => the
//                      server falls back to the scope baked into the image).
//   Container App   -> external HTTPS ingress on 8080, running as the identity,
//                      with the Entra-JWT auth env wired from the params.
//
// Resource types / apiVersions mirror the sibling Foundry app's verified IaC
// (Container Apps + user-assigned identity + AcrPull) — not invented.

@description('Location for all resources.')
param location string

@description('Tags applied to every resource (azd stamps azd-env-name here).')
param tags object = {}

@description('Short unique token for globally-unique resource names.')
param resourceToken string

// ── Entra auth (the hosted default) ────────────────────────────────────────
// When entraTenantId is set the Container App runs `--auth jwt`: it validates
// bearer JWTs against Entra's public JWKS and advertises Protected Resource
// Metadata (RFC 9728) so an MCP client discovers where to authorize. Leave it
// empty for a throwaway OPEN dev deploy (--auth none) — never for a real one.

@description('Microsoft Entra tenant (directory) ID. Empty => the app runs OPEN (--auth none, dev only). Set it to require Entra bearer tokens.')
param entraTenantId string = ''

@description('Expected token audience (aud) — the Entra app registration Application ID URI (api://<app-client-id>) or its client id. Required when entraTenantId is set.')
param entraAudience string = ''

@description('The JWT claim (or tenant:<x> scope prefix strips to) that maps a token to a DNA tenant. Default `tenant`; use `tid` to bind each Entra directory to a DNA tenant.')
param dnaTenantClaim string = 'tenant'

@description('CPU cores for the MCP container.')
param containerCpu string = '0.5'

@description('Memory for the MCP container.')
param containerMemory string = '1.0Gi'

var acrName = 'acrdnamcp${resourceToken}'
var identityName = 'id-dna-mcp-${resourceToken}'
var envName = 'cae-dna-mcp-${resourceToken}'
var logName = 'log-dna-mcp-${resourceToken}'
var storageName = 'stdnamcp${resourceToken}'
var appName = 'ca-dna-mcp-${resourceToken}'
var sourceShareName = 'dna-source'
var mcpPort = 8080

// Built-in role: AcrPull (stable Azure identifier).
var roleAcrPull = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

// Entra endpoints derived from the tenant — nothing to hand-copy. The login
// host comes from environment() so this stays correct across Azure clouds
// (public / Gov / China) rather than hardcoding login.microsoftonline.com.
var entraConfigured = !empty(entraTenantId)
var loginHost = environment().authentication.loginEndpoint // e.g. https://login.microsoftonline.com/
var jwksUri = entraConfigured ? '${loginHost}${entraTenantId}/discovery/v2.0/keys' : ''
var issuer = entraConfigured ? '${loginHost}${entraTenantId}/v2.0' : ''
var authServers = entraConfigured ? '${loginHost}${entraTenantId}/v2.0' : ''
var effectiveAuth = entraConfigured ? 'jwt' : 'none'

// ── observability + environment ────────────────────────────────────────────

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logName
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: envName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

// ── registry + identity (keyless image pull) ───────────────────────────────

resource registry 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: acrName
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false
    anonymousPullEnabled: false
  }
}

resource appIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: identityName
  location: location
  tags: tags
}

resource appToRegistry 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, appIdentity.id, roleAcrPull)
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleAcrPull)
    principalId: appIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ── DNA source (Azure Files, mounted read-only) ────────────────────────────
// The runtime only READS the source; seeding/publishing goes through
// scripts/push-scope.sh (upload to the share + revision restart), never the app.

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  tags: tags
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    allowSharedKeyAccess: true
  }
}

resource fileService 'Microsoft.Storage/storageAccounts/fileServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource sourceShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  parent: fileService
  name: sourceShareName
  properties: { shareQuota: 1 } // GiB — a DNA scope is a handful of YAML/MD files
}

// Azure Files access is account-key only for the share mount (no MI for the key),
// so the key is pulled via listKeys into the environment storage definition.
resource envSourceStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: env
  name: 'dnasource'
  properties: {
    azureFile: {
      accountName: storage.name
      accountKey: storage.listKeys().keys[0].value
      shareName: sourceShareName
      accessMode: 'ReadOnly'
    }
  }
}

// Predictable external FQDN from the env default domain (used to advertise the
// resource URL back to MCP clients for PRM discovery).
var appFqdn = '${appName}.${env.properties.defaultDomain}'
var resourceUrl = 'https://${appFqdn}'

// ── the MCP Container App ──────────────────────────────────────────────────

resource mcpApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  tags: union(tags, { 'azd-service-name': 'mcp' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${appIdentity.id}': {} }
  }
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: mcpPort
        transport: 'auto' // HTTP/2-capable; TLS terminated at the ingress
        allowInsecure: false
      }
      registries: [
        { server: registry.properties.loginServer, identity: appIdentity.id }
      ]
    }
    template: {
      containers: [
        {
          name: 'mcp'
          // azd overwrites this with the image it builds + pushes to the ACR.
          image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
          resources: { cpu: json(containerCpu), memory: containerMemory }
          env: [
            { name: 'DNA_MCP_TRANSPORT', value: 'http' }
            { name: 'DNA_MCP_HOST', value: '0.0.0.0' }
            { name: 'DNA_MCP_PORT', value: string(mcpPort) }
            { name: 'DNA_MCP_AUTH', value: effectiveAuth }
            // The DNA source: the mounted read-only share. Empty share => the
            // server falls back to the scope baked into the image.
            { name: 'DNA_BASE_DIR', value: '/mnt/dna' }
            // Entra-JWT auth (wired only when a tenant is configured; the values
            // are empty strings otherwise, and effectiveAuth is 'none').
            { name: 'DNA_MCP_JWKS_URI', value: jwksUri }
            { name: 'DNA_MCP_JWT_ISSUER', value: issuer }
            { name: 'DNA_MCP_JWT_AUDIENCE', value: entraAudience }
            { name: 'DNA_MCP_RESOURCE_URL', value: resourceUrl }
            { name: 'DNA_MCP_AUTH_SERVERS', value: authServers }
            // The token claim mapped to a DNA tenant (the auth<->tenancy bridge).
            { name: 'DNA_MCP_TENANT_CLAIM', value: dnaTenantClaim }
          ]
          volumeMounts: [
            { volumeName: 'dnasource', mountPath: '/mnt/dna' }
          ]
        }
      ]
      volumes: [
        { name: 'dnasource', storageType: 'AzureFile', storageName: envSourceStorage.name }
      ]
      // Scale-to-zero: idle = $0 (cold start on the first request). Raise
      // maxReplicas for concurrency; the MCP server holds no local write state.
      scale: { minReplicas: 0, maxReplicas: 2 }
    }
  }
}

// ── outputs (surfaced by azd into .azure/<env>/.env) ───────────────────────

output MCP_URL string = 'https://${mcpApp.properties.configuration.ingress.fqdn}'
output MCP_ENDPOINT string = 'https://${mcpApp.properties.configuration.ingress.fqdn}/mcp/'
output AUTH_MODE string = effectiveAuth
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = registry.properties.loginServer
output AZURE_CONTAINER_REGISTRY_NAME string = registry.name
output STORAGE_ACCOUNT_NAME string = storage.name
output DNA_SOURCE_SHARE string = sourceShareName
output APP_IDENTITY_CLIENT_ID string = appIdentity.properties.clientId
