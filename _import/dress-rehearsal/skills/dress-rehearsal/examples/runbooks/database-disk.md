# Runbook — database disk almost full

A fictional bookstore's orders database.

## Step 1 — Look at the disk
Open the database dashboard: disk used, and how fast it is growing.

## Step 2 — Free space safely
Delete the old backups kept on the same disk (older than 7 days). Never delete the write-ahead logs by hand.

## Step 3 — Grow the disk
If freeing space is not enough, grow the volume. Only the platform team can.

## Step 4 — Tell support
Tell the support channel if orders are failing.
