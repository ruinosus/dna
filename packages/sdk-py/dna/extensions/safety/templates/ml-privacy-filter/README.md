# ML Privacy Filter — Category Reference

All 8 categories supported by `openai/privacy-filter`. The strings below
match the model's `entity_group` output verbatim (T1 spec lock — confirmed
empirically against the live model).

| Key                | Description                                          |
|--------------------|------------------------------------------------------|
| `account_number`   | Bank/payment account numbers, credit card numbers    |
| `private_address`  | Street addresses, postal codes                       |
| `private_email`    | Email addresses                                      |
| `private_person`   | Personal names (first, last, full)                   |
| `private_phone`    | Phone numbers (all formats)                          |
| `private_url`      | URLs containing PII (e.g. `/api/users/alice`)        |
| `private_date`     | Dates of birth, appointment dates                    |
| `secret`           | Passwords, API tokens, private keys                  |

Use the keys verbatim in `spec.categories`. Setting `spec.categories: null`
(or omitting it) flags **all 8** categories.
