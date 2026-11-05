// Curated notes on operations, each of one kind, so the agent weighs it as what it is:
//   schema       — what Workday's public WSDLs (v47.0, read on 2026-11-05) show: `evidence` names the elements, types
//                  and values it rests on (tools/check-real.mjs finds each of them in an index), `absent` the
//                  operations it says do not exist, `absentFields` what no field of the request is named after;
//   description  — what Workday's own description of the operation says (`quote`: the words, checked against it);
//   inferred     — a deduction from the schema or the descriptions, not shown by them: check it;
//   sensitive    — what a response may carry about a person, from its fields' names and documentation;
//   tenant       — not in the schema at all: ask the tenant.
// Shown by show, related and copilot, with the source of each kind once (`sources`).
export const NOTES = {
  Add_Flexible_Work_Arrangement: [
    { kind: 'schema', text: 'No Get_Flexible_Work_Arrangement(s) operation exists in any service.', absent: ['Get_Flexible_Work_Arrangement', 'Get_Flexible_Work_Arrangements'] },
    { kind: 'inferred', text: 'To read arrangements, a RaaS report, or Get_Worker_Event_History and then Get_Event_Detail on the event, may do.' },
    { kind: 'schema', text: 'The arrangement type (Flexible_Work_Arrangement_Type_Reference) takes WID or Flexible_Work_Arrangement_Subtype_ID — a subtype, not Flexible_Work_Arrangement_Type_ID.', evidence: ['Flexible_Work_Arrangement_Type_Reference', 'Flexible_Work_Arrangement_Subtype_ID'] },
    { kind: 'schema', text: 'The reason (Reason_Reference) takes General_Event_Subcategory_ID or Event_Classification_Subcategory_ID; the days take Day_of_the_Week_ID.', evidence: ['Reason_Reference', 'General_Event_Subcategory_ID', 'Event_Classification_Subcategory_ID', 'Day_of_the_Week_ID'] },
    { kind: 'schema', text: 'The request has no questionnaire field.', absentFields: ['Questionnaire'] },
    { kind: 'inferred', text: "When the business process has a questionnaire or an attachment step, the web service likely only starts the event, and that step goes to the person's Workday inbox — confirm with the tenant's business process." },
    { kind: 'schema', text: 'The response carries Request_Flexible_Work_Arrangement_Event_Reference.', evidence: ['Request_Flexible_Work_Arrangement_Event_Reference'] },
    { kind: 'inferred', text: "That event's WID is what Get_Event_Detail and the approval operations take (their Event_Reference)." },
    { kind: 'description', text: 'When a worker has more than one job, the request must name one of them.', quote: 'When a worker has multiple jobs, you must specify 1 of the jobs' },
    { kind: 'inferred', text: 'To change an arrangement, ending it (End_Flexible_Work_Arrangement) and requesting a new one is the way the operations allow; the tenant may have another.' },
    { kind: 'tenant', text: "The business process's security domain, its approval routing, and whether it blocks approving one's own request." },
  ],
  End_Flexible_Work_Arrangement: [
    { kind: 'schema', text: 'It takes Worker_Reference, Flexible_Work_Arrangement_Reference (WID or Flexible_Work_Arrangement_ID) and End_Date; Reason_Reference is optional.', evidence: ['Worker_Reference', 'Flexible_Work_Arrangement_Reference', 'Flexible_Work_Arrangement_ID', 'End_Date', 'Reason_Reference'] },
    { kind: 'description', text: 'When a worker has more than one job, the request must name one of them.', quote: 'When a worker has multiple jobs, you must specify 1 of the jobs' },
  ],
  Get_References: [
    { kind: 'schema', text: 'Reference_ID_Type is free text: the values Workday knows are in Reference_IndexReferenceEnumeration (about 5,900). For a flexible work arrangement: Flexible_Work_Arrangement_Subtype_ID, General_Event_Subcategory_ID, Day_of_the_Week_ID.', evidence: ['Reference_ID_Type', 'Reference_IndexReferenceEnumeration', 'Flexible_Work_Arrangement_Subtype_ID', 'General_Event_Subcategory_ID', 'Day_of_the_Week_ID'] },
  ],
  Get_Worker_Event_History: [
    { kind: 'schema', text: 'The request element is Worker_Event_History_Get (not _Request); the person goes in Employee_Reference › Integration_ID_Reference › ID@System_ID, and Event_Date_Range_Data is optional.', evidence: ['Worker_Event_History_Get', 'Employee_Reference', 'Integration_ID_Reference', 'Event_Date_Range_Data'] },
    { kind: 'sensitive', text: 'It returns every event of the person (pay, leaves, termination), not only the request — keep only the events the flow needs.' },
  ],
  Get_Event_Detail: [
    { kind: 'schema', text: 'The operation is Get_Event_Detail; its request element is Get_Event_Details_Request.', evidence: ['Get_Event_Detail', 'Get_Event_Details_Request'] },
    { kind: 'schema', text: 'The request has Exclude_Process_History_Data and Exclude_Remaining_Step_Data; the response has Event_Target_Reference.', evidence: ['Exclude_Process_History_Data', 'Exclude_Remaining_Step_Data', 'Event_Target_Reference'] },
    { kind: 'inferred', text: "Event_Target_Reference is where the business object's ID (an arrangement, for one) may come." },
    { kind: 'sensitive', text: 'It returns comments, approvers and the reason of the request, which may be about health or family.' },
  ],
  Get_Workers: [
    { kind: 'schema', text: 'The position is in Worker_Data › Employment_Data › Worker_Job_Data › Position_Data › Position_ID, with Include_Employment_Information=true.', evidence: ['Worker_Data', 'Employment_Data', 'Worker_Job_Data', 'Position_Data', 'Position_ID', 'Include_Employment_Information'] },
    { kind: 'sensitive', text: 'Include_Compensation brings pay; Include_Employment_Information the whole job (contract, FTE, location, manager, dates, payroll data, company insider data — Company_Insider_Data); Include_Personal_Information personal data. Ask for the smallest Response_Group that answers.', evidence: ['Include_Compensation', 'Include_Personal_Information', 'Company_Insider_Data', 'Response_Group'] },
  ],
  Approve_Business_Process: [
    { kind: 'schema', text: 'Event_Reference takes WID or Event_ID, with an optional Comment.', evidence: ['Event_Reference', 'Event_ID', 'Comment'] },
    { kind: 'description', text: 'It approves the business process, if approvable, by the user: it runs as the approver.', quote: 'approves a business process, if approvable, by the user' },
  ],
  Deny_Business_Process: [
    { kind: 'schema', text: 'Event_Reference takes WID or Event_ID, with an optional Comment.', evidence: ['Event_Reference', 'Event_ID', 'Comment'] },
    { kind: 'description', text: 'It denies the business process, if deniable, by the user: it runs as the approver.', quote: 'denies a business process, if deniable, by the user' },
  ],
  Send_Back_Business_Process: [{ kind: 'schema', text: 'It takes the step to return to (Business_Process_Step_ID).', evidence: ['Business_Process_Step_ID'] }],
  Cancel_Business_Process: [
    { kind: 'schema', text: 'The request has Suppress_Notifications.', evidence: ['Suppress_Notifications'] },
    { kind: 'inferred', text: 'Suppress_Notifications, by its name, cancels without notifying the people involved — check its documentation in show.' },
  ],
}

