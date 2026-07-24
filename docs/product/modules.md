# Module Plan

## First Surface

Build the first KaosGDD v2 surface as a service cockpit:

- service launcher
- health checks
- module registry
- quick actions
- no database dependency

## Modules

| Module | First behavior | Long-term owner |
| --- | --- | --- |
| Dashboard | Service status and links | KaosGDD |
| Tasks | New task UI working with calendar | KaosGDD UI + Radicale |
| Calendar | Calendar view and adapter | Radicale |
| ROUN timetable | Standalone timetable | KaosGDD |
| Caregiver wage | Standalone family module | KaosGDD |
| Weather | Reuse/adapt current behavior | KaosGDD or weather adapter |
| Notes | Link first, adapter/search later | Wiki.js |
| Documents | Link first, adapter/search later | Paperless-ngx |
| Files | Link first, adapter later | SFTPGo |
| PDF | Link first, workflow adapter later | Stirling-PDF |
| Supplies | API adapter | KaosSupplies |
| Fax | Legacy bridge for now | KaosGDD legacy, KaosFaxMail later |
| PACS | API links only | KaosPACS |

## Not In First Pass

- moving PACS
- moving DICOM
- replacing fax bridge
- rebuilding reminders
- direct database integration
- global search indexing across all services

## ROUN

ROUN timetable stays standalone during the first v2 pass.

Do not connect it to Radicale/calendar until the workflow need is clear.

## Task Grammar

Radicale-backed tasks should use the legacy KaosGDD subtask grammar inside VTODO descriptions.

See [Radicale Task Plan](radicale-task-plan.md).
