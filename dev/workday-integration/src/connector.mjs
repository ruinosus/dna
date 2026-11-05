// The Microsoft Workday connector's actions, as Microsoft documents them (https://learn.microsoft.com/en-us/connectors/
// workdaysoap/, checked on 2026-11-05): the generic ones (SOAP, REST, RaaS) and the ready-made ones (Preview, REST under
// the hood, OAuth 2.0 only). Documentation, for the agent to weigh against a SOAP operation or a REST endpoint.
export const CONNECTOR_DOC = 'https://learn.microsoft.com/en-us/connectors/workdaysoap/'

export const CONNECTOR_ACTIONS = [
  { id: 'SOAP_Operation', name: 'Execute SOAP operation', params: ['service*', 'version*', 'requestBody*'], about: 'Executes a SOAP operation.' },
  { id: 'REST_Operation', name: 'Execute REST request (Preview)', preview: true, params: ['relativePath*', 'method', 'contentType', 'body'], about: "Executes a Workday REST request against the connection's REST base URL using the signed-in user's OAuth credentials; relativePath with the {tenant} placeholder (e.g. person/v4/{tenant}/values/commonPhone/phoneDeviceTypes/); Workday enforces the signed-in user's permissions; no idempotency keys (retrying a write is the caller's); requires OAuth 2.0." },
  { id: 'RaaS_Operation', name: 'Execute RaaS operation', params: ['accountName*', 'reportName*', 'requestBody*', 'reportInstanceName*'], about: 'Executes a RaaS (Report as a Service) operation.' },
  { id: 'GetWorkerMe', name: 'Get my worker profile (Preview)', preview: true, params: [], about: 'Returns the Workday profile of the authenticated worker (id, descriptor, isManager, businessTitle, primaryWorkEmail, primaryWorkPhone, primarySupervisoryOrganization).' },
  { id: 'GetWorkerInboxTasks', name: 'Get worker inbox tasks (Preview)', preview: true, params: ['workerID*', 'limit', 'offset'], about: 'Returns the inbox tasks assigned to the specified worker (id, descriptor, assigned, due, status, stepType, initiator, subject, overallProcess).' },
  { id: 'GetWorkerDirectReports', name: 'Get worker direct reports (Preview)', preview: true, params: ['workerID*', 'limit', 'offset'], about: 'Returns the workers who directly report to the specified worker.' },
  { id: 'GetWorkerPaySlips', name: 'Get worker pay slips (Preview)', preview: true, params: ['workerID*', 'limit', 'offset'], about: 'Returns pay slip summaries for the specified worker (pay components, gross, net, dates).' },
  { id: 'SearchWorkers', name: 'Search workers (Preview)', preview: true, params: ['search', 'limit', 'offset'], about: 'Searches for workers by name (people picker).' },
  { id: 'TransferEmployee', name: 'Transfer employee (Preview)', preview: true, params: ['workerID*', 'id', 'effective*', 'moveManagersTeam'], about: 'Initiates a job change (transfer) for the specified worker to a new supervisory organization.' },
  { id: 'GetSupervisoryOrganizationsManaged', name: 'Get supervisory organizations managed by worker (Preview)', preview: true, params: ['workerID*', 'limit', 'offset'], about: "Returns the supervisory organizations the worker manages (to resolve a manager's organization for a transfer)." },
  { id: 'GetFeedbackTemplates', name: 'Get feedback templates (Preview)', preview: true, params: ['search', 'templateType', 'worker', 'limit', 'offset'], about: 'Returns the feedback templates configured in the tenant.' },
  { id: 'RequestFeedback', name: 'Request feedback on worker (Preview)', preview: true, params: ['workerID*', 'id', 'feedbackConfidential', 'showFeedbackProviderName', 'expirationDate'], about: 'Requests feedback on the specified worker from one or more responders.' },
]