// Where each kind of note comes from: said once per answer (`sources`), not on every note.
export const NOTE_SOURCES = {
  schema: "Workday's public WSDLs (v47.0), checked on 2026-11-05; evidence, absent_operations and absent_fields are what it rests on",
  description: "Workday's description of the operation; quote is its words",
  inferred: 'a deduction, not shown by the schema: check it, say it as likely',
  sensitive: "what the response may carry about a person, from its fields' names and documentation",
  tenant: 'not in the schema: ask the tenant',
}

/** An operation's curated notes: each its kind, its text and what proves it (the source of each kind: NOTE_SOURCES). */
export function curatedNotes(op) {
  return (NOTES[op] ?? []).map((n) => ({
    kind: n.kind,
    text: n.kind === 'tenant' ? `To confirm in the tenant: ${n.text[0].toLowerCase()}${n.text.slice(1)}` : n.kind === 'sensitive' ? `Sensitive: ${n.text}` : n.text,
    ...(n.evidence ? { evidence: n.evidence } : {}),
    ...(n.absent ? { absent_operations: n.absent } : {}),
    ...(n.absentFields ? { absent_fields: n.absentFields } : {}),
    ...(n.quote ? { quote: n.quote } : {}),
  }))
}

/** The sources of the kinds the notes have, once. */
export const sourcesOf = (notes) => Object.fromEntries([...new Set(notes.map((n) => n.kind))].filter((k) => k in NOTE_SOURCES).map((k) => [k, NOTE_SOURCES[k]]))

// The Copilot Studio Workday connector, as Microsoft documents it (checked on 2026-11-05): the connector notes' kinds
export const CONNECTOR_SOURCES = {
  documentation: 'Microsoft: https://learn.microsoft.com/en-us/connectors/workdaysoap/ and https://learn.microsoft.com/en-us/microsoft-365/copilot/employee-self-service/workday-simplified-setup (checked on 2026-11-05)',
  practice: 'Power Platform practice',
  pointer: 'where the rest is',
}
