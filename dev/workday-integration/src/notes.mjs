// Curated notes on operations, from Workday's public WSDLs (v47.0, read on 2026-11-05): only what the schema shows;
// what the schema cannot show (security, routing) is marked «to confirm in the tenant». The «Sensitive:» notes say
// what a response may carry about a person. Shown by show, trace and copilot.
export const NOTES = {
  Add_Flexible_Work_Arrangement: [
    'There is no Get_Flexible_Work_Arrangement(s) in any service: read arrangements with a RaaS report, or with Get_Worker_Event_History and Get_Event_Detail.',
    'The arrangement type (Flexible_Work_Arrangement_Type_Reference) is a subtype: it takes WID or Flexible_Work_Arrangement_Subtype_ID — not Flexible_Work_Arrangement_Type_ID nor _Subcategory_ID.',
    'The reason (Reason_Reference) takes General_Event_Subcategory_ID or Event_Classification_Subcategory_ID; the days take Day_of_the_Week_ID.',
    'The request has no questionnaire fields: when the business process has a questionnaire or an attachment step, the web service only starts the event, and that step lands in the person\'s Workday inbox.',
    'The response carries Request_Flexible_Work_Arrangement_Event_Reference: keep its WID for Get_Event_Detail and for the approval.',
    'If the person has more than one job, the request must name the job or position.',
    'To change an arrangement, end it (End_Flexible_Work_Arrangement) and request a new one.',
    'To confirm in the tenant: the business process\'s security domain, its approval routing, and whether it blocks approving one\'s own request — the schema does not say.',
  ],
  End_Flexible_Work_Arrangement: [
    'It takes Worker_Reference, Flexible_Work_Arrangement_Reference (WID or Flexible_Work_Arrangement_ID) and End_Date; Reason_Reference is optional.',
    'If the person has more than one job, the request must name the job or position.',
  ],
  Get_References: [
    'Reference_ID_Type is free text: the valid values are in Reference_IndexReferenceEnumeration (about 5,900). For a flexible work arrangement: Flexible_Work_Arrangement_Subtype_ID, General_Event_Subcategory_ID, Day_of_the_Week_ID.',
  ],
  Get_Worker_Event_History: [
    'The request element is Worker_Event_History_Get (not _Request); the person goes in Employee_Reference › Integration_ID_Reference › ID@System_ID, and Event_Date_Range_Data is optional.',
    'Sensitive: it returns every event of the person (pay, leaves, termination), not only the request — keep only the events the flow needs.',
  ],
  Get_Event_Detail: [
    'The operation is Get_Event_Detail; its request element is Get_Event_Details_Request.',
    'Exclude_Process_History_Data and Exclude_Remaining_Step_Data trim the answer; Event_Target_Reference is where the object\'s ID may come (an arrangement, for one).',
    'Sensitive: it returns comments, approvers and the reason of the request, which may be about health or family.',
  ],
  Get_Workers: [
    'The position is in Worker_Data › Employment_Data › Worker_Job_Data › Position_Data › Position_ID, with Include_Employment_Information=true.',
    'Sensitive: Include_Compensation brings pay; Include_Employment_Information the whole job (contract, FTE, location, manager, dates, payroll data, Company_Insider); Include_Personal_Information personal data. Ask for the smallest Response_Group that answers.',
  ],
  Approve_Business_Process: ['Event_Reference takes WID or Event_ID, with an optional Comment; it runs as the approver.'],
  Deny_Business_Process: ['Event_Reference takes WID or Event_ID, with an optional Comment; it runs as the approver.'],
  Send_Back_Business_Process: ['It takes the step to return to (Business_Process_Step_ID).'],
  Cancel_Business_Process: ['Suppress_Notifications cancels without telling the people involved.'],
}
