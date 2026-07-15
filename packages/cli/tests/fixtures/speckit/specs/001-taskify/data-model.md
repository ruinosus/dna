# Data model — Taskify

## Board

- id: uuid
- team_id: uuid
- columns: Column[]

## Card

- id: uuid
- title: string
- column: enum(todo, doing, review, done)
