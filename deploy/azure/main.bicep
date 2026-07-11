// DNA hosted MCP — azd entry point (subscription-scoped).
//
// Provisions a resource group, then the whole hosting stack (in resources.bicep):
// Log Analytics + Container Apps env + ACR + user-assigned Managed Identity +
// Azure Files source share + the MCP Container App with Entra-JWT auth.
//
//   azd up                 # from deploy/azure/ — provisions + builds + deploys
//
// Everything is keyless: the image pull uses the managed identity, and Entra
// tokens are validated against the public JWKS (no secret in the template).

targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the azd environment — derives resource names and tags.')
param environmentName string

@description('Primary location for all resources (azd prompts for this).')
param location string

@description('Microsoft Entra tenant (directory) ID. Empty => the app runs OPEN (--auth none, dev only). azd maps ENTRA_TENANT_ID.')
param entraTenantId string = ''

@description('Expected token audience — the Entra app registration Application ID URI (api://<app-client-id>) or its client id. azd maps ENTRA_MCP_AUDIENCE.')
param entraAudience string = ''

@description('JWT claim mapped to a DNA tenant (default `tenant`; `tid` binds each Entra directory to a DNA tenant). azd maps DNA_MCP_TENANT_CLAIM.')
param dnaTenantClaim string = 'tenant'

var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var tags = { 'azd-env-name': environmentName }

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

module resources 'resources.bicep' = {
  name: 'dna-mcp-resources'
  scope: rg
  params: {
    location: location
    tags: tags
    resourceToken: resourceToken
    entraTenantId: entraTenantId
    entraAudience: entraAudience
    dnaTenantClaim: dnaTenantClaim
  }
}

output MCP_URL string = resources.outputs.MCP_URL
output MCP_ENDPOINT string = resources.outputs.MCP_ENDPOINT
output AUTH_MODE string = resources.outputs.AUTH_MODE
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = resources.outputs.AZURE_CONTAINER_REGISTRY_ENDPOINT
output AZURE_CONTAINER_REGISTRY_NAME string = resources.outputs.AZURE_CONTAINER_REGISTRY_NAME
output STORAGE_ACCOUNT_NAME string = resources.outputs.STORAGE_ACCOUNT_NAME
output DNA_SOURCE_SHARE string = resources.outputs.DNA_SOURCE_SHARE
output APP_IDENTITY_CLIENT_ID string = resources.outputs.APP_IDENTITY_CLIENT_ID
