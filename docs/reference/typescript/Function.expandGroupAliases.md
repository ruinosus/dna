# Function: expandGroupAliases()

```ts
function expandGroupAliases(groups?): Set<string>;
```

Expand the 'read' umbrella into its constituent groups. Other group
names pass through unchanged. 1:1 with the Py `expand_group_aliases`.

## Parameters

| Parameter | Type |
| ------ | ------ |
| `groups?` | `Iterable`\<`string`, `any`, `any`\> \| `null` |

## Returns

`Set`\<`string`\>
