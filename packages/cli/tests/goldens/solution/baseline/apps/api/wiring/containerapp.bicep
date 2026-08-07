// api — the container app resource, as a Bicep MODULE.
//
// ⛔ This file is reachable by the template. Its INVOCATION is not: the root
// bicep has to carry a line like
//
//   module apiApp '../../apps/api/wiring/containerapp.bicep' = { ... }
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

var appName = 'ca-api-${resourceToken}'

resource apiApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  tags: union(tags, { 'azd-service-name': 'api' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${appIdentityId}': {} }
  }
  properties: {
    managedEnvironmentId: managedEnvironmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: false // INTERNAL
        targetPort: 8080
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
          name: 'api'
          image: placeholderImage // azd overwrites this with the image it builds
          resources: { cpu: json(containerCpu), memory: containerMemory }
          env: [
            { name: 'DNA_API_HOST', value: '0.0.0.0' }
            { name: 'DNA_API_PORT', value: '8080' }
            { name: 'DNA_API_AUTH', value: 'config' }
            { name: 'DNA_SOURCE_URL', secretRef: 'dna-source-url' }
          ]
        }
      ]
      // can_sleep: True — the cost gate, AS A FIELD.
      // minReplicas 1 means this app never sleeps, and never-sleeping is a
      // recurring monthly bill, not a one-off.
      scale: { minReplicas: 0, maxReplicas: 2 }
    }
  }
}

output name string = appName
