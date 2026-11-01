# Facilitator’s script: The orders database is almost full

At lunchtime the orders database disk reaches 92% and keeps growing.

Made from `runbooks/database-disk.md`.

Starts at **12:40** · impact counted in failed orders.

## Roles

- **On-call engineer** — the player · can: delete-backups
- **Platform team** · can: grow-volume
- **Support lead** · can: tell-customers

## Scenes

### alert

«orders-db disk 92%» — the alert has been firing for 4 minutes.

- **Open the database dashboard** → dashboard _(+2 min · runbook Step 1)_
- **Snooze it until after lunch** → full _(+35 min · +400 failed orders)_

### dashboard

The disk grows 1% every 3 minutes. 18 GB of it are backups older than 7 days; 40 GB are write-ahead logs.

- **Delete the old backups** → breathing _(+5 min · needs delete-backups · runbook Step 2)_
- **Delete the write-ahead logs — they are the biggest** → broken _(+2 min · +900 failed orders)_
- **Ask the platform team to grow the volume** → grown _(+15 min · +60 failed orders · needs grow-volume · runbook Step 3)_

### full — end: worse

At 13:15 the disk is full and every order fails.

### breathing

The disk is at 71%. It still grows 1% every 3 minutes — you have about an hour.

> **12:52** Support — «a few customers say checkout is slow».

- **Grow the volume now, while there is time** → grown _(+15 min · needs grow-volume · runbook Step 3)_
- **Tell support what is going on** → told _(+2 min · needs tell-customers · tells the people affected · runbook Step 4)_

### broken — end: worse

The database stops — without its write-ahead logs it cannot recover on its own. Orders are failing.

### grown — end: resolved

The volume is now twice as big. The disk is at 38%.

### told

Support posts a note for customers. The disk is at 74%.

- **Grow the volume** → grown _(+15 min · needs grow-volume · runbook Step 3)_

## What the runbook does not say

- The runbook does not say who decides to grow the volume after hours, or how to reach the platform team. _(Step 3)_
- «Tell support» comes last; nothing says when customers should hear about it. _(Step 4)_
