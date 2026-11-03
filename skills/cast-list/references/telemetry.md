# What fired: the export of Application Insights

The YAML shows what an agent **should** log (`LogCustomTelemetryEvent`). What it **does** log is in Application
Insights, when the agent is connected to it (Copilot Studio › Settings › Advanced › Application Insights). cast-list
never reads it over the network: the person runs one query and exports the result, and the analysis reads the file.

## The query

In the Application Insights resource, open **Logs**, paste this, and export the result (**Export › CSV**):

```kusto
customEvents
| where timestamp > ago(30d)
| where tostring(customDimensions['designMode']) == "False"
| summarize vezes = count() by agente = cloud_RoleInstance, evento = name
```

- `designMode` leaves out the conversations of the test panel.
- `cloud_RoleInstance` is the agent's name in the default telemetry. When the team puts the agent's name in a field of
  its own events (such as `Agente`), use that instead: `agente = tostring(customDimensions['Agente'])`. cast-list finds
  the agent's column by its values (the schema name, the folder or the display name), not by its title.
- Change `30d` to the period you want, and pass the same number with `--telemetry-days`.
- **Export only these three columns.** Never add `text`, `fromName`, `user_Id` or any other column with what people
  said or who they are: cast-list reads only the agent, the event and the times, and the rest has no place in the file.

## Run

```
node scripts/build.mjs <agents-folder> --all --telemetry eventos.csv [--telemetry-days 30] [--lang pt]
```

The file is read on this run only (it is not kept in the cast file): pass it again on the next one.

- «O evento «X» de y não disparou em 30 dias» — the event is in y's YAML, y has lines in the export, and none is X.
- «y não tem nenhuma linha na telemetria: está ligado ao Application Insights?» — y is not in the export at all.
- An event of the export that no YAML has — Copilot Studio's own (`TopicStart`, `BotMessageReceived`…) — is left out.

The map's Cast tab shows each agent's events with the times they fired, and the workbook's **Telemetry** sheet has a
column with the times.
