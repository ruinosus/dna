// mcp-ws — the container app resource, as a Bicep MODULE.
//
// ⛔ This file is reachable by the template. Its INVOCATION is not: the root
// bicep has to carry a line like
//
//   module mcpwsApp '../../apps/mcp-ws/wiring/containerapp.bicep' = { ... }
//
// and Bicep has no glob or include for that. `dna solution new` prints it; a
// wiring guard in the consuming repo is what makes forgetting it fail loudly.

param location string
param tags object
param managedEnvironmentId string
param appIdentityId string
param registryName string
param placeholderImage string
param containerCpu string
param containerMemory string
param resourceToken string
param sourceUrl string

var appName = 'ca-mcp-ws-${resourceToken}'

resource mcpwsApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  tags: union(tags, { 'azd-service-name': 'mcp-ws' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${appIdentityId}': {} }
  }
  properties: {
    managedEnvironmentId: managedEnvironmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true // EXTERNAL
        targetPort: 8001
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        { server: '${registryName}.azurecr.io', identity: appIdentityId }
      ]
      secrets: [
        { name: 'dna-source-url', value: sourceUrl }
      ]
    }
    template: {
      containers: [
        {
          name: 'mcp-ws'
          image: placeholderImage // azd overwrites this with the image it builds
          resources: { cpu: json(containerCpu), memory: containerMemory }
          env: [
            { name: 'DNA_MCP_HOST', value: '0.0.0.0' }
            { name: 'DNA_MCP_PORT', value: '8001' }
            { name: 'DNA_MCP_AUTH', value: 'config' }
            { name: 'DNA_SOURCE_URL', secretRef: 'dna-source-url' }
          ]
        }
      ]
      // ⭐ can_sleep: True — the cost gate, AS A FIELD of the App.
      //
      // minReplicas 1 means this app never sleeps, and never-sleeping is a
      // RECURRING monthly bill, not a one-off: ~US$ 90/month, measured — the
      // dna-cloud copilot with a fixed replica was US$ 94.43 of a US$ 230.29
      // invoice, the single largest line on it.
      //
      // Per SERVICE, never per image: two doors over one image may answer
      // differently, and this file is the one that says which of them pays.
      scale: { minReplicas: 0, maxReplicas: 3 }
    }
  }
}

output name string = appName
