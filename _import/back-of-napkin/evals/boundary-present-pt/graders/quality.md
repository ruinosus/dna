---
type: llm
focus: { source: file, path: drawing.chalk }
---
The recipe draws the On-Behalf-Of flow correctly for a client: the user signs in to the app, the app calls our API with the user's token, the API exchanges it at the identity provider for a token to a downstream API on the user's behalf, and calls it. It ends with a highlight. Short texts in Portuguese. Fail it if the flow is wrong (for example the API using its own identity instead of the user's).
